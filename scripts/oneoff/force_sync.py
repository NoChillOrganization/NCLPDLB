"""
One-shot Discord command sync script.
Run: .venv/Scripts/python scripts/force_sync.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
import discord
from discord.ext import commands

COGS = [
    "src.bot.cogs.draft",
    "src.bot.cogs.team",
    "src.bot.cogs.league",
    "src.bot.cogs.admin",
    "src.bot.cogs.stats",
    "src.bot.cogs.sheet",
    "src.bot.cogs.misc",
]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


_synced = False


@bot.event
async def on_ready():
    global _synced
    if _synced:
        return  # skip on reconnect — extensions already loaded (H7/L28)
    _synced = True
    print(f"Logged in as {bot.user}")
    for cog in COGS:
        await bot.load_extension(cog)
    cmds = bot.tree.get_commands()
    print(f"Loaded {len(cmds)} commands")
    if not settings.discord_guild_id:
        print("ERROR: DISCORD_GUILD_ID is not set in .env")
        await bot.close()
        return
    guild = discord.Object(id=int(settings.discord_guild_id))
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    print(f"Synced {len(synced)} commands to guild {settings.discord_guild_id}")
    await bot.close()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(bot.start(settings.discord_token.get_secret_value()))
