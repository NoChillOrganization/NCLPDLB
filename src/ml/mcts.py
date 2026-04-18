"""
Monte Carlo Tree Search (MCTS) — battle decision engine.

Integrates with the existing decision pipeline in showdown_player.py:
  ShowdownBotPlayer.choose_move() → MCTSPlayer.choose_move()

The transformer model (transformer_model.py) provides:
  • prior probabilities   → expansion step
  • value estimates       → backup step

Algorithm
---------
  Selection   : UCB1 score = Q(s,a) + C * P(s,a) * sqrt(N(s)) / (1 + N(s,a))
  Expansion   : unvisited child with highest model prior
  Simulation  : use transformer value head (no rollout needed)
  Backprop    : update N and W up the path

Tuned for:
  • 25–50 simulations per move (fast enough on CPU between turns)
  • No game tree reuse (stateless per turn — simplifies integration)

Usage
-----
  from src.ml.mcts import MCTSConfig, run_mcts

  config = MCTSConfig(n_simulations=30, c_puct=1.5)
  action, stats = run_mcts(obs_vector, model, n_legal_actions, config)

  # In ShowdownBotPlayer:
  #   action_id = run_mcts(obs, model, n_legal_actions, config)[0]
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

# ── Dependency guard ──────────────────────────────────────────────────────────

try:
    import torch
    TORCH_OK = True
except ImportError:  # pragma: no cover
    TORCH_OK = False
    torch = None  # type: ignore

# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class MCTSConfig:
    """Hyperparameters for the MCTS engine."""
    n_simulations: int   = 30       # simulations per decision (25–50 recommended)
    c_puct:        float = 1.5      # exploration constant (UCB coefficient)
    dirichlet_eps: float = 0.25     # fraction of Dirichlet noise added at root
    dirichlet_alpha: float = 0.3    # Dirichlet concentration (0.3 = reasonable for ~26 actions)
    temperature:   float = 1.0      # action selection temperature (1.0 = proportional)
    value_scale:   float = 1.0      # scale applied to model value estimates


# ── Node ──────────────────────────────────────────────────────────────────────

@dataclass
class MCTSNode:
    """
    One node in the MCTS tree.

    Attributes
    ----------
    prior      : prior probability P(s, a) from the policy network
    visit_count: N(s, a) — number of times this node was visited
    value_sum  : W(s, a) — sum of backed-up values
    children   : child nodes indexed by action id
    is_expanded: whether expand() has been called
    """
    prior:       float = 0.0
    visit_count: int   = 0
    value_sum:   float = 0.0
    children:    dict[int, "MCTSNode"] = field(default_factory=dict)
    is_expanded: bool  = False

    @property
    def q_value(self) -> float:
        """Mean value estimate Q(s, a) = W(s, a) / N(s, a)."""
        if self.visit_count == 0:
            return 0.0
        return self.value_sum / self.visit_count

    def ucb_score(self, parent_visit_count: int, c_puct: float) -> float:
        """
        UCB1 score used for child selection.

        score = Q(s,a) + C * P(s,a) * sqrt(N(s)) / (1 + N(s,a))
        """
        exploration = (
            c_puct
            * self.prior
            * math.sqrt(parent_visit_count)
            / (1 + self.visit_count)
        )
        return self.q_value + exploration

    def is_leaf(self) -> bool:
        return not self.is_expanded or not self.children


# ── Core search ───────────────────────────────────────────────────────────────

class MCTS:
    """
    MCTS engine for a single battle turn.

    One instance per turn. Call search() once, then best_action() to get the
    chosen action.
    """

    def __init__(self, config: MCTSConfig | None = None) -> None:
        self.config = config or MCTSConfig()
        self.root   = MCTSNode(prior=1.0)

    # ── Public API ──────────────────────────────────────────────────────

    def search(
        self,
        obs: Any,
        model: Any,
        n_actions: int,
        legal_mask: "torch.Tensor | None" = None,
    ) -> "MCTSNode":
        """
        Run `config.n_simulations` MCTS simulations from the root.

        Args:
            obs        : observation vector (numpy array or torch tensor, shape (obs_dim,))
            model      : BattleTransformer — provides priors + value
            n_actions  : total action space size
            legal_mask : optional bool tensor (n_actions,) — True = illegal

        Returns:
            The root node after search (children contain visit counts).
        """
        if not TORCH_OK:  # pragma: no cover
            raise ImportError("PyTorch is required for MCTS.")

        # Get policy priors and value from model
        priors, root_value = self._model_eval(obs, model, n_actions, legal_mask)

        # Expand root
        self._expand(self.root, priors, n_actions, legal_mask)

        # Add Dirichlet noise at root for exploration
        if self.config.dirichlet_eps > 0:
            self._add_dirichlet_noise(self.root)

        # Run simulations
        for _ in range(self.config.n_simulations):
            path = self._select(self.root)
            leaf = path[-1]

            # Expand leaf if not terminal
            if leaf.is_leaf() and not leaf.is_expanded:
                leaf_priors, leaf_value = self._model_eval(
                    obs, model, n_actions, legal_mask
                )
                self._expand(leaf, leaf_priors, n_actions, legal_mask)
                value = leaf_value
            else:
                value = leaf.q_value or 0.0

            self._backprop(path, value)

        return self.root

    def best_action(self, deterministic: bool = True) -> int:
        """
        Return the action with the most visits (deterministic) or
        sample from visit-count distribution (stochastic).

        Args:
            deterministic: if True return argmax of visits; else sample.

        Returns:
            action id (int)
        """
        if not self.root.children:
            log.warning("[MCTS] No children — returning action 0")
            return 0

        visit_counts = np.array([
            node.visit_count for node in self.root.children.values()
        ], dtype=np.float32)
        actions = list(self.root.children.keys())

        if deterministic:
            return actions[int(np.argmax(visit_counts))]

        # Stochastic: sample proportional to visit_counts^(1/T)
        t = max(self.config.temperature, 1e-6)
        counts_t = visit_counts ** (1.0 / t)
        probs = counts_t / counts_t.sum()
        return int(np.random.choice(actions, p=probs))

    def action_probs(self) -> dict[int, float]:
        """Return normalized visit-count probabilities for all children."""
        if not self.root.children:
            return {}
        total = sum(n.visit_count for n in self.root.children.values())
        if total == 0:
            return {a: 1.0 / len(self.root.children) for a in self.root.children}
        return {
            action: node.visit_count / total
            for action, node in self.root.children.items()
        }

    # ── Internal ────────────────────────────────────────────────────────

    def _model_eval(
        self,
        obs: Any,
        model: Any,
        n_actions: int,
        legal_mask: "torch.Tensor | None",
    ) -> tuple[np.ndarray, float]:
        """Run a forward pass through the model. Returns (priors, value)."""
        probs_tensor = model.policy_probs(obs, legal_mask=legal_mask)
        priors = probs_tensor.cpu().numpy()

        _, value_t = model.forward(
            torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
        )
        value = float(value_t.item()) * self.config.value_scale
        return priors, value

    def _expand(
        self,
        node: MCTSNode,
        priors: np.ndarray,
        n_actions: int,
        legal_mask: "torch.Tensor | None",
    ) -> None:
        """Create child nodes for all legal actions."""
        for action_id in range(n_actions):
            if legal_mask is not None and legal_mask[action_id].item():
                continue   # skip illegal actions
            node.children[action_id] = MCTSNode(prior=float(priors[action_id]))
        node.is_expanded = True

    def _select(self, root: MCTSNode) -> list[MCTSNode]:
        """
        Walk from root to a leaf, selecting the child with the highest UCB score
        at each step.

        Returns the path (list of nodes) from root to the selected leaf.
        """
        path = [root]
        node = root
        while node.is_expanded and node.children:
            best_score  = float("-inf")
            best_child  = None
            parent_n    = node.visit_count

            for child in node.children.values():
                score = child.ucb_score(parent_n, self.config.c_puct)
                if score > best_score:
                    best_score = score
                    best_child = child

            if best_child is None:  # pragma: no cover
                break
            path.append(best_child)
            node = best_child
        return path

    def _backprop(self, path: list[MCTSNode], value: float) -> None:
        """Propagate value backup from leaf to root."""
        for node in reversed(path):
            node.visit_count += 1
            node.value_sum   += value
            # Flip value perspective at each level (if desired)
            # For cooperative self-play we keep the same sign
            # value = -value   # uncomment for zero-sum alternating perspective

    def _add_dirichlet_noise(self, root: MCTSNode) -> None:
        """Add Dirichlet noise to root priors for exploration."""
        if not root.children:
            return
        n = len(root.children)
        noise = np.random.dirichlet([self.config.dirichlet_alpha] * n)
        eps = self.config.dirichlet_eps
        for node, eta in zip(root.children.values(), noise):
            node.prior = (1 - eps) * node.prior + eps * float(eta)


# ── Functional interface ──────────────────────────────────────────────────────

def run_mcts(
    obs: Any,
    model: Any,
    n_actions: int,
    config: MCTSConfig | None = None,
    legal_mask: Any = None,
    deterministic: bool = True,
) -> tuple[int, dict]:
    """
    Convenience function: run MCTS and return (action_id, stats).

    Args:
        obs          : observation vector (numpy / torch, shape (obs_dim,))
        model        : BattleTransformer
        n_actions    : action space size (26 for gen9)
        config       : MCTSConfig (uses defaults if None)
        legal_mask   : bool tensor (n_actions,) True = illegal
        deterministic: select best action by visit count

    Returns:
        (action_id, stats_dict)
        stats_dict has keys: visit_counts, q_values, priors, action_probs
    """
    cfg = config or MCTSConfig()
    tree = MCTS(cfg)
    tree.search(obs, model, n_actions, legal_mask=legal_mask)

    action = tree.best_action(deterministic=deterministic)

    # Build stats for logging / replay buffer
    stats = {
        "visit_counts": {
            a: n.visit_count for a, n in tree.root.children.items()
        },
        "q_values": {
            a: n.q_value for a, n in tree.root.children.items()
        },
        "priors": {
            a: n.prior for a, n in tree.root.children.items()
        },
        "action_probs": tree.action_probs(),
        "n_simulations": cfg.n_simulations,
        "chosen_action": action,
    }
    return action, stats


# ── MCTSPlayer mixin ──────────────────────────────────────────────────────────

class MCTSPlayerMixin:
    """
    Mixin that replaces choose_move() in ShowdownBotPlayer with an MCTS decision.

    Usage:
        class MCTSBotPlayer(MCTSPlayerMixin, ShowdownBotPlayer):
            pass

    The mixin picks up `self._policy` (BattleTransformer) and wraps it with MCTS.
    """

    _mcts_config: MCTSConfig = MCTSConfig()

    def choose_move(self, battle: Any) -> Any:   # pragma: no cover
        """Use MCTS + transformer model to select the best action."""
        from src.ml.battle_env import build_observation, N_ACTIONS_GEN9, POKE_ENV_AVAILABLE
        if not POKE_ENV_AVAILABLE:
            return self.choose_random_move(battle)  # type: ignore[attr-defined]

        policy = getattr(self, "_policy", None)
        if policy is None:
            log.debug("[MCTSPlayerMixin] No model — using random")
            return self.choose_random_move(battle)  # type: ignore[attr-defined]

        try:
            obs = build_observation(battle)
            # Build legal action mask
            legal = _build_legal_mask(battle, N_ACTIONS_GEN9)
            action, stats = run_mcts(
                obs, policy, N_ACTIONS_GEN9,
                config=self._mcts_config,
                legal_mask=legal,
                deterministic=True,
            )
            log.debug(
                "[MCTS] turn=%d sims=%d action=%d visits=%d",
                getattr(battle, "turn", 0),
                stats["n_simulations"],
                action,
                stats["visit_counts"].get(action, 0),
            )
            return self._action_to_move(action, battle)  # type: ignore[attr-defined]
        except Exception as exc:
            log.warning("[MCTSPlayerMixin] Error: %s — falling back to random", exc)
            return self.choose_random_move(battle)  # type: ignore[attr-defined]


def _build_legal_mask(battle: Any, n_actions: int) -> "torch.Tensor | None":
    """
    Build a boolean mask of illegal actions for the current battle state.

    Returns a tensor of shape (n_actions,) where True = illegal.
    Returns None if torch is not available.
    """
    if not TORCH_OK:  # pragma: no cover
        return None
    mask = torch.ones(n_actions, dtype=torch.bool)
    try:
        # Mark legal moves as False (= not masked out)
        from poke_env.environment.singles_env import SinglesEnv
        for act in range(n_actions):
            try:
                order = SinglesEnv.action_to_order(act, battle)
                if order is not None:
                    mask[act] = False
            except ValueError:
                pass  # action is illegal — leave as True (expected poke-env signal)
            except Exception as _exc:
                log.warning("Unexpected error checking action %d legality: %s", act, _exc)
    except Exception:  # pragma: no cover
        # If poke-env not available, allow all actions
        mask.fill_(False)
    return mask
