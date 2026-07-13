"""Discord cog: creator registry admin commands. Requires ADMIN_ROLE_ID."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.api_client import PipelineAPIClient, PipelineAPIError
from bot.config import ADMIN_ROLE_ID, COLOR_ERROR, COLOR_INFO, COLOR_SUCCESS


def has_admin_role():
    async def predicate(ctx: commands.Context) -> bool:
        if not ADMIN_ROLE_ID:
            return True
        if not any(role.id == ADMIN_ROLE_ID for role in getattr(ctx.author, "roles", [])):
            raise commands.MissingRole(ADMIN_ROLE_ID)
        return True

    return commands.check(predicate)


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api = PipelineAPIClient()

    @commands.group(name="creators", invoke_without_command=True)
    @has_admin_role()
    async def creators(self, ctx: commands.Context) -> None:
        await ctx.reply("Subcommands: `list`, `add <channel_id> <name>`, `deactivate <name>`")

    @creators.command(name="list")
    @has_admin_role()
    async def creators_list(self, ctx: commands.Context, page: int = 1) -> None:
        try:
            data = await self.api.list_creators()
        except PipelineAPIError:
            await ctx.reply(embed=discord.Embed(description="Pipeline API is unavailable. Try again later.", color=COLOR_ERROR))
            return

        items = data if isinstance(data, list) else data.get("items", [])
        per_page = 10
        start = (page - 1) * per_page
        page_items = items[start : start + per_page]

        embed = discord.Embed(title=f"Creators (page {page})", color=COLOR_INFO)
        for c in page_items:
            status = "active" if c.get("is_active") else "inactive"
            embed.add_field(name=c["name"], value=f"{c.get('youtube_channel_id') or '—'} [{status}]", inline=False)
        await ctx.reply(embed=embed)

    @creators.command(name="add")
    @has_admin_role()
    async def creators_add(self, ctx: commands.Context, channel_id: str, *, name: str) -> None:
        try:
            await self.api.add_creator({"name": name, "youtube_channel_id": channel_id})
        except PipelineAPIError:
            await ctx.reply(embed=discord.Embed(description="Pipeline API is unavailable. Try again later.", color=COLOR_ERROR))
            return
        await ctx.reply(embed=discord.Embed(description=f"Added creator `{name}`.", color=COLOR_SUCCESS))

    @creators.command(name="deactivate")
    @has_admin_role()
    async def creators_deactivate(self, ctx: commands.Context, *, name: str) -> None:
        try:
            data = await self.api.list_creators()
            items = data if isinstance(data, list) else data.get("items", [])
            match = next((c for c in items if c["name"].lower() == name.lower()), None)
            if match is None:
                await ctx.reply(f"No creator found named `{name}`.")
                return
            await self.api._request("DELETE", f"/creators/{match['id']}", admin=True)
        except PipelineAPIError:
            await ctx.reply(embed=discord.Embed(description="Pipeline API is unavailable. Try again later.", color=COLOR_ERROR))
            return
        await ctx.reply(embed=discord.Embed(description=f"Deactivated `{name}`.", color=COLOR_SUCCESS))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
