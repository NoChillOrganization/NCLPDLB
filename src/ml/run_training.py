"""
Local AI Training System — main runner.

Wires together:
  • SelfPlayLoop    (self_play.py)   — AccountA vs AccountB via poke-env
  • PolicyTrainer   (trainer.py)    — trains BattleTransformer from replay buffer
  • FastAPI server  (api.py)        — exposes /stats, /start, /stop, /config
  • Dashboard       (dashboard.html)— served at GET /

How to run
----------
  1. Start local Pokemon Showdown server:
       cd pokemon-showdown
       node pokemon-showdown start --no-security

  2. (Optional) Install a pre-trained model:
       Copy models/latest.pt to the project root, or let it train from scratch.

  3. Start training system:
       python -m src.ml.run_training

  4. Open the dashboard:
       http://localhost:8080

  5. Click "Start" in the dashboard to begin self-play training.

CLI options
-----------
  --port      HTTP port for API + dashboard  (default: 8080)
  --format    Showdown battle format         (default: gen9randombattle)
  --mcts-sims MCTS simulations per move      (default: 30)
  --buffer    Replay buffer capacity         (default: 50000)
  --lr        Transformer learning rate      (default: 3e-4)
  --train-every Train after N games          (default: 5)
  --model     Path to load a model from      (default: models/latest.pt if exists)

Requirements
------------
  pip install fastapi uvicorn poke-env torch numpy websockets
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
from pathlib import Path

log = logging.getLogger(__name__)


# ── Windows asyncio fix ───────────────────────────────────────────────────────

def _apply_windows_event_loop_fix() -> None:
    """Ensure ProactorEventLoop is used on Windows for WebSocket + subprocess support."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        log.debug("Applied WindowsProactorEventLoopPolicy")


# ── Dependency checks ─────────────────────────────────────────────────────────

def _check_dependencies() -> list[str]:
    """Return list of missing critical packages."""
    missing = []
    for pkg, import_name in [
        ("fastapi",   "fastapi"),
        ("uvicorn",   "uvicorn"),
        ("torch",     "torch"),
        ("poke_env",  "poke_env"),
        ("websockets","websockets"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)
    return missing


# ── Self-play thread ──────────────────────────────────────────────────────────

def _run_self_play_in_thread(
    loop_obj: "SelfPlayLoop",
) -> None:
    """
    Run the async SelfPlayLoop in a dedicated thread with its own event loop.

    This keeps the asyncio poke-env self-play on a separate event loop from
    the uvicorn FastAPI server, avoiding event-loop sharing issues on Windows.
    """
    _apply_windows_event_loop_fix()

    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    try:
        new_loop.run_until_complete(loop_obj.run_forever())
    except Exception as exc:
        log.error("[SelfPlayThread] Fatal error: %s", exc, exc_info=True)
        try:
            from src.ml.api import update_state
            update_state(status="error")
        except Exception:
            pass
    finally:
        new_loop.close()


# ── Main entry point ──────────────────────────────────────────────────────────

def main(
    port: int = 8080,
    fmt: str = "gen9randombattle",
    mcts_sims: int = 30,
    buffer_capacity: int = 50_000,
    lr: float = 3e-4,
    train_every: int = 5,
    model_path: str | None = None,
) -> None:
    """
    Build all components and start the API server + self-play thread.

    Self-play only runs when the dashboard sets status="running" via POST /start.
    """
    _apply_windows_event_loop_fix()

    # ── 1. Check dependencies ────────────────────────────────────────────
    missing = _check_dependencies()
    if missing:
        log.warning(
            "Missing optional packages (some features disabled): %s\n"
            "Install with: pip install %s",
            ", ".join(missing),
            " ".join(missing),
        )

    # ── 2. Build model ───────────────────────────────────────────────────
    from src.ml.transformer_model import build_default_model, load_model

    model_file = Path(model_path) if model_path else Path("models/latest.pt")
    if model_file.exists():
        log.info("Loading model from %s", model_file)
        model = load_model(model_file)
    else:
        log.info("No saved model found — starting from scratch (random weights)")
        model = build_default_model()

    # ── 3. Build replay buffer + trainer ────────────────────────────────
    from src.ml.trainer import ReplayBuffer, PolicyTrainer

    buffer  = ReplayBuffer(capacity=buffer_capacity)
    trainer = PolicyTrainer(model=model, lr=lr)

    # ── 4. Build shared stats + self-play loop ───────────────────────────
    from src.ml.self_play import SharedStats, SelfPlayLoop
    from src.ml.mcts import MCTSConfig

    stats       = SharedStats()
    mcts_config = MCTSConfig(n_simulations=mcts_sims)

    # Sync initial mcts_sims into the API state
    try:
        from src.ml.api import update_state
        update_state(mcts_sims=mcts_sims, status="stopped")
    except Exception:
        pass

    loop_obj = SelfPlayLoop(
        model=model,
        buffer=buffer,
        stats=stats,
        mcts_config=mcts_config,
        fmt=fmt,
        train_every=train_every,
        trainer=trainer,
    )

    # ── 5. Wire API config changes → MCTSConfig ──────────────────────────
    # Patch SelfPlayLoop to pick up mcts_sims changes at runtime.
    # We monkey-patch run_game() to refresh config from API state before each game.
    _orig_run_game = loop_obj.run_game

    async def _run_game_with_live_config() -> dict:
        try:
            from src.ml.api import get_state
            sims = get_state().get("mcts_sims", mcts_sims)
            loop_obj.mcts_config = MCTSConfig(n_simulations=sims)
        except Exception:
            pass
        return await _orig_run_game()

    loop_obj.run_game = _run_game_with_live_config  # type: ignore[method-assign]

    # ── 6. Launch self-play in background thread ─────────────────────────
    sp_thread = threading.Thread(
        target=_run_self_play_in_thread,
        args=(loop_obj,),
        name="self-play",
        daemon=True,
    )
    sp_thread.start()
    log.info("Self-play thread started (paused until you click Start in dashboard)")

    # ── 7. Start FastAPI server (blocking) ────────────────────────────────
    try:
        import uvicorn
        from src.ml.api import app

        if app is None:
            raise ImportError("FastAPI app not initialized — install fastapi + uvicorn")

        log.info("=" * 60)
        log.info("  Dashboard : http://localhost:%d", port)
        log.info("  API stats : http://localhost:%d/stats", port)
        log.info("  Format    : %s", fmt)
        log.info("  MCTS sims : %d", mcts_sims)
        log.info("  Buffer    : %d capacity", buffer_capacity)
        log.info("=" * 60)
        log.info("Open the dashboard and click Start to begin training.")
        log.info("Press Ctrl+C to stop.")

        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

    except KeyboardInterrupt:
        log.info("Shutting down...")
    finally:
        try:
            from src.ml.api import update_state
            update_state(status="stopped")
        except Exception:
            pass


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Pokemon AI local training system — self-play + transformer + dashboard",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--port",        type=int,   default=8080,               help="API/dashboard port")
    ap.add_argument("--format",      default="gen9randombattle",             help="Showdown format")
    ap.add_argument("--mcts-sims",   type=int,   default=30,                 help="MCTS simulations per move")
    ap.add_argument("--buffer",      type=int,   default=50_000,             help="Replay buffer capacity")
    ap.add_argument("--lr",          type=float, default=3e-4,               help="Transformer learning rate")
    ap.add_argument("--train-every", type=int,   default=5,                  help="Train after N games (0=off)")
    ap.add_argument("--model",       default=None,                           help="Path to a .pt model checkpoint")
    return ap.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    args = _parse_args()
    main(
        port=args.port,
        fmt=args.format,
        mcts_sims=args.mcts_sims,
        buffer_capacity=args.buffer,
        lr=args.lr,
        train_every=args.train_every,
        model_path=args.model,
    )
