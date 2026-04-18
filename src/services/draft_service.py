"""
Draft Service — Core draft engine.
Handles Snake, Auction, Tiered, and Adaptive Ban draft formats.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from src.data.db import delete_draft as _db_delete_draft
from src.data.db import load_all_drafts, save_draft as _db_save_draft
from src.data.models import Draft, DraftBan, DraftFormat, DraftPick, DraftStatus, Pokemon
from src.data.pokeapi import pokemon_db
from src.data.sheets import sheets

log = logging.getLogger(__name__)

AUCTION_STARTING_BUDGET = 1000  # Points each player starts with in auction drafts

# In-memory draft cache (one active draft per guild)
_active_drafts: dict[str, Draft] = {}

# Per-guild timer tasks (auto-skip when timer expires)
_timer_tasks: dict[str, asyncio.Task] = {}


async def _persist_draft(draft: Draft) -> None:
    """Write draft state to SQLite.  Errors are logged but not re-raised."""
    try:
        await _db_save_draft(draft.guild_id, draft.model_dump_json())
    except Exception as exc:
        log.error("Failed to persist draft %s to SQLite: %s", draft.guild_id, exc)


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
class EloMatchResult:
    winner_old_elo: int
    winner_new_elo: int
    loser_old_elo: int
    loser_new_elo: int


class DraftService:
    """Manages all draft operations for all formats."""

    # ── Startup restore ────────────────────────────────────────
    async def restore_active_drafts(self) -> None:
        """Reload any in-progress drafts from SQLite into the in-memory cache."""
        rows = await load_all_drafts()
        restored = 0
        for guild_id, draft_json in rows:
            try:
                draft = Draft.model_validate_json(draft_json)
                _active_drafts[guild_id] = draft
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
        # Persist league setup to Google Sheets
        sheets.save_league_setup({
            "league_id": draft.draft_id,
            "server_id": guild_id,
            "commissioner_id": commissioner_id,
            "format": format.value,
            "total_rounds": rounds,
            "timer_seconds": timer_seconds,
            "status": "setup",
            "created_at": draft.created_at,
        })
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
            return AddPlayerResult(success=False, error=f"Draft is full ({draft.max_players}/16 players max).")
        draft.player_order.append(player_id)
        if team_name:
            draft.team_names[player_id] = team_name
        # Initialize auction budget if auction format
        if draft.format == DraftFormat.AUCTION:
            draft.budget[player_id] = AUCTION_STARTING_BUDGET
        log.info(f"Player {player_id} ({player_name}) joined draft {draft.draft_id} (pool {pool})")
        return AddPlayerResult(success=True, player_count=len(draft.player_order))

    # ── Start ──────────────────────────────────────────────────
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

        # Start ban phase if adaptive banning is enabled
        if draft.format == DraftFormat.CUSTOM:
            draft.status = DraftStatus.BAN_PHASE
        else:
            draft.status = DraftStatus.ACTIVE
            # Start pick timer for the first player
            if draft.timer_seconds > 0:
                self._start_timer(guild_id, draft, on_timeout)

        log.info(f"Draft {draft.draft_id} started with {len(draft.player_order)} players")
        await _persist_draft(draft)
        return draft

    # ── Pick ───────────────────────────────────────────────────
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

        # Cancel existing timer — player picked in time
        self._cancel_timer(guild_id)

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
            return PickResult(success=False, error=f"Pokemon '{pokemon_name}' not found.")

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
        sheets.save_pick(pick.model_dump())

        # Advance pick pointer
        self._advance_pick(draft)

        # Start timer for next player (if draft still active)
        if draft.status == DraftStatus.ACTIVE and draft.timer_seconds > 0:
            self._start_timer(guild_id, draft, on_timeout)

        await _persist_draft(draft)
        next_id = draft.current_player_id
        return PickResult(
            success=True,
            pokemon=pokemon,
            next_player_name=f"<@{next_id}>" if next_id else "Draft complete!",
            round=draft.current_round,
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

    # ── Timer ──────────────────────────────────────────────────
    def _start_timer(
        self,
        guild_id: str,
        draft: Draft,
        on_timeout: Callable[[str, str], Awaitable[None]] | None,
    ) -> None:
        """Start a countdown task for the current player's pick."""
        self._cancel_timer(guild_id)

        current_player = draft.current_player_id
        if not current_player:
            return

        sleep_secs = draft.timer_seconds  # capture at task-creation time

        async def _timer_task():
            await asyncio.sleep(sleep_secs)
            # Only auto-skip if still the same player's turn
            active = _active_drafts.get(guild_id)
            if active and active.status == DraftStatus.ACTIVE and active.current_player_id == current_player:
                log.info(f"Pick timer expired for {current_player} in guild {guild_id} — auto-skipping")
                self._advance_pick(active)
                if on_timeout:
                    try:
                        await on_timeout(guild_id, current_player)
                    except Exception as e:
                        log.error(f"on_timeout callback error: {e}", exc_info=True)
                # Start timer for the next player
                if active.status == DraftStatus.ACTIVE and active.timer_seconds > 0:
                    self._start_timer(guild_id, active, on_timeout)

        _timer_tasks[guild_id] = asyncio.get_running_loop().create_task(_timer_task())

    def _cancel_timer(self, guild_id: str) -> None:
        """Cancel the current pick timer for a guild, if any."""
        task = _timer_tasks.pop(guild_id, None)
        if task and not task.done():
            task.cancel()

    # ── Ban ────────────────────────────────────────────────────
    async def ban_pokemon(self, guild_id: str, player_id: str, pokemon_name: str) -> BanResult:
        draft = _active_drafts.get(guild_id)
        if not draft:
            return BanResult(success=False, error="No active draft.")
        if draft.status != DraftStatus.BAN_PHASE:
            return BanResult(success=False, error="Not in ban phase.")

        pokemon = pokemon_db.find(pokemon_name)
        if not pokemon:
            return BanResult(success=False, error=f"Pokemon '{pokemon_name}' not found.")

        ban = DraftBan(
            draft_id=draft.draft_id,
            player_id=player_id,
            pokemon_name=pokemon.name,
        )
        draft.bans.append(ban)
        return BanResult(success=True, pokemon=pokemon)

    # ── Bid ────────────────────────────────────────────────────
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
            return BidResult(success=False, error="Bid must be at least 1 coin.")
        if amount > budget:
            return BidResult(success=False, error=f"Insufficient budget. You have {budget} coins.")

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

    # ── Admin ops ──────────────────────────────────────────────
    async def force_skip(self, guild_id: str, player_id: str) -> object:
        self._cancel_timer(guild_id)
        draft = _active_drafts.get(guild_id)
        if draft:
            self._advance_pick(draft)
        return type("r", (), {"next_player": f"<@{draft.current_player_id}>"})()

    async def pause_draft(self, guild_id: str) -> None:
        self._cancel_timer(guild_id)
        if draft := _active_drafts.get(guild_id):
            draft.status = DraftStatus.PAUSED

    async def resume_draft(self, guild_id: str) -> None:
        if draft := _active_drafts.get(guild_id):
            draft.status = DraftStatus.ACTIVE

    async def reset_draft(self, guild_id: str) -> None:
        self._cancel_timer(guild_id)
        _active_drafts.pop(guild_id, None)
        log.warning(f"Draft reset for guild {guild_id}")

    async def override_pick(self, guild_id: str, player_id: str, old_pokemon: str, new_pokemon: str) -> None:
        draft = _active_drafts.get(guild_id)
        if draft:
            for pick in draft.picks:
                if pick.player_id == player_id and pick.pokemon_name.lower() == old_pokemon.lower():
                    pick.pokemon_name = new_pokemon
                    break

    async def get_active_draft(self, guild_id: str) -> Draft | None:
        return _active_drafts.get(guild_id)

    # Re-export enums for convenience
    DraftFormat = DraftFormat
    DraftStatus = DraftStatus
