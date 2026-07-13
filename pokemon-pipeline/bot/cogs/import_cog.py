"""Discord cog: on-demand imports, backfill control, pipeline status."""

from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

from bot.api_client import PipelineAPIClient, PipelineAPIError
from bot.config import COLOR_ERROR, COLOR_INFO, COLOR_PENDING, COLOR_SUCCESS, IMPORT_ROLE_ID

_POLL_INTERVAL_S = 5
_POLL_TIMEOUT_S = 120


class ImportCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api = PipelineAPIClient()

    def _has_import_role(self, ctx: commands.Context) -> bool:
        if not IMPORT_ROLE_ID:
            return True
        return any(role.id == IMPORT_ROLE_ID for role in getattr(ctx.author, "roles", []))

    @commands.command(name="import")
    async def import_(self, ctx: commands.Context, kind: str, source: str, external_id: str = "") -> None:
        if not self._has_import_role(ctx):
            await ctx.reply(embed=discord.Embed(description="Permission denied.", color=COLOR_ERROR))
            return

        try:
            if kind == "tournament":
                await self._import_tournament(ctx, source, external_id)
            elif kind == "creator":
                await self._import_creator(ctx, source)
            else:
                await ctx.reply(f"Unknown import kind `{kind}`. Use `tournament` or `creator`.")
        except PipelineAPIError:
            await ctx.reply(
                embed=discord.Embed(description="Pipeline API is unavailable. Try again later.", color=COLOR_ERROR)
            )

    async def _import_tournament(self, ctx: commands.Context, source: str, external_id: str) -> None:
        trigger = await self.api.trigger_import(source, external_id)
        task_id = trigger["task_id"]
        message = await ctx.reply(
            embed=discord.Embed(
                title="Import started", description=f"source={source} id={external_id}", color=COLOR_PENDING
            )
        )
        await self._poll_and_edit(message, task_id)

    async def _import_creator(self, ctx: commands.Context, creator_name: str) -> None:
        creators = await self.api.list_creators()
        match = next((c for c in creators.get("items", creators if isinstance(creators, list) else []) if c["name"].lower() == creator_name.lower()), None)
        if match is None:
            await ctx.reply(f"No creator found named `{creator_name}`.")
            return
        result = await self.api.trigger_creator_sync(match["id"])
        await ctx.reply(embed=discord.Embed(title="Creator sync triggered", description=creator_name, color=COLOR_INFO))
        if "task_id" in result:
            message = await ctx.send(embed=discord.Embed(description="Polling status...", color=COLOR_PENDING))
            await self._poll_and_edit(message, result["task_id"])

    async def _poll_and_edit(self, message: discord.Message, task_id: str) -> None:
        elapsed = 0
        while elapsed < _POLL_TIMEOUT_S:
            try:
                status = await self.api.get_task_status(task_id)
            except PipelineAPIError:
                await message.edit(embed=discord.Embed(description="Pipeline API is unavailable.", color=COLOR_ERROR))
                return

            if status["status"] in ("SUCCESS", "FAILURE"):
                color = COLOR_SUCCESS if status["status"] == "SUCCESS" else COLOR_ERROR
                desc = str(status.get("result") or status.get("error") or status["status"])
                await message.edit(embed=discord.Embed(title=f"Task {status['status']}", description=desc, color=color))
                return

            await message.edit(
                embed=discord.Embed(title="In progress...", description=f"status={status['status']}", color=COLOR_PENDING)
            )
            await asyncio.sleep(_POLL_INTERVAL_S)
            elapsed += _POLL_INTERVAL_S

        await message.edit(embed=discord.Embed(description="Timed out waiting for task.", color=COLOR_ERROR))

    @commands.command(name="pipeline")
    async def pipeline(self, ctx: commands.Context, subcommand: str) -> None:
        if subcommand != "status":
            return
        try:
            stats = await self.api.get_pipeline_stats()
        except PipelineAPIError:
            await ctx.reply(embed=discord.Embed(description="Pipeline API is unavailable. Try again later.", color=COLOR_ERROR))
            return

        embed = discord.Embed(title="Pipeline Status", color=COLOR_INFO)
        embed.add_field(name="Total teams", value=str(stats.get("total_teams", "?")))
        for platform, count in stats.get("per_source_tournament_counts", {}).items():
            embed.add_field(name=platform, value=f"{count} tournaments")
        await ctx.reply(embed=embed)

    @commands.command(name="backfill")
    async def backfill(self, ctx: commands.Context, subcommand: str, source: str | None = None) -> None:
        if not self._has_import_role(ctx):
            await ctx.reply(embed=discord.Embed(description="Permission denied.", color=COLOR_ERROR))
            return
        try:
            if subcommand == "start":
                result = await self.api.backfill_start(source)
                await ctx.reply(
                    embed=discord.Embed(
                        title="Backfill started",
                        description=f"pending={result['pending_count']} est_minutes={result['estimated_minutes']}",
                        color=COLOR_PENDING,
                    )
                )
            elif subcommand == "status":
                status = await self.api.backfill_status()
                embed = discord.Embed(title="Backfill Progress", color=COLOR_INFO)
                embed.add_field(name="Complete", value=f"{status['percent_complete']}%")
                embed.add_field(name="Done", value=str(status["done"]))
                embed.add_field(name="Pending", value=str(status["pending"]))
                embed.add_field(name="Failed", value=str(status["failed"]))
                await ctx.reply(embed=embed)
        except PipelineAPIError:
            await ctx.reply(embed=discord.Embed(description="Pipeline API is unavailable. Try again later.", color=COLOR_ERROR))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ImportCog(bot))
