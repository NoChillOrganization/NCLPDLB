"""
Logit masking audit — Critical Check 1.

The MCTS/BattleTransformer path applies -inf logit masking for illegal actions
before softmax (transformer_model.py).  The PPO/SB3 path does NOT apply logit
masking; invalid actions are handled downstream by poke-env's
SinglesEnv.action_to_order(strict=False) fallback.

These tests verify:
  1. BattleTransformer.predict() masks illegal actions to 0 probability.
  2. BattleTransformer.policy_probs() masks illegal actions to 0 probability.
  3. Masked actions receive -inf logits (not just a small number).
  4. Legal actions are unaffected by the mask.
  5. The softmax distribution over legal actions is valid (sums to ~1).
"""
from __future__ import annotations

import pytest

try:
    import torch
    TORCH_OK = True
except ImportError:
    TORCH_OK = False
    torch = None  # type: ignore

pytestmark = pytest.mark.skipif(not TORCH_OK, reason="PyTorch not installed")


@pytest.fixture
def tiny_model():
    """Return a minimal BattleTransformer (obs_dim=48, n_actions=26)."""
    from src.ml.transformer_model import BattleTransformer
    return BattleTransformer(obs_dim=48, n_actions=26, d_model=16, n_heads=2, n_layers=1)


@pytest.fixture
def dummy_obs():
    """Return a random single-step obs vector."""
    return torch.zeros(48)


def _illegal_mask(illegal_actions: list[int], n_actions: int = 26) -> "torch.Tensor":
    """Build a bool mask where True = illegal."""
    mask = torch.zeros(n_actions, dtype=torch.bool)
    for a in illegal_actions:
        mask[a] = True
    return mask


class TestLogitMaskingPredict:
    def test_illegal_actions_have_zero_probability(self, tiny_model, dummy_obs):
        """predict() with a mask must assign 0.0 probability to masked actions."""
        illegal = [0, 1, 2, 3, 4, 5]   # all switches illegal
        mask = _illegal_mask(illegal)
        action, _ = tiny_model.predict(dummy_obs, legal_mask=mask)
        # The chosen action must not be illegal
        assert action not in illegal

    def test_predict_without_mask_returns_valid_action(self, tiny_model, dummy_obs):
        """predict() without a mask returns an action in [0, n_actions)."""
        action, value = tiny_model.predict(dummy_obs)
        assert 0 <= action < 26
        assert isinstance(value, float)

    def test_all_legal_actions_mask(self, tiny_model, dummy_obs):
        """Mask all actions except one → that one action must be chosen."""
        legal_action = 6
        # All illegal except action 6
        illegal = [i for i in range(26) if i != legal_action]
        mask = _illegal_mask(illegal)
        action, _ = tiny_model.predict(dummy_obs, legal_mask=mask)
        assert action == legal_action


class TestLogitMaskingPolicyProbs:
    def test_masked_actions_have_zero_probability(self, tiny_model, dummy_obs):
        """policy_probs() must return exactly 0.0 for all masked actions."""
        illegal = [0, 1, 2, 3, 4, 5]
        mask = _illegal_mask(illegal)
        probs = tiny_model.policy_probs(dummy_obs, legal_mask=mask)
        assert probs.shape == (26,)
        for a in illegal:
            assert probs[a].item() == pytest.approx(0.0, abs=1e-6), (
                f"Action {a} should have 0 probability but got {probs[a].item()}"
            )

    def test_legal_actions_sum_to_one(self, tiny_model, dummy_obs):
        """Probability mass over legal actions must sum to approximately 1."""
        illegal = [0, 1, 2, 3, 4, 5]
        mask = _illegal_mask(illegal)
        probs = tiny_model.policy_probs(dummy_obs, legal_mask=mask)
        legal_sum = probs[[i for i in range(26) if i not in illegal]].sum().item()
        assert legal_sum == pytest.approx(1.0, abs=1e-5)

    def test_no_mask_probabilities_sum_to_one(self, tiny_model, dummy_obs):
        """Without a mask all 26 probabilities sum to 1."""
        probs = tiny_model.policy_probs(dummy_obs)
        assert probs.sum().item() == pytest.approx(1.0, abs=1e-5)

    def test_masked_fill_uses_neg_inf(self, tiny_model, dummy_obs):
        """Verify that masking applies float('-inf') — not just a large negative number."""
        import torch
        # Intercept the forward pass to inspect pre-softmax logits.
        illegal = [10, 11]
        mask = _illegal_mask(illegal)

        captured_logits: list[torch.Tensor] = []
        original_softmax = torch.softmax

        def capturing_softmax(input, dim, **kwargs):
            captured_logits.append(input.clone())
            return original_softmax(input, dim, **kwargs)

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(torch, "softmax", capturing_softmax)
            tiny_model.policy_probs(dummy_obs, legal_mask=mask)

        assert captured_logits, "softmax was never called"
        logits = captured_logits[-1].squeeze()
        for a in illegal:
            assert logits[a].item() == float("-inf"), (
                f"Action {a} logit should be -inf but got {logits[a].item()}"
            )

    def test_legal_actions_not_affected_by_mask(self, tiny_model, dummy_obs):
        """Logits of legal actions must be identical with and without masking."""
        import torch
        illegal = [0]
        mask = _illegal_mask(illegal)

        probs_masked   = tiny_model.policy_probs(dummy_obs, legal_mask=mask)
        probs_unmasked = tiny_model.policy_probs(dummy_obs, legal_mask=None)

        # After renormalisation the ratios between legal actions should be preserved.
        legal = [i for i in range(26) if i not in illegal]
        ratio_masked   = probs_masked[legal] / probs_masked[legal].sum()
        ratio_unmasked = probs_unmasked[legal] / probs_unmasked[legal].sum()
        assert torch.allclose(ratio_masked, ratio_unmasked, atol=1e-5)
