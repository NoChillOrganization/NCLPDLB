"""
Unit tests for src/ml/transformer_model.py — BattleTransformer, save/load helpers.
Covers the branches not hit by other test files.
"""
import pytest

torch = pytest.importorskip("torch")

from src.ml.transformer_model import (
    BattleTransformer,
    build_default_model,
    save_model,
    load_model,
)
from src.ml.battle_env import OBS_DIM, N_ACTIONS_GEN9


@pytest.fixture
def model():
    return BattleTransformer(obs_dim=OBS_DIM, n_actions=N_ACTIONS_GEN9,
                             d_model=32, n_heads=4, n_layers=1, ffn_dim=64)


class TestForwardWithMask:

    def test_forward_with_padding_mask(self, model):
        """Line 196 — forward() branch when mask is not None."""
        batch, seq = 2, 4
        obs = torch.zeros(batch, seq, OBS_DIM)
        # mask: True = padding to ignore
        mask = torch.zeros(batch, seq, dtype=torch.bool)
        mask[0, -1] = True  # pad last position in first sample

        logits, value = model(obs, mask=mask)
        assert logits.shape == (batch, N_ACTIONS_GEN9)
        assert value.shape == (batch, 1)


class TestPredict:

    def test_predict_with_1d_input(self, model):
        obs = torch.zeros(OBS_DIM)
        action, value = model.predict(obs)
        assert isinstance(action, int)
        assert 0 <= action < N_ACTIONS_GEN9
        assert isinstance(value, float)

    def test_predict_with_2d_input(self, model):
        """Lines 234-235 — dim==2 branch in predict()."""
        obs = torch.zeros(1, OBS_DIM)
        action, value = model.predict(obs)
        assert isinstance(action, int)
        assert 0 <= action < N_ACTIONS_GEN9

    def test_predict_with_3d_input(self, model):
        obs = torch.zeros(1, 1, OBS_DIM)
        action, value = model.predict(obs)
        assert isinstance(action, int)

    def test_predict_with_temperature_not_one(self, model):
        """Line 243 — temperature != 1.0 branch."""
        obs = torch.zeros(OBS_DIM)
        action_sharp, _ = model.predict(obs, temperature=0.1)
        action_soft, _ = model.predict(obs, temperature=2.0)
        # Both should return valid actions regardless of temperature
        assert 0 <= action_sharp < N_ACTIONS_GEN9
        assert 0 <= action_soft < N_ACTIONS_GEN9

    def test_predict_with_legal_mask(self, model):
        obs = torch.zeros(OBS_DIM)
        # Mask all actions except action 0
        mask = torch.ones(N_ACTIONS_GEN9, dtype=torch.bool)
        mask[0] = False  # only action 0 is legal
        action, _ = model.predict(obs, legal_mask=mask)
        assert action == 0


class TestPolicyProbs:

    def test_policy_probs_with_1d_input(self, model):
        obs = torch.zeros(OBS_DIM)
        probs = model.policy_probs(obs)
        assert probs.shape == (N_ACTIONS_GEN9,)
        assert abs(probs.sum().item() - 1.0) < 1e-5

    def test_policy_probs_with_2d_input(self, model):
        """Lines 266-267 — dim==2 branch in policy_probs()."""
        obs = torch.zeros(1, OBS_DIM)
        probs = model.policy_probs(obs)
        assert probs.shape == (N_ACTIONS_GEN9,)

    def test_policy_probs_with_legal_mask(self, model):
        """Masked actions get 0 probability."""
        obs = torch.zeros(OBS_DIM)
        mask = torch.ones(N_ACTIONS_GEN9, dtype=torch.bool)
        mask[3] = False  # only action 3 is legal
        probs = model.policy_probs(obs, legal_mask=mask)
        # All masked actions should be ~0
        masked_probs = probs.clone()
        masked_probs[3] = 0.0
        assert masked_probs.sum().item() < 1e-5


class TestNumParameters:

    def test_num_parameters_positive(self, model):
        """Line 277 — num_parameters()."""
        n = model.num_parameters()
        assert isinstance(n, int)
        assert n > 0

    def test_larger_model_has_more_params(self):
        small = BattleTransformer(d_model=32, n_layers=1)
        large = BattleTransformer(d_model=128, n_layers=4)
        assert large.num_parameters() > small.num_parameters()


class TestSaveLoad:

    def test_save_and_load_roundtrip(self, tmp_path):
        """Lines 297-308 save_model, lines 322-333 load_model.
        Uses default architecture — save_model only persists obs_dim/n_actions/d_model.
        """
        m = BattleTransformer()  # all defaults
        path = tmp_path / "model.pt"
        save_model(m, path)
        assert path.exists()

        loaded = load_model(str(path))
        assert isinstance(loaded, BattleTransformer)

        # Weights should match
        for p1, p2 in zip(m.parameters(), loaded.parameters()):
            assert torch.allclose(p1, p2)

    def test_load_nonexistent_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_model(tmp_path / "does_not_exist.pt")

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "subdir" / "nested" / "model.pt"
        model = BattleTransformer(d_model=32, n_layers=1)
        save_model(model, path)
        assert path.exists()


class TestBuildDefaultModel:

    def test_build_default_model_returns_battle_transformer(self):
        """Line 338 — build_default_model()."""
        m = build_default_model()
        assert isinstance(m, BattleTransformer)
        assert m.obs_dim == OBS_DIM
        assert m.n_actions == N_ACTIONS_GEN9
