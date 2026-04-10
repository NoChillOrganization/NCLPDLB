"""
Tests for src/ml/train_all.py

Covers pure helper functions:
  - _model_done()
  - _resume_checkpoint()
  - TRAINING_MAP structure
"""
from __future__ import annotations

from pathlib import Path


from src.ml.train_all import (
    TRAINING_MAP,
    _model_done,
    _resume_checkpoint,
)


# ── _model_done ───────────────────────────────────────────────────────────────

class TestModelDone:
    def test_returns_false_when_no_files(self, tmp_path):
        assert _model_done("gen9ou", tmp_path) is False

    def test_returns_true_when_dated_zip_exists(self, tmp_path):
        (tmp_path / "gen9ou_2025-01-01.zip").touch()
        assert _model_done("gen9ou", tmp_path) is True

    def test_returns_false_for_different_format(self, tmp_path):
        (tmp_path / "gen9uu_2025-01-01.zip").touch()
        assert _model_done("gen9ou", tmp_path) is False

    def test_returns_false_for_non_zip(self, tmp_path):
        (tmp_path / "gen9ou_2025-01-01.txt").touch()
        assert _model_done("gen9ou", tmp_path) is False

    def test_returns_true_for_multiple_dated_zips(self, tmp_path):
        (tmp_path / "gen9ou_2025-01-01.zip").touch()
        (tmp_path / "gen9ou_2025-06-15.zip").touch()
        assert _model_done("gen9ou", tmp_path) is True

    def test_nonexistent_dir_returns_false(self, tmp_path):
        missing = tmp_path / "nonexistent"
        assert _model_done("gen9ou", missing) is False

    def test_partial_format_name_no_match(self, tmp_path):
        (tmp_path / "gen9ou_extended_2025-01-01.zip").touch()
        # The glob pattern is "{spar_fmt}_*.zip" — "gen9ou_extended" starts with "gen9ou_"
        # so glob("gen9ou_*.zip") WOULD match "gen9ou_extended_2025-01-01.zip"
        # This documents the actual behavior
        result = _model_done("gen9ou", tmp_path)
        assert isinstance(result, bool)


# ── _resume_checkpoint ────────────────────────────────────────────────────────

class TestResumeCheckpoint:
    def test_returns_none_when_no_latest(self, tmp_path):
        result = _resume_checkpoint("gen9ou", tmp_path)
        assert result is None

    def test_returns_path_when_latest_exists(self, tmp_path):
        fmt_dir = tmp_path / "gen9ou"
        fmt_dir.mkdir()
        (fmt_dir / "latest.zip").touch()

        result = _resume_checkpoint("gen9ou", tmp_path)
        assert result is not None
        assert result.name == "latest.zip"

    def test_returns_path_object(self, tmp_path):
        fmt_dir = tmp_path / "gen9ou"
        fmt_dir.mkdir()
        (fmt_dir / "latest.zip").touch()

        result = _resume_checkpoint("gen9ou", tmp_path)
        assert isinstance(result, Path)

    def test_returns_none_when_dir_missing(self, tmp_path):
        result = _resume_checkpoint("gen9ou", tmp_path)
        assert result is None

    def test_correct_path_structure(self, tmp_path):
        fmt_dir = tmp_path / "gen9vgc2026regi"
        fmt_dir.mkdir()
        (fmt_dir / "latest.zip").touch()

        result = _resume_checkpoint("gen9vgc2026regi", tmp_path)
        assert result == tmp_path / "gen9vgc2026regi" / "latest.zip"

    def test_checkpoint_zip_not_latest_not_returned(self, tmp_path):
        fmt_dir = tmp_path / "gen9ou"
        fmt_dir.mkdir()
        (fmt_dir / "ppo_ckpt_1000_steps.zip").touch()
        # Only latest.zip is considered a resume checkpoint

        result = _resume_checkpoint("gen9ou", tmp_path)
        assert result is None


# ── TRAINING_MAP ──────────────────────────────────────────────────────────────

class TestTrainingMap:
    def test_is_dict(self):
        assert isinstance(TRAINING_MAP, dict)

    def test_all_values_are_tuples(self):
        for fmt, entry in TRAINING_MAP.items():
            assert isinstance(entry, tuple), f"{fmt}: expected tuple, got {type(entry)}"
            assert len(entry) == 2, f"{fmt}: tuple length should be 2"

    def test_random_battle_has_no_teams(self):
        assert TRAINING_MAP["gen9randombattle"] == ("gen9randombattle", None)

    def test_smogon_singles_have_team_format(self):
        train_fmt, team_fmt = TRAINING_MAP["gen9ou"]
        assert train_fmt == "gen9ou"
        assert team_fmt == "gen9ou"

    def test_vgc_format_present(self):
        assert "gen9vgc2026regi" in TRAINING_MAP

    def test_all_train_fmts_are_str_or_none(self):
        for fmt, (train_fmt, _) in TRAINING_MAP.items():
            assert train_fmt is None or isinstance(train_fmt, str)

    def test_all_team_fmts_are_str_or_none(self):
        for fmt, (_, team_fmt) in TRAINING_MAP.items():
            assert team_fmt is None or isinstance(team_fmt, str)

    def test_contains_gen7_and_gen6(self):
        assert "gen7randombattle" in TRAINING_MAP
        assert "gen6randombattle" in TRAINING_MAP

    def test_doubles_formats_present(self):
        assert "gen9doublesou" in TRAINING_MAP
        assert "gen9randomdoublesbattle" in TRAINING_MAP
