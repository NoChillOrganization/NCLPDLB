"""
Tests for src/ml/showdown_player.py

Covers pure helper functions:
  - _get_opponent_name()
  - best_model_for_format()
  - BotChallenger._format_result()
  - Import sanity for browser_trainer.py
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock


from src.ml.showdown_player import (
    BotChallenger,
    _get_opponent_name,
    best_model_for_format,
)


# ── _get_opponent_name ────────────────────────────────────────────────────────

class TestGetOpponentName:
    def test_returns_opponent_username(self):
        battle = MagicMock()
        battle.opponent_username = "TestPlayer"
        assert _get_opponent_name(battle) == "TestPlayer"

    def test_returns_unknown_when_none(self):
        battle = MagicMock()
        battle.opponent_username = None
        assert _get_opponent_name(battle) == "Unknown"

    def test_returns_unknown_on_exception(self):
        class BadBattle:
            @property
            def opponent_username(self):
                raise AttributeError("no attribute")
        result = _get_opponent_name(BadBattle())
        assert result == "Unknown"


# ── best_model_for_format ─────────────────────────────────────────────────────

class TestBestModelForFormat:
    def test_returns_none_when_nothing_exists(self, tmp_path):
        result = best_model_for_format(
            "gen9ou",
            save_dir=str(tmp_path / "policy"),
            results_dir=str(tmp_path / "results"),
        )
        assert result is None

    def test_prefers_dated_model_in_subdir(self, tmp_path):
        fmt = "gen9ou"
        subdir = tmp_path / "results" / fmt
        subdir.mkdir(parents=True)
        # Create two dated models
        (subdir / f"{fmt}_2025-01-01.zip").touch()
        (subdir / f"{fmt}_2025-06-15.zip").touch()

        result = best_model_for_format(
            fmt,
            save_dir=str(tmp_path / "policy"),
            results_dir=str(tmp_path / "results"),
        )
        assert result is not None
        assert "2025-06-15" in result.name

    def test_falls_back_to_flat_results_dir(self, tmp_path):
        fmt = "gen9ou"
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / f"{fmt}_2025-03-01.zip").touch()

        result = best_model_for_format(
            fmt,
            save_dir=str(tmp_path / "policy"),
            results_dir=str(results_dir),
        )
        assert result is not None
        assert "2025-03-01" in result.name

    def test_falls_back_to_latest_zip(self, tmp_path):
        fmt = "gen9ou"
        fmt_save = tmp_path / "policy" / fmt
        fmt_save.mkdir(parents=True)
        (fmt_save / "latest.zip").touch()

        result = best_model_for_format(
            fmt,
            save_dir=str(tmp_path / "policy"),
            results_dir=str(tmp_path / "results"),
        )
        assert result is not None
        assert result.name == "latest.zip"

    def test_falls_back_to_newest_ppo_checkpoint(self, tmp_path):
        fmt = "gen9ou"
        fmt_save = tmp_path / "policy" / fmt
        fmt_save.mkdir(parents=True)
        (fmt_save / "ppo_ckpt_1000_steps.zip").touch()
        (fmt_save / "ppo_ckpt_2000_steps.zip").touch()

        result = best_model_for_format(
            fmt,
            save_dir=str(tmp_path / "policy"),
            results_dir=str(tmp_path / "results"),
        )
        assert result is not None
        assert "ppo_ckpt_2000" in result.name

    def test_subdir_result_beats_flat_result(self, tmp_path):
        fmt = "gen9ou"
        # Flat result
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / f"{fmt}_2025-01-01.zip").touch()
        # Subdir result (preferred)
        subdir = results_dir / fmt
        subdir.mkdir()
        (subdir / f"{fmt}_2025-06-01.zip").touch()

        result = best_model_for_format(
            fmt,
            save_dir=str(tmp_path / "policy"),
            results_dir=str(results_dir),
        )
        assert result is not None
        assert "2025-06-01" in result.name

    def test_dated_model_beats_latest_zip(self, tmp_path):
        fmt = "gen9ou"
        # Create a latest.zip in save_dir
        fmt_save = tmp_path / "policy" / fmt
        fmt_save.mkdir(parents=True)
        (fmt_save / "latest.zip").touch()
        # Also create a dated model in results_dir
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / f"{fmt}_2025-06-01.zip").touch()

        result = best_model_for_format(
            fmt,
            save_dir=str(tmp_path / "policy"),
            results_dir=str(results_dir),
        )
        assert result is not None
        assert "2025-06-01" in result.name

    def test_returns_path_object(self, tmp_path):
        fmt = "gen9ou"
        fmt_save = tmp_path / "policy" / fmt
        fmt_save.mkdir(parents=True)
        (fmt_save / "latest.zip").touch()

        result = best_model_for_format(
            fmt,
            save_dir=str(tmp_path / "policy"),
            results_dir=str(tmp_path / "results"),
        )
        assert isinstance(result, Path)


# ── BotChallenger._format_result ─────────────────────────────────────────────

class TestBotChallengerFormatResult:
    """Test the _format_result method without initializing BotChallenger fully."""

    def _make_challenger(self, fmt: str = "gen9ou", username: str = "TestBot"):
        """Create a BotChallenger bypassing __init__ (which requires poke-env)."""
        challenger = BotChallenger.__new__(BotChallenger)
        challenger.fmt = fmt
        challenger.username = username
        return challenger

    def test_won_battle(self):
        challenger = self._make_challenger()
        battle = MagicMock()
        battle.won = True
        battle.lost = False
        battle.turn = 25

        result = challenger._format_result(battle)
        assert result["winner"] == "bot"

    def test_lost_battle(self):
        challenger = self._make_challenger()
        battle = MagicMock()
        battle.won = False
        battle.lost = True
        battle.turn = 30

        result = challenger._format_result(battle)
        assert result["winner"] == "opponent"

    def test_tied_battle(self):
        challenger = self._make_challenger()
        battle = MagicMock()
        battle.won = False
        battle.lost = False
        battle.turn = 100

        result = challenger._format_result(battle)
        assert result["winner"] == "tie"

    def test_result_contains_required_keys(self):
        challenger = self._make_challenger()
        battle = MagicMock()
        battle.won = True
        battle.lost = False
        battle.turn = 15

        result = challenger._format_result(battle)
        required = {"winner", "turns", "replay_url", "format", "bot_name", "opponent"}
        assert required.issubset(result.keys())

    def test_result_format_matches_init(self):
        challenger = self._make_challenger(fmt="gen9vgc2026regi", username="BotUser")
        battle = MagicMock()
        battle.won = True
        battle.lost = False
        battle.turn = 10

        result = challenger._format_result(battle)
        assert result["format"] == "gen9vgc2026regi"
        assert result["bot_name"] == "BotUser"

    def test_replay_url_passthrough(self):
        challenger = self._make_challenger()
        battle = MagicMock()
        battle.won = True
        battle.lost = False
        battle.turn = 5

        result = challenger._format_result(battle, replay_url="https://example.com/replay")
        assert result["replay_url"] == "https://example.com/replay"

    def test_replay_url_none_by_default(self):
        challenger = self._make_challenger()
        battle = MagicMock()
        battle.won = True
        battle.lost = False
        battle.turn = 5

        result = challenger._format_result(battle)
        assert result["replay_url"] is None


# ── browser_trainer import sanity ─────────────────────────────────────────────

class TestBrowserTrainerImport:
    def test_module_importable(self):
        """browser_trainer.py should import without errors (no Playwright needed)."""
        import src.ml.browser_trainer  # noqa: F401
        assert True

    def test_constants_defined(self):
        from src.ml.browser_trainer import SHOWDOWN_URL, DEFAULT_SAVE_DIR, DEFAULT_RESULTS_DIR
        assert SHOWDOWN_URL == "https://play.pokemonshowdown.com"
        assert "data/ml/policy" in DEFAULT_SAVE_DIR
        assert "results" in DEFAULT_RESULTS_DIR
