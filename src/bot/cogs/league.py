"""
League Cog — League management, schedules, multi-server support.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

import discord
from discord import app_commands
from discord.ext import commands

from src.bot.permissions import (
    ROLE_COACH,
    ROLE_GUILDMASTER,
    member_has_role,
    require_role,
)
from src.data.sheets import Tab, sheets
from src.services.elo_service import EloService
from src.services.notification_service import NotificationService

log = logging.getLogger(__name__)

RESULT_CONFIRM_TIMEOUT_SECONDS = 300


class ResultConfirmView(discord.ui.View):
    """Only the named opponent can confirm; the result is applied at most once."""

    def __init__(
        self,
        *,
        opponent: discord.Member,
        on_confirm: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=RESULT_CONFIRM_TIMEOUT_SECONDS)
        self._opponent = opponent
        self._on_confirm = on_confirm
        self._settled = False
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self._opponent.id:
            return True
        await interaction.response.send_message(
            f"Only {self._opponent.display_name} can answer this.", ephemeral=True
        )
        return False

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self._settled:
            return
        self._settled = True
        self.stop()
        if interaction.message is not None:
            await interaction.message.edit(view=None)
        await self._on_confirm(interaction)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self._settled:
            return
        self._settled = True
        self.stop()
        await interaction.response.edit_message(
            content="Result declined. Nothing was recorded.", view=None
        )

    async def on_timeout(self) -> None:
        if self._settled or self.message is None:
            return
        try:
            await self.message.edit(
                content="Result expired. Nothing was recorded.", view=None
            )
        except discord.HTTPException:
            pass


class LeagueCog(commands.Cog, name="League"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.elo = EloService()
        self.notifications = NotificationService(bot)

    @app_commands.command(
        name="league-create", description="Create a new draft league for this server"
    )
    @require_role(ROLE_GUILDMASTER)
    @app_commands.describe(
        name="League name", format="Draft format", season="Season number"
    )
    async def league_create(
        self,
        interaction: discord.Interaction,
        name: str,
        format: str = "snake",
        season: int = 1,
    ) -> None:
        await interaction.response.defer()
        league_data = {
            "league_id": str(uuid.uuid4())[:8],
            "server_id": str(interaction.guild_id),
            "league_name": name,
            "season": season,
            "format": format,
            "status": "setup",
            "commissioner_id": str(interaction.user.id),
            "commissioner_name": interaction.user.display_name,
        }
        await asyncio.to_thread(sheets.save_league_setup, league_data)
        embed = discord.Embed(
            title=f"League '{name}' Created!",
            description=(
                f"**Format:** {format.title()} | **Season:** {season}\n"
                f"**Commissioner:** {interaction.user.mention}\n"
                f"League settings saved to Setup tab. Use `/draft-setup` to configure the draft."
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"League ID: {league_data['league_id']}")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="schedule", description="View the match schedule")
    @require_role(ROLE_COACH)
    @app_commands.describe(
        week="Filter to a specific week (leave blank for all)",
        pool="Filter by pool (A or B)",
    )
    async def schedule(
        self,
        interaction: discord.Interaction,
        week: int | None = None,
        pool: str | None = None,
    ) -> None:
        await interaction.response.defer()
        rows = await asyncio.to_thread(sheets.read_all, Tab.SCHEDULE)
        if week is not None:
            rows = [r for r in rows if str(r.get("week", "")) == str(week)]
        if pool:
            rows = [r for r in rows if str(r.get("pool", "")).upper() == pool.upper()]
        if not rows:
            await interaction.followup.send("No matches scheduled yet.", ephemeral=True)
            return
        lines = []
        for r in rows[:20]:  # Discord embed limit
            result = r.get("winner_name", "")
            status = f"✅ {result}" if result else "⏳ Pending"
            lines.append(
                f"**Wk {r.get('week', '?')}** [{r.get('pool', 'A')}] "
                f"{r.get('player1_name', '?')} vs {r.get('player2_name', '?')} — {status}"
            )
        embed = discord.Embed(
            title="Match Schedule",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Use /sheet-schedule to add matches")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="result", description="Report a match result")
    @require_role(ROLE_COACH)
    @app_commands.describe(opponent="Your opponent", won="Did you win?")
    async def result(
        self,
        interaction: discord.Interaction,
        opponent: discord.Member,
        won: bool,
    ) -> None:
        if opponent.id == interaction.user.id or opponent.bot:
            await interaction.response.send_message(
                "Pick another league coach as your opponent.", ephemeral=True
            )
            return
        if not member_has_role(opponent, ROLE_COACH):
            await interaction.response.send_message(
                f"{opponent.mention} is not a league coach.", ephemeral=True
            )
            return

        loser = opponent if won else interaction.user
        winner = interaction.user if won else opponent
        view = ResultConfirmView(
            opponent=opponent,
            on_confirm=lambda i: self._record_result(i, winner, loser),
        )
        await interaction.response.send_message(
            f"{opponent.mention}, {interaction.user.mention} reports **{winner.display_name}** "
            f"beat **{loser.display_name}**. Confirm within 5 minutes to record it.",
            view=view,
            allowed_mentions=discord.AllowedMentions(users=[opponent]),
        )
        view.message = await interaction.original_response()

    async def _record_result(
        self,
        interaction: discord.Interaction,
        winner: discord.Member,
        loser: discord.Member,
    ) -> None:
        """Apply a confirmed result. `interaction` is the opponent's button click."""
        await interaction.response.defer()
        match_result = await self.elo.record_match(
            guild_id=str(interaction.guild_id),
            winner_id=str(winner.id),
            loser_id=str(loser.id),
            winner_name=winner.display_name,
            loser_name=loser.display_name,
        )

        # Persist match to Sheets — best-effort: a write failure must not suppress
        # the embed or leave ELO mutated with no user feedback.
        try:
            await asyncio.to_thread(
                sheets.save_match_stats,
                {
                    "match_id": str(uuid.uuid4())[:8],
                    "league_id": str(interaction.guild_id),
                    "winner_id": str(winner.id),
                    "loser_id": str(loser.id),
                    "p1_team": [],
                    "p2_team": [],
                },
            )
        except Exception:
            log.exception("[result] Non-fatal: failed to persist match stats to Sheets")

        embed = discord.Embed(
            title="Match Result Recorded!",
            description=f"**Winner:** {winner.mention}\n**Loser:** {loser.mention}",
            color=discord.Color.green(),
        )
        embed.add_field(
            name=f"{winner.display_name} ELO",
            value=f"{match_result.winner_old_elo} → **{match_result.winner_new_elo}** (+{match_result.winner_new_elo - match_result.winner_old_elo})",
        )
        embed.add_field(
            name=f"{loser.display_name} ELO",
            value=f"{match_result.loser_old_elo} → **{match_result.loser_new_elo}** ({match_result.loser_new_elo - match_result.loser_old_elo})",
        )
        await interaction.followup.send(embed=embed)

        # DM both players about ELO change
        await self.notifications.notify_elo_update(
            str(winner.id),
            won=True,
            old_elo=match_result.winner_old_elo,
            new_elo=match_result.winner_new_elo,
            opponent_name=loser.display_name,
        )
        await self.notifications.notify_elo_update(
            str(loser.id),
            won=False,
            old_elo=match_result.loser_old_elo,
            new_elo=match_result.loser_new_elo,
            opponent_name=winner.display_name,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LeagueCog(bot))
