"""
Tests for src/ml/api.py — FastAPI training dashboard backend.

Covers:
  - get_state() / update_state() thread-safe helpers
  - GET /stats, GET /, POST /start, POST /stop, POST /config routes
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("fastapi", reason="fastapi not installed")
pytest.importorskip("starlette", reason="starlette not installed")

from starlette.testclient import TestClient

import src.ml.api as api_module
from src.ml.api import get_state, update_state, app


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reset_state() -> None:
    """Bring _STATE back to clean defaults between tests."""
    update_state(
        games=0,
        wins=0,
        losses=0,
        ties=0,
        status="stopped",
        mcts_sims=30,
        train_steps=0,
        buffer_size=0,
        last_loss=None,
    )
    # winrate recalculates automatically; force it to 0
    with api_module._STATE_LOCK:
        api_module._STATE["winrate"] = 0.0


@pytest.fixture(autouse=True)
def reset_api_state():
    """Reset global API state before every test."""
    _reset_state()
    yield
    _reset_state()


# ── get_state / update_state ──────────────────────────────────────────────────

class TestGetState:
    def test_returns_snapshot_dict(self):
        state = get_state()
        assert isinstance(state, dict)
        assert "games" in state
        assert "status" in state

    def test_is_a_copy_not_the_original(self):
        state = get_state()
        state["games"] = 999
        assert get_state()["games"] == 0  # original unchanged


class TestUpdateState:
    def test_updates_single_field(self):
        update_state(status="running")
        assert get_state()["status"] == "running"

    def test_updates_multiple_fields(self):
        update_state(games=10, wins=7, losses=3)
        s = get_state()
        assert s["games"] == 10
        assert s["wins"] == 7
        assert s["losses"] == 3

    def test_winrate_auto_calculated_when_games_nonzero(self):
        update_state(games=4, wins=3)
        assert get_state()["winrate"] == pytest.approx(0.75)

    def test_winrate_stays_zero_when_no_games(self):
        update_state(games=0, wins=0)
        assert get_state()["winrate"] == 0.0

    def test_winrate_rounded_to_4_places(self):
        update_state(games=3, wins=1)
        assert get_state()["winrate"] == pytest.approx(round(1 / 3, 4))


# ── FastAPI routes ────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    return TestClient(app)


class TestStatsRoute:
    def test_returns_200(self, client):
        r = client.get("/stats")
        assert r.status_code == 200

    def test_body_contains_expected_keys(self, client):
        body = client.get("/stats").json()
        for key in ("games", "wins", "losses", "ties", "winrate", "status", "mcts_sims"):
            assert key in body

    def test_reflects_current_state(self, client):
        update_state(games=5, wins=3, status="running")
        body = client.get("/stats").json()
        assert body["games"] == 5
        assert body["wins"] == 3
        assert body["status"] == "running"


class TestDashboardRoute:
    def test_returns_200_when_html_file_exists(self, client):
        from pathlib import Path
        html = Path(__file__).parent.parent.parent / "src" / "ml" / "dashboard.html"
        if html.exists():
            r = client.get("/")
            assert r.status_code == 200
        else:
            r = client.get("/")
            assert r.status_code == 404


class TestStartRoute:
    def test_start_when_stopped_returns_ok(self, client):
        body = client.post("/start").json()
        assert body["ok"] is True

    def test_start_flips_status_to_running(self, client):
        client.post("/start")
        assert get_state()["status"] == "running"

    def test_start_when_already_running_returns_not_ok(self, client):
        client.post("/start")
        body = client.post("/start").json()
        assert body["ok"] is False
        assert "Already running" in body["message"]


class TestStopRoute:
    def test_stop_returns_ok(self, client):
        client.post("/start")
        body = client.post("/stop").json()
        assert body["ok"] is True

    def test_stop_flips_status_to_stopped(self, client):
        client.post("/start")
        client.post("/stop")
        assert get_state()["status"] == "stopped"

    def test_stop_when_already_stopped_still_ok(self, client):
        body = client.post("/stop").json()
        assert body["ok"] is True


class TestConfigRoute:
    def test_valid_mcts_sims_accepted(self, client):
        body = client.post("/config", json={"mcts_sims": 50}).json()
        assert body["ok"] is True
        assert body["mcts_sims"] == 50

    def test_config_updates_state(self, client):
        client.post("/config", json={"mcts_sims": 100})
        assert get_state()["mcts_sims"] == 100

    def test_mcts_sims_below_min_rejected(self, client):
        r = client.post("/config", json={"mcts_sims": 0})
        assert r.status_code == 422

    def test_mcts_sims_above_max_rejected(self, client):
        r = client.post("/config", json={"mcts_sims": 201})
        assert r.status_code == 422

    def test_mcts_sims_at_boundary_min(self, client):
        body = client.post("/config", json={"mcts_sims": 1}).json()
        assert body["ok"] is True

    def test_mcts_sims_at_boundary_max(self, client):
        body = client.post("/config", json={"mcts_sims": 200}).json()
        assert body["ok"] is True
