"""
Action selection — the one place a Battle agent turns a battle into an order.

Observation -> model inference -> action id -> poke-env BattleOrder, plus the
error policy. Callers differ only in the model adapter, the deterministic flag,
singles vs doubles, and what happens on failure:

  * ``on_error="fallback"`` (live play: /spar, ShowdownBotPlayer): log an ERROR
    with the exception and return ``fallback(battle)`` (a random legal move).
  * ``on_error="raise"`` (training opponents, self-play data generation): the
    error propagates so a mapper/shape bug is not mistaken for a weak agent.

The model-inference seam is ``ModelInference``; its two adapters are
``PPOInference`` (SB3 PPO policy) and ``MCTSInference`` (BattleTransformer +
MCTS). Doubles is only supported by the PPO adapter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

import numpy as np

from src.ml.battle_env import (
    N_ACTIONS_GEN9,
    OBS_DIM,
    OBS_DIM_DOUBLES,
    build_doubles_observation,
    build_observation,
)
from src.ml.mcts import MCTSConfig, _build_legal_mask, run_mcts

try:
    from poke_env.battle import DoubleBattle
except ImportError:  # pragma: no cover
    DoubleBattle = None  # type: ignore

log = logging.getLogger(__name__)


class ActionSelectionError(RuntimeError):
    """The pipeline could not produce an order (bad mapping, wrong battle type...)."""


class ModelInference(Protocol):
    """Seam: observation (+ battle, for masking) -> (action, optional stats).

    The action is an int action id, or for doubles a 2-element array (one id per
    active Pokémon); ``action_to_order`` converts either to what poke-env needs.
    """

    supports_doubles: bool

    def infer(self, obs: np.ndarray, battle: Any) -> tuple[Any, dict | None]:
        """Return (action, MCTS stats or None) for this observation."""


class PPOInference:
    """Adapter for a stable-baselines3 PPO policy (no legal mask — PPO has none)."""

    supports_doubles = True

    def __init__(self, policy: Any, *, deterministic: bool) -> None:
        self.policy = policy
        self.deterministic = deterministic

    def infer(self, obs: np.ndarray, battle: Any) -> tuple[Any, dict | None]:
        action, _ = self.policy.predict(
            obs.reshape(1, -1), deterministic=self.deterministic
        )
        # Singles: a numpy integer; doubles: a 2-element array. Don't squash it to an
        # int: the doubles mapper indexes it and the singles mapper calls .item().
        return action[0], None


class MCTSInference:
    """Adapter for BattleTransformer + MCTS over the legal-masked singles action space."""

    supports_doubles = False

    def __init__(
        self, model: Any, config: MCTSConfig | None = None, *, deterministic: bool
    ) -> None:
        self.model = model
        self.config = config
        self.deterministic = deterministic

    def infer(self, obs: np.ndarray, battle: Any) -> tuple[Any, dict | None]:
        legal_mask = _build_legal_mask(battle, N_ACTIONS_GEN9)
        # Full action space + legal_mask so MCTS can prune illegal nodes.
        return run_mcts(
            obs,
            self.model,
            N_ACTIONS_GEN9,
            config=self.config,
            legal_mask=legal_mask,
            deterministic=self.deterministic,
        )


@dataclass
class Choice:
    """Result of one selection. action_id/stats/obs are None when a fallback ran."""

    order: Any
    obs: np.ndarray | None = None
    action_id: Any = None  # int id (MCTS, PPO singles) or 2-element array (PPO doubles)
    stats: dict | None = None


def check_obs_dim(policy: Any, *, doubles: bool = False) -> None:
    """Raise ValueError if a loaded PPO policy's obs dim isn't the env's current one."""
    expected = OBS_DIM_DOUBLES if doubles else OBS_DIM
    shape = policy.observation_space.shape
    loaded = shape[0] if shape else None
    if loaded != expected:
        raise ValueError(
            f"Model obs dim mismatch: model has {loaded}, env expects {expected}. "
            f"Retrain with the current observation space before loading."
        )


def action_to_order(action: Any, battle: Any, *, doubles: bool = False) -> Any:
    """Map an action to a poke-env BattleOrder (singles or doubles mapper).

    poke-env's mappers need numpy types: the singles one calls ``action.item()`` for
    move actions and the doubles one indexes ``action[0]`` / ``action[1]``. A plain
    ``int`` made every move action raise (AttributeError), which the old per-copy
    fallbacks swallowed as a random move.
    """
    if doubles:
        from poke_env.environment.doubles_env import DoublesEnv as env

        mapped = np.asarray(action, dtype=np.int64)
    else:
        from poke_env.environment.singles_env import SinglesEnv as env

        mapped = np.int64(action)
    order = env.action_to_order(mapped, battle)
    if order is None:
        raise ActionSelectionError(f"action {action} has no legal order")
    return order


class ActionSelector:
    """Pick an order for a battle through one ModelInference adapter."""

    def __init__(
        self,
        inference: ModelInference,
        *,
        doubles: bool = False,
        on_error: Literal["raise", "fallback"],
        label: str = "ActionSelector",
    ) -> None:
        if doubles and not inference.supports_doubles:
            raise NotImplementedError(
                f"{type(inference).__name__} does not support doubles battles"
            )
        self.inference = inference
        self.doubles = doubles
        self.on_error = on_error
        self.label = label

    def choose(
        self, battle: Any, fallback: Callable[[Any], Any] | None = None
    ) -> Choice:
        # Battle-type mismatch is a caller bug, never a "weak agent": always raise.
        is_doubles = DoubleBattle is not None and isinstance(battle, DoubleBattle)
        if is_doubles != self.doubles:
            raise ActionSelectionError(
                f"{self.label}: {'doubles' if is_doubles else 'singles'} battle given "
                f"to a {'doubles' if self.doubles else 'singles'} selector "
                f"(doubles is not supported here)"
            )
        try:
            obs = (
                build_doubles_observation(battle)
                if self.doubles
                else build_observation(battle)
            )
            action_id, stats = self.inference.infer(obs, battle)
            order = action_to_order(action_id, battle, doubles=self.doubles)
        except Exception as exc:
            if self.on_error == "raise" or fallback is None:
                raise
            log.error(
                "[%s] action selection failed: %s — falling back to random",
                self.label,
                exc,
                exc_info=True,
            )
            return Choice(order=fallback(battle))
        return Choice(order=order, obs=obs, action_id=action_id, stats=stats)
