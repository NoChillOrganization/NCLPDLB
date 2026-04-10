"""
Tests for src/ml/train_matchup.py

Covers: _embed_team_matrix, train_format, predict_matchup, train_combined.
Uses real numpy + sklearn (both installed) with tiny synthetic datasets.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pytest
from sklearn.ensemble import GradientBoostingClassifier

from src.ml.train_matchup import (
    _embed_team_matrix,
    predict_matchup,
    train_combined,
    train_format,
)

TEAM_SIZE = 6
VOCAB_SIZE = 20


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_team_data(n: int, vocab_size: int = VOCAB_SIZE, seed: int = 0):
    rng = np.random.default_rng(seed)
    X = rng.integers(1, vocab_size, size=(n, TEAM_SIZE * 2)).astype(np.int32)
    y = rng.integers(0, 2, size=n)
    return X, y


def _write_fmt_dir(
    tmp_dir: Path,
    fmt: str,
    n: int = 60,
    seed: int = 0,
    vocab_size: int = VOCAB_SIZE,
    write_vocab: bool = True,
) -> Path:
    fmt_dir = tmp_dir / fmt
    fmt_dir.mkdir(parents=True, exist_ok=True)
    X, y = _make_team_data(n, vocab_size=vocab_size, seed=seed)
    np.save(fmt_dir / "X_team.npy", X)
    np.save(fmt_dir / "y_team.npy", y)
    if write_vocab:
        vocab = {"token2id": {f"poke{i}": i for i in range(vocab_size)}}
        (fmt_dir / "species_vocab.json").write_text(json.dumps(vocab), encoding="utf-8")
    return fmt_dir


def _write_model_pkl(
    fmt_dir: Path,
    fmt: str,
    vocab_size: int = VOCAB_SIZE,
    write_vocab: bool = True,
) -> None:
    X, y = _make_team_data(60, vocab_size=vocab_size)
    Xf = _embed_team_matrix(X, vocab_size)
    model = GradientBoostingClassifier(n_estimators=5, max_depth=2, random_state=0)
    model.fit(Xf, y)
    bundle = {"model": model, "vocab_size": vocab_size, "format": fmt}
    with open(fmt_dir / "matchup_model.pkl", "wb") as f:
        pickle.dump(bundle, f)
    if write_vocab:
        vocab = {"token2id": {f"poke{i}": i for i in range(vocab_size)}}
        (fmt_dir / "species_vocab.json").write_text(json.dumps(vocab), encoding="utf-8")


# ── _embed_team_matrix ────────────────────────────────────────────────────────

class TestEmbedTeamMatrix:
    def test_output_shape(self):
        X = np.zeros((10, 12), dtype=np.int32)
        result = _embed_team_matrix(X, vocab_size=50)
        # p1_bag + p2_bag + p1_unique + p2_unique + overlap = 50*4 + 1
        assert result.shape == (10, 50 * 4 + 1)

    def test_all_zeros_input(self):
        X = np.zeros((5, 12), dtype=np.int32)
        result = _embed_team_matrix(X, vocab_size=10)
        assert result.sum() == 0.0

    def test_same_team_full_overlap(self):
        # Both teams have species 1-6 → overlap = 6
        X = np.tile(np.arange(1, 7), (8, 2)).astype(np.int32)
        result = _embed_team_matrix(X, vocab_size=10)
        overlap_col = result[:, -1]
        np.testing.assert_array_equal(overlap_col, 6.0)

    def test_different_teams_no_overlap(self):
        X = np.zeros((5, 12), dtype=np.int32)
        X[:, :6] = np.arange(1, 7)    # p1: species 1–6
        X[:, 6:] = np.arange(7, 13)   # p2: species 7–12
        result = _embed_team_matrix(X, vocab_size=15)
        overlap_col = result[:, -1]
        np.testing.assert_array_equal(overlap_col, 0.0)

    def test_dtype_float32(self):
        X, _ = _make_team_data(10)
        result = _embed_team_matrix(X, vocab_size=VOCAB_SIZE)
        assert result.dtype == np.float32

    def test_large_vocab(self):
        X, _ = _make_team_data(20, vocab_size=512)
        result = _embed_team_matrix(X, vocab_size=512)
        assert result.shape == (20, 512 * 4 + 1)

    def test_single_row(self):
        X = np.array([[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]], dtype=np.int32)
        result = _embed_team_matrix(X, vocab_size=15)
        assert result.shape[0] == 1

    def test_partial_overlap(self):
        # p1: [1,2,3,4,5,6], p2: [1,2,3,7,8,9] → 3 shared
        X = np.array([[1, 2, 3, 4, 5, 6, 1, 2, 3, 7, 8, 9]], dtype=np.int32)
        result = _embed_team_matrix(X, vocab_size=15)
        assert result[0, -1] == 3.0


# ── train_format ──────────────────────────────────────────────────────────────

class TestTrainFormat:
    def test_missing_data_returns_empty(self, tmp_path):
        result = train_format("gen9ou", ml_dir=tmp_path)
        assert result == {}

    def test_too_few_samples_returns_empty(self, tmp_path):
        _write_fmt_dir(tmp_path, "gen9ou", n=10)
        result = train_format("gen9ou", ml_dir=tmp_path, n_folds=2)
        assert result == {}

    def test_trains_and_returns_metrics(self, tmp_path):
        _write_fmt_dir(tmp_path, "gen9ou", n=60)
        result = train_format("gen9ou", ml_dir=tmp_path, n_folds=2)
        assert result["format"] == "gen9ou"
        assert "accuracy" in result
        assert "roc_auc" in result
        assert "log_loss" in result
        assert result["n_samples"] == 60
        assert 0.0 <= result["accuracy"] <= 1.0
        assert 0.0 <= result["roc_auc"] <= 1.0

    def test_saves_model_and_metrics_files(self, tmp_path):
        _write_fmt_dir(tmp_path, "gen9ou", n=60)
        train_format("gen9ou", ml_dir=tmp_path, n_folds=2)
        assert (tmp_path / "gen9ou" / "matchup_model.pkl").exists()
        assert (tmp_path / "gen9ou" / "matchup_metrics.json").exists()

    def test_saved_model_is_loadable(self, tmp_path):
        _write_fmt_dir(tmp_path, "gen9ou", n=60)
        train_format("gen9ou", ml_dir=tmp_path, n_folds=2)
        with open(tmp_path / "gen9ou" / "matchup_model.pkl", "rb") as f:
            bundle = pickle.load(f)
        assert "model" in bundle
        assert "vocab_size" in bundle
        assert bundle["format"] == "gen9ou"

    def test_no_vocab_file_uses_default_512(self, tmp_path):
        _write_fmt_dir(tmp_path, "gen9ou", n=60, write_vocab=False)
        result = train_format("gen9ou", ml_dir=tmp_path, n_folds=2)
        assert result.get("vocab_size") == 512

    def test_metrics_json_has_no_model_key(self, tmp_path):
        _write_fmt_dir(tmp_path, "gen9ou", n=60)
        train_format("gen9ou", ml_dir=tmp_path, n_folds=2)
        metrics = json.loads(
            (tmp_path / "gen9ou" / "matchup_metrics.json").read_text(encoding="utf-8")
        )
        assert "model" not in metrics
        assert "accuracy" in metrics


# ── predict_matchup ───────────────────────────────────────────────────────────

class TestPredictMatchup:
    def test_no_model_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No trained model"):
            predict_matchup(["pikachu"] * 6, ["charmander"] * 6,
                            fmt="gen9ou", ml_dir=tmp_path)

    def test_returns_probability_dict(self, tmp_path):
        fmt_dir = tmp_path / "gen9ou"
        fmt_dir.mkdir()
        _write_model_pkl(fmt_dir, "gen9ou")
        result = predict_matchup(
            [f"poke{i}" for i in range(1, 7)],
            [f"poke{i}" for i in range(7, 13)],
            fmt="gen9ou",
            ml_dir=tmp_path,
        )
        assert "p1_win_prob" in result
        assert "p2_win_prob" in result

    def test_probabilities_sum_to_one(self, tmp_path):
        fmt_dir = tmp_path / "gen9ou"
        fmt_dir.mkdir()
        _write_model_pkl(fmt_dir, "gen9ou")
        result = predict_matchup(
            ["poke1"] * 6, ["poke2"] * 6, fmt="gen9ou", ml_dir=tmp_path
        )
        assert abs(result["p1_win_prob"] + result["p2_win_prob"] - 1.0) < 1e-6

    def test_probabilities_in_range(self, tmp_path):
        fmt_dir = tmp_path / "gen9ou"
        fmt_dir.mkdir()
        _write_model_pkl(fmt_dir, "gen9ou")
        result = predict_matchup(
            ["poke1"] * 6, ["poke2"] * 6, fmt="gen9ou", ml_dir=tmp_path
        )
        assert 0.0 <= result["p1_win_prob"] <= 1.0
        assert 0.0 <= result["p2_win_prob"] <= 1.0

    def test_short_team_padded_with_zeros(self, tmp_path):
        fmt_dir = tmp_path / "gen9ou"
        fmt_dir.mkdir()
        _write_model_pkl(fmt_dir, "gen9ou")
        result = predict_matchup(
            ["poke1", "poke2"],  # only 2 mons
            ["poke3", "poke4"],
            fmt="gen9ou",
            ml_dir=tmp_path,
        )
        assert "p1_win_prob" in result

    def test_no_vocab_file(self, tmp_path):
        """Works without vocab file (empty vocab → all unknown mapped to 0)."""
        fmt_dir = tmp_path / "gen9ou"
        fmt_dir.mkdir()
        _write_model_pkl(fmt_dir, "gen9ou", write_vocab=False)
        # model was trained with vocab_size, but inference can still run
        result = predict_matchup(
            ["unknown_mon"] * 6, ["other_mon"] * 6,
            fmt="gen9ou",
            ml_dir=tmp_path,
        )
        assert "p1_win_prob" in result

    def test_unknown_species_maps_to_zero(self, tmp_path):
        """Species not in vocab get mapped to index 0 (UNK)."""
        fmt_dir = tmp_path / "gen9ou"
        fmt_dir.mkdir()
        _write_model_pkl(fmt_dir, "gen9ou")
        result = predict_matchup(
            ["nonexistent_mon_xyz"] * 6,
            ["nonexistent_mon_abc"] * 6,
            fmt="gen9ou",
            ml_dir=tmp_path,
        )
        assert 0.0 <= result["p1_win_prob"] <= 1.0


# ── train_combined ────────────────────────────────────────────────────────────

class TestTrainCombined:
    def test_no_data_returns_empty(self, tmp_path):
        result = train_combined(["gen9ou", "gen9nu"], ml_dir=tmp_path)
        assert result == {}

    def test_trains_combined_model(self, tmp_path):
        _write_fmt_dir(tmp_path, "gen9ou", n=60, seed=0)
        _write_fmt_dir(tmp_path, "gen9nu", n=60, seed=1)
        result = train_combined(["gen9ou", "gen9nu"], ml_dir=tmp_path, n_folds=2)
        assert result["format"] == "combined"
        assert result["n_samples"] >= 60

    def test_saves_combined_files(self, tmp_path):
        _write_fmt_dir(tmp_path, "gen9ou", n=60, seed=0)
        _write_fmt_dir(tmp_path, "gen9nu", n=60, seed=1)
        train_combined(["gen9ou", "gen9nu"], ml_dir=tmp_path, n_folds=2)
        combined_dir = tmp_path / "combined"
        assert (combined_dir / "matchup_model.pkl").exists()
        assert (combined_dir / "global_vocab.json").exists()
        assert (combined_dir / "matchup_metrics.json").exists()

    def test_combined_metrics_has_no_model(self, tmp_path):
        _write_fmt_dir(tmp_path, "gen9ou", n=60, seed=0)
        _write_fmt_dir(tmp_path, "gen9nu", n=60, seed=1)
        train_combined(["gen9ou", "gen9nu"], ml_dir=tmp_path, n_folds=2)
        metrics = json.loads(
            (tmp_path / "combined" / "matchup_metrics.json").read_text(encoding="utf-8")
        )
        assert "model" not in metrics
        assert "accuracy" in metrics

    def test_skips_formats_with_insufficient_data(self, tmp_path):
        # gen9ou has 100 samples (≥20); gen9nu has only 10 (< 20) → skipped
        _write_fmt_dir(tmp_path, "gen9ou", n=100, seed=0)
        _write_fmt_dir(tmp_path, "gen9nu", n=10, seed=1)
        result = train_combined(["gen9ou", "gen9nu"], ml_dir=tmp_path, n_folds=2)
        assert result["n_samples"] == 100

    def test_global_vocab_written_correctly(self, tmp_path):
        _write_fmt_dir(tmp_path, "gen9ou", n=60, seed=0)
        _write_fmt_dir(tmp_path, "gen9nu", n=60, seed=1)
        train_combined(["gen9ou", "gen9nu"], ml_dir=tmp_path, n_folds=2)
        vocab_data = json.loads(
            (tmp_path / "combined" / "global_vocab.json").read_text(encoding="utf-8")
        )
        assert "token2id" in vocab_data
        assert "<UNK>" in vocab_data["token2id"]
        assert vocab_data["token2id"]["<UNK>"] == 0
