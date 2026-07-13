"""Discord cog: team browsing, search, meta, and similarity commands."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.api_client import PipelineAPIClient, PipelineAPIError
from bot.config import COLOR_ERROR, COLOR_INFO


class TeamCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api = PipelineAPIClient()

    async def _safe(self, ctx: commands.Context, coro):
        try:
            return await coro
        except PipelineAPIError:
            await ctx.reply(embed=discord.Embed(description="Pipeline API is unavailable. Try again later.", color=COLOR_ERROR))
            return None

    @commands.group(name="team", invoke_without_command=True)
    async def team(self, ctx: commands.Context, team_id: int) -> None:
        team = await self._safe(ctx, self.api.get_team(team_id))
        if team is None:
            return
        embed = discord.Embed(title=f"Team #{team_id}", color=COLOR_INFO)
        embed.add_field(name="Regulation", value=team.get("regulation") or "—")
        embed.add_field(name="Format", value=team.get("format_type") or "—")
        embed.add_field(name="Tags", value=", ".join(team.get("archetype_tags", [])) or "none", inline=False)
        for mon in (team.get("parsed_json") or [])[:6]:
            moves = ", ".join(m for m in [mon.get("move1"), mon.get("move2"), mon.get("move3"), mon.get("move4")] if m)
            embed.add_field(
                name=f"{mon.get('species')} @ {mon.get('item') or '—'}",
                value=f"Tera: {mon.get('tera_type') or '—'}\n{moves}",
                inline=True,
            )
        await ctx.reply(embed=embed)

    @team.command(name="search")
    async def team_search(self, ctx: commands.Context, *species: str) -> None:
        result = await self._safe(ctx, self.api.search_teams({"q": "+".join(species)}))
        if result is None:
            return
        items = result.get("items", [])[:5]
        if not items:
            await ctx.reply("No teams found.")
            return
        for team in items:
            species_list = ", ".join(m.get("species", "?") for m in (team.get("parsed_json") or [])[:6])
            embed = discord.Embed(title=f"Team #{team['id']}", description=species_list, color=COLOR_INFO)
            embed.add_field(name="Regulation", value=team.get("regulation") or "—")
            embed.add_field(name="Format", value=team.get("format_type") or "—")
            await ctx.send(embed=embed)

    @team.command(name="paste")
    async def team_paste(self, ctx: commands.Context, team_id: int) -> None:
        paste = await self._safe(ctx, self.api.get_team_paste(team_id))
        if paste is None:
            return
        await ctx.reply(f"```\n{paste[:1900]}\n```")

    @commands.command(name="tournament")
    async def tournament(self, ctx: commands.Context, tournament_id: int) -> None:
        result = await self._safe(ctx, self.api.get_tournament_teams(tournament_id))
        if result is None:
            return
        embed = discord.Embed(title=f"Tournament #{tournament_id} — Top 8", color=COLOR_INFO)
        for item in result.get("items", [])[:8]:
            embed.add_field(
                name=f"#{item.get('final_placing') or '?'} {item['player_name']}",
                value=f"Team #{item['team_id']}",
                inline=False,
            )
        await ctx.reply(embed=embed)

    @commands.command(name="meta")
    async def meta(self, ctx: commands.Context, regulation: str) -> None:
        result = await self._safe(ctx, self.api.search_teams({"regulation": regulation, "per_page": 100}))
        if result is None:
            return
        counts: dict[str, int] = {}
        for team in result.get("items", []):
            for mon in team.get("parsed_json") or []:
                species = mon.get("species")
                if species:
                    counts[species] = counts.get(species, 0) + 1
        top10 = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
        embed = discord.Embed(title=f"Meta: {regulation}", color=COLOR_INFO)
        for species, count in top10:
            embed.add_field(name=species, value=str(count))
        await ctx.reply(embed=embed)

    @commands.command(name="similar")
    async def similar(self, ctx: commands.Context, team_id: int) -> None:
        result = await self._safe(ctx, self.api.get_similar_teams(team_id, k=5))
        if result is None:
            return
        embed = discord.Embed(title=f"Teams similar to #{team_id}", color=COLOR_INFO)
        for entry in result.get("similar", []):
            embed.add_field(name=f"Team #{entry.get('team_id')}", value=f"distance: {entry.get('distance', '?')}", inline=False)
        if not result.get("similar"):
            embed.description = "No similar teams found (embeddings may not be computed yet)."
        await ctx.reply(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TeamCog(bot))
