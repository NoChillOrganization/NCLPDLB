"""
ML Cog — /ml-stats command and startup stats cache.
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.bot.permissions import ROLE_COACH, require_role

log = logging.getLogger(__name__)

try:
    from src.data.sheets import learning_sheets

    _SHEETS_AVAILABLE = True
except Exception:  # pragma: no cover
    learning_sheets = None  # type: ignore
    _SHEETS_AVAILABLE = False


def _fmt_pct(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val * 100:.1f}%"


def _fmt_ckpt(name: str) -> str:
    if not name or name == "—":
        return "—"
    # strip .zip suffix for display
    return name.replace(".zip", "")


def _build_stats_table(rows: list[dict]) -> str:
    """Render stats as a fixed-width code-block table."""
    if not rows:
        return "No battle data recorded yet."
    col_fmt = max(len(r["format"]) for r in rows)
    col_fmt = max(col_fmt, 6)
    header = (
        f"{'Format':<{col_fmt}}  {'Battles':>7}  {'Win%':>6}  "
        f"{'Last Ckpt':<20}  {'Step':>8}  Last Trained"
    )
    sep = "─" * len(header)
    lines = [header, sep]
    for r in rows:
        ckpt = _fmt_ckpt(r.get("last_checkpoint", "—"))
        step = r.get("last_step", "—")
        ts = r.get("last_trained", "—")
        # truncate timestamp to date only
        if ts and ts != "—":
            ts = ts[:10]
        lines.append(
            f"{r['format']:<{col_fmt}}  {r['battles']:>7}  "
            f"{_fmt_pct(r['win_rate']):>6}  {ckpt:<20}  {str(step):>8}  {ts}"
        )
    return "```\n" + "\n".join(lines) + "\n```"


class MLCog(commands.Cog, name="ML"):
    """Machine learning training stats and model management."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._stats_cache: list[dict] = []
        self._cache_lock = asyncio.Lock()

    async def cog_load(self) -> None:
        """Warm the stats cache on startup."""
        await self._refresh_cache()

    async def _refresh_cache(self) -> None:
        if not _SHEETS_AVAILABLE or not learning_sheets or not learning_sheets.enabled:
            return
        try:
            rows = await asyncio.get_running_loop().run_in_executor(
                None, learning_sheets.get_stats_table
            )
            async with self._cache_lock:
                self._stats_cache = rows
            log.info("[MLCog] Stats cache refreshed: %d formats", len(rows))
        except Exception as exc:
            log.warning("[MLCog] Failed to refresh stats cache: %s", exc)

    # ── /ml-stats ─────────────────────────────────────────────────────

    @app_commands.command(
        name="ml-stats", description="Show ML training stats per format"
    )
    @require_role(ROLE_COACH)
    @app_commands.describe(refresh="Re-fetch latest data from the sheet")
    async def ml_stats(
        self,
        interaction: discord.Interaction,
        refresh: bool = False,
    ) -> None:
        await interaction.response.defer()

        if not _SHEETS_AVAILABLE or not learning_sheets or not learning_sheets.enabled:
            await interaction.followup.send(
                "ML learning spreadsheet not configured. Set `ML_LEARNING_SPREADSHEET_ID` in `.env`.",
                ephemeral=True,
            )
            return

        if refresh:
            await self._refresh_cache()

        async with self._cache_lock:
            rows = list(self._stats_cache)

        table = _build_stats_table(rows)

        total_battles = sum(r["battles"] for r in rows)
        formats_with_data = len(rows)
        overall_wr = (
            sum(r["win_rate"] * r["battles"] for r in rows) / total_battles
            if total_battles > 0
            else None
        )

        embed = discord.Embed(
            title="ML Training Stats",
            description=table,
            color=discord.Color.purple(),
        )
        embed.add_field(name="Total Battles", value=str(total_battles), inline=True)
        embed.add_field(
            name="Formats Tracked", value=str(formats_with_data), inline=True
        )
        embed.add_field(
            name="Overall Win Rate", value=_fmt_pct(overall_wr), inline=True
        )
        embed.set_footer(
            text="Data from ML learning spreadsheet · /ml-stats refresh:True to update"
        )

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MLCog(bot))
