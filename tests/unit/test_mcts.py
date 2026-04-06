"""
Unit tests for src/ml/mcts.py — MCTSConfig, MCTSNode, MCTS, run_mcts, _build_legal_mask.
"""
import math
import pytest
import numpy as np

torch = pytest.importorskip("torch")

from src.ml.mcts import (
    MCTSConfig,
    MCTSNode,
    MCTS,
    run_mcts,
    _build_legal_mask,
)
from src.ml.battle_env import N_ACTIONS_GEN9, OBS_DIM


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_mock_model(n_actions: int = N_ACTIONS_GEN9):
    """A minimal BattleTransformer stand-in for MCTS tests."""
    from unittest.mock import MagicMock
    model = MagicMock()
    model.policy_probs.return_value = torch.ones(n_actions) / n_actions
    model.forward.return_value = (
        torch.zeros(1, n_actions),
        torch.tensor([[0.5]]),
    )
    return model


def make_obs(n: int = OBS_DIM) -> np.ndarray:
    return np.zeros(n, dtype=np.float32)


# ── MCTSConfig ─────────────────────────────────────────────────────────────────

class TestMCTSConfig:

    def test_default_values(self):
        cfg = MCTSConfig()
        assert cfg.n_simulations == 30
        assert cfg.c_puct == 1.5
        assert cfg.dirichlet_eps == 0.25
        assert cfg.temperature == 1.0
        assert cfg.value_scale == 1.0

    def test_custom_values(self):
        cfg = MCTSConfig(n_simulations=10, c_puct=2.0, temperature=0.5)
        assert cfg.n_simulations == 10
        assert cfg.c_puct == 2.0
        assert cfg.temperature == 0.5


# ── MCTSNode ───────────────────────────────────────────────────────────────────

class TestMCTSNode:

    def test_default_q_value_is_zero_when_unvisited(self):
        node = MCTSNode()
        assert node.q_value == 0.0

    def test_q_value_after_visits(self):
        node = MCTSNode()
        node.visit_count = 2
        node.value_sum = 1.0
        assert node.q_value == pytest.approx(0.5)

    def test_ucb_score_unexplored_child_high(self):
        child = MCTSNode(prior=1.0)
        # parent has been visited many times; child hasn't
        score = child.ucb_score(parent_visit_count=100, c_puct=1.5)
        assert score > 10  # exploration term dominates

    def test_ucb_score_increases_with_parent_visits(self):
        child = MCTSNode(prior=0.5)
        low = child.ucb_score(1, 1.5)
        high = child.ucb_score(100, 1.5)
        assert high > low

    def test_is_leaf_when_not_expanded(self):
        node = MCTSNode()
        assert node.is_leaf()

    def test_not_leaf_when_expanded_with_children(self):
        node = MCTSNode()
        node.is_expanded = True
        node.children[0] = MCTSNode()
        assert not node.is_leaf()

    def test_is_leaf_when_expanded_but_no_children(self):
        node = MCTSNode()
        node.is_expanded = True
        assert node.is_leaf()


# ── MCTS ───────────────────────────────────────────────────────────────────────

class TestMCTS:

    def test_search_returns_root_with_children(self):
        model = make_mock_model()
        obs = make_obs()
        cfg = MCTSConfig(n_simulations=5)
        tree = MCTS(cfg)
        root = tree.search(obs, model, N_ACTIONS_GEN9)
        assert root.is_expanded
        assert len(root.children) > 0

    def test_search_root_has_visit_counts(self):
        model = make_mock_model()
        obs = make_obs()
        cfg = MCTSConfig(n_simulations=10)
        tree = MCTS(cfg)
        tree.search(obs, model, N_ACTIONS_GEN9)
        total_visits = sum(n.visit_count for n in tree.root.children.values())
        assert total_visits >= cfg.n_simulations

    def test_best_action_deterministic_returns_int(self):
        model = make_mock_model()
        obs = make_obs()
        tree = MCTS(MCTSConfig(n_simulations=5))
        tree.search(obs, model, N_ACTIONS_GEN9)
        action = tree.best_action(deterministic=True)
        assert isinstance(action, int)
        assert 0 <= action < N_ACTIONS_GEN9

    def test_best_action_stochastic_returns_valid_int(self):
        model = make_mock_model()
        obs = make_obs()
        tree = MCTS(MCTSConfig(n_simulations=10))
        tree.search(obs, model, N_ACTIONS_GEN9)
        action = tree.best_action(deterministic=False)
        assert isinstance(action, int)
        assert 0 <= action < N_ACTIONS_GEN9

    def test_best_action_no_children_returns_zero(self):
        tree = MCTS()
        assert tree.best_action() == 0

    def test_action_probs_empty_when_no_children(self):
        tree = MCTS()
        assert tree.action_probs() == {}

    def test_action_probs_sums_to_one(self):
        model = make_mock_model()
        obs = make_obs()
        tree = MCTS(MCTSConfig(n_simulations=10))
        tree.search(obs, model, N_ACTIONS_GEN9)
        probs = tree.action_probs()
        assert abs(sum(probs.values()) - 1.0) < 1e-5

    def test_action_probs_uniform_when_all_zero_visits(self):
        """action_probs falls back to uniform distribution when total visits == 0."""
        tree = MCTS()
        tree.root.is_expanded = True
        tree.root.children[0] = MCTSNode(prior=0.5)
        tree.root.children[1] = MCTSNode(prior=0.5)
        probs = tree.action_probs()
        assert abs(probs[0] - 0.5) < 1e-9
        assert abs(probs[1] - 0.5) < 1e-9

    def test_search_with_legal_mask(self):
        """Masked actions should not appear as children."""
        model = make_mock_model(n_actions=4)
        obs = make_obs()
        # Mask actions 1, 2 — only 0 and 3 are legal
        mask = torch.tensor([False, True, True, False])
        tree = MCTS(MCTSConfig(n_simulations=5))
        tree.search(obs, model, 4, legal_mask=mask)
        assert 1 not in tree.root.children
        assert 2 not in tree.root.children

    def test_dirichlet_noise_zero_eps_skips_noise(self):
        """dirichlet_eps=0 should not modify priors."""
        model = make_mock_model()
        obs = make_obs()
        cfg = MCTSConfig(n_simulations=3, dirichlet_eps=0.0)
        tree = MCTS(cfg)
        tree.search(obs, model, N_ACTIONS_GEN9)
        # Should complete without error
        assert tree.root.is_expanded


# ── run_mcts ───────────────────────────────────────────────────────────────────

class TestRunMcts:

    def test_returns_action_and_stats(self):
        model = make_mock_model()
        obs = make_obs()
        action, stats = run_mcts(obs, model, N_ACTIONS_GEN9)
        assert isinstance(action, int)
        assert 0 <= action < N_ACTIONS_GEN9
        assert "visit_counts" in stats
        assert "q_values" in stats
        assert "priors" in stats
        assert "action_probs" in stats
        assert "n_simulations" in stats
        assert stats["chosen_action"] == action

    def test_uses_default_config_when_none(self):
        model = make_mock_model()
        obs = make_obs()
        _, stats = run_mcts(obs, model, N_ACTIONS_GEN9, config=None)
        assert stats["n_simulations"] == MCTSConfig().n_simulations

    def test_custom_config_is_used(self):
        model = make_mock_model()
        obs = make_obs()
        cfg = MCTSConfig(n_simulations=3)
        _, stats = run_mcts(obs, model, N_ACTIONS_GEN9, config=cfg)
        assert stats["n_simulations"] == 3

    def test_stochastic_selection(self):
        model = make_mock_model()
        obs = make_obs()
        action, _ = run_mcts(obs, model, N_ACTIONS_GEN9, deterministic=False)
        assert 0 <= action < N_ACTIONS_GEN9


# ── _build_legal_mask ──────────────────────────────────────────────────────────

class TestBuildLegalMask:

    def test_returns_tensor_with_correct_size(self):
        """When torch is available, returns a bool tensor of shape (n_actions,)."""
        mask = _build_legal_mask(battle=None, n_actions=10)
        assert mask is not None
        assert mask.shape == (10,)
        assert mask.dtype == torch.bool
