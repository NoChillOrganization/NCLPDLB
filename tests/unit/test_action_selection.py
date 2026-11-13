"""
Unit tests for src/ml/action_selection.py — the shared Battle-agent action
selection module (model-inference seam, mapping, failure policy).

Uses fake policies/models and fake battles; no live Showdown server needed.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

pytest.importorskip("poke_env")
torch = pytest.importorskip("torch")

from poke_env.battle import DoubleBattle  # noqa: E402

from src.ml import action_selection as asel  # noqa: E402
from src.ml.action_selection import (  # noqa: E402
    ActionSelectionError,
    ActionSelector,
    MCTSInference,
    PPOInference,
    check_obs_dim,
)
from src.ml.battle_env import N_ACTIONS_GEN9, OBS_DIM, OBS_DIM_DOUBLES  # noqa: E402


class FakePolicy:
    """SB3-like policy: records the deterministic flag and obs shape it was given."""

    def __init__(self, action: int = 4) -> None:
        self.action = action
        self.calls: list[tuple[tuple, bool]] = []

    def predict(self, obs, deterministic):
        self.calls.append((obs.shape, deterministic))
        return np.array([self.action]), None


def _singles_obs(_battle):
    return np.zeros(OBS_DIM, dtype=np.float32)


def _doubles_obs(_battle):
    return np.zeros(OBS_DIM_DOUBLES, dtype=np.float32)


@pytest.fixture
def patched_env():
    """Fake observation builders and order mappers for singles and doubles."""
    from poke_env.environment.doubles_env import DoublesEnv
    from poke_env.environment.singles_env import SinglesEnv

    with (
        patch.object(asel, "build_observation", side_effect=_singles_obs),
        patch.object(asel, "build_doubles_observation", side_effect=_doubles_obs),
        patch.object(
            SinglesEnv, "action_to_order", side_effect=lambda a, b: f"singles:{a}"
        ),
        patch.object(
            DoublesEnv, "action_to_order", side_effect=lambda a, b: f"doubles:{a}"
        ),
    ):
        yield


def _ppo(policy=None, *, deterministic=True, doubles=False, on_error="raise"):
    return ActionSelector(
        PPOInference(policy or FakePolicy(), deterministic=deterministic),
        doubles=doubles,
        on_error=on_error,
        label="test",
    )


# ── PPO adapter: mapping, deterministic flag ─────────────────────────────────


class TestPPOSelection:
    @pytest.mark.parametrize("deterministic", [True, False])
    def test_deterministic_flag_is_explicit_and_forwarded(
        self, patched_env, deterministic
    ):
        policy = FakePolicy(action=4)
        choice = _ppo(policy, deterministic=deterministic).choose(MagicMock())
        assert policy.calls == [((1, OBS_DIM), deterministic)]
        assert choice.order == "singles:4"
        assert choice.action_id == 4
        assert choice.obs.shape == (OBS_DIM,)
        assert choice.stats is None

    def test_doubles_uses_doubles_observation_and_mapper(self, patched_env):
        policy = FakePolicy(action=7)
        battle = MagicMock(spec=DoubleBattle)
        choice = _ppo(policy, doubles=True).choose(battle)
        assert policy.calls == [((1, OBS_DIM_DOUBLES), True)]
        assert choice.order == "doubles:7"

    def test_deterministic_has_no_default(self):
        with pytest.raises(TypeError):
            PPOInference(FakePolicy())  # type: ignore[call-arg]


# ── MCTS adapter ─────────────────────────────────────────────────────────────


class TestMCTSSelection:
    def _model(self):
        model = MagicMock()
        model.policy_probs.return_value = torch.ones(N_ACTIONS_GEN9) / N_ACTIONS_GEN9
        model.forward.return_value = (
            torch.zeros(1, N_ACTIONS_GEN9),
            torch.tensor([[0.5]]),
        )
        return model

    def test_action_is_chosen_from_legal_masked_distribution(self, patched_env):
        mask = torch.ones(N_ACTIONS_GEN9, dtype=torch.bool)
        mask[3] = False  # only action 3 is legal
        sel = ActionSelector(
            MCTSInference(self._model(), deterministic=False),
            on_error="raise",
        )
        with patch.object(asel, "_build_legal_mask", return_value=mask):
            choice = sel.choose(MagicMock())
        assert choice.action_id == 3
        assert choice.order == "singles:3"
        assert choice.stats["action_probs"] == {3: pytest.approx(1.0)}

    def test_config_and_deterministic_forwarded_to_run_mcts(self, patched_env):
        cfg = object()
        with (
            patch.object(asel, "_build_legal_mask", return_value="mask"),
            patch.object(
                asel, "run_mcts", return_value=(2, {"action_probs": {}})
            ) as run,
        ):
            ActionSelector(
                MCTSInference("model", cfg, deterministic=True), on_error="raise"
            ).choose(MagicMock())
        _, kwargs = run.call_args
        assert kwargs == {
            "config": cfg,
            "legal_mask": "mask",
            "deterministic": True,
        }
        assert run.call_args.args[1:3] == ("model", N_ACTIONS_GEN9)


# ── Failure policy ───────────────────────────────────────────────────────────


class TestFailurePolicy:
    def test_live_fallback_logs_error_and_returns_fallback_move(
        self, patched_env, caplog
    ):
        policy = FakePolicy()
        policy.predict = MagicMock(side_effect=RuntimeError("boom"))
        fallback = MagicMock(return_value="random_legal")
        with caplog.at_level(logging.ERROR, logger="src.ml.action_selection"):
            choice = _ppo(policy, on_error="fallback").choose(MagicMock(), fallback)
        assert choice.order == "random_legal"
        assert choice.action_id is None
        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert errors and errors[0].exc_info is not None
        assert "boom" in str(errors[0].exc_info[1])

    def test_live_fallback_covers_mapper_returning_none(self, patched_env, caplog):
        from poke_env.environment.singles_env import SinglesEnv

        with (
            patch.object(SinglesEnv, "action_to_order", return_value=None),
            caplog.at_level(logging.ERROR, logger="src.ml.action_selection"),
        ):
            choice = _ppo(on_error="fallback").choose(MagicMock(), lambda b: "rand")
        assert choice.order == "rand"
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_training_raises_instead_of_falling_back(self, patched_env):
        policy = FakePolicy()
        policy.predict = MagicMock(side_effect=ValueError("shape"))
        fallback = MagicMock()
        with pytest.raises(ValueError, match="shape"):
            _ppo(policy, on_error="raise").choose(MagicMock(), fallback)
        fallback.assert_not_called()

    def test_training_raises_when_mapper_returns_none(self, patched_env):
        from poke_env.environment.singles_env import SinglesEnv

        with patch.object(SinglesEnv, "action_to_order", return_value=None):
            with pytest.raises(ActionSelectionError):
                _ppo(on_error="raise").choose(MagicMock())


# ── Doubles scope ────────────────────────────────────────────────────────────


class TestDoublesUnsupported:
    def test_mcts_adapter_rejects_doubles(self):
        with pytest.raises(NotImplementedError, match="doubles"):
            ActionSelector(
                MCTSInference("model", deterministic=True),
                doubles=True,
                on_error="raise",
            )

    @pytest.mark.parametrize("on_error", ["raise", "fallback"])
    def test_singles_selector_rejects_doubles_battle_even_when_live(
        self, patched_env, on_error
    ):
        battle = MagicMock(spec=DoubleBattle)
        fallback = MagicMock()
        with pytest.raises(ActionSelectionError, match="doubles"):
            _ppo(on_error=on_error).choose(battle, fallback)
        fallback.assert_not_called()

    def test_doubles_selector_rejects_singles_battle(self, patched_env):
        with pytest.raises(ActionSelectionError, match="singles"):
            _ppo(doubles=True).choose(MagicMock())


# ── Obs-dim guard ────────────────────────────────────────────────────────────


class TestCheckObsDim:
    @staticmethod
    def _policy(dim):
        p = MagicMock()
        p.observation_space.shape = (dim,) if dim is not None else ()
        return p

    def test_matching_singles_and_doubles_dims_pass(self):
        check_obs_dim(self._policy(OBS_DIM))
        check_obs_dim(self._policy(OBS_DIM_DOUBLES), doubles=True)

    def test_mismatch_raises_value_error(self):
        with pytest.raises(ValueError, match="obs dim mismatch"):
            check_obs_dim(self._policy(OBS_DIM - 30))
        with pytest.raises(ValueError, match="obs dim mismatch"):
            check_obs_dim(self._policy(OBS_DIM), doubles=True)

    def test_empty_shape_raises(self):
        with pytest.raises(ValueError, match="model has None"):
            check_obs_dim(self._policy(None))
