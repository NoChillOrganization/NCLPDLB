"""
Team View — Discord embed showing a player's full drafted roster with analytics.
"""
from __future__ import annotations

import discord

from src.data.models import TeamRoster


class TeamEmbedView(discord.ui.View):
    def __init__(self, roster: TeamRoster, owner: discord.Member) -> None:
        super().__init__(timeout=120)
        self.roster = roster
        self.owner = owner

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.owner.display_name}'s Team",
            color=discord.Color.blurple(),
        )
        if not self.roster.pokemon:
            embed.description = "No Pokemon drafted yet."
            return embed

        lines = []
        for i, p in enumerate(self.roster.pokemon, 1):
            tier_badge = f"[{p.showdown_tier}]"
            lines.append(f"`{i}.` **{p.name}** {tier_badge} — {p.type_string}")

        embed.description = "\n".join(lines)
        embed.add_field(
            name="Type Coverage",
            value=", ".join(t.title() for t in self.roster.type_coverage) or "None",
            inline=False,
        )
        embed.set_footer(text=f"{len(self.roster.pokemon)} Pokemon | Use /analysis for full breakdown")
        return embed

    @discord.ui.button(label="Full Analysis", style=discord.ButtonStyle.primary, emoji="📊")
    async def analysis(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from src.services.analytics_service import AnalyticsService
        svc = AnalyticsService()
        report = svc.analyze_pokemon_list(self.roster.pokemon)
        embed = discord.Embed(title=f"Team Analysis — {self.owner.display_name}", color=discord.Color.blurple())
        embed.add_field(name="Coverage", value=report.coverage_summary, inline=False)
        embed.add_field(name="Weaknesses", value=report.weakness_summary, inline=False)
        embed.add_field(name="Speed Tiers", value=report.speed_summary, inline=False)
        embed.add_field(name="Archetype", value=report.archetype, inline=True)
        embed.add_field(name="Threat Score", value=str(report.threat_score), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Showdown Export", style=discord.ButtonStyle.secondary, emoji="📋")
    async def export(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from src.services.team_service import TeamService
        svc = TeamService()
        text = await svc.export_showdown(
            guild_id=str(interaction.guild_id),
            player_id=str(self.owner.id),
        )
        await interaction.response.send_message(
            f"**Showdown Export:**\n```\n{text}\n```",
            ephemeral=True,
        )
