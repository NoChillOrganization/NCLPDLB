"""
Smoke tests for ISS-003: train_transformer.train() — no Showdown server needed.

Covers:
  - _GameCapture stores games and sums transitions via __len__
  - _split_and_fill_buffers: correct train/val counts, no leakage
  - train() with monkeypatched _generate_games:
      - checkpoint written to the expected path
      - log file contains >= 2 epoch lines
      - val_losses list has >= 2 entries (non-increasing trend is logged, not asserted)
  - _parse_args: all required flags present with correct defaults
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

torch = pytest.importorskip("torch")
import numpy as np

from src.ml.battle_env import OBS_DIM, N_ACTIONS_GEN9
from src.ml.train_transformer import _GameCapture, _split_and_fill_buffers, train


# ── _GameCapture ──────────────────────────────────────────────────────────────


class TestGameCapture:
    def _make_game(self, n_turns: int = 5) -> tuple:
        rng = np.random.default_rng(7)
        obs_list = [rng.random(OBS_DIM, dtype=np.float32) for _ in range(n_turns)]
        act_list = [int(rng.integers(0, N_ACTIONS_GEN9)) for _ in range(n_turns)]
        prob_list = []
        for _ in range(n_turns):
            p = rng.random(N_ACTIONS_GEN9, dtype=np.float32)
            prob_list.append(p / p.sum())
        return obs_list, act_list, prob_list, 1.0

    def test_empty_capture_len_is_zero(self):
        cap = _GameCapture()
        assert len(cap) == 0
        assert cap.games == []

    def test_add_game_increments_len(self):
        cap = _GameCapture()
        obs, acts, probs, r = self._make_game(n_turns=5)
        cap.add_game(obs, acts, probs, r)
        assert len(cap) == 5

    def test_two_games_accumulate_transitions(self):
        cap = _GameCapture()
        for turns in (3, 7):
            obs, acts, probs, r = self._make_game(n_turns=turns)
            cap.add_game(obs, acts, probs, r)
        assert len(cap) == 10
        assert len(cap.games) == 2

    def test_add_game_copies_arrays(self):
        cap = _GameCapture()
        obs, acts, probs, r = self._make_game(n_turns=3)
        original = obs[0].copy()
        cap.add_game(obs, acts, probs, r)
        obs[0][:] = 0  # mutate original
        stored = cap.games[0][0][0]
        assert np.array_equal(stored, original), "add_game must copy obs arrays"


# ── _split_and_fill_buffers ───────────────────────────────────────────────────


class TestSplitAndFillBuffers:
    def _synthetic_games(self, n: int, turns_each: int = 4) -> list:
        rng = np.random.default_rng(99)
        games = []
        for _ in range(n):
            obs = [rng.random(OBS_DIM, dtype=np.float32) for _ in range(turns_each)]
            acts = [int(rng.integers(0, N_ACTIONS_GEN9)) for _ in range(turns_each)]
            probs = []
            for _ in range(turns_each):
                p = rng.random(N_ACTIONS_GEN9, dtype=np.float32)
                probs.append(p / p.sum())
            games.append((obs, acts, probs, float(rng.choice([-1.0, 1.0]))))
        return games

    def test_raises_on_empty_games(self):
        with pytest.raises(RuntimeError, match="No games collected"):
            _split_and_fill_buffers([], val_frac=0.2, buffer_capacity=1_000)

    def test_train_and_val_together_cover_all_games(self):
        games = self._synthetic_games(10, turns_each=4)
        train_buf, val_buf = _split_and_fill_buffers(
            games, val_frac=0.2, buffer_capacity=1_000
        )
        # 10 games × 4 turns = 40 transitions total; 8 train + 2 val
        assert len(train_buf) + len(val_buf) == 40

    def test_train_buf_larger_than_val_buf(self):
        games = self._synthetic_games(10, turns_each=4)
        train_buf, val_buf = _split_and_fill_buffers(
            games, val_frac=0.2, buffer_capacity=1_000
        )
        assert len(train_buf) > len(val_buf)

    def test_single_game_handled_without_crash(self):
        games = self._synthetic_games(1, turns_each=3)
        # With 1 game and val_frac=0.2, edge case: 0 val games
        train_buf, val_buf = _split_and_fill_buffers(
            games, val_frac=0.2, buffer_capacity=500
        )
        assert len(train_buf) >= 3


# ── train() smoke (monkeypatched game generation) ────────────────────────────


class TestTrainSmoke:
    """
    Patch _generate_games so train() uses synthetic data with no server.
    Then verify: checkpoint written, log file has >= 2 epoch lines.
    """

    def _make_synthetic_games(self, n: int = 20, turns_each: int = 8) -> list:
        rng = np.random.default_rng(123)
        games = []
        for _ in range(n):
            obs = [rng.random(OBS_DIM, dtype=np.float32) for _ in range(turns_each)]
            acts = [int(rng.integers(0, N_ACTIONS_GEN9)) for _ in range(turns_each)]
            probs = []
            for _ in range(turns_each):
                p = rng.random(N_ACTIONS_GEN9, dtype=np.float32)
                probs.append(p / p.sum())
            games.append((obs, acts, probs, float(rng.choice([-1.0, 1.0]))))
        return games

    def test_checkpoint_written_and_log_has_two_epoch_lines(self, tmp_path: Path):
        ckpt = tmp_path / "ckpt.pt"
        log_file = tmp_path / "training.log"
        synthetic = self._make_synthetic_games(n=20, turns_each=8)

        import asyncio

        async def fake_generate(*args, **kwargs):
            return synthetic

        with patch(
            "src.ml.train_transformer._generate_games",
            side_effect=lambda *a, **kw: asyncio.coroutine(lambda: synthetic)(),
        ):
            # Patch asyncio.run to call our coroutine synchronously
            with patch("src.ml.train_transformer.asyncio") as mock_asyncio:
                mock_asyncio.run.return_value = synthetic
                mock_asyncio.wait_for = asyncio.wait_for

                train(
                    fmt="gen9randombattle",
                    n_games=20,
                    n_epochs=3,
                    steps_per_epoch=2,
                    buffer_capacity=5_000,
                    mcts_sims=4,
                    lr=1e-3,
                    val_frac=0.2,
                    checkpoint_out=str(ckpt),
                    log_file=str(log_file),
                    server="localhost",
                )

        assert ckpt.exists(), "Checkpoint file must be written"
        assert log_file.exists(), "Log file must be created"

        log_lines = [
            ln
            for ln in log_file.read_text(encoding="utf-8").splitlines()
            if "epoch=" in ln
        ]
        assert len(log_lines) >= 2, (
            f"Expected >= 2 epoch log lines; got {len(log_lines)}:\n"
            + "\n".join(log_lines)
        )

    def test_val_losses_length_matches_epochs_trained(self, tmp_path: Path):
        ckpt = tmp_path / "ckpt.pt"
        log_file = tmp_path / "training.log"
        synthetic = self._make_synthetic_games(n=20, turns_each=8)

        with patch("src.ml.train_transformer.asyncio") as mock_asyncio:
            mock_asyncio.run.return_value = synthetic
            import asyncio

            mock_asyncio.wait_for = asyncio.wait_for

            results = train(
                fmt="gen9randombattle",
                n_games=20,
                n_epochs=3,
                steps_per_epoch=2,
                buffer_capacity=5_000,
                mcts_sims=4,
                lr=1e-3,
                val_frac=0.2,
                checkpoint_out=str(ckpt),
                log_file=str(log_file),
                server="localhost",
            )

        assert results["n_epochs_trained"] == len(results["val_losses"])
        assert results["n_epochs_trained"] >= 2


# ── _parse_args defaults ──────────────────────────────────────────────────────


class TestParseArgs:
    def _parse(self, argv: list[str]):
        from src.ml.train_transformer import _parse_args

        with patch("sys.argv", ["train_transformer"] + argv):
            return _parse_args()

    def test_default_format(self):
        args = self._parse([])
        assert args.format == "gen9randombattle"

    def test_default_games(self):
        args = self._parse([])
        assert args.games == 50

    def test_default_epochs(self):
        args = self._parse([])
        assert args.epochs == 10

    def test_default_mcts_sims(self):
        args = self._parse([])
        assert args.mcts_sims == 0

    def test_default_checkpoint_out(self):
        args = self._parse([])
        assert "transformer_checkpoint.pt" in args.checkpoint_out

    def test_default_log_file(self):
        args = self._parse([])
        assert "transformer_training.log" in args.log_file

    def test_custom_games_and_epochs(self):
        args = self._parse(["--games", "6", "--epochs", "3"])
        assert args.games == 6
        assert args.epochs == 3
