"""Tests for pure helper functions in bot cogs and views."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.bot.cogs.team import decode_attachment_bytes
from src.bot.views.team_import_view import build_confirm_embed
from src.bot.cogs.admin import _model_exists, _build_progress_embed, _build_queue_embed


# ── decode_attachment_bytes ────────────────────────────────────────────────────

def test_decode_utf8_text():
    data = "Pokémon Showdown export".encode("utf-8")
    assert decode_attachment_bytes(data) == "Pokémon Showdown export"


def test_decode_ascii():
    data = b"Garchomp @ Choice Scarf"
    assert decode_attachment_bytes(data) == "Garchomp @ Choice Scarf"


def test_decode_invalid_bytes_uses_replacement():
    data = b"\xff\xfe" + b"Valid"
    result = decode_attachment_bytes(data)
    assert "Valid" in result  # replacement chars for invalid bytes, ASCII survives


def test_decode_empty_bytes():
    assert decode_attachment_bytes(b"") == ""


# ── build_confirm_embed (uncovered paths) ─────────────────────────────────────

def test_build_confirm_embed_unknown_format_key():
    """Unknown format key falls back to the key itself in the title."""
    embed = build_confirm_embed("gen9fakefmt", ["Pikachu"])
    assert "gen9fakefmt" in embed.title


def test_build_confirm_embed_empty_pokemon_list():
    embed = build_confirm_embed("gen9ou", [])
    pokemon_field = next(f for f in embed.fields if f.name == "Pokemon")
    assert pokemon_field.value == "No Pokemon found."


# ── _model_exists ─────────────────────────────────────────────────────────────

def test_model_exists_per_format_subdir(tmp_path):
    fmt_dir = tmp_path / "gen9ou"
    fmt_dir.mkdir()
    (fmt_dir / "gen9ou_2026-01-01.zip").touch()
    assert _model_exists(tmp_path, "gen9ou") is True


def test_model_exists_flat_root(tmp_path):
    (tmp_path / "gen9ou_2026-01-01.zip").touch()
    assert _model_exists(tmp_path, "gen9ou") is True


def test_model_exists_false(tmp_path):
    assert _model_exists(tmp_path, "gen9ou") is False


def test_model_exists_different_format_no_match(tmp_path):
    (tmp_path / "gen9uu_2026-01-01.zip").touch()
    assert _model_exists(tmp_path, "gen9ou") is False


# ── _build_progress_embed ─────────────────────────────────────────────────────

def test_build_progress_embed_initial():
    embed = _build_progress_embed("gen9ou", 0, 500_000, 1)
    assert "gen9ou" in embed.title
    assert "⚙️" in embed.title


def test_build_progress_embed_done():
    embed = _build_progress_embed("gen9ou", 500_000, 500_000, 1, done=True)
    assert "✅" in embed.title
    assert "gen9ou" in embed.title


def test_build_progress_embed_failed():
    embed = _build_progress_embed("gen9ou", 0, 500_000, 1, failed=True)
    assert "❌" in embed.title


def test_build_progress_embed_retry():
    embed = _build_progress_embed("gen9ou", 100_000, 500_000, 2)
    assert "🔄" in embed.title
    assert "attempt 2" in embed.title


def test_build_progress_embed_description_has_steps():
    embed = _build_progress_embed("gen9ou", 250_000, 500_000, 1)
    assert "250,000" in embed.description
    assert "500,000" in embed.description


def test_build_progress_embed_zero_total_no_crash():
    embed = _build_progress_embed("gen9ou", 0, 0, 1)
    assert embed is not None


# ── _build_queue_embed ────────────────────────────────────────────────────────

def test_build_queue_embed_initial_queued():
    embed = _build_queue_embed(5, 0, 500_000)
    assert "🚀" in embed.title
    assert "5 format(s)" in embed.title


def test_build_queue_embed_currently_training():
    embed = _build_queue_embed(5, 0, 500_000, current_fmt="gen9ou", current_steps=100_000, n_done=1)
    assert "⚙️" in embed.title
    assert "gen9ou" in embed.title


def test_build_queue_embed_done_all_success():
    embed = _build_queue_embed(5, 0, 500_000, n_done=5, done=True)
    assert "✅" in embed.title


def test_build_queue_embed_done_with_failures():
    embed = _build_queue_embed(5, 0, 500_000, n_done=4, n_failed=1, done=True)
    assert "⚠️" in embed.title


def test_build_queue_embed_with_skipped():
    embed = _build_queue_embed(5, 2, 500_000)
    assert "2 skipped" in embed.description


def test_build_queue_embed_description_has_queue_summary():
    embed = _build_queue_embed(10, 3, 500_000, n_done=2, n_failed=1)
    assert "done" in embed.description
    assert "failed" in embed.description
    assert "remaining" in embed.description
