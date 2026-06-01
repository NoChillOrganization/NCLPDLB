"""
Unit tests for ISS-003: PolicyTrainer.validation_loss().

Covers:
  - Returns dict with the expected keys when buffer is ready
  - All values are finite floats
  - Model parameters are NOT changed after the call (no-grad, no optimizer step)
  - Returns empty dict when buffer is too small (not ready)
  - Model is restored to training mode after the call
"""
from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
import numpy as np

from src.ml.trainer import ReplayBuffer, PolicyTrainer
from src.ml.transformer_model import build_default_model
from src.ml.battle_env import OBS_DIM, N_ACTIONS_GEN9


def _fill_buffer(buf: ReplayBuffer, n: int) -> None:
    """Push `n` synthetic transitions into the buffer."""
    rng = np.random.default_rng(42)
    for _ in range(n):
        obs = rng.random(OBS_DIM, dtype=np.float32)
        action = int(rng.integers(0, N_ACTIONS_GEN9))
        reward = float(rng.choice([-1.0, 0.0, 1.0]))
        probs = rng.random(N_ACTIONS_GEN9, dtype=np.float32)
        probs /= probs.sum()
        buf.add(obs, action, reward, done=False, action_probs=probs)


class TestValidationLoss:
    def setup_method(self):
        self.model = build_default_model()
        self.trainer = PolicyTrainer(self.model)
        self.buf = ReplayBuffer(capacity=1_000)
        _fill_buffer(self.buf, 512)  # well above default batch_size=256

    # ── Return shape ──────────────────────────────────────────────────────────

    def test_returns_dict_with_val_keys(self):
        metrics = self.trainer.validation_loss(self.buf)
        assert isinstance(metrics, dict)
        assert "val_policy_loss" in metrics
        assert "val_value_loss" in metrics
        assert "val_total_loss" in metrics

    def test_all_values_are_finite(self):
        metrics = self.trainer.validation_loss(self.buf)
        for key, val in metrics.items():
            assert torch.isfinite(torch.tensor(val)), f"{key}={val} is not finite"

    def test_all_values_are_positive(self):
        """Both CE and MSE are non-negative by definition."""
        metrics = self.trainer.validation_loss(self.buf)
        for key, val in metrics.items():
            assert val >= 0.0, f"{key}={val} should be non-negative"

    # ── No-grad guarantee ─────────────────────────────────────────────────────

    def test_model_parameters_unchanged(self):
        """
        Snapshot model weights before, call validation_loss, compare after.
        Any change would mean autograd ran an optimiser step — that's a bug.
        """
        before = {
            name: param.data.clone()
            for name, param in self.model.named_parameters()
        }
        self.trainer.validation_loss(self.buf)
        for name, param in self.model.named_parameters():
            assert torch.equal(param.data, before[name]), (
                f"Parameter '{name}' changed during validation_loss — "
                "no_grad / no optimiser step was violated"
            )

    # ── Training mode restored ────────────────────────────────────────────────

    def test_model_is_in_training_mode_after_call(self):
        """validation_loss must restore model.training=True in its finally block."""
        self.trainer.validation_loss(self.buf)
        assert self.model.training, "model.training should be True after validation_loss"

    def test_model_was_not_in_training_mode_before_but_restored_after(self):
        """Even if model was manually set to eval mode before, we restore it."""
        self.model.train(False)  # simulate caller having set eval mode
        self.trainer.validation_loss(self.buf)
        # PolicyTrainer.validation_loss always restores to train(True) in finally
        assert self.model.training

    # ── Empty buffer ──────────────────────────────────────────────────────────

    def test_empty_buffer_returns_empty_dict(self):
        empty_buf = ReplayBuffer(capacity=1_000)
        metrics = self.trainer.validation_loss(empty_buf, batch_size=256)
        assert metrics == {}

    def test_undersized_buffer_returns_empty_dict(self):
        small_buf = ReplayBuffer(capacity=1_000)
        _fill_buffer(small_buf, 10)  # far fewer than batch_size=256
        metrics = self.trainer.validation_loss(small_buf, batch_size=256)
        assert metrics == {}

    # ── Custom batch size ─────────────────────────────────────────────────────

    def test_custom_batch_size_still_returns_finite_losses(self):
        metrics = self.trainer.validation_loss(self.buf, batch_size=32)
        assert metrics
        for val in metrics.values():
            assert torch.isfinite(torch.tensor(val))
