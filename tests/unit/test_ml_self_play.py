"""
Tests for src/ml/self_play.py — SharedStats and LadderLoop.

Covers:
  - SharedStats: record(), winrate, snapshot(), thread-safety
  - LadderLoop: __init__(), _make_player() error paths, run_forever() logic
"""
from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.self_play import SharedStats, LadderLoop
from src.ml.mcts import MCTSConfig


# ── SharedStats ───────────────────────────────────────────────────────────────

class TestSharedStatsInit:
    def test_initial_values_are_zero(self):
        s = SharedStats()
        assert s.games == 0
        assert s.wins == 0
        assert s.losses == 0
        assert s.ties == 0

    def test_initial_winrate_is_zero(self):
        s = SharedStats()
        assert s.winrate == 0.0


class TestSharedStatsRecord:
    def test_record_win(self):
        s = SharedStats()
        s.record("win")
        assert s.games == 1
        assert s.wins == 1
        assert s.losses == 0
        assert s.ties == 0

    def test_record_loss(self):
        s = SharedStats()
        s.record("loss")
        assert s.games == 1
        assert s.losses == 1
        assert s.wins == 0
        assert s.ties == 0

    def test_record_tie(self):
        s = SharedStats()
        s.record("tie")
        assert s.games == 1
        assert s.ties == 1
        assert s.wins == 0
        assert s.losses == 0

    def test_record_unknown_outcome_falls_into_tie_branch(self):
        s = SharedStats()
        s.record("draw")  # else branch → increments ties
        assert s.games == 1
        assert s.wins == 0
        assert s.losses == 0
        assert s.ties == 1

    def test_multiple_records_accumulate(self):
        s = SharedStats()
        s.record("win")
        s.record("win")
        s.record("loss")
        assert s.games == 3
        assert s.wins == 2
        assert s.losses == 1


class TestSharedStatsWinrate:
    def test_winrate_zero_when_no_games(self):
        s = SharedStats()
        assert s.winrate == 0.0

    def test_winrate_calculation(self):
        s = SharedStats()
        s.record("win")
        s.record("win")
        s.record("loss")
        assert s.winrate == pytest.approx(2 / 3)

    def test_winrate_one_when_all_wins(self):
        s = SharedStats()
        for _ in range(5):
            s.record("win")
        assert s.winrate == pytest.approx(1.0)

    def test_winrate_zero_when_all_losses(self):
        s = SharedStats()
        for _ in range(3):
            s.record("loss")
        assert s.winrate == 0.0


class TestSharedStatsSnapshot:
    def test_snapshot_contains_all_keys(self):
        s = SharedStats()
        snap = s.snapshot()
        assert set(snap.keys()) == {"games", "wins", "losses", "ties", "winrate"}

    def test_snapshot_reflects_current_state(self):
        s = SharedStats()
        s.record("win")
        s.record("loss")
        snap = s.snapshot()
        assert snap["games"] == 2
        assert snap["wins"] == 1
        assert snap["losses"] == 1
        assert snap["winrate"] == pytest.approx(0.5)

    def test_snapshot_is_independent_copy(self):
        s = SharedStats()
        snap = s.snapshot()
        s.record("win")
        # snapshot should not reflect the new record
        assert snap["games"] == 0


class TestSharedStatsThreadSafety:
    def test_concurrent_records_do_not_lose_counts(self):
        s = SharedStats()
        n = 100

        def record_wins():
            for _ in range(n):
                s.record("win")

        def record_losses():
            for _ in range(n):
                s.record("loss")

        t1 = threading.Thread(target=record_wins)
        t2 = threading.Thread(target=record_losses)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert s.games == 2 * n
        assert s.wins == n
        assert s.losses == n


# ── LadderLoop ────────────────────────────────────────────────────────────────

def _make_loop(**kwargs) -> LadderLoop:
    defaults = dict(
        model=MagicMock(),
        buffer=MagicMock(),
        stats=SharedStats(),
        mcts_config=MCTSConfig(),
        fmt="gen9randombattle",
        train_every=5,
        trainer=None,
        username="TestBot",
        password="secret",
    )
    defaults.update(kwargs)
    return LadderLoop(**defaults)


class TestLadderLoopInit:
    def test_attributes_set_correctly(self):
        model = MagicMock()
        buffer = MagicMock()
        stats = SharedStats()
        config = MCTSConfig(n_simulations=10)

        loop = LadderLoop(
            model=model,
            buffer=buffer,
            stats=stats,
            mcts_config=config,
            fmt="gen9ou",
            train_every=3,
            trainer=None,
            username="Bot",
            password="pw",
        )

        assert loop.model is model
        assert loop.buffer is buffer
        assert loop.stats is stats
        assert loop.mcts_config is config
        assert loop.fmt == "gen9ou"
        assert loop.train_every == 3
        assert loop.trainer is None
        assert loop.username == "Bot"
        assert loop.password == "pw"
        assert loop._player is None
        assert loop._games_since_train == 0

    def test_default_mcts_config_created_when_none(self):
        loop = LadderLoop(
            model=MagicMock(),
            buffer=MagicMock(),
            stats=SharedStats(),
            mcts_config=None,
        )
        assert isinstance(loop.mcts_config, MCTSConfig)


class TestLadderLoopMakePlayer:
    def test_raises_runtime_error_when_no_username(self):
        loop = _make_loop(username="")
        with pytest.raises(RuntimeError, match="Showdown account is required"):
            loop._make_player()

    def test_raises_runtime_error_when_poke_env_unavailable(self):
        loop = _make_loop(username="Bot")
        with patch("src.ml.self_play.POKE_ENV_OK", False), \
             patch("src.ml.self_play.POKE_ENV_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="poke-env is required"):
                loop._make_player()

    def test_returns_cached_player_on_second_call(self):
        loop = _make_loop()
        mock_player = MagicMock()
        loop._player = mock_player  # pre-set cached player
        result = loop._make_player()
        assert result is mock_player


# ── LadderLoop.run_forever ────────────────────────────────────────────────────

class TestLadderLoopRunForever:
    @pytest.mark.asyncio
    async def test_runs_one_game_and_stops_at_max_games(self):
        loop = _make_loop()
        snapshot = {"games": 1, "wins": 1, "losses": 0, "ties": 0, "winrate": 1.0}
        loop.run_game = AsyncMock(return_value=snapshot)

        # get_state is imported locally inside run_forever from src.ml.api
        with patch("src.ml.api.get_state", return_value={"status": "running"}), \
             patch("src.ml.api.update_state"):
            await loop.run_forever(max_games=1)

        loop.run_game.assert_called_once()

    @pytest.mark.asyncio
    async def test_pauses_when_status_is_stopped(self):
        """When status=stopped, the loop sleeps; when status flips to running it proceeds."""
        loop = _make_loop()
        snapshot = {"games": 1, "wins": 0, "losses": 1, "ties": 0, "winrate": 0.0}
        loop.run_game = AsyncMock(return_value=snapshot)

        call_count = 0

        def _state_sequence():
            nonlocal call_count
            call_count += 1
            # First call: stopped → sleep; subsequent: running → play
            if call_count == 1:
                return {"status": "stopped"}
            return {"status": "running"}

        with patch("src.ml.api.get_state", side_effect=_state_sequence), \
             patch("src.ml.api.update_state"), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await loop.run_forever(max_games=1)

        loop.run_game.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancelled_error_breaks_loop(self):
        loop = _make_loop()
        loop.run_game = AsyncMock(side_effect=asyncio.CancelledError)

        with patch("src.ml.api.get_state", return_value={"status": "running"}), \
             patch("src.ml.api.update_state"):
            # Should complete without propagating CancelledError
            await loop.run_forever(max_games=5)

        # run_game was called once before CancelledError broke the loop
        loop.run_game.assert_called_once()

    @pytest.mark.asyncio
    async def test_generic_exception_retries_after_sleep(self):
        loop = _make_loop()
        snapshot = {"games": 1, "wins": 1, "losses": 0, "ties": 0, "winrate": 1.0}
        # First call raises; second succeeds
        loop.run_game = AsyncMock(side_effect=[RuntimeError("network"), snapshot])

        with patch("src.ml.api.get_state", return_value={"status": "running"}), \
             patch("src.ml.api.update_state"), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await loop.run_forever(max_games=1)

        assert loop.run_game.call_count == 2

    @pytest.mark.asyncio
    async def test_triggers_training_after_train_every_games(self):
        loop = _make_loop(train_every=2)
        mock_trainer = MagicMock()
        mock_trainer.train_epochs.return_value = {"step": 1, "policy_loss": 0.1, "value_loss": 0.1, "total_loss": 0.2}
        mock_trainer.save = MagicMock()
        loop.trainer = mock_trainer

        snapshot = {"games": 1, "wins": 1, "losses": 0, "ties": 0, "winrate": 1.0}
        loop.run_game = AsyncMock(return_value=snapshot)

        with patch("src.ml.api.get_state", return_value={"status": "running"}), \
             patch("src.ml.api.update_state"):
            await loop.run_forever(max_games=2)

        mock_trainer.train_epochs.assert_called_once()
        mock_trainer.save.assert_called_once()
        assert loop._games_since_train == 0  # reset after training


# ── SelfPlayLoop alias ────────────────────────────────────────────────────────

class TestSelfPlayLoopAlias:
    def test_selfplayloop_is_alias_for_ladderloop(self):
        from src.ml.self_play import SelfPlayLoop
        assert SelfPlayLoop is LadderLoop


# ── LadderLoop._make_player (new-player path) ──────────────────────────────────

class TestMakePlayerCreatesNew:
    def test_creates_mcts_player_and_caches_it(self):
        """When _player is None and credentials present, creates MCTSPlayer."""
        loop = _make_loop(username="Bot", password="pw")

        mock_player = MagicMock()
        mock_player_cls = MagicMock(return_value=mock_player)

        with patch("src.ml.self_play.POKE_ENV_OK", True), \
             patch("src.ml.self_play.POKE_ENV_AVAILABLE", True), \
             patch("src.ml.self_play.MCTSPlayer", mock_player_cls), \
             patch("time.sleep"):
            result = loop._make_player()

        assert result is mock_player
        assert loop._player is mock_player
        mock_player_cls.assert_called_once()

    def test_second_call_returns_cached_player_without_recreating(self):
        loop = _make_loop()
        cached = MagicMock()
        loop._player = cached

        with patch("src.ml.self_play.POKE_ENV_OK", True), \
             patch("src.ml.self_play.POKE_ENV_AVAILABLE", True):
            result = loop._make_player()

        assert result is cached


# ── LadderLoop.run_game ────────────────────────────────────────────────────────

class TestRunGame:
    def _loop_with_mock_player(self, wins_delta=0, losses_delta=0):
        loop = _make_loop()
        player = MagicMock()
        player.n_won_battles = 0
        player.n_lost_battles = 0

        async def _fake_ladder(*a, **kw):
            player.n_won_battles += wins_delta
            player.n_lost_battles += losses_delta

        player.ladder = _fake_ladder
        loop._make_player = MagicMock(return_value=player)
        return loop

    @pytest.mark.asyncio
    async def test_run_game_records_win(self):
        loop = self._loop_with_mock_player(wins_delta=1)
        with patch("asyncio.wait_for", new=lambda coro, timeout: coro):
            snap = await loop.run_game()
        assert snap["wins"] == 1
        assert snap["losses"] == 0

    @pytest.mark.asyncio
    async def test_run_game_records_loss(self):
        loop = self._loop_with_mock_player(losses_delta=1)
        with patch("asyncio.wait_for", new=lambda coro, timeout: coro):
            snap = await loop.run_game()
        assert snap["losses"] == 1

    @pytest.mark.asyncio
    async def test_run_game_records_tie(self):
        loop = self._loop_with_mock_player()  # no delta → tie
        with patch("asyncio.wait_for", new=lambda coro, timeout: coro):
            snap = await loop.run_game()
        assert snap["ties"] == 1

    @pytest.mark.asyncio
    async def test_run_game_returns_snapshot_dict(self):
        loop = self._loop_with_mock_player(wins_delta=1)
        with patch("asyncio.wait_for", new=lambda coro, timeout: coro):
            snap = await loop.run_game()
        assert set(snap.keys()) == {"games", "wins", "losses", "ties", "winrate"}


# ── run_forever except: pass branches ─────────────────────────────────────────

class TestRunForeverExceptionBranches:
    @pytest.mark.asyncio
    async def test_get_state_raises_is_swallowed(self):
        """If get_state() raises, loop continues to run_game normally."""
        loop = _make_loop()
        snapshot = {"games": 1, "wins": 1, "losses": 0, "ties": 0, "winrate": 1.0}
        loop.run_game = AsyncMock(return_value=snapshot)

        with patch("src.ml.api.get_state", side_effect=RuntimeError("api down")), \
             patch("src.ml.api.update_state"):
            await loop.run_forever(max_games=1)

        loop.run_game.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_state_after_game_raises_is_swallowed(self):
        """If update_state raises after game completes, loop keeps running."""
        loop = _make_loop()
        snapshot = {"games": 1, "wins": 1, "losses": 0, "ties": 0, "winrate": 1.0}
        loop.run_game = AsyncMock(return_value=snapshot)

        call_count = 0

        def _update_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("state update failed")

        with patch("src.ml.api.get_state", return_value={"status": "running"}), \
             patch("src.ml.api.update_state", side_effect=_update_side_effect):
            await loop.run_forever(max_games=1)

        loop.run_game.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_state_after_training_raises_is_swallowed(self):
        """If update_state raises after trainer.train_epochs, loop keeps going."""
        loop = _make_loop(train_every=1)
        mock_trainer = MagicMock()
        mock_trainer.train_epochs.return_value = {
            "step": 1, "policy_loss": 0.1, "value_loss": 0.1, "total_loss": 0.2
        }
        mock_trainer.save = MagicMock()
        loop.trainer = mock_trainer

        snapshot = {"games": 1, "wins": 1, "losses": 0, "ties": 0, "winrate": 1.0}
        loop.run_game = AsyncMock(return_value=snapshot)

        update_calls = []

        def _update_side_effect(**kwargs):
            update_calls.append(kwargs)
            # Let the first call (post-game stats) succeed; raise on subsequent
            if len(update_calls) > 1:
                raise RuntimeError("train state update failed")

        with patch("src.ml.api.get_state", return_value={"status": "running"}), \
             patch("src.ml.api.update_state", side_effect=_update_side_effect):
            await loop.run_forever(max_games=1)

        mock_trainer.train_epochs.assert_called_once()


# ── MCTSPlayer ─────────────────────────────────────────────────────────────────

class TestMCTSPlayer:
    """Tests for MCTSPlayer — requires poke-env installed (POKE_ENV_OK=True)."""

    def _make_player(self, **kwargs):
        from src.ml.self_play import MCTSPlayer
        from src.ml.mcts import MCTSConfig

        defaults = dict(
            model=MagicMock(),
            mcts_config=MCTSConfig(n_simulations=4),
            replay_buffer=MagicMock(),
            stats=SharedStats(),
        )
        defaults.update(kwargs)
        # Prevent actual poke-env WebSocket connection
        with patch("poke_env.player.player.Player.__init__", return_value=None):
            p = MCTSPlayer.__new__(MCTSPlayer)
            p._model = defaults["model"]
            p._mcts_config = defaults["mcts_config"]
            p._replay_buffer = defaults["replay_buffer"]
            p._stats = defaults["stats"]
            p._name = kwargs.get("name", "AccountA")
            p._turn_obs = []
            p._turn_acts = []
            p._turn_probs = []
        return p

    def test_init_sets_all_attributes(self):
        from src.ml.self_play import MCTSPlayer
        from src.ml.mcts import MCTSConfig

        model = MagicMock()
        buf = MagicMock()
        stats = SharedStats()
        cfg = MCTSConfig(n_simulations=4)

        with patch("poke_env.player.player.Player.__init__", return_value=None):
            p = MCTSPlayer.__new__(MCTSPlayer)
            MCTSPlayer.__init__(p, model=model, mcts_config=cfg,
                                replay_buffer=buf, stats=stats, name="Bot")

        assert p._model is model
        assert p._mcts_config is cfg
        assert p._replay_buffer is buf
        assert p._stats is stats
        assert p._name == "Bot"
        assert p._turn_obs == []
        assert p._turn_acts == []
        assert p._turn_probs == []

    def test_choose_move_success_records_experience(self):
        import numpy as np
        p = self._make_player()
        battle = MagicMock()

        obs = np.zeros(10, dtype=np.float32)
        legal_mask = np.zeros(10, dtype=bool)
        mcts_stats = {"action_probs": {0: 0.8, 1: 0.2}}

        with patch("src.ml.battle_env.build_observation", return_value=obs), \
             patch("src.ml.self_play._build_legal_mask", return_value=legal_mask), \
             patch("src.ml.self_play.run_mcts", return_value=(0, mcts_stats)), \
             patch.object(p, "_action_to_move", return_value="move_order") as mock_atm:
            result = p.choose_move(battle)

        assert result == "move_order"
        assert len(p._turn_obs) == 1
        assert len(p._turn_acts) == 1
        assert p._turn_acts[0] == 0

    def test_choose_move_exception_falls_back_to_random(self):
        p = self._make_player()
        battle = MagicMock()
        p.choose_random_move = MagicMock(return_value="random_order")

        with patch("src.ml.battle_env.build_observation", side_effect=RuntimeError("obs error")):
            result = p.choose_move(battle)

        assert result == "random_order"
        assert p._turn_obs == []  # nothing was recorded

    def test_battle_finished_callback_win(self):
        p = self._make_player()
        import numpy as np
        p._turn_obs = [np.zeros(10)]
        p._turn_acts = [0]
        p._turn_probs = [None]

        battle = MagicMock()
        battle.won = True
        battle.lost = False

        with patch("poke_env.player.player.Player._battle_finished_callback", return_value=None):
            p._battle_finished_callback(battle)

        p._replay_buffer.add_game.assert_called_once()
        args = p._replay_buffer.add_game.call_args[0]
        assert args[3] == 1.0  # reward
        # Buffers cleared after game
        assert p._turn_obs == []

    def test_battle_finished_callback_loss(self):
        p = self._make_player()
        import numpy as np
        p._turn_obs = [np.zeros(10)]
        p._turn_acts = [0]
        p._turn_probs = [None]

        battle = MagicMock()
        battle.won = False
        battle.lost = True

        with patch("poke_env.player.player.Player._battle_finished_callback", return_value=None):
            p._battle_finished_callback(battle)

        args = p._replay_buffer.add_game.call_args[0]
        assert args[3] == -1.0

    def test_battle_finished_callback_tie(self):
        p = self._make_player()
        import numpy as np
        p._turn_obs = [np.zeros(10)]
        p._turn_acts = [0]
        p._turn_probs = [None]

        battle = MagicMock()
        battle.won = False
        battle.lost = False

        with patch("poke_env.player.player.Player._battle_finished_callback", return_value=None):
            p._battle_finished_callback(battle)

        args = p._replay_buffer.add_game.call_args[0]
        assert args[3] == 0.0

    def test_battle_finished_callback_empty_turns_returns_early(self):
        p = self._make_player()
        battle = MagicMock()

        with patch("poke_env.player.player.Player._battle_finished_callback", return_value=None):
            p._battle_finished_callback(battle)

        p._replay_buffer.add_game.assert_not_called()

    def test_battle_finished_callback_buffer_error_swallowed(self):
        p = self._make_player()
        import numpy as np
        p._turn_obs = [np.zeros(10)]
        p._turn_acts = [0]
        p._turn_probs = [None]
        p._replay_buffer.add_game.side_effect = RuntimeError("buffer full")

        battle = MagicMock()
        battle.won = True
        battle.lost = False

        with patch("poke_env.player.player.Player._battle_finished_callback", return_value=None):
            p._battle_finished_callback(battle)  # must not raise

    def test_action_to_move_success(self):
        p = self._make_player()
        p.choose_random_move = MagicMock(return_value="random")
        battle = MagicMock()
        mock_order = MagicMock()

        with patch("poke_env.environment.singles_env.SinglesEnv.action_to_order",
                   return_value=mock_order):
            result = p._action_to_move(0, battle)

        assert result is mock_order

    def test_action_to_move_none_falls_back_to_random(self):
        p = self._make_player()
        p.choose_random_move = MagicMock(return_value="random")
        battle = MagicMock()

        with patch("poke_env.environment.singles_env.SinglesEnv.action_to_order",
                   return_value=None):
            result = p._action_to_move(0, battle)

        assert result == "random"

    def test_action_to_move_exception_falls_back_to_random(self):
        p = self._make_player()
        p.choose_random_move = MagicMock(return_value="random")
        battle = MagicMock()

        with patch("poke_env.environment.singles_env.SinglesEnv.action_to_order",
                   side_effect=Exception("no order")):
            result = p._action_to_move(0, battle)

        assert result == "random"
