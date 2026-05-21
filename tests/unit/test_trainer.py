"""
Tests for src/ml/trainer.py

Covers:
  ReplayBuffer  — add, add_game, sample, __len__, capacity, is_ready, circular eviction,
                  uniform fallback when action_probs=None, thread-safety
  PolicyTrainer — train_step, train_epochs, save, load, step_count property
"""
from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

try:
    import torch
    TORCH_OK = True
except ImportError:
    TORCH_OK = False

pytestmark = pytest.mark.skipif(not TORCH_OK, reason="PyTorch not installed")

from src.ml.battle_env import N_ACTIONS_GEN9, OBS_DIM  # noqa: E402
from src.ml.trainer import ReplayBuffer, PolicyTrainer  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _obs(obs_dim: int = OBS_DIM) -> np.ndarray:
    return np.random.rand(obs_dim).astype(np.float32)


def _probs(n_actions: int = N_ACTIONS_GEN9) -> np.ndarray:
    p = np.random.rand(n_actions).astype(np.float32)
    return p / p.sum()


def _tiny_model():
    from src.ml.transformer_model import BattleTransformer
    return BattleTransformer(
        obs_dim=OBS_DIM, n_actions=N_ACTIONS_GEN9,
        d_model=16, n_heads=2, n_layers=1,
    )


# ── ReplayBuffer ──────────────────────────────────────────────────────────────

class TestReplayBufferInit:
    def test_empty_on_creation(self):
        buf = ReplayBuffer(capacity=100)
        assert len(buf) == 0

    def test_capacity_property(self):
        buf = ReplayBuffer(capacity=512)
        assert buf.capacity == 512

    def test_custom_obs_dim_and_n_actions(self):
        buf = ReplayBuffer(capacity=10, obs_dim=8, n_actions=4)
        assert buf.capacity == 10
        assert len(buf) == 0

    def test_is_ready_false_when_empty(self):
        buf = ReplayBuffer(capacity=100)
        assert not buf.is_ready(1)


class TestReplayBufferAdd:
    def test_add_increments_size(self):
        buf = ReplayBuffer(capacity=100)
        buf.add(_obs(), 0, 1.0, False)
        assert len(buf) == 1

    def test_multiple_adds_accumulate(self):
        buf = ReplayBuffer(capacity=100)
        for _ in range(10):
            buf.add(_obs(), 0, 0.0, False)
        assert len(buf) == 10

    def test_size_capped_at_capacity(self):
        cap = 5
        buf = ReplayBuffer(capacity=cap)
        for _ in range(cap + 3):
            buf.add(_obs(), 0, 0.0, False)
        assert len(buf) == cap

    def test_add_with_action_probs_stored(self):
        buf = ReplayBuffer(capacity=10, obs_dim=OBS_DIM, n_actions=N_ACTIONS_GEN9)
        probs = _probs()
        buf.add(_obs(), 3, 1.0, True, action_probs=probs)
        batch = buf.sample(1)
        np.testing.assert_allclose(
            batch["action_probs"].numpy()[0], probs, atol=1e-5
        )

    def test_add_without_action_probs_uses_uniform_fallback(self):
        buf = ReplayBuffer(capacity=10, obs_dim=OBS_DIM, n_actions=N_ACTIONS_GEN9)
        buf.add(_obs(), 0, 0.0, False, action_probs=None)
        batch = buf.sample(1)
        probs = batch["action_probs"].numpy()[0]
        expected = 1.0 / N_ACTIONS_GEN9
        np.testing.assert_allclose(probs, expected, atol=1e-6)

    def test_circular_eviction_overwrites_oldest(self):
        cap = 3
        buf = ReplayBuffer(capacity=cap, obs_dim=1, n_actions=2)
        for i in range(cap + 1):
            buf.add(np.array([float(i)], dtype=np.float32), 0, 0.0, False)
        # Buffer is full, size stays at cap
        assert len(buf) == cap

    def test_done_flag_stored_correctly(self):
        buf = ReplayBuffer(capacity=10, obs_dim=OBS_DIM, n_actions=N_ACTIONS_GEN9)
        buf.add(_obs(), 0, 1.0, True)
        batch = buf.sample(1)
        assert bool(batch["done"][0].item()) is True

    def test_reward_stored_correctly(self):
        buf = ReplayBuffer(capacity=10, obs_dim=OBS_DIM, n_actions=N_ACTIONS_GEN9)
        buf.add(_obs(), 0, -1.0, True)
        batch = buf.sample(1)
        assert pytest.approx(float(batch["rewards"][0].item()), abs=1e-5) == -1.0

    def test_action_stored_correctly(self):
        buf = ReplayBuffer(capacity=10, obs_dim=OBS_DIM, n_actions=N_ACTIONS_GEN9)
        buf.add(_obs(), 7, 0.0, False)
        batch = buf.sample(1)
        assert int(batch["actions"][0].item()) == 7


class TestReplayBufferAddGame:
    def test_add_game_pushes_all_steps(self):
        buf = ReplayBuffer(capacity=100)
        obs_list = [_obs() for _ in range(5)]
        acts = [i for i in range(5)]
        probs_list = [_probs() for _ in range(5)]
        buf.add_game(obs_list, acts, probs_list, reward=1.0)
        assert len(buf) == 5

    def test_add_game_done_only_on_last_step(self):
        """done=True only for the last transition of the game."""
        buf = ReplayBuffer(capacity=100, obs_dim=OBS_DIM, n_actions=N_ACTIONS_GEN9)
        n = 4
        buf.add_game(
            [_obs() for _ in range(n)],
            list(range(n)),
            [_probs() for _ in range(n)],
            reward=1.0,
        )
        # Inspect internal buffer directly (sample is with-replacement)
        done_flags = buf._done[:n].tolist()
        assert sum(done_flags) == 1
        assert done_flags[-1] is True

    def test_add_game_applies_reward_to_all_steps(self):
        buf = ReplayBuffer(capacity=100)
        reward = -1.0
        n = 3
        buf.add_game(
            [_obs() for _ in range(n)],
            [0] * n,
            [None] * n,
            reward=reward,
        )
        batch = buf.sample(n)
        rewards = batch["rewards"].numpy()
        np.testing.assert_allclose(rewards, reward, atol=1e-5)

    def test_add_game_with_none_probs_uses_uniform(self):
        buf = ReplayBuffer(capacity=10, obs_dim=OBS_DIM, n_actions=N_ACTIONS_GEN9)
        buf.add_game([_obs()], [0], [None], reward=0.0)
        batch = buf.sample(1)
        probs = batch["action_probs"].numpy()[0]
        np.testing.assert_allclose(probs, 1.0 / N_ACTIONS_GEN9, atol=1e-6)


class TestReplayBufferSample:
    def test_sample_returns_expected_keys(self):
        buf = ReplayBuffer(capacity=100)
        for _ in range(10):
            buf.add(_obs(), 0, 0.0, False)
        batch = buf.sample(5)
        assert set(batch.keys()) == {"obs", "actions", "rewards", "done", "action_probs"}

    def test_sample_batch_size_matches(self):
        buf = ReplayBuffer(capacity=100)
        for _ in range(20):
            buf.add(_obs(), 0, 0.0, False)
        batch = buf.sample(8)
        assert batch["obs"].shape[0] == 8

    def test_sample_obs_shape(self):
        buf = ReplayBuffer(capacity=100)
        for _ in range(10):
            buf.add(_obs(), 0, 0.0, False)
        batch = buf.sample(4)
        assert batch["obs"].shape == (4, OBS_DIM)

    def test_sample_raises_when_too_few_transitions(self):
        buf = ReplayBuffer(capacity=100)
        buf.add(_obs(), 0, 0.0, False)
        with pytest.raises(ValueError, match="Buffer has only"):
            buf.sample(10)

    def test_sample_raises_on_empty_buffer(self):
        buf = ReplayBuffer(capacity=100)
        with pytest.raises(ValueError):
            buf.sample(1)

    def test_sample_tensor_dtypes(self):
        buf = ReplayBuffer(capacity=100)
        for _ in range(5):
            buf.add(_obs(), 2, 1.0, True)
        batch = buf.sample(3)
        assert batch["obs"].dtype == torch.float32
        assert batch["actions"].dtype == torch.long
        assert batch["rewards"].dtype == torch.float32
        assert batch["done"].dtype == torch.bool
        assert batch["action_probs"].dtype == torch.float32


class TestReplayBufferIsReady:
    def test_not_ready_when_below_min(self):
        buf = ReplayBuffer(capacity=100)
        for _ in range(5):
            buf.add(_obs(), 0, 0.0, False)
        assert not buf.is_ready(10)

    def test_ready_at_exact_min(self):
        buf = ReplayBuffer(capacity=100)
        for _ in range(10):
            buf.add(_obs(), 0, 0.0, False)
        assert buf.is_ready(10)

    def test_ready_above_min(self):
        buf = ReplayBuffer(capacity=100)
        for _ in range(20):
            buf.add(_obs(), 0, 0.0, False)
        assert buf.is_ready(10)


class TestReplayBufferThreadSafety:
    def test_concurrent_adds_do_not_corrupt_size(self):
        """Multiple threads adding simultaneously should not exceed capacity."""
        cap = 200
        buf = ReplayBuffer(capacity=cap)
        n_threads = 8
        adds_per_thread = 50

        def worker():
            for _ in range(adds_per_thread):
                buf.add(_obs(), 0, 0.0, False)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(buf) == cap


# ── PolicyTrainer ─────────────────────────────────────────────────────────────

@pytest.fixture
def tiny_model():
    return _tiny_model()


@pytest.fixture
def full_buffer():
    """A buffer with 128 transitions ready for sampling."""
    buf = ReplayBuffer(capacity=256)
    for _ in range(128):
        buf.add(_obs(), np.random.randint(N_ACTIONS_GEN9), float(np.random.choice([-1, 1])), False)
    return buf


@pytest.fixture
def trainer(tiny_model):
    return PolicyTrainer(tiny_model, lr=1e-3)


class TestPolicyTrainerInit:
    def test_step_count_starts_at_zero(self, trainer):
        assert trainer.step_count == 0

    def test_default_save_path(self, tiny_model):
        t = PolicyTrainer(tiny_model)
        assert t.save_path == Path("models/latest.pt")

    def test_custom_save_path(self, tiny_model, tmp_path):
        p = tmp_path / "my_model.pt"
        t = PolicyTrainer(tiny_model, save_path=p)
        assert t.save_path == p

    def test_value_coef_stored(self, tiny_model):
        t = PolicyTrainer(tiny_model, value_coef=0.25)
        assert t.value_coef == 0.25


class TestPolicyTrainerTrainStep:
    def test_returns_empty_dict_when_buffer_not_ready(self, trainer):
        buf = ReplayBuffer(capacity=100)
        result = trainer.train_step(buf, batch_size=64)
        assert result == {}

    def test_returns_metrics_when_buffer_ready(self, trainer, full_buffer):
        result = trainer.train_step(full_buffer, batch_size=32)
        assert set(result.keys()) == {"policy_loss", "value_loss", "total_loss", "step"}

    def test_losses_are_finite(self, trainer, full_buffer):
        result = trainer.train_step(full_buffer, batch_size=32)
        assert np.isfinite(result["policy_loss"])
        assert np.isfinite(result["value_loss"])
        assert np.isfinite(result["total_loss"])

    def test_step_count_increments_on_success(self, trainer, full_buffer):
        trainer.train_step(full_buffer, batch_size=32)
        assert trainer.step_count == 1

    def test_step_count_does_not_increment_when_skipped(self, trainer):
        buf = ReplayBuffer(capacity=100)
        trainer.train_step(buf, batch_size=64)
        assert trainer.step_count == 0

    def test_step_field_matches_step_count(self, trainer, full_buffer):
        result = trainer.train_step(full_buffer, batch_size=32)
        assert result["step"] == trainer.step_count

    def test_multiple_steps_accumulate_count(self, trainer, full_buffer):
        for _ in range(3):
            trainer.train_step(full_buffer, batch_size=32)
        assert trainer.step_count == 3

    def test_total_loss_equals_policy_plus_value(self, trainer, full_buffer):
        result = trainer.train_step(full_buffer, batch_size=32)
        expected = result["policy_loss"] + trainer.value_coef * result["value_loss"]
        assert pytest.approx(result["total_loss"], abs=1e-4) == expected


class TestPolicyTrainerTrainEpochs:
    def test_returns_empty_when_buffer_not_ready(self, trainer):
        buf = ReplayBuffer(capacity=100)
        result = trainer.train_epochs(buf, n_epochs=3, batch_size=64)
        assert result == {}

    def test_returns_metrics_with_n_epochs(self, trainer, full_buffer):
        result = trainer.train_epochs(full_buffer, n_epochs=3, batch_size=32)
        assert set(result.keys()) == {
            "policy_loss", "value_loss", "total_loss", "n_epochs", "step"
        }
        assert result["n_epochs"] == 3

    def test_step_count_increments_per_epoch(self, trainer, full_buffer):
        trainer.train_epochs(full_buffer, n_epochs=4, batch_size=32)
        assert trainer.step_count == 4

    def test_averaged_losses_are_finite(self, trainer, full_buffer):
        result = trainer.train_epochs(full_buffer, n_epochs=2, batch_size=32)
        assert np.isfinite(result["policy_loss"])
        assert np.isfinite(result["value_loss"])
        assert np.isfinite(result["total_loss"])

    def test_step_field_matches_final_step_count(self, trainer, full_buffer):
        result = trainer.train_epochs(full_buffer, n_epochs=2, batch_size=32)
        assert result["step"] == trainer.step_count


class TestPolicyTrainerSave:
    def test_save_calls_save_model(self, trainer, tmp_path):
        dest = tmp_path / "out.pt"
        with patch("src.ml.trainer.PolicyTrainer.save") as mock_save:
            mock_save.return_value = dest
            trainer.save(dest)
        mock_save.assert_called_once_with(dest)

    def test_save_returns_path_object(self, trainer, tmp_path):
        dest = tmp_path / "weights.pt"
        with patch("src.ml.transformer_model.save_model"):
            result = trainer.save(dest)
        assert result == dest

    def test_save_uses_default_path_when_none(self, trainer):
        with patch("src.ml.transformer_model.save_model") as mock_save:
            result = trainer.save()
        assert result == trainer.save_path
        mock_save.assert_called_once()

    def test_save_accepts_string_path(self, trainer, tmp_path):
        dest_str = str(tmp_path / "model.pt")
        with patch("src.ml.transformer_model.save_model"):
            result = trainer.save(dest_str)
        assert result == Path(dest_str)


class TestPolicyTrainerLoad:
    def test_load_updates_model_state(self, tmp_path):
        """save then load produces identical model weights.

        Uses build_default_model() so the saved config (obs_dim, n_actions,
        d_model) exactly matches what load_model reconstructs (n_layers and
        n_heads use their defaults).
        """
        from src.ml.transformer_model import build_default_model, save_model, load_model
        model = build_default_model()
        t = PolicyTrainer(model)
        dest = tmp_path / "snap.pt"
        save_model(t.model, dest)

        # Perturb model weights
        with torch.no_grad():
            for p in t.model.parameters():
                p.fill_(0.0)

        t.load(dest)

        ref = load_model(dest)
        for p_loaded, p_ref in zip(t.model.parameters(), ref.parameters()):
            assert torch.allclose(p_loaded, p_ref)

    def test_load_uses_default_path_when_none(self, trainer):
        fake_model = _tiny_model()
        with patch("src.ml.transformer_model.load_model", return_value=fake_model) as mock_load:
            trainer.load()
        mock_load.assert_called_once_with(trainer.save_path)

    def test_load_accepts_string_path(self, tmp_path):
        """Passing a str path (not Path) should not raise."""
        from src.ml.transformer_model import build_default_model, save_model
        model = build_default_model()
        t = PolicyTrainer(model)
        dest = tmp_path / "w.pt"
        save_model(t.model, dest)
        t.load(str(dest))  # should not raise
