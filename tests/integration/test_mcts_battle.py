"""
Integration test: MCTSPlayer plays one full gen9randombattle against
poke-env RandomPlayer on a LOCAL Showdown server (ws://localhost:8000).

SKIPPED automatically when no server is reachable on localhost:8000
(local Windows dev / machines without Node running). Runs for real in CI
where the workflow starts a local Showdown server before this job.

To run locally:
    # 1. Start the bundled server (write exports.port=8000 first):
    #    node F:\\NCLPDLB\\pokemon-showdown\\pokemon-showdown start --no-security
    # 2. pytest tests/integration/test_mcts_battle.py -v
"""

from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.battle_env import POKE_ENV_AVAILABLE  # noqa: E402


def _server_reachable(
    host: str = "127.0.0.1", port: int = 8000, timeout: float = 1.0
) -> bool:
    """Return True if a TCP connection to host:port succeeds within timeout seconds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


SERVER_UP = _server_reachable()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not POKE_ENV_AVAILABLE,
        reason="poke-env not installed",
    ),
    pytest.mark.skipif(
        not SERVER_UP,
        reason="No Showdown server on localhost:8000 — start it first to run this test",
    ),
]


@pytest.fixture
def replay_buffer():
    from src.ml.trainer import ReplayBuffer

    return ReplayBuffer()


@pytest.fixture
def mcts_player(replay_buffer):
    from src.ml.self_play import MCTSPlayer, SharedStats
    from src.ml.mcts import MCTSConfig
    from src.ml.transformer_model import build_default_model
    from src.ml.showdown_modes import server_config_for_mode, MODE_LOCALHOST

    player = MCTSPlayer(
        model=build_default_model(),
        mcts_config=MCTSConfig(n_simulations=8, dirichlet_eps=0.0),
        replay_buffer=replay_buffer,
        stats=SharedStats(),
        name="AccountA",
        battle_format="gen9randombattle",
        server_configuration=server_config_for_mode(MODE_LOCALHOST),
    )
    # Stash buffer on player for test assertions
    player._test_buffer = replay_buffer
    return player


@pytest.fixture
def random_opponent():
    from poke_env.player import RandomPlayer
    from src.ml.showdown_modes import server_config_for_mode, MODE_LOCALHOST

    return RandomPlayer(
        battle_format="gen9randombattle",
        server_configuration=server_config_for_mode(MODE_LOCALHOST),
    )


class TestMCTSBattleIntegration:
    async def test_mcts_completes_full_battle_vs_random(
        self, mcts_player, random_opponent
    ):
        """MCTSPlayer finishes one battle vs RandomPlayer without error.

        Verifies:
          - battle completes (n_finished_battles == 1)
          - outcome is exactly one of win/loss/tie
          - experience was recorded in the replay buffer (_battle_finished_callback ran)
        """
        await asyncio.wait_for(
            mcts_player.battle_against(random_opponent, n_battles=1),
            timeout=120.0,
        )

        # Battle completed
        assert mcts_player.n_finished_battles == 1

        # Exactly one outcome registered
        assert (
            mcts_player.n_won_battles
            + mcts_player.n_lost_battles
            + mcts_player.n_tied_battles
            == 1
        )

        # _battle_finished_callback pushed experience to the replay buffer
        assert len(mcts_player._test_buffer) > 0
