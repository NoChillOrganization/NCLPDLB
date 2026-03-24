"""
Tests for src/ml/train_policy.py

Covers pure-logic functions only:
  - _check_showdown_server()
  - _check_showdown_server_if_local()
  - SelfPlayCallback.__init__, _on_step, _save_and_swap
  - Constants: DOUBLES_FORMATS, PPO_HYPERPARAMS
"""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ml.train_policy import (
    DOUBLES_FORMATS,
    PPO_HYPERPARAMS,
    SelfPlayCallback,
    _check_showdown_server,
    _check_showdown_server_if_local,
)


# ── _check_showdown_server ────────────────────────────────────────────────────

class TestCheckShowdownServer:
    def test_reachable_does_not_raise(self):
        with patch("socket.create_connection"):
            _check_showdown_server()  # should not raise

    def test_unreachable_raises_runtime_error(self):
        with patch("socket.create_connection", side_effect=OSError("refused")):
            with pytest.raises(RuntimeError, match="Cannot reach local Showdown server"):
                _check_showdown_server()

    def test_error_message_contains_port(self):
        with patch("socket.create_connection", side_effect=OSError()):
            with pytest.raises(RuntimeError, match="8000"):
                _check_showdown_server()


# ── _check_showdown_server_if_local ──────────────────────────────────────────

class TestCheckShowdownServerIfLocal:
    def test_localhost_mode_calls_check(self):
        with patch("src.ml.train_policy._check_showdown_server") as mock_check:
            _check_showdown_server_if_local("localhost")
            mock_check.assert_called_once()

    def test_non_localhost_skips_check(self):
        with patch("src.ml.train_policy._check_showdown_server") as mock_check:
            _check_showdown_server_if_local("showdown")
            mock_check.assert_not_called()

    def test_browser_mode_skips_check(self):
        with patch("src.ml.train_policy._check_showdown_server") as mock_check:
            _check_showdown_server_if_local("browser")
            mock_check.assert_not_called()


# ── Constants ─────────────────────────────────────────────────────────────────

class TestConstants:
    def test_doubles_formats_is_set(self):
        assert isinstance(DOUBLES_FORMATS, set)

    def test_doubles_formats_contains_vgc(self):
        assert "gen9vgc2026regi" in DOUBLES_FORMATS
        assert "gen9vgc2025regg" in DOUBLES_FORMATS

    def test_doubles_formats_contains_smogon_doubles(self):
        assert "gen9doublesou" in DOUBLES_FORMATS
        assert "gen9randomdoublesbattle" in DOUBLES_FORMATS

    def test_ppo_hyperparams_has_required_keys(self):
        required = {
            "learning_rate", "n_steps", "batch_size", "n_epochs",
            "gamma", "gae_lambda", "clip_range", "ent_coef",
            "vf_coef", "max_grad_norm", "policy_kwargs",
        }
        assert required.issubset(PPO_HYPERPARAMS.keys())

    def test_ppo_hyperparams_types(self):
        assert isinstance(PPO_HYPERPARAMS["learning_rate"], float)
        assert isinstance(PPO_HYPERPARAMS["n_steps"], int)
        assert isinstance(PPO_HYPERPARAMS["batch_size"], int)
        assert isinstance(PPO_HYPERPARAMS["policy_kwargs"], dict)

    def test_ppo_net_arch(self):
        net_arch = PPO_HYPERPARAMS["policy_kwargs"]["net_arch"]
        assert isinstance(net_arch, list)
        assert len(net_arch) >= 2


# ── SelfPlayCallback ──────────────────────────────────────────────────────────

class TestSelfPlayCallback:
    def _make_callback(self, tmp_path: Path, swap_every: int = 100):
        opponent = MagicMock()
        cb = SelfPlayCallback(
            opponent_player=opponent,
            save_dir=tmp_path,
            swap_every=swap_every,
            verbose=0,
        )
        cb.model = MagicMock()
        return cb, opponent

    def test_init_sets_attributes(self, tmp_path):
        opponent = MagicMock()
        cb = SelfPlayCallback(
            opponent_player=opponent,
            save_dir=tmp_path,
            swap_every=50_000,
            verbose=1,
        )
        assert cb.opponent_player is opponent
        assert cb.save_dir == tmp_path
        assert cb.swap_every == 50_000
        assert cb._last_swap == 0
        assert cb._swap_count == 0

    def test_on_step_returns_true(self, tmp_path):
        cb, _ = self._make_callback(tmp_path)
        cb.num_timesteps = 0
        with patch("shutil.copy"):
            result = cb._on_step()
        assert result is True

    def test_on_step_triggers_swap_when_threshold_reached(self, tmp_path):
        cb, opponent = self._make_callback(tmp_path, swap_every=100)
        cb.num_timesteps = 200  # 200 - 0 >= 100 → triggers swap

        with patch("shutil.copy"):
            cb._on_step()

        cb.model.save.assert_called_once()
        opponent.load_policy.assert_called_once()
        assert cb._swap_count == 1

    def test_on_step_no_swap_when_below_threshold(self, tmp_path):
        cb, opponent = self._make_callback(tmp_path, swap_every=1000)
        cb.num_timesteps = 50  # 50 < 1000 → no swap

        with patch("shutil.copy"):
            cb._on_step()

        cb.model.save.assert_not_called()
        assert cb._swap_count == 0

    def test_save_and_swap_increments_count(self, tmp_path):
        cb, _ = self._make_callback(tmp_path)

        with patch("shutil.copy"):
            cb._save_and_swap()
            cb._save_and_swap()

        assert cb._swap_count == 2

    def test_save_and_swap_calls_model_save(self, tmp_path):
        cb, _ = self._make_callback(tmp_path)

        with patch("shutil.copy"):
            cb._save_and_swap()

        cb.model.save.assert_called_once()
        saved_path = cb.model.save.call_args[0][0]
        assert "swap_0001.zip" in saved_path

    def test_save_and_swap_calls_opponent_load(self, tmp_path):
        cb, opponent = self._make_callback(tmp_path)
        latest_path = tmp_path / "latest.zip"

        with patch("shutil.copy"):
            cb._save_and_swap()

        opponent.load_policy.assert_called_once_with(latest_path)

    def test_save_and_swap_copies_to_latest(self, tmp_path):
        cb, _ = self._make_callback(tmp_path)

        with patch("shutil.copy") as mock_copy:
            cb._save_and_swap()

        mock_copy.assert_called_once()
        src, dst = mock_copy.call_args[0]
        assert "swap_0001.zip" in src
        assert "latest.zip" in dst

    def test_verbose_logging(self, tmp_path):
        """Verbose=1 should not raise."""
        opponent = MagicMock()
        cb = SelfPlayCallback(
            opponent_player=opponent,
            save_dir=tmp_path,
            swap_every=1,
            verbose=1,
        )
        cb.model = MagicMock()
        cb.num_timesteps = 1

        with patch("shutil.copy"):
            cb._on_step()  # should not raise even with verbose=1

    def test_last_swap_updated_after_swap(self, tmp_path):
        cb, _ = self._make_callback(tmp_path, swap_every=100)
        cb.num_timesteps = 200

        with patch("shutil.copy"):
            cb._on_step()

        assert cb._last_swap == 200

    def test_multiple_swaps_on_step(self, tmp_path):
        cb, opponent = self._make_callback(tmp_path, swap_every=100)

        for ts in [100, 200, 300]:
            cb.num_timesteps = ts
            with patch("shutil.copy"):
                cb._on_step()

        assert cb._swap_count == 3
        assert opponent.load_policy.call_count == 3
