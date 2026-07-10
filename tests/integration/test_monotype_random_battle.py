"""
Integration test: two poke-env RandomPlayers play one full
gen9monotyperandombattle on a LOCAL Showdown server (ws://localhost:8000).

This format has ``bestOfDefault: true`` on the server (unlike gen9randombattle),
so this test doubles as a guard that a single battle still completes without the
env stalling on a best-of-3 series. If the server forces Bo3 and poke-env can't
handle it, this test hangs and hits the timeout — the signal to add a
TRAINING_FORMAT_ALIASES remap in train_policy.py.

SKIPPED automatically when no server is reachable on localhost:8000
(local dev without Node running). Runs for real in CI where the workflow starts a
local Showdown server before this job.

To run locally:
    # 1. Start the bundled server (write exports.port=8000 first):
    #    node F:\\NCLPDLB\\pokemon-showdown\\pokemon-showdown start --no-security
    # 2. pytest tests/integration/test_monotype_random_battle.py -v
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

FORMAT = "gen9monotyperandombattle"


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


def _random_player(name: str):
    from poke_env.player import RandomPlayer
    from src.ml.showdown_modes import server_config_for_mode, MODE_LOCALHOST

    return RandomPlayer(
        battle_format=FORMAT,
        server_configuration=server_config_for_mode(MODE_LOCALHOST),
    )


class TestMonotypeRandomBattleIntegration:
    async def test_single_battle_completes(self):
        """A single gen9monotyperandombattle completes vs a random opponent.

        Verifies the server-generated monotype random teams battle runs end to
        end and exactly one outcome registers — i.e. bestOfDefault:true does not
        stall poke-env into an unfinished best-of-3 series.
        """
        player = _random_player("MonoA")
        opponent = _random_player("MonoB")

        await asyncio.wait_for(
            player.battle_against(opponent, n_battles=1),
            timeout=120.0,
        )

        assert player.n_finished_battles == 1
        assert (
            player.n_won_battles + player.n_lost_battles + player.n_tied_battles == 1
        )
