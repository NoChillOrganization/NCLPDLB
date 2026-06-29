"""
Miscellaneous commands cog — /help, /help-roles, /models-status.
"""

import csv
import logging
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from src.bot.permissions import ROLE_COACH, ROLE_GUILDMASTER, ROLE_MOD, require_role
from src.config import settings

log = logging.getLogger(__name__)

_CSV_PATH = Path(__file__).parent.parent.parent.parent / "discord_commands.csv"


def build_help_embed(csv_path: Path = _CSV_PATH) -> discord.Embed:
    """Build a category-grouped help embed from discord_commands.csv."""
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
        value = "\n".join(cmds)[:1024]
        embed.add_field(name=cat, value=value, inline=False)

    return embed


class MiscCog(commands.Cog, name="Misc"):
    """Miscellaneous utility commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="Show all available bot commands")
    @require_role(ROLE_COACH)
    async def help_cmd(self, interaction: discord.Interaction) -> None:
        """Display all bot commands grouped by category, sourced from commands.csv."""
        await interaction.response.defer(ephemeral=True)
        embed = build_help_embed()
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="help-roles", description="Show which roles can use which commands"
    )
    @require_role(ROLE_COACH)
    async def help_roles(self, interaction: discord.Interaction) -> None:
        """Static embed mapping the 3 server roles to their command groups."""
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="Role Permissions",
            description="Commands are restricted to the 3 league roles (highest → lowest).",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name=f"👑 {ROLE_GUILDMASTER}",
            value=(
                "league-create, draft-setup, draft-create, draft-start, draft-cancel\n"
                "admin-update, admin-sync, admin-reset, admin-train, admin-train-all\n"
                "admin-pull-models, admin-cancel-pull, admin-set-repo\n"
                "sheet-setup, sheet-pokedex"
            ),
            inline=False,
        )
        embed.add_field(
            name=f"🛡️ {ROLE_MOD}",
            value=(
                "admin-skip, admin-pause, admin-resume, admin-override-pick\n"
                "admin-showdown-check, admin-list-releases\n"
                "sheet-standings, sheet-schedule, sheet-result, sheet-transaction\n"
                "sheet-rule, sheet-player, sheet-playoff\n"
                "*(also has all Draft League Coaches permissions)*"
            ),
            inline=False,
        )
        embed.add_field(
            name=f"🎮 {ROLE_COACH}",
            value=(
                "draft-join, pick, ban, bid, draft-status, draft-board\n"
                "schedule, result\n"
                "team, team-register, trade, trade-accept, trade-decline, teamimport, teamexport, legality\n"
                "analysis, matchup, standings, replay, match-upload, pokemon, spar\n"
                "ml-stats, models-status, help, help-roles"
            ),
            inline=False,
        )
        embed.set_footer(text="Server admins (Manage Server) bypass all role checks.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="models-status",
        description="Show which trained AI models are installed locally",
    )
    @require_role(ROLE_COACH)
    async def models_status(self, interaction: discord.Interaction) -> None:
        """Scan data/ml/policy/ and report present/missing models per format."""
        await interaction.response.defer(ephemeral=True)
        from src.ml.train_all import TRAINING_MAP

        policy_dir = Path(__file__).parents[3] / settings.ml_policy_dir
        lines: list[str] = []
        for fmt in TRAINING_MAP:
            model_path = policy_dir / fmt / "final_model.zip"
            if model_path.exists():
                size_kb = model_path.stat().st_size // 1024
                lines.append(f"✅ `{fmt}` — {size_kb} KB")
            else:
                lines.append(f"❌ `{fmt}` — not installed")

        installed = sum(1 for line in lines if line.startswith("✅"))
        embed = discord.Embed(
            title="Local Model Status",
            description="\n".join(lines) or "No formats in TRAINING_MAP.",
            color=discord.Color.green()
            if installed == len(lines)
            else discord.Color.orange(),
        )
        embed.set_footer(
            text=f"{installed}/{len(lines)} models installed · Use /admin-pull-models to download"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MiscCog(bot))
