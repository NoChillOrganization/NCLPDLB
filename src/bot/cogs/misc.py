"""
Miscellaneous commands cog — /help and other utility commands.
"""
import csv
import logging
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)

# discord_commands.csv is 4 dirs up from this file:
# src/bot/cogs/misc.py -> cogs -> bot -> src -> project_root
_CSV_PATH = Path(__file__).parent.parent.parent.parent / "discord_commands.csv"


def build_help_embed(csv_path: Path = _CSV_PATH) -> discord.Embed:
    """Build a category-grouped help embed from discord_commands.csv.

    Reads the CSV at call time so the embed always reflects the current file
    without requiring a bot restart. Groups commands by Category column.

    Args:
        csv_path: Path to discord_commands.csv. Defaults to project-root location.

    Returns:
        discord.Embed with one field per category.
    """
    embed = discord.Embed(title="Bot Commands", color=discord.Color.blurple())
    if not csv_path.exists():
        embed.description = "Command list unavailable (discord_commands.csv not found)."
        return embed

    categories: dict[str, list[str]] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cat = row.get("Category", "Other")
            cmd = row.get("Command", "")
            if cmd:
                categories.setdefault(cat, []).append(cmd)

    for cat, cmds in categories.items():
        embed.add_field(name=cat, value="\n".join(cmds), inline=False)

    return embed


class MiscCog(commands.Cog, name="Misc"):
    """Miscellaneous utility commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="Show all available bot commands")
    async def help_cmd(self, interaction: discord.Interaction) -> None:
        """Display all bot commands grouped by category, sourced from commands.csv."""
        await interaction.response.defer(ephemeral=True)
        embed = build_help_embed()
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MiscCog(bot))
