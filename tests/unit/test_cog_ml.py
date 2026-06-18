"""Tests for src/bot/cogs/ml.py — MLCog and helper functions."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.cogs.ml import MLCog, _build_stats_table, _fmt_pct, _fmt_ckpt


# ── Pure helper tests ──────────────────────────────────────────────────────────

def test_fmt_pct_none():
    assert _fmt_pct(None) == "—"


def test_fmt_pct_zero():
    assert _fmt_pct(0.0) == "0.0%"


def test_fmt_pct_value():
    assert _fmt_pct(0.666) == "66.6%"


def test_fmt_ckpt_empty():
    assert _fmt_ckpt("") == "—"


def test_fmt_ckpt_dash():
    assert _fmt_ckpt("—") == "—"


def test_fmt_ckpt_strips_zip():
    assert _fmt_ckpt("policy_gen9ou_final.zip") == "policy_gen9ou_final"


def test_fmt_ckpt_no_zip():
    assert _fmt_ckpt("policy_gen9ou_final") == "policy_gen9ou_final"


def test_build_stats_table_empty():
    result = _build_stats_table([])
    assert result == "No battle data recorded yet."


def test_build_stats_table_renders_rows():
    rows = [
        {
            "format": "gen9ou", "battles": 50, "win_rate": 0.6,
            "last_checkpoint": "model.zip", "last_step": "1000",
            "last_trained": "2026-01-15 12:00:00",
        }
    ]
    result = _build_stats_table(rows)
    assert "```" in result
    assert "gen9ou" in result
    assert "50" in result
    assert "60.0%" in result
    assert "2026-01-15" in result  # date truncated from full timestamp


def test_build_stats_table_truncates_timestamp():
    rows = [
        {
            "format": "gen9ou", "battles": 1, "win_rate": 1.0,
            "last_checkpoint": "—", "last_step": "—",
            "last_trained": "2026-05-21 10:30:00",
        }
    ]
    result = _build_stats_table(rows)
    assert "2026-05-21" in result
    assert "10:30:00" not in result


# ── MLCog tests ────────────────────────────────────────────────────────────────

def make_interaction():
    interaction = MagicMock()
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


@pytest.fixture
def bot():
    b = MagicMock()
    return b


@pytest.fixture
def cog(bot):
    return MLCog(bot)


async def call_ml_stats(cog, interaction, refresh=False):
    """Invoke the ml_stats callback directly (bypasses app_commands.Command wrapper)."""
    await cog.ml_stats.callback(cog, interaction, refresh=refresh)


@pytest.mark.asyncio
async def test_ml_stats_not_configured(cog):
    interaction = make_interaction()
    with patch("src.bot.cogs.ml._SHEETS_AVAILABLE", False):
        await call_ml_stats(cog, interaction)
    interaction.followup.send.assert_called_once()
    assert interaction.followup.send.call_args.kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_ml_stats_sheets_disabled(cog):
    interaction = make_interaction()
    mock_ls = MagicMock()
    mock_ls.enabled = False
    with patch("src.bot.cogs.ml._SHEETS_AVAILABLE", True), \
         patch("src.bot.cogs.ml.learning_sheets", mock_ls):
        await call_ml_stats(cog, interaction)
    interaction.followup.send.assert_called_once()
    assert interaction.followup.send.call_args.kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_ml_stats_empty_cache(cog):
    interaction = make_interaction()
    mock_ls = MagicMock()
    mock_ls.enabled = True
    cog._stats_cache = []
    with patch("src.bot.cogs.ml._SHEETS_AVAILABLE", True), \
         patch("src.bot.cogs.ml.learning_sheets", mock_ls):
        await call_ml_stats(cog, interaction)
    interaction.followup.send.assert_called_once()
    embed = interaction.followup.send.call_args.kwargs.get("embed")
    assert embed is not None
    assert "No battle data" in embed.description


@pytest.mark.asyncio
async def test_ml_stats_with_data(cog):
    interaction = make_interaction()
    mock_ls = MagicMock()
    mock_ls.enabled = True
    cog._stats_cache = [
        {
            "format": "gen9ou", "battles": 10, "win_rate": 0.7,
            "last_checkpoint": "model.zip", "last_step": "500",
            "last_trained": "2026-05-21",
        }
    ]
    with patch("src.bot.cogs.ml._SHEETS_AVAILABLE", True), \
         patch("src.bot.cogs.ml.learning_sheets", mock_ls):
        await call_ml_stats(cog, interaction)
    embed = interaction.followup.send.call_args.kwargs.get("embed")
    assert embed is not None
    assert "gen9ou" in embed.description
    field_names = [f.name for f in embed.fields]
    assert "Total Battles" in field_names
    assert "Formats Tracked" in field_names
    assert "Overall Win Rate" in field_names


@pytest.mark.asyncio
async def test_ml_stats_refresh_triggers_cache_update(cog):
    interaction = make_interaction()
    mock_ls = MagicMock()
    mock_ls.enabled = True
    mock_ls.get_stats_table.return_value = []
    cog._stats_cache = []
    with patch("src.bot.cogs.ml._SHEETS_AVAILABLE", True), \
         patch("src.bot.cogs.ml.learning_sheets", mock_ls):
        loop = asyncio.get_event_loop()
        with patch.object(loop, "run_in_executor", new=AsyncMock(return_value=[])):
            await call_ml_stats(cog, interaction, refresh=True)
    interaction.followup.send.assert_called_once()
