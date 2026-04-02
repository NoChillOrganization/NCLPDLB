"""
MCTS Self-Play Loop — AccountA vs AccountB.

Architecture
------------
  MCTSPlayer      — poke-env Player that uses BattleTransformer + MCTS to choose moves.
                    Collects (obs, action, action_probs) for each turn.
  SelfPlayLoop    — runs AccountA vs AccountB continuously, pushes completed game
                    experience to a shared ReplayBuffer, updates SharedStats.

Flow per game
-------------
  1. AccountA challenges AccountB in the given format.
  2. Both players use MCTSPlayer.choose_move() — runs MCTS with the shared model.
  3. On battle end, propagate terminal reward (+1 win / -1 loss / 0 tie) to all steps.
  4. Push the game's experience to ReplayBuffer.
  5. Update SharedStats (games / wins / losses / ties).

Requirements
------------
  • Local Pokemon Showdown server running on ws://localhost:8000
    Start with: node pokemon-showdown start --no-security
  • pip install poke-env>=0.8.1 torch numpy

Usage
-----
  from src.ml.self_play import SelfPlayLoop, SharedStats
  from src.ml.trainer import ReplayBuffer
  from src.ml.transformer_model import build_default_model
  from src.ml.mcts import MCTSConfig

  stats  = SharedStats()
  buffer = ReplayBuffer()
  model  = build_default_model()
  config = MCTSConfig(n_simulations=30)

  loop = SelfPlayLoop(model=model, buffer=buffer, stats=stats, mcts_config=config)
  asyncio.run(loop.run_forever())
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

# ── Dependency guards ─────────────────────────────────────────────────────────

try:
    from poke_env.player import Player, RandomPlayer
    from poke_env.ps_client.server_configuration import LocalhostServerConfiguration
    POKE_ENV_OK = True
except ImportError:  # pragma: no cover
    POKE_ENV_OK = False
    Player = object       # type: ignore
    RandomPlayer = object # type: ignore

try:
    import torch
    TORCH_OK = True
except ImportError:  # pragma: no cover
    TORCH_OK = False
    torch = None  # type: ignore

from src.ml.battle_env import OBS_DIM, N_ACTIONS_GEN9, POKE_ENV_AVAILABLE
from src.ml.mcts import MCTSConfig, run_mcts, _build_legal_mask


# ── Shared stats ──────────────────────────────────────────────────────────────

class SharedStats:
    """
    Thread-safe counter bag shared between self-play and API state.

    The API (api.py) mirrors these values into its global STATE on each game.
    """

    def __init__(self) -> None:
        self._lock   = threading.Lock()
        self.games   = 0
        self.wins    = 0   # AccountA wins
        self.losses  = 0   # AccountB wins
        self.ties    = 0

    def record(self, winner: str) -> None:
        """Record one game result. winner: 'AccountA' | 'AccountB' | 'tie'."""
        with self._lock:
            self.games += 1
            if winner == "AccountA":
                self.wins   += 1
            elif winner == "AccountB":
                self.losses += 1
            else:
                self.ties   += 1

    @property
    def winrate(self) -> float:
        with self._lock:
            return self.wins / self.games if self.games else 0.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "games":   self.games,
                "wins":    self.wins,
                "losses":  self.losses,
                "ties":    self.ties,
                "winrate": self.winrate,
            }


# ── MCTS Player ───────────────────────────────────────────────────────────────

if POKE_ENV_OK and POKE_ENV_AVAILABLE:

    class MCTSPlayer(RandomPlayer):
        """
        poke-env Player that uses BattleTransformer + MCTS for move selection.

        Collects (obs, action, action_probs) per turn into self._turn_buffer.
        On battle end, assigns terminal reward and pushes to the shared ReplayBuffer.

        Args:
            model       : shared BattleTransformer (read-only during self-play)
            mcts_config : MCTS hyperparameters
            replay_buffer: shared ReplayBuffer to push completed games into
            stats       : SharedStats to update after each game
            name        : "AccountA" or "AccountB" — determines reward sign
            **kwargs    : forwarded to poke-env Player.__init__
        """

        def __init__(
            self,
            model: Any,
            mcts_config: MCTSConfig,
            replay_buffer: Any,   # ReplayBuffer — avoid circular import type hint
            stats: SharedStats,
            name: str = "AccountA",
            **kwargs: Any,
        ) -> None:
            super().__init__(**kwargs)
            self._model        = model
            self._mcts_config  = mcts_config
            self._replay_buffer = replay_buffer
            self._stats         = stats
            self._name          = name

            # Accumulate turns for the current game
            self._turn_obs:   list[np.ndarray]       = []
            self._turn_acts:  list[int]               = []
            self._turn_probs: list[np.ndarray | None] = []

        def choose_move(self, battle: Any) -> Any:
            """Run MCTS and return the chosen order. Record experience."""
            try:
                from src.ml.battle_env import build_observation
                obs = build_observation(battle)

                # Build legal action mask (True = illegal)
                legal_mask = _build_legal_mask(battle, N_ACTIONS_GEN9)

                action, stats = run_mcts(
                    obs,
                    self._model,
                    N_ACTIONS_GEN9,
                    config=self._mcts_config,
                    legal_mask=legal_mask,
                    deterministic=False,  # stochastic during self-play for diversity
                )

                # Convert MCTS visit-count distribution to probability array
                probs = np.zeros(N_ACTIONS_GEN9, dtype=np.float32)
                for a, p in stats["action_probs"].items():
                    probs[a] = p

                self._turn_obs.append(obs)
                self._turn_acts.append(action)
                self._turn_probs.append(probs)

                return self._action_to_move(action, battle)

            except Exception as exc:
                log.warning("[MCTSPlayer:%s] choose_move error: %s — random fallback", self._name, exc)
                return self.choose_random_move(battle)

        def _battle_finished_callback(self, battle: Any) -> None:
            """Called by poke-env when a battle ends. Push experience to buffer."""
            super()._battle_finished_callback(battle)

            if not self._turn_obs:
                return

            # Determine terminal reward from this player's perspective
            if battle.won:
                reward = 1.0
                winner = self._name
            elif battle.lost:
                reward = -1.0
                winner = "AccountB" if self._name == "AccountA" else "AccountA"
            else:
                reward = 0.0
                winner = "tie"

            # Push entire game to replay buffer
            try:
                self._replay_buffer.add_game(
                    self._turn_obs,
                    self._turn_acts,
                    self._turn_probs,
                    reward,
                )
            except Exception as exc:
                log.warning("[MCTSPlayer:%s] replay buffer push error: %s", self._name, exc)

            log.debug(
                "[MCTSPlayer:%s] game done — reward=%.1f turns=%d buffer=%d",
                self._name, reward, len(self._turn_obs), len(self._replay_buffer),
            )

            # Reset for next game
            self._turn_obs   = []
            self._turn_acts  = []
            self._turn_probs = []

        def _action_to_move(self, action_id: int, battle: Any) -> Any:
            """Convert action index to a poke-env BattleOrder."""
            try:
                from poke_env.environment.singles_env import SinglesEnv
                order = SinglesEnv.action_to_order(action_id, battle)
                if order is not None:
                    return order
            except Exception:
                pass
            return self.choose_random_move(battle)

else:  # pragma: no cover

    class MCTSPlayer:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "poke-env is not installed. Run: pip install poke-env>=0.8.1"
            )


# ── Self-play loop ────────────────────────────────────────────────────────────

class SelfPlayLoop:
    """
    Run AccountA vs AccountB games continuously using MCTS decisions.

    Each game:
      1. AccountA challenges AccountB in the configured format.
      2. Both players use MCTS to choose moves.
      3. Experience is pushed to the shared replay buffer.
      4. SharedStats are updated.

    The loop checks `api.get_state()["status"]` on each iteration so the
    FastAPI /start and /stop endpoints can pause and resume training.

    Args:
        model       : shared BattleTransformer (inference only — training happens
                      in a separate thread via PolicyTrainer)
        buffer      : shared ReplayBuffer
        stats       : SharedStats
        mcts_config : MCTS hyperparameters
        fmt         : Showdown format string (default: gen9randombattle)
        train_every : run a PolicyTrainer step after every N games (0 = disabled)
        trainer     : PolicyTrainer instance (required if train_every > 0)
    """

    def __init__(
        self,
        model: Any,
        buffer: Any,
        stats: SharedStats,
        mcts_config: MCTSConfig | None = None,
        fmt: str = "gen9randombattle",
        train_every: int = 5,
        trainer: Any = None,
    ) -> None:
        self.model       = model
        self.buffer      = buffer
        self.stats       = stats
        self.mcts_config = mcts_config or MCTSConfig()
        self.fmt         = fmt
        self.train_every = train_every
        self.trainer     = trainer
        self._games_since_train = 0

    def _make_players(self) -> tuple[Any, Any]:
        """Create fresh MCTSPlayer pair for one session."""
        if not POKE_ENV_OK or not POKE_ENV_AVAILABLE:
            raise RuntimeError(
                "poke-env is required for SelfPlayLoop. "
                "Install with: pip install poke-env>=0.8.1"
            )

        common = dict(
            model=self.model,
            mcts_config=self.mcts_config,
            replay_buffer=self.buffer,
            stats=self.stats,
            battle_format=self.fmt,
            server_configuration=LocalhostServerConfiguration,
        )
        player_a = MCTSPlayer(name="AccountA", **common)
        player_b = MCTSPlayer(name="AccountB", **common)
        import time; time.sleep(2.0)
314    return player_a, player_b
315
316    async def run_game(self) -> dict:

        wins_before   = player_a.n_won_battles
        losses_before = player_a.n_lost_battles

        await asyncio.wait_for(player_a.battle_against(player_b, n_battles=1), timeout=600.0)

        # Record outcome once here (not in each player's callback — avoids double-counting)
        if player_a.n_won_battles > wins_before:
            winner = "AccountA"
        elif player_a.n_lost_battles > losses_before:
            winner = "AccountB"
        else:
            winner = "tie"
        self.stats.record(winner)

        return self.stats.snapshot()

    async def run_forever(self, max_games: int | None = None) -> None:
        """
        Run self-play games until stopped.

        Polls api.get_state()["status"] — stops when set to "stopped".
        Respects max_games if provided (for testing).
        """
        game_count = 0

        while True:
            # Check API stop signal
            try:
                from src.ml.api import get_state
                if get_state()["status"] == "stopped":
                    log.info("[SelfPlay] Status=stopped — waiting...")
                    await asyncio.sleep(2.0)
                    continue
            except Exception:
                pass

            try:
                snapshot = await self.run_game()
                game_count += 1
                self._games_since_train += 1

                log.info(
                    "[SelfPlay] Game %d — W=%d L=%d T=%d winrate=%.1f%%",
                    snapshot["games"],
                    snapshot["wins"],
                    snapshot["losses"],
                    snapshot["ties"],
                    snapshot["winrate"] * 100,
                )

                # Sync stats back to API state
                try:
                    from src.ml.api import update_state
                    update_state(
                        games=snapshot["games"],
                        wins=snapshot["wins"],
                        losses=snapshot["losses"],
                        ties=snapshot["ties"],
                        buffer_size=len(self.buffer),
                    )
                except Exception:
                    pass

                # Periodic training
                if (
                    self.trainer is not None
                    and self.train_every > 0
                    and self._games_since_train >= self.train_every
                ):
                    self._games_since_train = 0
                    metrics = self.trainer.train_epochs(self.buffer, n_epochs=4)
                    if metrics:
                        log.info(
                            "[Train] step=%d policy=%.4f value=%.4f total=%.4f",
                            metrics.get("step", 0),
                            metrics.get("policy_loss", 0),
                            metrics.get("value_loss", 0),
                            metrics.get("total_loss", 0),
                        )
                        try:
                            from src.ml.api import update_state
                            update_state(
                                train_steps=metrics.get("step", 0),
                                last_loss=round(metrics.get("total_loss", 0), 4),
                            )
                        except Exception:
                            pass
                        self.trainer.save()

            except asyncio.CancelledError:
                log.info("[SelfPlay] Cancelled.")
                break
            except Exception as exc:
                log.error("[SelfPlay] Game error: %s", exc, exc_info=True)
                await asyncio.sleep(3.0)  # brief pause before retrying

            if max_games is not None and game_count >= max_games:
                log.info("[SelfPlay] Reached max_games=%d — stopping.", max_games)
                break


