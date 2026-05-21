"""
League Cog — League management, schedules, multi-server support.
"""
import uuid

import discord
from discord import app_commands
from discord.ext import commands

from src.data.sheets import Tab, sheets
from src.services.elo_service import EloService
from src.services.notification_service import NotificationService


class LeagueCog(commands.Cog, name="League"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.elo = EloService()
        self.notifications = NotificationService(bot)

    @app_commands.command(name="league-create", description="Create a new draft league for this server")
    @app_commands.describe(name="League name", format="Draft format", season="Season number")
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
        sheets.save_league_setup(league_data)
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
    @app_commands.describe(week="Filter to a specific week (leave blank for all)", pool="Filter by pool (A or B)")
    async def schedule(
        self,
        interaction: discord.Interaction,
        week: int | None = None,
        pool: str | None = None,
    ) -> None:
        await interaction.response.defer()
        rows = sheets.read_all(Tab.SCHEDULE)
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
    @app_commands.describe(opponent="Your opponent", won="Did you win?")
    async def result(
        self,
        interaction: discord.Interaction,
        opponent: discord.Member,
        won: bool,
    ) -> None:
        await interaction.response.defer()
        loser = opponent if won else interaction.user
        winner = interaction.user if won else opponent

        match_result = await self.elo.record_match(
            guild_id=str(interaction.guild_id),
            winner_id=str(winner.id),
            loser_id=str(loser.id),
            winner_name=winner.display_name,
            loser_name=loser.display_name,
        )

        # Persist match to Sheets
        sheets.save_match_stats({
            "match_id": str(uuid.uuid4())[:8],
            "league_id": str(interaction.guild_id),
            "winner_id": str(winner.id),
            "loser_id": str(loser.id),
            "p1_team": [],
            "p2_team": [],
        })

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
            str(winner.id), won=True,
            old_elo=match_result.winner_old_elo, new_elo=match_result.winner_new_elo,
            opponent_name=loser.display_name,
        )
        await self.notifications.notify_elo_update(
            str(loser.id), won=False,
            old_elo=match_result.loser_old_elo, new_elo=match_result.loser_new_elo,
            opponent_name=winner.display_name,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LeagueCog(bot))
