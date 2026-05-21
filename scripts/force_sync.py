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


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    for cog in COGS:
        await bot.load_extension(cog)
    cmds = bot.tree.get_commands()
    print(f"Loaded {len(cmds)} commands")
    guild = discord.Object(id=int(settings.discord_guild_id))
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    print(f"Synced {len(synced)} commands to guild {settings.discord_guild_id}")
    await bot.close()
    print("Done.")


asyncio.run(bot.start(settings.discord_token))
