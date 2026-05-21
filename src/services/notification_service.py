"""
Notification Service — DM players for draft turns, match reminders, trade offers.

All public methods return True on successful delivery and False on any failure
(Forbidden, NotFound, or network error) so callers never need to catch exceptions.
"""
from __future__ import annotations

import logging

import discord

log = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot

    async def notify_pick_turn(self, player_id: str, pokemon_hint: str = "", time_remaining: int = 60) -> bool:
        """DM a player that it's their turn to pick."""
        return await self._dm(
            player_id,
            f"**It's your turn to pick!**\n"
            f"You have **{time_remaining} seconds**.\n"
            f"Use `/pick <pokemon>` in the draft channel.\n"
            + (f"Suggested: *{pokemon_hint}*" if pokemon_hint else ""),
        )

    async def notify_pick_warning(self, player_id: str, seconds_left: int = 30) -> bool:
        """30-second warning DM."""
        return await self._dm(
            player_id,
            f"⚠️ **{seconds_left} seconds left** to make your pick! Use `/pick <pokemon>` now.",
        )

    async def notify_trade_offer(
        self,
        player_id: str,
        from_name: str,
        offering: str,
        requesting: str,
        trade_id: str,
    ) -> bool:
        return await self._dm(
            player_id,
            f"**Trade offer from {from_name}!**\n"
            f"They offer **{offering}** for your **{requesting}**.\n"
            f"Use `/trade-accept {trade_id}` to accept or `/trade-decline {trade_id}` to decline.",
        )

    async def notify_trade_accepted(self, player_id: str, given: str, received: str) -> bool:
        return await self._dm(
            player_id,
            f"✅ **Trade accepted!**\nYou gave **{given}** and received **{received}**.",
        )

    async def notify_match_reminder(
        self,
        player_id: str,
        opponent_name: str,
        minutes_until: int = 60,
    ) -> bool:
        return await self._dm(
            player_id,
            f"⏰ **Match reminder!**\n"
            f"You play vs **{opponent_name}** in **{minutes_until} minutes**.\n"
            f"Submit your result with `/result` after the battle.",
        )

    async def notify_draft_complete(self, player_id: str, team_summary: str) -> bool:
        return await self._dm(
            player_id,
            f"🎉 **The draft is complete!**\n\nYour team:\n{team_summary}\n\n"
            f"Use `/analysis` to see your team breakdown.",
        )

    async def notify_elo_update(
        self,
        player_id: str,
        won: bool,
        old_elo: int,
        new_elo: int,
        opponent_name: str,
    ) -> bool:
        direction = "📈" if won else "📉"
        result = "won" if won else "lost"
        delta = new_elo - old_elo
        sign = "+" if delta >= 0 else ""
        return await self._dm(
            player_id,
            f"{direction} **Match result vs {opponent_name}**: you **{result}**!\n"
            f"ELO: **{old_elo}** → **{new_elo}** ({sign}{delta})",
        )

    async def _dm(self, player_id: str, message: str) -> bool:
        """Send a DM to a user by ID. Returns True if successful."""
        try:
            user = self.bot.get_user(int(player_id)) or await self.bot.fetch_user(int(player_id))
            await user.send(message)
            return True
        except discord.Forbidden:
            log.debug(f"Cannot DM user {player_id} — DMs disabled.")
            return False
        except discord.NotFound:
            log.warning(f"User {player_id} not found.")
            return False
        except Exception as e:
            log.error(f"DM error for {player_id}: {e}", exc_info=True)
            return False
