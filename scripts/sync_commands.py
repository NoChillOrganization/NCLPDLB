"""
One-shot command sync script.
Loads all cogs, syncs slash commands to the configured guild (or globally), then exits.

Usage:
    .venv/Scripts/python scripts/sync_commands.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import discord
from discord.ext import commands
from src.config import settings
from src.bot.main import COGS

intents = discord.Intents.default()


async def main() -> None:
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    async with bot:
        await bot.login(settings.discord_token)

        for cog in COGS:
            try:
                await bot.load_extension(cog)
                print(f"  Loaded: {cog}")
            except Exception as e:
                print(f"  WARN: {cog}: {e}")

        if settings.discord_guild_id:
            guild = discord.Object(id=int(settings.discord_guild_id))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"\n✅ Synced {len(synced)} command(s) to guild {settings.discord_guild_id}")
        else:
            synced = await bot.tree.sync()
            print(f"\n✅ Synced {len(synced)} command(s) globally (may take up to 1 hour)")

        print("Done.")


asyncio.run(main())
