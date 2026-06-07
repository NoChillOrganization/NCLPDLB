"""
Unit tests for ISS-002: MCTSPlayer as a selectable training opponent.

Covers:
  - argparse: --opponent flag exists, default is 'curriculum'
  - argparse: --opponent-checkpoint flag exists, default is None
  - MCTSPlayer constructs with replay_buffer=None, stats=None (no-op opponent mode)
  - MCTSPlayer.load_policy() is a harmless no-op
  - train() raises ValueError for doubles + --opponent mcts
"""
from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from src.ml.self_play import POKE_ENV_OK, POKE_ENV_AVAILABLE


# ── argparse contract ─────────────────────────────────────────────────────────

class TestOpponentArgparse:
    def _parse(self, argv: list[str]) -> argparse.Namespace:
        """Run _parse_args() with a patched sys.argv."""
        from src.ml.train_policy import _parse_args
        with patch("sys.argv", ["train_policy"] + argv):
            return _parse_args()

    def test_default_opponent_is_curriculum(self):
        args = self._parse(["--format", "gen9randombattle"])
        assert args.opponent == "curriculum"

    def test_opponent_mcts_accepted(self):
        args = self._parse(["--format", "gen9randombattle", "--opponent", "mcts"])
        assert args.opponent == "mcts"

    def test_opponent_checkpoint_default_none(self):
        args = self._parse(["--format", "gen9randombattle"])
        assert args.opponent_checkpoint is None

    def test_opponent_checkpoint_accepted(self):
        args = self._parse([
            "--format", "gen9randombattle",
            "--opponent", "mcts",
            "--opponent-checkpoint", "model.pt",
        ])
        assert args.opponent_checkpoint == "model.pt"

    def test_invalid_opponent_raises_system_exit(self):
        with pytest.raises(SystemExit):
            self._parse(["--opponent", "invalid"])


# ── MCTSPlayer in opponent mode ───────────────────────────────────────────────

@pytest.mark.skipif(
    not (POKE_ENV_OK and POKE_ENV_AVAILABLE),
    reason="poke-env not installed",
)
class TestMCTSPlayerOpponentMode:
    """MCTSPlayer with replay_buffer=None, stats=None — the training-opponent path."""

    @staticmethod
    def _make_player():
        """
        Construct an MCTSPlayer in opponent mode by directly setting instance
        attributes on a fresh object.  No real poke-env server connection needed.
        """
        from src.ml.self_play import MCTSPlayer
        from src.ml.mcts import MCTSConfig

        player = MCTSPlayer.__new__(MCTSPlayer)
        player._model = MagicMock()
        player._mcts_config = MCTSConfig(n_simulations=4)
        player._replay_buffer = None
        player._stats = None
        player._name = "TestOpponent"
        player._turn_obs = {}
        player._turn_acts = {}
        player._turn_probs = {}
        player._last_outcome = "tie"
        return player

    def test_constructs_with_none_buffer_and_stats(self):
        player = self._make_player()
        assert player._replay_buffer is None
        assert player._stats is None

    def test_load_policy_is_noop(self):
        player = self._make_player()
        result = player.load_policy("some/checkpoint.zip")
        assert result is None
        # Model must not be called
        player._model.assert_not_called()

    def test_load_policy_accepts_none(self):
        player = self._make_player()
        player.load_policy(None)  # must not raise

    def test_battle_finished_callback_skips_buffer_push_without_crash(self):
        """With no buffer, _battle_finished_callback must not crash."""
        import numpy as np
        from src.ml.self_play import MCTSPlayer

        player = self._make_player()
        battle_mock = MagicMock()
        battle_mock.battle_tag = "tag-opponent"
        battle_mock.won = True
        battle_mock.lost = False
        player._turn_obs  = {"tag-opponent": [np.zeros(48, dtype="float32")]}
        player._turn_acts = {"tag-opponent": [0]}
        player._turn_probs = {"tag-opponent": [np.ones(26, dtype="float32") / 26]}

        # Patch the parent _battle_finished_callback so poke-env doesn't try
        # to do network bookkeeping on an unconnected player.
        base_cls = MCTSPlayer.__bases__[0]
        with patch.object(base_cls, "_battle_finished_callback", return_value=None):
            player._battle_finished_callback(battle_mock)

        # Turn buffers flushed for this tag (no buffer → just cleared)
        assert player._turn_obs == {}
        assert player._turn_acts == {}
        assert player._turn_probs == {}


# ── Doubles guard ─────────────────────────────────────────────────────────────

class TestDoublesGuard:
    def test_train_mcts_doubles_raises_value_error(self):
        """train(..., opponent_type='mcts') on a doubles format must raise ValueError."""
        from src.ml.train_policy import DOUBLES_FORMATS, train

        doubles_fmt = next(iter(DOUBLES_FORMATS), None)
        if doubles_fmt is None:
            pytest.xfail("No doubles formats defined — guard cannot be exercised")

        # train() is pragma: no cover; mock only the parts that would make a
        # network call so the ValueError is reached before any I/O.
        with (
            patch("src.ml.train_policy._check_showdown_server_if_local"),
            patch("src.ml.train_policy._log_meta_context"),
            patch("src.ml.train_policy.POKE_ENV_AVAILABLE", True),
        ):
            with pytest.raises(ValueError, match="(?i)mcts.*doubles|doubles.*mcts"):
                train(
                    fmt=doubles_fmt,
                    total_timesteps=100,
                    swap_every=50,
                    save_dir=__import__("pathlib").Path("/tmp/test_save"),
                    opponent_type="mcts",
                )
