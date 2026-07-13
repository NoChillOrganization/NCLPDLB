"""Discord bot entry point — loads cogs, configures prefix, handles errors globally."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from bot.config import BOT_PREFIX, BOT_TOKEN, COLOR_ERROR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

COGS = [
    "bot.cogs.import_cog",
    "bot.cogs.team_cog",
    "bot.cogs.admin_cog",
]


@bot.event
async def on_ready() -> None:
    logger.info("Logged in as %s (guilds=%d)", bot.user, len(bot.guilds))


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRole):
        await ctx.reply(embed=discord.Embed(description="You do not have permission to use this command.", color=COLOR_ERROR))
        return
    logger.error("Unhandled command error in %s: %s", ctx.command, error)
    await ctx.reply(embed=discord.Embed(description="Something went wrong running that command.", color=COLOR_ERROR))


async def main() -> None:
    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
