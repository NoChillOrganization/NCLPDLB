"""
Offline MCTS self-play trainer for BattleTransformer.

Pairs two MCTSPlayer instances on a local Showdown server, collects game data,
splits 80/20 train/val at the game level (no leakage), and trains
BattleTransformer across multiple epochs, logging val loss to a file.

Architecture
------------
  _GameCapture      — duck-typed ReplayBuffer that stores raw game tuples so
                      we can split train/val at the game boundary before filling
                      real buffers.
  _generate_games   — runs player_a.battle_against(player_b, n) on the local
                      Showdown server; both players push to _GameCapture.
  _split_and_fill   — 80/20 game-level split → two real ReplayBuffers.
  train()           — generate → split → epoch loop → save checkpoint.

Usage
-----
  python -m src.ml.train_transformer --games 50 --epochs 10
  python -m src.ml.train_transformer --games 6 --epochs 3   # CI smoke

Requirements
------------
  • A local Pokemon Showdown server on ws://localhost:8000
    (node pokemon-showdown/pokemon-showdown start --no-security)
  • pip install poke-env>=0.8.1 torch numpy
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Default paths ─────────────────────────────────────────────────────────────

DEFAULT_CHECKPOINT_OUT = "src/ml/models/transformer_checkpoint.pt"
DEFAULT_LOG_FILE = "logs/transformer_training.log"
DEFAULT_FORMAT = "gen9randombattle"


# ── Game capture collector ────────────────────────────────────────────────────


class _GameCapture:
    """
    Duck-typed replacement for ReplayBuffer when collecting self-play data.

    MCTSPlayer calls ``add_game(obs_list, act_list, probs_list, reward)`` at
    battle end.  We store each game as a raw tuple here so that the caller can
    split train/val at the game level before flattening into real ReplayBuffers.
    This avoids leakage that would occur if we sliced a flat buffer.

    __len__ returns total transitions (sum across games), satisfying the
    ``len(self._replay_buffer)`` debug-log in MCTSPlayer._battle_finished_callback.
    """

    def __init__(self) -> None:
        self._games: list[tuple] = []

    def add_game(
        self,
        observations: list,
        actions: list,
        action_probs_list: list,
        reward: float,
    ) -> None:
        """Append one completed game's data."""
        self._games.append(
            (
                [o.copy() for o in observations],
                list(actions),
                [p.copy() if p is not None else None for p in action_probs_list],
                float(reward),
            )
        )

    def __len__(self) -> int:
        """Total transitions collected (across all games)."""
        return sum(len(g[0]) for g in self._games)

    @property
    def games(self) -> list:
        return list(self._games)


# ── Generate games via local self-play ───────────────────────────────────────


async def _generate_games(
    model: Any,
    mcts_config: Any,
    n_games: int,
    fmt: str,
    server: str,
) -> list:
    """
    Pair two MCTSPlayers and run ``n_games`` battles on the local Showdown server.

    Both players share one _GameCapture so every game's data (from both
    perspectives) ends up in the same collection.

    Returns the list of raw game tuples from the capture.
    """
    from src.ml.self_play import MCTSPlayer, SharedStats
    from src.ml.showdown_modes import server_config_for_mode

    srv_cfg = server_config_for_mode(server)
    capture = _GameCapture()

    player_a = MCTSPlayer(
        model=model,
        mcts_config=mcts_config,
        replay_buffer=capture,
        stats=SharedStats(),
        name="AccountA",
        battle_format=fmt,
        server_configuration=srv_cfg,
    )
    player_b = MCTSPlayer(
        model=model,
        mcts_config=mcts_config,
        replay_buffer=capture,
        stats=SharedStats(),
        name="AccountB",
        battle_format=fmt,
        server_configuration=srv_cfg,
    )

    log.info("[generate] Running %d games (%s)…", n_games, fmt)
    await asyncio.wait_for(
        player_a.battle_against(player_b, n_battles=n_games),
        timeout=300.0 * n_games,
    )
    log.info(
        "[generate] Done. %d games → %d transitions",
        len(capture.games),
        len(capture),
    )
    return capture.games


# ── Train/val split ───────────────────────────────────────────────────────────


def _split_and_fill_buffers(
    all_games: list,
    val_frac: float,
    buffer_capacity: int,
) -> tuple:
    """
    Split ``all_games`` 80/20 at the game level and fill two ReplayBuffers.

    Game-level split: turns from the same game never span both splits, so
    the val set gives a leakage-free estimate of generalisation.

    Returns (train_buf, val_buf).
    """
    from src.ml.trainer import ReplayBuffer

    n = len(all_games)
    if n == 0:
        raise RuntimeError(
            "No games collected — cannot train. "
            "Check that the local Showdown server is running on ws://localhost:8000."
        )

    n_val = max(1, int(n * val_frac))
    n_train = max(1, n - n_val)
    if n_train + n_val > n:
        # Edge case: 1 game total — use it for both splits
        n_val = 0
        n_train = n

    train_games = all_games[:n_train]
    val_games = all_games[n_train : n_train + n_val] if n_val else []

    train_buf = ReplayBuffer(capacity=buffer_capacity)
    val_buf = ReplayBuffer(capacity=buffer_capacity)

    for obs_list, act_list, probs_list, reward in train_games:
        train_buf.add_game(obs_list, act_list, probs_list, reward)
    for obs_list, act_list, probs_list, reward in val_games:
        val_buf.add_game(obs_list, act_list, probs_list, reward)

    log.info(
        "[split] train=%d games (%d transitions) | val=%d games (%d transitions)",
        len(train_games),
        len(train_buf),
        len(val_games),
        len(val_buf),
    )
    return train_buf, val_buf


# ── Main training function ────────────────────────────────────────────────────


def train(
    fmt: str = DEFAULT_FORMAT,
    n_games: int = 50,
    n_epochs: int = 10,
    steps_per_epoch: int = 4,
    buffer_capacity: int = 50_000,
    mcts_sims: int = 0,
    lr: float = 1e-3,
    val_frac: float = 0.2,
    checkpoint_out: str = DEFAULT_CHECKPOINT_OUT,
    log_file: str = DEFAULT_LOG_FILE,
    server: str = "localhost",
    resume: str | None = None,
) -> dict:
    """
    Run offline MCTS self-play and train BattleTransformer to convergence.

    Steps:
      1. Build (or resume) a BattleTransformer.
      2. Generate ``n_games`` of MCTS self-play on the local Showdown server.
      3. Split collected data 80/20 at the game level.
      4. Run ``n_epochs`` of training, logging val loss after each epoch to
         ``log_file`` in the format ``epoch=N train=X.XXXX val=X.XXXX``.
      5. Save the final model to ``checkpoint_out``.

    Args:
        fmt:              Showdown battle format string.
        n_games:          Number of self-play games to generate.
        n_epochs:         Training epochs.
        steps_per_epoch:  Gradient steps per epoch (passed to train_epochs).
        buffer_capacity:  Capacity of each ReplayBuffer (train + val).
        mcts_sims:        MCTS simulations per move.
        lr:               Optimizer learning rate.
        val_frac:         Fraction of games held out for validation.
        checkpoint_out:   Output path for the saved checkpoint.
        log_file:         Path to append training log lines.
        server:           Showdown server mode ("localhost").
        resume:           Optional path to a prior checkpoint to resume from.

    Returns a metrics dict with keys:
        checkpoint, n_epochs_trained, val_losses, train_losses, val_delta.
    """
    from src.ml.transformer_model import build_default_model, load_model, save_model
    from src.ml.trainer import PolicyTrainer
    from src.ml.mcts import MCTSConfig

    # ── Model ────────────────────────────────────────────────────────
    if resume:
        log.info("[train_transformer] Resuming from %s", resume)
        model = load_model(resume)
    else:
        log.info("[train_transformer] Starting from random weights")
        model = build_default_model()

    mcts_config = MCTSConfig(n_simulations=mcts_sims)
    trainer = PolicyTrainer(model, lr=lr, save_path=checkpoint_out)

    # ── Generate games ───────────────────────────────────────────────
    all_games = asyncio.run(_generate_games(model, mcts_config, n_games, fmt, server))

    # ── Split buffers ────────────────────────────────────────────────
    train_buf, val_buf = _split_and_fill_buffers(all_games, val_frac, buffer_capacity)

    # ── Set up file logging ──────────────────────────────────────────
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    )
    progress_log = logging.getLogger("train_transformer.progress")
    progress_log.addHandler(file_handler)
    progress_log.setLevel(logging.INFO)
    progress_log.propagate = True

    # ── Epoch loop ───────────────────────────────────────────────────
    val_losses: list[float] = []
    train_losses: list[float] = []

    try:
        for epoch in range(1, n_epochs + 1):
            train_metrics = trainer.train_epochs(train_buf, n_epochs=steps_per_epoch)
            # Clamp val batch to available data so small training runs still validate.
            val_bs = max(1, min(256, len(val_buf)))
            val_metrics = (
                trainer.validation_loss(val_buf, batch_size=val_bs)
                if val_bs > 0
                else {}
            )

            if not train_metrics or not val_metrics:
                log.warning(
                    "[train_transformer] epoch=%d: buffer not ready — skipping "
                    "(need more games or a larger batch size)",
                    epoch,
                )
                continue

            t_loss = train_metrics["total_loss"]
            v_loss = val_metrics["val_total_loss"]
            train_losses.append(t_loss)
            val_losses.append(v_loss)

            msg = "epoch=%d train=%.4f val=%.4f" % (epoch, t_loss, v_loss)
            progress_log.info(msg)
            log.info("[train_transformer] %s", msg)
    finally:
        file_handler.close()
        progress_log.removeHandler(file_handler)

    # ── Save checkpoint ──────────────────────────────────────────────
    out_path = Path(checkpoint_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_model(model, out_path)
    log.info("[train_transformer] Checkpoint saved: %s", out_path)

    # ── Convergence check ────────────────────────────────────────────
    val_delta = 0.0
    if len(val_losses) >= 2:
        val_delta = val_losses[0] - val_losses[-1]
        if val_delta <= 0:
            log.warning(
                "[train_transformer] Val loss did not decrease (delta=%.4f). "
                "Try more games, more epochs, or a lower learning rate.",
                val_delta,
            )
        else:
            log.info(
                "[train_transformer] Val loss decreased by %.4f over %d epochs",
                val_delta,
                len(val_losses),
            )

    return {
        "checkpoint": str(out_path),
        "n_epochs_trained": len(val_losses),
        "val_losses": val_losses,
        "train_losses": train_losses,
        "val_delta": val_delta,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Train BattleTransformer via offline MCTS self-play"
    )
    ap.add_argument(
        "--format",
        "-f",
        default=DEFAULT_FORMAT,
        help=f"Showdown battle format (default: {DEFAULT_FORMAT})",
    )
    ap.add_argument(
        "--games",
        type=int,
        default=50,
        help="Number of self-play games to generate (default: 50)",
    )
    ap.add_argument(
        "--epochs",
        type=int,
        default=10,
        help="Training epochs (default: 10)",
    )
    ap.add_argument(
        "--steps-per-epoch",
        type=int,
        default=4,
        help="Gradient steps per epoch (default: 4)",
    )
    ap.add_argument(
        "--buffer",
        type=int,
        default=50_000,
        help="ReplayBuffer capacity (default: 50000)",
    )
    ap.add_argument(
        "--mcts-sims",
        type=int,
        default=0,
        help="MCTS simulations per move (0 = honest prior-shaping pass; >0 requires forward model)",
    )
    ap.add_argument(
        "--lr",
        type=float,
        default=1e-3,
        help="Optimizer learning rate (default: 1e-3)",
    )
    ap.add_argument(
        "--val-frac",
        type=float,
        default=0.2,
        help="Fraction of games held out for validation (default: 0.2)",
    )
    ap.add_argument(
        "--checkpoint-out",
        default=DEFAULT_CHECKPOINT_OUT,
        help=f"Output path for the saved checkpoint (default: {DEFAULT_CHECKPOINT_OUT})",
    )
    ap.add_argument(
        "--log-file",
        default=DEFAULT_LOG_FILE,
        help=f"Path for the training log (default: {DEFAULT_LOG_FILE})",
    )
    ap.add_argument(
        "--server",
        default="localhost",
        choices=["localhost"],
        help="Showdown server mode — only 'localhost' supported for offline training",
    )
    ap.add_argument(
        "--resume",
        default=None,
        metavar="CHECKPOINT.pt",
        help="Resume training from a saved BattleTransformer checkpoint",
    )
    return ap.parse_args()


if __name__ == "__main__":
    import logging as _logging

    _logging.basicConfig(
        level=_logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    args = _parse_args()
    results = train(
        fmt=args.format,
        n_games=args.games,
        n_epochs=args.epochs,
        steps_per_epoch=args.steps_per_epoch,
        buffer_capacity=args.buffer,
        mcts_sims=args.mcts_sims,
        lr=args.lr,
        val_frac=args.val_frac,
        checkpoint_out=args.checkpoint_out,
        log_file=args.log_file,
        server=args.server,
        resume=args.resume,
    )
    print(
        "Done. checkpoint=%s | epochs=%d | val_delta=%+.4f"
        % (results["checkpoint"], results["n_epochs_trained"], results["val_delta"])
    )
