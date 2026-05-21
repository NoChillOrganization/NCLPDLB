"""
Replay Buffer and Policy Trainer for BattleTransformer.

Components
----------
  ReplayBuffer   — thread-safe circular buffer storing (obs, action, reward, done)
  PolicyTrainer  — trains BattleTransformer with:
                     policy loss : cross-entropy vs MCTS action probabilities
                     value  loss : MSE vs terminal game reward

Designed for:
  • CPU training on Windows (no CUDA required)
  • Low memory footprint (configurable buffer size)
  • Thread-safe: self-play threads push to buffer while training reads from it
  • Save / load to models/latest.pt

Usage
-----
  from src.ml.trainer import ReplayBuffer, PolicyTrainer
  from src.ml.transformer_model import build_default_model

  buffer  = ReplayBuffer(capacity=20_000)
  model   = build_default_model()
  trainer = PolicyTrainer(model)

  # In self-play loop:
  buffer.add(obs, action, reward, done, action_probs)

  # Training step:
  if len(buffer) >= 256:
      metrics = trainer.train_step(buffer, batch_size=64)
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

# ── Dependency guard ──────────────────────────────────────────────────────────

try:
    import torch
    import torch.nn as nn
    TORCH_OK = True
except ImportError:  # pragma: no cover
    TORCH_OK = False
    torch = None   # type: ignore
    nn    = None   # type: ignore

from src.ml.battle_env import OBS_DIM, N_ACTIONS_GEN9  # noqa: E402


# ── Replay Buffer ─────────────────────────────────────────────────────────────

class ReplayBuffer:
    """
    Thread-safe circular buffer for self-play experience.

    Each slot stores:
      obs         : float32 (obs_dim,)   — battle observation vector
      action      : int64               — chosen action index
      reward      : float32             — terminal reward (+1 win, -1 loss, 0 tie)
      done        : bool                — True on final step of a game
      action_probs: float32 (n_actions,) — MCTS visit-count distribution (target policy)

    Args:
        capacity  : maximum number of transitions to store (FIFO eviction)
        obs_dim   : observation vector size (default: OBS_DIM = 48)
        n_actions : action space size (default: N_ACTIONS_GEN9 = 26)
    """

    def __init__(
        self,
        capacity: int = 50_000,
        obs_dim: int = OBS_DIM,
        n_actions: int = N_ACTIONS_GEN9,
    ) -> None:
        self._capacity  = capacity
        self._obs_dim   = obs_dim
        self._n_actions = n_actions
        self._lock      = threading.Lock()

        self._obs   = np.zeros((capacity, obs_dim),   dtype=np.float32)
        self._acts  = np.zeros(capacity,               dtype=np.int64)
        self._rews  = np.zeros(capacity,               dtype=np.float32)
        self._done  = np.zeros(capacity,               dtype=bool)
        self._probs = np.zeros((capacity, n_actions),  dtype=np.float32)

        self._ptr  = 0
        self._size = 0

    # ── Write ────────────────────────────────────────────────────────────

    def add(
        self,
        obs: np.ndarray,
        action: int,
        reward: float,
        done: bool,
        action_probs: np.ndarray | None = None,
    ) -> None:
        """Push one transition into the buffer (overwrites oldest if full)."""
        with self._lock:
            self._obs[self._ptr]  = obs
            self._acts[self._ptr] = action
            self._rews[self._ptr] = reward
            self._done[self._ptr] = done

            if action_probs is not None:
                self._probs[self._ptr] = action_probs
            else:
                # Uniform fallback if no MCTS probs are provided
                self._probs[self._ptr] = 1.0 / self._n_actions

            self._ptr  = (self._ptr + 1) % self._capacity
            self._size = min(self._size + 1, self._capacity)

    def add_game(
        self,
        observations: list[np.ndarray],
        actions: list[int],
        action_probs_list: list[np.ndarray | None],
        reward: float,
    ) -> None:
        """
        Push an entire game into the buffer at once.

        The terminal `reward` is applied to every step in the game.
        `done` is True only on the last step.
        """
        n = len(observations)
        for i, (obs, act, probs) in enumerate(
            zip(observations, actions, action_probs_list)
        ):
            self.add(obs, act, reward, done=(i == n - 1), action_probs=probs)

    # ── Read ─────────────────────────────────────────────────────────────

    def sample(self, batch_size: int) -> dict[str, "torch.Tensor"]:
        """
        Sample a random batch.

        Returns a dict with keys:
          obs, actions, rewards, done, action_probs
        All values are CPU torch tensors.

        Raises ValueError if the buffer has fewer entries than batch_size.
        """
        if not TORCH_OK:  # pragma: no cover
            raise ImportError("PyTorch is required for ReplayBuffer.sample()")

        with self._lock:
            size = self._size
            if size < batch_size:
                raise ValueError(
                    f"Buffer has only {size} transitions; need {batch_size}"
                )
            indices = np.random.randint(0, size, size=batch_size)
            # Copy under lock to avoid torn reads from concurrent add() calls
            obs   = self._obs[indices].copy()
            acts  = self._acts[indices].copy()
            rews  = self._rews[indices].copy()
            done  = self._done[indices].copy()
            probs = self._probs[indices].copy()

        return {
            "obs":          torch.as_tensor(obs,   dtype=torch.float32),
            "actions":      torch.as_tensor(acts,  dtype=torch.long),
            "rewards":      torch.as_tensor(rews,  dtype=torch.float32),
            "done":         torch.as_tensor(done,  dtype=torch.bool),
            "action_probs": torch.as_tensor(probs, dtype=torch.float32),
        }

    # ── Info ─────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        with self._lock:
            return self._size

    @property
    def capacity(self) -> int:
        return self._capacity

    def is_ready(self, min_size: int) -> bool:
        """Return True once the buffer has at least `min_size` transitions."""
        return len(self) >= min_size


# ── Policy Trainer ────────────────────────────────────────────────────────────

class PolicyTrainer:
    """
    Train a BattleTransformer from replay buffer samples.

    Losses
    ------
      policy loss : cross-entropy(predicted_logits, mcts_action_probs)
                    (soft target — uses full MCTS distribution, not one-hot)
      value  loss : MSE(predicted_value, terminal_reward)

    Args:
        model      : BattleTransformer to train
        lr         : Adam learning rate (default 3e-4)
        value_coef : weight applied to value loss (default 0.5)
        save_path  : where to auto-save after each epoch (default: models/latest.pt)
    """

    DEFAULT_SAVE_PATH = Path("models/latest.pt")

    def __init__(
        self,
        model: Any,
        lr: float = 3e-4,
        value_coef: float = 0.5,
        save_path: str | Path | None = None,
    ) -> None:
        if not TORCH_OK:  # pragma: no cover
            raise ImportError("PyTorch is required for PolicyTrainer.")

        self.model       = model
        self.value_coef  = value_coef
        self.save_path   = Path(save_path) if save_path else self.DEFAULT_SAVE_PATH
        self.optimizer   = torch.optim.Adam(model.parameters(), lr=lr)
        self._step_count = 0

    # ── Single gradient step ─────────────────────────────────────────────

    def train_step(
        self,
        buffer: ReplayBuffer,
        batch_size: int = 64,
    ) -> dict[str, float]:
        """
        One gradient update.

        Returns metrics dict with keys: policy_loss, value_loss, total_loss.
        Returns empty dict if buffer is not ready yet.
        """
        if not buffer.is_ready(batch_size):
            return {}

        self.model.train()
        batch = buffer.sample(batch_size)

        # Add seq_len=1 dimension: (batch, 1, obs_dim)
        obs = batch["obs"].unsqueeze(1)

        policy_logits, value_pred = self.model(obs)
        # policy_logits: (batch, n_actions)
        # value_pred:    (batch, 1)

        # Policy loss — cross-entropy with soft MCTS targets
        log_probs = torch.log_softmax(policy_logits, dim=-1)
        policy_loss = -(batch["action_probs"] * log_probs).sum(dim=-1).mean()

        # Value loss — MSE against terminal reward
        value_loss = nn.functional.mse_loss(
            value_pred.squeeze(-1),
            batch["rewards"],
        )

        total_loss = policy_loss + self.value_coef * value_loss

        self.optimizer.zero_grad()
        total_loss.backward()
        # Gradient clipping for training stability on CPU
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
        self.optimizer.step()

        self._step_count += 1

        return {
            "policy_loss": float(policy_loss.item()),
            "value_loss":  float(value_loss.item()),
            "total_loss":  float(total_loss.item()),
            "step":        self._step_count,
        }

    # ── Multi-epoch training ─────────────────────────────────────────────

    def train_epochs(
        self,
        buffer: ReplayBuffer,
        n_epochs: int = 1,
        batch_size: int = 64,
    ) -> dict[str, float]:
        """
        Run `n_epochs` gradient steps and return averaged metrics.

        Skips silently if the buffer is not ready.
        """
        all_policy = []
        all_value  = []
        all_total  = []

        for _ in range(n_epochs):
            m = self.train_step(buffer, batch_size)
            if m:
                all_policy.append(m["policy_loss"])
                all_value.append(m["value_loss"])
                all_total.append(m["total_loss"])

        if not all_total:
            return {}

        return {
            "policy_loss": float(np.mean(all_policy)),
            "value_loss":  float(np.mean(all_value)),
            "total_loss":  float(np.mean(all_total)),
            "n_epochs":    n_epochs,
            "step":        self._step_count,
        }

    # ── Save / load ──────────────────────────────────────────────────────

    def save(self, path: str | Path | None = None) -> Path:
        """Save model weights to disk. Returns the path written."""
        from src.ml.transformer_model import save_model
        target = Path(path) if path else self.save_path
        save_model(self.model, target)
        log.info("Trainer saved model to %s (step %d)", target, self._step_count)
        return target

    def load(self, path: str | Path | None = None) -> None:
        """Load model weights from disk (in-place, keeps optimizer state)."""
        from src.ml.transformer_model import load_model
        source = Path(path) if path else self.save_path
        loaded = load_model(source)
        self.model.load_state_dict(loaded.state_dict())
        log.info("Trainer loaded model from %s", source)

    @property
    def step_count(self) -> int:
        return self._step_count
