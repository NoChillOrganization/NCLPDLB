"""
Unit tests for src/ml/trainer.py — ReplayBuffer and PolicyTrainer.
"""
import pytest
import numpy as np

torch = pytest.importorskip("torch")

from src.ml.trainer import ReplayBuffer, PolicyTrainer
from src.ml.transformer_model import build_default_model
from src.ml.battle_env import OBS_DIM, N_ACTIONS_GEN9


# ── ReplayBuffer ───────────────────────────────────────────────────────────────

class TestReplayBuffer:

    def test_initial_len_is_zero(self):
        buf = ReplayBuffer(capacity=100)
        assert len(buf) == 0

    def test_capacity_property(self):
        buf = ReplayBuffer(capacity=42)
        assert buf.capacity == 42

    def test_add_increments_len(self):
        buf = ReplayBuffer(capacity=10)
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        buf.add(obs, action=0, reward=1.0, done=False)
        assert len(buf) == 1

    def test_add_with_action_probs(self):
        buf = ReplayBuffer(capacity=10)
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        probs = np.ones(N_ACTIONS_GEN9, dtype=np.float32) / N_ACTIONS_GEN9
        buf.add(obs, action=5, reward=-1.0, done=True, action_probs=probs)
        assert len(buf) == 1

    def test_add_without_probs_uses_uniform_fallback(self):
        buf = ReplayBuffer(capacity=10)
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        buf.add(obs, action=0, reward=0.0, done=False, action_probs=None)
        assert len(buf) == 1

    def test_buffer_wraps_on_overflow(self):
        buf = ReplayBuffer(capacity=3)
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        for i in range(5):
            buf.add(obs, action=i, reward=0.0, done=False)
        assert len(buf) == 3  # capped at capacity

    def test_is_ready_false_below_min(self):
        buf = ReplayBuffer(capacity=100)
        assert not buf.is_ready(10)

    def test_is_ready_true_at_min(self):
        buf = ReplayBuffer(capacity=100)
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        for _ in range(10):
            buf.add(obs, action=0, reward=0.0, done=False)
        assert buf.is_ready(10)

    def test_sample_returns_correct_keys(self):
        buf = ReplayBuffer(capacity=100)
        obs = np.random.rand(OBS_DIM).astype(np.float32)
        for _ in range(20):
            buf.add(obs, action=0, reward=1.0, done=False)
        batch = buf.sample(8)
        assert set(batch.keys()) == {"obs", "actions", "rewards", "done", "action_probs"}

    def test_sample_returns_correct_shapes(self):
        buf = ReplayBuffer(capacity=100)
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        for _ in range(20):
            buf.add(obs, action=3, reward=0.5, done=False)
        batch = buf.sample(8)
        assert batch["obs"].shape == (8, OBS_DIM)
        assert batch["actions"].shape == (8,)
        assert batch["rewards"].shape == (8,)
        assert batch["action_probs"].shape == (8, N_ACTIONS_GEN9)

    def test_sample_raises_when_too_few_transitions(self):
        buf = ReplayBuffer(capacity=100)
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        buf.add(obs, action=0, reward=0.0, done=False)
        with pytest.raises(ValueError, match="Buffer has only"):
            buf.sample(64)

    def test_add_game_pushes_all_steps(self):
        buf = ReplayBuffer(capacity=100)
        n = 5
        observations = [np.zeros(OBS_DIM, dtype=np.float32) for _ in range(n)]
        actions = list(range(n))
        probs_list = [None] * n
        buf.add_game(observations, actions, probs_list, reward=1.0)
        assert len(buf) == n


# ── PolicyTrainer ──────────────────────────────────────────────────────────────

class TestPolicyTrainer:

    @pytest.fixture
    def small_model(self):
        return build_default_model()

    def test_init_step_count_zero(self, small_model):
        trainer = PolicyTrainer(small_model)
        assert trainer.step_count == 0

    def test_train_step_returns_empty_when_buffer_not_ready(self, small_model):
        trainer = PolicyTrainer(small_model)
        buf = ReplayBuffer(capacity=100)
        result = trainer.train_step(buf, batch_size=64)
        assert result == {}

    def test_train_step_returns_metrics_when_ready(self, small_model):
        trainer = PolicyTrainer(small_model, lr=1e-3)
        buf = ReplayBuffer(capacity=200)
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        for _ in range(100):
            buf.add(obs, action=0, reward=1.0, done=False)
        metrics = trainer.train_step(buf, batch_size=32)
        assert "policy_loss" in metrics
        assert "value_loss" in metrics
        assert "total_loss" in metrics
        assert metrics["step"] == 1

    def test_train_step_increments_step_count(self, small_model):
        trainer = PolicyTrainer(small_model)
        buf = ReplayBuffer(capacity=200)
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        for _ in range(100):
            buf.add(obs, action=0, reward=1.0, done=False)
        trainer.train_step(buf, batch_size=32)
        trainer.train_step(buf, batch_size=32)
        assert trainer.step_count == 2

    def test_train_epochs_returns_averaged_metrics(self, small_model):
        trainer = PolicyTrainer(small_model)
        buf = ReplayBuffer(capacity=200)
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        for _ in range(100):
            buf.add(obs, action=0, reward=1.0, done=False)
        metrics = trainer.train_epochs(buf, n_epochs=3, batch_size=32)
        assert "n_epochs" in metrics
        assert metrics["n_epochs"] == 3

    def test_train_epochs_empty_when_buffer_not_ready(self, small_model):
        trainer = PolicyTrainer(small_model)
        buf = ReplayBuffer(capacity=100)
        result = trainer.train_epochs(buf, n_epochs=5)
        assert result == {}

    def test_save_and_load_preserves_weights(self, small_model, tmp_path):
        trainer = PolicyTrainer(small_model, save_path=tmp_path / "model.pt")
        saved = trainer.save()
        assert saved.exists()

        trainer.load(saved)  # reload into the same model — should not raise
