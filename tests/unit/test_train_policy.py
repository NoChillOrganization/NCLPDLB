"""
Tests for src/ml/train_policy.py

Covers pure-logic functions only:
  - _check_showdown_server()
  - _check_showdown_server_if_local()
  - SelfPlayCallback.__init__, _on_step, _save_and_swap
  - Constants: DOUBLES_FORMATS, PPO_HYPERPARAMS
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ml.train_policy import (
    DOUBLES_FORMATS,
    PPO_HYPERPARAMS,
    CurriculumCallback,
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


# ── CurriculumCallback ────────────────────────────────────────────────────────

class TestCurriculumCallback:
    """Tests for CurriculumCallback (pure logic, no poke-env or live server)."""

    def _make_cb(
        self,
        tmp_path: Path,
        swap_every: int = 1_000,
        win_threshold: float = 0.70,
        min_episodes: int = 10,
        verbose: int = 0,
    ):
        opponent = MagicMock()
        cb = CurriculumCallback(
            opponent_player=opponent,
            save_dir=tmp_path,
            swap_every=swap_every,
            win_threshold=win_threshold,
            min_episodes=min_episodes,
            verbose=verbose,
        )
        cb.model = MagicMock()
        cb.num_timesteps = 0
        return cb, opponent

    def _push_episodes(self, cb, wins: int, total: int):
        """Simulate episode completions by injecting info dicts."""
        results = [1] * wins + [0] * (total - wins)
        for r in results:
            cb.locals = {"infos": [{"episode": {"r": r}}]}
            cb._on_step()

    # ── init ──────────────────────────────────────────────────────

    def test_init_defaults(self, tmp_path):
        cb, _ = self._make_cb(tmp_path)
        assert cb._phase == "warmup"
        assert cb._swap_count == 0
        assert cb._last_swap == 0
        assert len(cb._win_window) == 0

    def test_init_stores_params(self, tmp_path):
        opponent = MagicMock()
        cb = CurriculumCallback(
            opponent_player=opponent,
            save_dir=tmp_path,
            swap_every=500,
            win_threshold=0.80,
            min_episodes=200,
        )
        cb.model = MagicMock()
        assert cb.swap_every == 500
        assert cb.win_threshold == 0.80
        assert cb.min_episodes == 200

    # ── _on_step always returns True ──────────────────────────────

    def test_on_step_returns_true(self, tmp_path):
        cb, _ = self._make_cb(tmp_path)
        cb.locals = {"infos": []}
        assert cb._on_step() is True

    # ── warmup phase: no graduation below threshold ───────────────

    def test_no_graduation_below_win_threshold(self, tmp_path):
        """60 % wins with 70 % threshold → stays in warmup."""
        cb, opponent = self._make_cb(tmp_path, min_episodes=10, win_threshold=0.70)
        with patch("shutil.copy"):
            self._push_episodes(cb, wins=6, total=10)  # 60 %

        assert cb._phase == "warmup"
        cb.model.save.assert_not_called()
        opponent.load_policy.assert_not_called()

    def test_no_graduation_window_not_full(self, tmp_path):
        """Only 5 episodes pushed when min_episodes=10 → window not full yet."""
        cb, opponent = self._make_cb(tmp_path, min_episodes=10, win_threshold=0.50)
        with patch("shutil.copy"):
            self._push_episodes(cb, wins=5, total=5)

        assert cb._phase == "warmup"
        cb.model.save.assert_not_called()

    # ── warmup phase: graduation at threshold ─────────────────────

    def test_graduates_at_threshold(self, tmp_path):
        """70 % wins with 70 % threshold → graduates to selfplay."""
        cb, opponent = self._make_cb(tmp_path, min_episodes=10, win_threshold=0.70)
        with patch("shutil.copy"):
            self._push_episodes(cb, wins=7, total=10)  # exactly 70 %

        assert cb._phase == "selfplay"
        cb.model.save.assert_called_once()
        opponent.load_policy.assert_called_once()

    def test_graduate_sets_last_swap(self, tmp_path):
        cb, _ = self._make_cb(tmp_path, min_episodes=5, win_threshold=0.60)
        cb.num_timesteps = 999
        with patch("shutil.copy"):
            self._push_episodes(cb, wins=5, total=5)  # 100 %

        assert cb._last_swap == 999

    def test_graduate_increments_swap_count(self, tmp_path):
        cb, _ = self._make_cb(tmp_path, min_episodes=5, win_threshold=0.60)
        with patch("shutil.copy"):
            self._push_episodes(cb, wins=5, total=5)

        assert cb._swap_count == 1

    def test_graduation_is_idempotent(self, tmp_path):
        """Once in selfplay phase, further episodes don't retrigger graduation."""
        cb, opponent = self._make_cb(tmp_path, min_episodes=5, win_threshold=0.60)
        with patch("shutil.copy"):
            self._push_episodes(cb, wins=5, total=5)   # graduate
            # Now push more wins — should not call save again from _graduate
            _ = cb.model.save.call_count
            self._push_episodes(cb, wins=5, total=5)

        # swap may occur if timesteps advance, but graduation code won't run again
        assert cb._phase == "selfplay"

    # ── selfplay phase: checkpoint swaps ─────────────────────────

    def test_selfplay_swap_triggers_when_interval_reached(self, tmp_path):
        cb, opponent = self._make_cb(tmp_path, swap_every=100, min_episodes=5, win_threshold=0.60)
        cb.verbose = 1
        with patch("shutil.copy"):
            self._push_episodes(cb, wins=5, total=5)  # graduate at ts=0
            cb.num_timesteps = 100                    # advance past swap_every
            cb.locals = {"infos": []}
            cb._on_step()

        assert cb._swap_count == 2  # 1 from graduation + 1 swap
        assert opponent.load_policy.call_count == 2

    def test_selfplay_no_swap_below_interval(self, tmp_path):
        cb, opponent = self._make_cb(tmp_path, swap_every=1000, min_episodes=5, win_threshold=0.60)
        with patch("shutil.copy"):
            self._push_episodes(cb, wins=5, total=5)  # graduate
            cb.num_timesteps = 50   # well below swap_every
            cb.locals = {"infos": []}
            cb._on_step()

        assert cb._swap_count == 1  # only the graduation save

    # ── win/loss tracking ─────────────────────────────────────────

    def test_positive_reward_counted_as_win(self, tmp_path):
        cb, _ = self._make_cb(tmp_path, min_episodes=1, win_threshold=0.99)
        with patch("shutil.copy"):  # graduation may fire; avoid file I/O
            cb.locals = {"infos": [{"episode": {"r": 1.0}}]}
            cb._on_step()
        assert list(cb._win_window) == [1]

    def test_zero_reward_counted_as_loss(self, tmp_path):
        cb, _ = self._make_cb(tmp_path, min_episodes=1, win_threshold=0.99)
        cb.locals = {"infos": [{"episode": {"r": 0.0}}]}
        cb._on_step()
        assert list(cb._win_window) == [0]

    def test_negative_reward_counted_as_loss(self, tmp_path):
        cb, _ = self._make_cb(tmp_path, min_episodes=1, win_threshold=0.99)
        cb.locals = {"infos": [{"episode": {"r": -1.0}}]}
        cb._on_step()
        assert list(cb._win_window) == [0]

    def test_infos_without_episode_key_ignored(self, tmp_path):
        cb, _ = self._make_cb(tmp_path)
        cb.locals = {"infos": [{"other_key": 42}]}
        cb._on_step()
        assert len(cb._win_window) == 0

    def test_missing_infos_key_ignored(self, tmp_path):
        cb, _ = self._make_cb(tmp_path)
        cb.locals = {}
        result = cb._on_step()
        assert result is True

    # ── verbose logging doesn't raise ────────────────────────────

    def test_verbose_graduation_does_not_raise(self, tmp_path):
        cb, _ = self._make_cb(tmp_path, min_episodes=5, win_threshold=0.60, verbose=1)
        with patch("shutil.copy"):
            self._push_episodes(cb, wins=5, total=5)
        # If we got here without exception, it's fine
        assert cb._phase == "selfplay"


# ── CurriculumOpponent ────────────────────────────────────────────────────────

class TestCurriculumOpponent:
    """
    Mock-based tests — never instantiate the real CurriculumOpponent because
    MaxBasePowerPlayer requires a live Showdown connection.
    """

    def _make_mock_opponent(self, has_policy: bool = False):
        """Return a MagicMock that mimics CurriculumOpponent's interface."""
        opponent = MagicMock()
        opponent._policy = MagicMock() if has_policy else None
        opponent._is_doubles = False
        return opponent

    def test_load_policy_sets_policy(self, tmp_path):
        """load_policy() should call PPO.load and store the result."""
        fake_zip = tmp_path / "latest.zip"
        fake_zip.write_bytes(b"fake")

        with patch("src.ml.train_policy.PPO") as mock_ppo_cls:
            mock_model = MagicMock()
            mock_ppo_cls.load.return_value = mock_model

            # Build a real-ish object by importing the class then calling load_policy
            # via the method itself on a MagicMock that has the real method bound.
            import src.ml.train_policy as tp
            if not hasattr(tp, "CurriculumOpponent"):
                pytest.skip("CurriculumOpponent not accessible (POKE_ENV_OK=False)")

            # Simulate load_policy by calling it on a fresh mock instance
            instance = MagicMock()
            instance._policy = None
            # Call the actual unbound method
            tp.CurriculumOpponent.load_policy(instance, fake_zip)
            mock_ppo_cls.load.assert_called_once_with(str(fake_zip))
            assert instance._policy == mock_model

    def test_load_policy_handles_exception(self, tmp_path):
        """If PPO.load raises, _policy stays None and no exception propagates."""
        fake_zip = tmp_path / "missing.zip"

        with patch("src.ml.train_policy.PPO") as mock_ppo_cls:
            mock_ppo_cls.load.side_effect = FileNotFoundError("no file")

            import src.ml.train_policy as tp
            if not hasattr(tp, "CurriculumOpponent"):
                pytest.skip("CurriculumOpponent not accessible (POKE_ENV_OK=False)")

            instance = MagicMock()
            instance._policy = None
            tp.CurriculumOpponent.load_policy(instance, fake_zip)
            assert instance._policy is None  # stays None after failure

    def test_choose_move_delegates_to_max_base_power_when_no_policy(self):
        """With _policy=None, choose_move should delegate to MaxBasePowerPlayer."""
        import src.ml.train_policy as tp
        if not hasattr(tp, "CurriculumOpponent"):
            pytest.skip("CurriculumOpponent not accessible (POKE_ENV_OK=False)")

        battle = MagicMock()

        # Patch MaxBasePowerPlayer.choose_move at the class level so that Python's
        # super() mechanics can find it via normal MRO (avoids unbound-call TypeError).
        with patch.object(tp.MaxBasePowerPlayer, "choose_move", return_value="max_power_order"):
            # Create a minimal real subclass instance so super() works properly.
            class _TestableCurriculumOpponent(tp.CurriculumOpponent):
                def __init__(self):  # skip poke-env account/server setup
                    self._policy = None
                    self._is_doubles = False

            instance = _TestableCurriculumOpponent()
            result = instance.choose_move(battle)

        assert result == "max_power_order"

    def test_choose_move_uses_ppo_when_policy_loaded(self):
        """With _policy set, choose_move should call policy.predict."""
        import src.ml.train_policy as tp
        if not hasattr(tp, "CurriculumOpponent"):
            pytest.skip("CurriculumOpponent not accessible (POKE_ENV_OK=False)")

        import numpy as np
        mock_policy = MagicMock()
        mock_policy.predict.return_value = (np.array([3]), None)

        instance = MagicMock()
        instance._policy = mock_policy
        instance._is_doubles = False
        battle = MagicMock()

        with patch("src.ml.train_policy.build_observation") as mock_obs, \
             patch("poke_env.environment.singles_env.SinglesEnv.action_to_order",
                   return_value="ppo_order"):
            mock_obs.return_value = MagicMock(reshape=MagicMock(return_value=MagicMock()))
            _ = tp.CurriculumOpponent.choose_move(instance, battle)

        mock_policy.predict.assert_called_once()


# ── CurriculumCallback — secondary metrics ────────────────────────────────────

class TestCurriculumCallbackTypeEff:
    """Tests for mean_type_eff graduation metric and policy collapse check."""

    import numpy as _np

    def _make_cb(self, tmp_path, min_episodes=10, win_threshold=0.70,
                 mean_type_eff_threshold=1.2, min_type_eff_samples=5):
        opponent = MagicMock()
        cb = CurriculumCallback(
            opponent_player=opponent,
            save_dir=tmp_path,
            swap_every=10_000,
            win_threshold=win_threshold,
            min_episodes=min_episodes,
            mean_type_eff_threshold=mean_type_eff_threshold,
            min_type_eff_samples=min_type_eff_samples,
        )
        cb.model = MagicMock()
        cb.num_timesteps = 0
        return cb, opponent

    def _push_wins(self, cb, wins, total):
        """Push episode results without obs_tensor (type_eff window stays empty)."""
        results = [1] * wins + [0] * (total - wins)
        for r in results:
            cb.locals = {"infos": [{"episode": {"r": r}}]}
            cb._on_step()

    def _push_type_eff_obs(self, cb, n, eff_obs_val):
        """Push N steps with a move action (action=6, move slot 0) and given type_eff obs."""
        import numpy as np
        # Build obs with the eff value at MOVE_TYPE_EFF_OBS_IDXS[0] = index 6
        obs = np.zeros((1, 48), dtype=np.float32)
        obs[0, 6] = eff_obs_val   # slot 0 type_eff
        for _ in range(n):
            cb.locals = {
                "infos": [],
                "obs_tensor": obs,
                "actions": np.array([6]),   # move slot 0, no gimmick
            }
            cb._on_step()

    # ── _should_graduate ──────────────────────────────────────────

    def test_should_graduate_win_rate_only_when_eff_window_empty(self, tmp_path):
        """When type_eff window has fewer than min_type_eff_samples, only win_rate is checked."""
        cb, _ = self._make_cb(tmp_path, min_episodes=5, min_type_eff_samples=100)
        with patch("shutil.copy"):
            self._push_wins(cb, wins=5, total=5)   # 100 % wins, no obs injected
        assert cb._phase == "selfplay"

    def test_should_not_graduate_when_eff_below_threshold(self, tmp_path):
        """70 % wins but mean_type_eff below 1.2 → stays in warmup."""
        import numpy as np
        cb, _ = self._make_cb(
            tmp_path, min_episodes=10, win_threshold=0.70,
            mean_type_eff_threshold=1.2, min_type_eff_samples=5,
        )
        # neutral obs_val → raw_mult = 2^(0.0 * 2) = 1.0 < 1.2
        with patch("shutil.copy"):
            self._push_type_eff_obs(cb, n=5, eff_obs_val=0.0)
            self._push_wins(cb, wins=7, total=10)
        assert cb._phase == "warmup"

    def test_should_graduate_when_both_metrics_met(self, tmp_path):
        """70 % wins AND mean_type_eff >= 1.2 → graduates."""
        import numpy as np
        cb, _ = self._make_cb(
            tmp_path, min_episodes=10, win_threshold=0.70,
            mean_type_eff_threshold=1.2, min_type_eff_samples=5,
        )
        # obs_val=0.5 → raw_mult = 2^(0.5*2) = 2.0 ≥ 1.2
        with patch("shutil.copy"):
            self._push_type_eff_obs(cb, n=5, eff_obs_val=0.5)
            self._push_wins(cb, wins=7, total=10)
        assert cb._phase == "selfplay"

    # ── _track_step_type_eff ─────────────────────────────────────

    def test_switch_action_not_tracked(self, tmp_path):
        """Switch actions (0-5) should not append to type_eff window."""
        import numpy as np
        cb, _ = self._make_cb(tmp_path)
        obs = np.zeros((1, 48), dtype=np.float32)
        obs[0, 6] = 0.9
        cb.locals = {"infos": [], "obs_tensor": obs, "actions": np.array([3])}  # switch
        cb._on_step()
        assert len(cb._type_eff_window) == 0

    def test_move_action_appends_raw_mult(self, tmp_path):
        """Move action 6 (slot 0) with eff_obs=0.5 → raw_mult=2.0 appended."""
        import numpy as np
        cb, _ = self._make_cb(tmp_path)
        obs = np.zeros((1, 48), dtype=np.float32)
        obs[0, 6] = 0.5   # slot 0 type_eff obs value
        cb.locals = {"infos": [], "obs_tensor": obs, "actions": np.array([6])}
        cb._on_step()
        assert len(cb._type_eff_window) == 1
        assert cb._type_eff_window[0] == pytest.approx(2.0)

    def test_tera_action_uses_correct_slot(self, tmp_path):
        """Action 22 → tera slot 0 → move_slot = (22-6) % 4 = 0."""
        import numpy as np
        cb, _ = self._make_cb(tmp_path)
        obs = np.zeros((1, 48), dtype=np.float32)
        obs[0, 6] = 1.0   # slot 0 → 4x effective → raw_mult=4.0
        cb.locals = {"infos": [], "obs_tensor": obs, "actions": np.array([22])}
        cb._on_step()
        assert cb._type_eff_window[0] == pytest.approx(4.0)

    def test_missing_obs_tensor_silently_skipped(self, tmp_path):
        """No obs_tensor in locals → no crash, no data added."""
        import numpy as np
        cb, _ = self._make_cb(tmp_path)
        cb.locals = {"infos": [], "actions": np.array([6])}
        cb._on_step()
        assert len(cb._type_eff_window) == 0

    # ── _check_policy_collapse ────────────────────────────────────

    def test_policy_collapse_warning_when_concentrated(self, tmp_path, caplog):
        """Warning is emitted when one action exceeds 80 % over 1000 steps."""
        import numpy as np
        import logging
        cb, _ = self._make_cb(tmp_path)
        obs = np.zeros((1, 48), dtype=np.float32)
        with caplog.at_level(logging.WARNING, logger="src.ml.train_policy"):
            for _ in range(1000):
                cb.locals = {
                    "infos": [],
                    "obs_tensor": obs,
                    "actions": np.array([6]),   # always same action
                }
                cb._on_step()
        assert any("PolicyCollapse" in r.message for r in caplog.records)

    def test_no_collapse_warning_with_diverse_actions(self, tmp_path, caplog):
        """No warning when actions are spread across multiple indices."""
        import numpy as np
        import logging
        cb, _ = self._make_cb(tmp_path)
        obs = np.zeros((1, 48), dtype=np.float32)
        with caplog.at_level(logging.WARNING, logger="src.ml.train_policy"):
            for i in range(1000):
                action = i % 26   # uniform distribution across all actions
                cb.locals = {
                    "infos": [],
                    "obs_tensor": obs,
                    "actions": np.array([action]),
                }
                cb._on_step()
        assert not any("PolicyCollapse" in r.message for r in caplog.records)

    def test_collapse_counters_reset_after_check(self, tmp_path):
        """Action counts and total reset to 0 after each 1000-step check window."""
        import numpy as np
        cb, _ = self._make_cb(tmp_path)
        obs = np.zeros((1, 48), dtype=np.float32)
        for _ in range(1000):
            cb.locals = {"infos": [], "obs_tensor": obs, "actions": np.array([6])}
            cb._on_step()
        assert cb._action_total == 0
        assert cb._action_counts == {}
