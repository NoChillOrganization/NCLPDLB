"""
Draft Service — Core draft engine.
Handles Snake, Auction, Tiered, and Custom (snake picks after a "Ban phase") draft formats.
`linear` exists in DraftFormat but is not offered by /draft-create or the wizard.
Auction nominations: no command creates one; `current_nomination_id` is only cleared here
(close_nomination), so setting it is the nomination view's job (known gap: none exists yet).

Lifecycle invariants live here, not in the cogs: every transition of a started draft runs
under the guild's lock, ends by persisting to SQLite (a COMPLETED draft is removed), and
leaves the pick timer matching the pick pointer. The auto-skip callback is remembered per
guild, so callers do not have to pass it on every call.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from src.data.db import delete_draft as _db_delete_draft
from src.data.db import load_all_drafts, save_draft as _db_save_draft
from src.data.models import (
    Draft,
    DraftBan,
    DraftFormat,
    DraftPick,
    DraftStatus,
    Pokemon,
)
from src.data.pokeapi import pokemon_db
from src.data.sheets import league_sheet

log = logging.getLogger(__name__)

AUCTION_STARTING_BUDGET = 1000  # Points each player starts with in auction drafts

# In-memory draft cache (one active draft per guild)
_active_drafts: dict[str, Draft] = {}

# Per-guild locks — serialise every state transition so TOCTOU is impossible (M9)
_pick_locks: dict[str, asyncio.Lock] = {}

# Per-guild timer tasks (auto-skip when timer expires)
_timer_tasks: dict[str, asyncio.Task] = {}
# Per-guild auto-skip callback, remembered for the whole draft so every timer
# (after /pick, force-skip, resume) still announces the skip.
_timeout_callbacks: dict[str, Callable[[str, str], Awaitable[None]]] = {}
# Strong references to fire-and-forget League sheet writes so GC cannot cancel them
_background_tasks: set[asyncio.Task] = set()


def _guild_lock(guild_id: str) -> asyncio.Lock:
    return _pick_locks.setdefault(guild_id, asyncio.Lock())


def _locked(method):
    """Run a draft state transition, and its persist, under the guild's lock."""

    @functools.wraps(method)
    async def wrapper(self, guild_id: str, *args, **kwargs):
        async with _guild_lock(guild_id):
            return await method(self, guild_id, *args, **kwargs)

    return wrapper


def _sheet_write(write: Callable[[dict], Awaitable[None]], row: dict) -> None:
    """Fire-and-forget League sheet write: never delays the caller; failures are logged."""
    task = asyncio.get_running_loop().create_task(write(row))
    _background_tasks.add(task)
    task.add_done_callback(_sheet_write_done)


def _sheet_write_done(task: asyncio.Task) -> None:
    _background_tasks.discard(task)
    if not task.cancelled() and task.exception():
        log.error("League sheet write failed: %s", task.exception())


async def _persist_draft(draft: Draft) -> bool:
    """Write draft state to SQLite.  Errors are logged but not re-raised.

    A COMPLETED draft is removed instead: there is nothing left to restore.

    Returns False on failure so callers can warn users that a restart would
    lose this draft (see PickResult.persistence_ok).
    """
    if draft.status == DraftStatus.COMPLETED:
        await _delete_persisted_draft(draft.guild_id)
        return True
    try:
        await _db_save_draft(draft.guild_id, draft.model_dump_json())
        return True
    except Exception as exc:
        log.error("Failed to persist draft %s to SQLite: %s", draft.guild_id, exc)
        return False


async def _delete_persisted_draft(guild_id: str) -> None:
    """Remove draft from SQLite.  Errors are logged but not re-raised."""
    try:
        await _db_delete_draft(guild_id)
    except Exception as exc:
        log.error("Failed to delete draft %s from SQLite: %s", guild_id, exc)


@dataclass
class PickResult:
    success: bool
    pokemon: Pokemon | None = None
    next_player_name: str = ""
    round: int = 1
    error: str = ""
    # False when the post-pick SQLite write failed — the draft is currently
    # unprotected against a bot restart. Callers should warn the user.
    persistence_ok: bool = True


@dataclass
class DraftCreateResult:
    draft_id: str
    player_count: int = 0


@dataclass
class AddPlayerResult:
    success: bool
    player_count: int = 0
    error: str = ""


@dataclass
class BidResult:
    success: bool
    current_high: int = 0
    error: str = ""


@dataclass
class BanResult:
    success: bool
    pokemon: Pokemon | None = None
    error: str = ""


@dataclass
class ForceSkipResult:
    success: bool
    next_player: str = ""
    error: str = ""


@dataclass
class EloMatchResult:
    winner_old_elo: int
    winner_new_elo: int
    loser_old_elo: int
    loser_new_elo: int


class DraftService:
    """Manages all draft operations for all formats."""

    # ── Startup restore ────────────────────────────────────────
    async def restore_active_drafts(
        self,
        on_timeout: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        """Reload any in-progress drafts from SQLite and restart pick timers."""
        rows = await load_all_drafts()
        restored = 0
        for guild_id, draft_json in rows:
            try:
                draft = Draft.model_validate_json(draft_json)
                _active_drafts[guild_id] = draft
                # M3: restart pick timer so auto-skip still fires after a restart
                self._start_timer(guild_id, draft, on_timeout)
                restored += 1
            except Exception as exc:
                log.error("Could not restore draft for guild %s: %s", guild_id, exc)
        if restored:
            log.info("Restored %d in-progress draft(s) from SQLite", restored)

    # ── Create ─────────────────────────────────────────────────
    async def create_draft(
        self,
        guild_id: str,
        commissioner_id: str,
        format: DraftFormat = DraftFormat.SNAKE,
        rounds: int = 6,
        timer_seconds: int = 60,
        tier_mode: bool = False,
        game_format: str = "showdown",
        tera_captains_per_team: int = 0,
        tera_types_per_captain: int = 1,
    ) -> Draft:
        draft = Draft(
            draft_id=str(uuid.uuid4())[:8],
            guild_id=guild_id,
            league_id=guild_id,
            commissioner_id=commissioner_id,
            format=format,
            total_rounds=rounds,
            timer_seconds=timer_seconds,
            tier_mode=tier_mode,
            game_format=game_format,
            tera_captains_per_team=tera_captains_per_team,
            tera_types_per_captain=tera_types_per_captain,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        _active_drafts[guild_id] = draft
        _timeout_callbacks.pop(guild_id, None)  # the previous draft's callback is stale
        # Persist league setup to Google Sheets (fire-and-forget — don't block draft creation)
        _sheet_write(
            league_sheet.save_league_setup,
            {
                "league_id": guild_id,  # one League per server: league id == guild id
                "server_id": guild_id,
                "commissioner_id": commissioner_id,
                "format": format.value,
                "total_rounds": rounds,
                "timer_seconds": timer_seconds,
                "status": "setup",
                "created_at": draft.created_at,
            },
        )
        log.info(f"Draft {draft.draft_id} created for guild {guild_id}")
        return draft

    async def create_draft_from_config(self, config: dict) -> "Draft":
        """Create a draft from a wizard config dict (used by the setup wizard)."""
        return await self.create_draft(
            guild_id=config.get("guild_id", ""),
            commissioner_id=config.get("commissioner_id", ""),
            format=DraftFormat(config.get("format", "snake")),
            rounds=int(config.get("total_rounds", 6)),
            timer_seconds=int(config.get("timer_seconds", 60)),
            game_format=config.get("game_format", "showdown"),
            tera_captains_per_team=int(config.get("tera_captains_per_team", 0)),
            tera_types_per_captain=int(config.get("tera_types_per_captain", 1)),
        )

    def get_draft(self, guild_id: str) -> "Draft | None":
        """Return the current in-memory Draft for a guild, or None."""
        return _active_drafts.get(guild_id)

    # ── Join ───────────────────────────────────────────────────
    async def add_player(
        self,
        guild_id: str,
        player_id: str,
        player_name: str = "",
        team_name: str = "",
        pool: str = "A",
        draft_id: str | None = None,
    ) -> AddPlayerResult:
        draft = _active_drafts.get(guild_id)
        if not draft:
            return AddPlayerResult(success=False, error="No active draft found.")
        if draft.status != DraftStatus.SETUP:
            return AddPlayerResult(success=False, error="Draft has already started.")
        if player_id in draft.player_order:
            return AddPlayerResult(success=False, error="You've already joined.")
        if len(draft.player_order) >= draft.max_players:
            return AddPlayerResult(
                success=False,
                error=f"Draft is full ({draft.max_players}/16 players max).",
            )
        draft.player_order.append(player_id)
        if team_name:
            draft.team_names[player_id] = team_name
        # Initialize auction budget if auction format
        if draft.format == DraftFormat.AUCTION:
            draft.budget[player_id] = AUCTION_STARTING_BUDGET
        log.info(
            f"Player {player_id} ({player_name}) joined draft {draft.draft_id} (pool {pool})"
        )
        return AddPlayerResult(success=True, player_count=len(draft.player_order))

    # ── Start ──────────────────────────────────────────────────
    @_locked
    async def start_draft(
        self,
        guild_id: str,
        commissioner_id: str,
        on_timeout: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> Draft:
        """
        Start the draft.

        Args:
            guild_id: The Discord server ID.
            commissioner_id: Must match draft.commissioner_id.
            on_timeout: Optional async callback(guild_id, skipped_player_id) called
                        when the pick timer fires. Use this to post a channel message.
        """
        draft = _active_drafts.get(guild_id)
        if not draft:
            raise ValueError("No draft found to start.")
        if draft.commissioner_id != commissioner_id:
            raise PermissionError("Only the commissioner can start the draft.")
        if len(draft.player_order) < 2:
            raise ValueError("Need at least 2 players to start.")

        # Custom format starts with the Ban phase
        if draft.format == DraftFormat.CUSTOM:
            draft.status = DraftStatus.BAN_PHASE
        else:
            draft.status = DraftStatus.ACTIVE
        # Start pick timer for the first player. None runs during the Ban phase,
        # but the callback is remembered for when resume_draft ends it.
        self._start_timer(guild_id, draft, on_timeout)

        log.info(
            f"Draft {draft.draft_id} started with {len(draft.player_order)} players"
        )
        await _persist_draft(draft)
        return draft

    # ── Pick ───────────────────────────────────────────────────
    @_locked
    async def make_pick(
        self,
        guild_id: str,
        player_id: str,
        pokemon_name: str,
        tera_type: str = "",
        is_tera_captain: bool = False,
        on_timeout: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> PickResult:
        draft = _active_drafts.get(guild_id)
        if not draft:
            return PickResult(success=False, error="No active draft.")
        if draft.status != DraftStatus.ACTIVE:
            return PickResult(success=False, error="Draft is not currently active.")
        if draft.current_player_id != player_id:
            return PickResult(success=False, error="It's not your turn.")

        # Check if already picked
        already_picked = [p.pokemon_name.lower() for p in draft.picks]
        if pokemon_name.lower() in already_picked:
            return PickResult(success=False, error=f"{pokemon_name} is already taken.")

        # Check if banned
        banned = [b.pokemon_name.lower() for b in draft.bans]
        if pokemon_name.lower() in banned:
            return PickResult(success=False, error=f"{pokemon_name} has been banned.")

        # Validate Pokemon exists
        pokemon = pokemon_db.find(pokemon_name)
        if not pokemon:
            return PickResult(
                success=False, error=f"Pokemon '{pokemon_name}' not found."
            )

        pick = DraftPick(
            draft_id=draft.draft_id,
            player_id=player_id,
            pokemon_name=pokemon.name,
            round=draft.current_round,
            pick_number=len(draft.picks) + 1,
            tera_type=tera_type,
            is_tera_captain=is_tera_captain,
        )
        draft.picks.append(pick)
        _sheet_write(league_sheet.save_pick, pick.model_dump(mode="json"))

        # Player picked in time: the timer is replaced only now, after validation,
        # so a rejected pick above leaves the player's auto-skip running.
        persisted = await self._next_turn(guild_id, draft, on_timeout)
        next_id = draft.current_player_id
        return PickResult(
            success=True,
            pokemon=pokemon,
            next_player_name=f"<@{next_id}>" if next_id else "Draft complete!",
            round=draft.current_round,
            persistence_ok=persisted,
        )

    def _advance_pick(self, draft: Draft) -> None:
        """Advance to next pick, handling round transitions and snake reversals."""
        draft.current_pick_index += 1
        if draft.current_pick_index >= len(draft.player_order):
            draft.current_pick_index = 0
            draft.current_round += 1
            if draft.current_round > draft.total_rounds:
                draft.status = DraftStatus.COMPLETED
                log.info(f"Draft {draft.draft_id} completed!")
                # SQLite cleanup happens in _persist_draft, which every caller awaits next

    async def _next_turn(
        self,
        guild_id: str,
        draft: Draft,
        on_timeout: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> bool:
        """End the current turn: advance, restart the pick timer, persist.

        The one place a turn ends (pick, auto-skip, force-skip), so the timer and
        SQLite always agree with the pick pointer. Returns False if the SQLite
        write failed.
        """
        self._advance_pick(draft)
        self._start_timer(guild_id, draft, on_timeout)
        return await _persist_draft(draft)

    # ── Timer ──────────────────────────────────────────────────
    def _start_timer(
        self,
        guild_id: str,
        draft: Draft,
        on_timeout: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        """(Re)start the countdown for the current player's pick.

        Safe to call after any transition: no timer runs unless the draft is
        ACTIVE with timer_seconds > 0. A callback passed here replaces the one
        remembered for the guild.
        """
        self._cancel_timer(guild_id)
        if on_timeout is not None:
            _timeout_callbacks[guild_id] = on_timeout

        current_player = draft.current_player_id
        if (
            draft.status != DraftStatus.ACTIVE
            or draft.timer_seconds <= 0
            or not current_player
        ):
            return

        sleep_secs = draft.timer_seconds  # capture at task-creation time

        async def _timer_task():
            await asyncio.sleep(sleep_secs)
            async with _guild_lock(guild_id):
                if _timer_tasks.get(guild_id) is not asyncio.current_task():
                    return  # superseded while waiting for the lock
                # From here the skip runs to completion: deregister first, so the
                # next player's pick (which cancels "the timer") cannot cancel it
                # halfway through the persist or the announcement.
                del _timer_tasks[guild_id]
                # Only auto-skip if still the same player's turn
                active = _active_drafts.get(guild_id)
                if not (
                    active
                    and active.status == DraftStatus.ACTIVE
                    and active.current_player_id == current_player
                ):
                    return
                log.info(
                    f"Pick timer expired for {current_player} in guild {guild_id} — auto-skipping"
                )
                # M2: persist state after auto-skip so restarts see the correct turn
                # (also starts the timer for the next player)
                await self._next_turn(guild_id, active)
            announce = _timeout_callbacks.get(guild_id)
            if announce:
                try:
                    await announce(guild_id, current_player)
                except Exception as e:
                    log.error(f"on_timeout callback error: {e}", exc_info=True)

        _timer_tasks[guild_id] = asyncio.get_running_loop().create_task(_timer_task())

    def _cancel_timer(self, guild_id: str) -> None:
        """Cancel the current pick timer for a guild, if any."""
        task = _timer_tasks.pop(guild_id, None)
        if task and not task.done():
            task.cancel()

    # ── Ban ────────────────────────────────────────────────────
    @_locked
    async def ban_pokemon(
        self, guild_id: str, player_id: str, pokemon_name: str
    ) -> BanResult:
        draft = _active_drafts.get(guild_id)
        if not draft:
            return BanResult(success=False, error="No active draft.")
        if draft.status != DraftStatus.BAN_PHASE:
            return BanResult(success=False, error="Not in ban phase.")
        # C4: only registered participants may ban
        if player_id not in draft.player_order:
            return BanResult(
                success=False, error="You are not a participant in this draft."
            )

        pokemon = pokemon_db.find(pokemon_name)
        if not pokemon:
            return BanResult(
                success=False, error=f"Pokemon '{pokemon_name}' not found."
            )

        ban = DraftBan(
            draft_id=draft.draft_id,
            player_id=player_id,
            pokemon_name=pokemon.name,
        )
        draft.bans.append(ban)
        await _persist_draft(draft)
        return BanResult(success=True, pokemon=pokemon)

    # ── Bid ────────────────────────────────────────────────────
    @_locked
    async def place_bid(self, guild_id: str, player_id: str, amount: int) -> BidResult:
        draft = _active_drafts.get(guild_id)
        if not draft or draft.format != DraftFormat.AUCTION:
            return BidResult(success=False, error="No active auction draft.")
        if draft.status != DraftStatus.ACTIVE:
            return BidResult(success=False, error="Draft is not currently active.")
        if not draft.current_nomination_id:
            return BidResult(success=False, error="No active nomination to bid on.")

        # Budget check
        budget = draft.budget.get(player_id, 0)
        if amount < 1:
            return BidResult(success=False, error="Bid must be at least 1 point.")
        if amount > budget:
            return BidResult(
                success=False, error=f"Insufficient budget. You have {budget} points."
            )

        # Reject if bid does not exceed current high bid
        current_bids: dict[str, int] = draft.nomination_bids.setdefault(
            draft.current_nomination_id, {}
        )
        current_high_val = max(current_bids.values(), default=0)
        if amount <= current_high_val:
            return BidResult(
                success=False,
                error=f"Your bid of {amount} must exceed the current high bid of {current_high_val}.",
            )

        # Record the bid
        current_bids[player_id] = amount
        log.info(
            f"Bid placed: guild={guild_id} player={player_id} "
            f"amount={amount} nomination={draft.current_nomination_id}"
        )
        return BidResult(success=True, current_high=amount)

    @_locked
    async def close_nomination(self, guild_id: str) -> PickResult:
        """Award the current nomination to the highest bidder and deduct budget."""
        draft = _active_drafts.get(guild_id)
        if not draft or draft.format != DraftFormat.AUCTION:
            return PickResult(success=False, error="No active auction draft.")
        nom_id = draft.current_nomination_id
        if not nom_id:
            return PickResult(success=False, error="No active nomination.")
        bids = draft.nomination_bids.get(nom_id, {})
        if not bids:
            return PickResult(success=False, error="No bids placed.")
        winner_id = max(bids, key=lambda p: bids[p])
        amount = bids[winner_id]
        pokemon = pokemon_db.find(nom_id)
        if not pokemon:
            return PickResult(success=False, error=f"Pokemon '{nom_id}' not found.")
        pick = DraftPick(
            draft_id=draft.draft_id,
            player_id=winner_id,
            pokemon_name=pokemon.name,
            round=draft.current_round,
            pick_number=len(draft.picks) + 1,
        )
        draft.picks.append(pick)
        draft.budget[winner_id] = draft.budget.get(winner_id, 0) - amount
        draft.current_nomination_id = ""
        _sheet_write(league_sheet.save_pick, pick.model_dump(mode="json"))
        self._advance_pick(draft)
        await _persist_draft(draft)
        log.info(
            f"Auction: {winner_id} won {pokemon.name} for {amount} points in guild {guild_id}"
        )
        return PickResult(success=True, pokemon=pokemon, round=draft.current_round)

    # ── Admin ops ──────────────────────────────────────────────
    @_locked
    async def force_skip(self, guild_id: str, player_id: str) -> ForceSkipResult:
        draft = _active_drafts.get(guild_id)
        if not draft:
            return ForceSkipResult(success=False, error="No active draft found.")
        if draft.status != DraftStatus.ACTIVE:
            return ForceSkipResult(
                success=False, error="Draft is not currently active."
            )
        # Skip only the named player: if they picked in the meantime, the next
        # player must not lose their turn.
        if draft.current_player_id != player_id:
            return ForceSkipResult(success=False, error="It's not that player's turn.")
        await self._next_turn(guild_id, draft)
        next_id = draft.current_player_id
        return ForceSkipResult(
            success=True,
            next_player=f"<@{next_id}>" if next_id else "Draft complete!",
        )

    @_locked
    async def pause_draft(self, guild_id: str) -> bool:
        """Pause the draft and stop its pick timer. False if there is no unfinished draft."""
        draft = _active_drafts.get(guild_id)
        if not draft or draft.status == DraftStatus.COMPLETED:
            return False
        draft.status = DraftStatus.PAUSED
        self._cancel_timer(guild_id)
        await _persist_draft(draft)
        return True

    @_locked
    async def resume_draft(self, guild_id: str) -> bool:
        """Make the draft ACTIVE and restart the pick timer for the current player.

        Also how a moderator ends the Ban phase of a custom draft.
        False if there is no unfinished draft.
        """
        draft = _active_drafts.get(guild_id)
        if not draft or draft.status == DraftStatus.COMPLETED:
            return False
        if draft.status != DraftStatus.ACTIVE:
            draft.status = DraftStatus.ACTIVE
            self._start_timer(guild_id, draft)
            await _persist_draft(draft)
        return True

    @_locked
    async def reset_draft(self, guild_id: str) -> None:
        self._cancel_timer(guild_id)
        _timeout_callbacks.pop(guild_id, None)
        _active_drafts.pop(guild_id, None)
        await _delete_persisted_draft(guild_id)
        log.warning(f"Draft reset for guild {guild_id}")

    @_locked
    async def override_pick(
        self, guild_id: str, player_id: str, old_pokemon: str, new_pokemon: str
    ) -> None:
        draft = _active_drafts.get(guild_id)
        if draft:
            for pick in draft.picks:
                if (
                    pick.player_id == player_id
                    and pick.pokemon_name.lower() == old_pokemon.lower()
                ):
                    pick.pokemon_name = new_pokemon
                    # Saved to SQLite only: the League sheet is not updated
                    await _persist_draft(draft)
                    break

    async def get_active_draft(self, guild_id: str) -> Draft | None:
        return _active_drafts.get(guild_id)

    # Re-export enums for convenience
    DraftFormat = DraftFormat
    DraftStatus = DraftStatus
