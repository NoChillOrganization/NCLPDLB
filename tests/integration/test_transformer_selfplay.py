"""
Integration test: BattleTransformer offline self-play training via
train_transformer.train() on a LOCAL Showdown server (ws://localhost:8000).

SKIPPED automatically when no server is reachable on localhost:8000.
Runs for real in CI where the workflow starts a local Showdown server first.

To run locally:
    # 1. Start the bundled server:
    #    node F:\\NCLPDLB\\pokemon-showdown\\pokemon-showdown start --no-security
    # 2. pytest tests/integration/test_transformer_selfplay.py -v
"""

from __future__ import annotations

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


def test_train_produces_checkpoint_and_log(tmp_path: Path) -> None:
    """
    Run a tiny offline MCTS self-play training session (2 games, 2 epochs,
    8 MCTS sims) and verify:
      - Checkpoint file exists after training
      - Log file exists and contains >= 1 epoch= line
      - train() returns n_epochs_trained >= 1
    """
    from src.ml.train_transformer import train

    ckpt = tmp_path / "transformer_checkpoint.pt"
    log_file = tmp_path / "transformer_training.log"

    results = train(
        fmt="gen9randombattle",
        n_games=2,
        n_epochs=2,
        steps_per_epoch=2,
        buffer_capacity=10_000,
        mcts_sims=8,
        lr=1e-3,
        val_frac=0.3,
        checkpoint_out=str(ckpt),
        log_file=str(log_file),
        server="localhost",
    )

    assert ckpt.exists(), "Checkpoint must be written after training"
    assert log_file.exists(), "Training log file must exist"

    epoch_lines = [
        ln for ln in log_file.read_text(encoding="utf-8").splitlines() if "epoch=" in ln
    ]
    assert len(epoch_lines) >= 1, (
        f"Expected >= 1 epoch log line; got {len(epoch_lines)}:\n"
        + "\n".join(epoch_lines)
    )
    assert results["n_epochs_trained"] >= 1, "At least one training epoch must complete"


def test_train_checkpoint_loadable(tmp_path: Path) -> None:
    """
    Verify the saved checkpoint can be loaded back via load_model.
    """
    from src.ml.train_transformer import train
    from src.ml.transformer_model import load_model

    ckpt = tmp_path / "ckpt.pt"

    train(
        fmt="gen9randombattle",
        n_games=2,
        n_epochs=1,
        steps_per_epoch=1,
        buffer_capacity=5_000,
        mcts_sims=8,
        lr=1e-3,
        val_frac=0.3,
        checkpoint_out=str(ckpt),
        log_file=str(tmp_path / "training.log"),
        server="localhost",
    )

    loaded = load_model(ckpt)
    assert loaded is not None, "Checkpoint must be loadable by load_model()"
