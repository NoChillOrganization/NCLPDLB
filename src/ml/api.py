"""
FastAPI backend for the local AI training system.

Endpoints
---------
  GET  /stats   — current training state (games, wins, losses, winrate, status, mcts_sims)
  GET  /        — serve dashboard.html
  POST /start   — begin self-play training loop
  POST /stop    — stop training loop
  POST /config  — update runtime config (mcts_sims)

State is held in a module-level dict protected by a threading.Lock so that
the asyncio FastAPI thread and the background training thread can both read
and write safely.

Usage
-----
  # Standalone (for testing):
  uvicorn src.ml.api:app --host 0.0.0.0 --port 8080 --reload

  # Via run_training.py (recommended):
  python -m src.ml.run_training --port 8080
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Dependency guard ──────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
    from pydantic import BaseModel, Field
    FASTAPI_OK = True
except ImportError:  # pragma: no cover
    FASTAPI_OK = False
    FastAPI = None       # type: ignore
    HTTPException = CORSMiddleware = FileResponse = JSONResponse = Field = None  # type: ignore
    BaseModel = object   # type: ignore


# ── Global training state ─────────────────────────────────────────────────────

_STATE_LOCK = threading.Lock()

_STATE: dict[str, Any] = {
    "games":     0,
    "wins":      0,
    "losses":    0,
    "ties":      0,
    "winrate":   0.0,
    "status":    "stopped",   # "stopped" | "running" | "error"
    "mcts_sims": 30,
    "train_steps": 0,
    "buffer_size": 0,
    "last_loss":   None,
}

# Handle to the running training coroutine / thread (set by run_training.py)
_training_handle: Any = None


def get_state() -> dict[str, Any]:
    """Return a snapshot of the training state (thread-safe)."""
    with _STATE_LOCK:
        return dict(_STATE)


def update_state(**kwargs: Any) -> None:
    """Update one or more fields in the global training state (thread-safe)."""
    with _STATE_LOCK:
        _STATE.update(kwargs)
        # Keep winrate in sync
        games = _STATE["games"]
        if games > 0:
            _STATE["winrate"] = round(_STATE["wins"] / games, 4)
        else:
            _STATE["winrate"] = 0.0


# ── FastAPI app ───────────────────────────────────────────────────────────────

if FASTAPI_OK:
    app = FastAPI(title="Pokemon AI Trainer", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request / response models ────────────────────────────────────────

    class ConfigRequest(BaseModel):
        mcts_sims: int = Field(default=30, ge=1, le=200)

    # ── Routes ───────────────────────────────────────────────────────────

    @app.get("/stats")
    def route_stats() -> JSONResponse:
        """Return current training statistics."""
        return JSONResponse(get_state())

    @app.get("/")
    def route_dashboard() -> FileResponse:
        """Serve the training dashboard HTML."""
        html_path = Path(__file__).parent / "dashboard.html"
        if not html_path.exists():
            raise HTTPException(
                status_code=404,
                detail="dashboard.html not found — make sure it is in src/ml/",
            )
        return FileResponse(str(html_path), media_type="text/html")

    @app.post("/start")
    def route_start() -> JSONResponse:
        """Signal the training loop to start."""
        with _STATE_LOCK:
            if _STATE["status"] == "running":
                return JSONResponse({"ok": False, "message": "Already running"})

        # The actual loop is controlled by run_training.py via _training_handle.
        # Here we just flip the flag; the runner polls it.
        update_state(status="running")
        log.info("[API] Training start requested")
        return JSONResponse({"ok": True, "message": "Training started"})

    @app.post("/stop")
    def route_stop() -> JSONResponse:
        """Signal the training loop to stop after the current game."""
        update_state(status="stopped")
        log.info("[API] Training stop requested")
        return JSONResponse({"ok": True, "message": "Training stopped"})

    @app.post("/config")
    def route_config(req: ConfigRequest) -> JSONResponse:
        """Update runtime configuration."""
        update_state(mcts_sims=req.mcts_sims)
        log.info("[API] Config updated: mcts_sims=%d", req.mcts_sims)
        return JSONResponse({"ok": True, "mcts_sims": req.mcts_sims})

else:  # pragma: no cover
    # Stub so imports don't crash when fastapi is not installed
    app = None  # type: ignore
    log.warning(
        "FastAPI not installed — API server disabled. "
        "Run: pip install fastapi uvicorn"
    )
