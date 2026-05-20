"""
Tests for src/ml/browser_trainer.py — pure-function coverage only.

No Playwright browser, no network, no real poke-env server required.
All imports that touch heavy dependencies are deferred to test bodies.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

try:
    from stable_baselines3 import PPO  # noqa: F401
    SB3_OK = True
except ImportError:
    SB3_OK = False

try:
    from poke_env.ps_client.account_configuration import AccountConfiguration  # noqa: F401
    POKE_ENV_OK = True
except ImportError:
    POKE_ENV_OK = False

from src.ml.battle_env import OBS_DIM


# ── TestAccountConfigsForModeBrowser ─────────────────────────────────────────

class TestAccountConfigsForModeBrowser:
    """account_configs_for_mode(MODE_BROWSER) credential routing."""

    def test_raises_without_env_vars(self):
        from src.ml.showdown_modes import account_configs_for_mode, MODE_BROWSER
        blank = {
            "SHOWDOWN_TRAIN_USER1": "",
            "SHOWDOWN_TRAIN_PASS1": "",
            "SHOWDOWN_TRAIN_USER2": "",
            "SHOWDOWN_TRAIN_PASS2": "",
        }
        with patch.dict(os.environ, blank):
            with pytest.raises(ValueError, match="SHOWDOWN_TRAIN_USER1"):
                account_configs_for_mode(MODE_BROWSER)

    def test_raises_partial_env_vars(self):
        from src.ml.showdown_modes import account_configs_for_mode, MODE_BROWSER
        partial = {
            "SHOWDOWN_TRAIN_USER1": "u1",
            "SHOWDOWN_TRAIN_PASS1": "p1",
            "SHOWDOWN_TRAIN_USER2": "",
            "SHOWDOWN_TRAIN_PASS2": "",
        }
        with patch.dict(os.environ, partial):
            with pytest.raises(ValueError):
                account_configs_for_mode(MODE_BROWSER)

    def test_error_message_contains_browser_showdown(self):
        from src.ml.showdown_modes import account_configs_for_mode, MODE_BROWSER
        blank = {
            "SHOWDOWN_TRAIN_USER1": "",
            "SHOWDOWN_TRAIN_PASS1": "",
            "SHOWDOWN_TRAIN_USER2": "",
            "SHOWDOWN_TRAIN_PASS2": "",
        }
        with patch.dict(os.environ, blank):
            with pytest.raises(ValueError, match="Browser/Showdown"):
                account_configs_for_mode(MODE_BROWSER)

    @pytest.mark.skipif(not POKE_ENV_OK, reason="poke-env not installed")
    def test_returns_account_configurations_when_all_vars_set(self):
        from src.ml.showdown_modes import account_configs_for_mode, MODE_BROWSER
        all_vars = {
            "SHOWDOWN_TRAIN_USER1": "u1",
            "SHOWDOWN_TRAIN_PASS1": "p1",
            "SHOWDOWN_TRAIN_USER2": "u2",
            "SHOWDOWN_TRAIN_PASS2": "p2",
        }
        with patch.dict(os.environ, all_vars):
            result = account_configs_for_mode(MODE_BROWSER)
        assert isinstance(result, tuple)
        assert len(result) == 2
        acc1, acc2 = result
        assert acc1 is not None
        assert acc2 is not None


# ── TestDefaultResultsDir ─────────────────────────────────────────────────────

class TestDefaultResultsDir:
    """browser_trainer and train_policy must agree on results dir."""

    def test_browser_trainer_uses_same_results_dir_as_train_policy(self):
        from pathlib import Path
        from src.ml.browser_trainer import DEFAULT_RESULTS_DIR as bt_dir
        from src.ml.train_policy import DEFAULT_RESULTS_DIR as tp_dir
        assert Path(bt_dir) == Path(tp_dir)


# ── TestBuildObservationFromDom ───────────────────────────────────────────────

class TestBuildObservationFromDom:
    """build_observation_from_dom() with mock Playwright page."""

    def _make_empty_page(self):
        page = MagicMock()
        page.locator.return_value.count.return_value = 0
        return page

    def test_returns_zero_vector_on_empty_page(self):
        from src.ml.browser_trainer import build_observation_from_dom
        page = self._make_empty_page()
        obs = build_observation_from_dom(page)
        assert obs.shape == (OBS_DIM,)
        assert np.all(obs == 0.0)

    def test_returns_float32_array(self):
        from src.ml.browser_trainer import build_observation_from_dom
        page = self._make_empty_page()
        obs = build_observation_from_dom(page)
        assert obs.dtype == np.float32

    def test_obs_dim_matches_battle_env_constant(self):
        from src.ml.browser_trainer import build_observation_from_dom
        page = self._make_empty_page()
        obs = build_observation_from_dom(page)
        assert len(obs) == OBS_DIM

    def test_does_not_raise_on_dom_exception(self):
        from src.ml.browser_trainer import build_observation_from_dom
        page = MagicMock()
        page.locator.side_effect = Exception("DOM exploded")
        obs = build_observation_from_dom(page)
        assert obs.shape == (OBS_DIM,)
        assert obs.dtype == np.float32


# ── TestReplayEnv ─────────────────────────────────────────────────────────────

class TestReplayEnv:
    """_ReplayEnv step/reset contract (no SB3 gym.Env dependency needed)."""

    def _make_obs(self):
        return np.ones(OBS_DIM, dtype=np.float32) * 0.5

    def test_step_returns_stored_transition(self):
        from src.ml.browser_trainer import _ReplayEnv
        obs_arr = self._make_obs()
        env = _ReplayEnv([(obs_arr, 1.0, True)])
        env.reset()
        obs, reward, terminated, truncated, info = env.step(0)
        np.testing.assert_array_equal(obs, obs_arr)
        assert reward == 1.0
        assert terminated is True
        assert truncated is False

    def test_step_returns_zeros_when_exhausted(self):
        from src.ml.browser_trainer import _ReplayEnv
        env = _ReplayEnv([])
        env.reset()
        obs, reward, terminated, truncated, info = env.step(0)
        assert terminated is True
        assert reward == 0.0
        assert obs.shape == (OBS_DIM,)

    def test_reset_replays_from_start(self):
        from src.ml.browser_trainer import _ReplayEnv
        obs1 = np.ones(OBS_DIM, dtype=np.float32) * 0.1
        obs2 = np.ones(OBS_DIM, dtype=np.float32) * 0.9
        env = _ReplayEnv([(obs1, 0.5, False), (obs2, 1.0, True)])
        env.reset()
        env.step(0)
        env.step(0)
        env.reset()
        obs, reward, _, _, _ = env.step(0)
        np.testing.assert_array_equal(obs, obs1)
        assert reward == 0.5

    def test_reset_returns_zero_obs(self):
        from src.ml.browser_trainer import _ReplayEnv
        env = _ReplayEnv([(self._make_obs(), 1.0, True)])
        result = env.reset()
        obs, info = result
        assert obs.shape == (OBS_DIM,)
        assert isinstance(info, dict)

    def test_has_observation_and_action_space(self):
        from src.ml.browser_trainer import _ReplayEnv
        env = _ReplayEnv([])
        assert hasattr(env, "observation_space")
        assert hasattr(env, "action_space")
