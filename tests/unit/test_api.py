"""
Tests for src/ml/api.py — get_state, update_state, and all FastAPI routes.
"""
from __future__ import annotations

import importlib
import sys
from unittest.mock import patch

import pytest

fastapi_tc = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_tc.TestClient

import src.ml.api as api_module
from src.ml.api import app, get_state, update_state


# ── Helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_state():
    """Restore _STATE to defaults before each test."""
    defaults = {
        "games": 0, "wins": 0, "losses": 0, "ties": 0,
        "winrate": 0.0, "status": "stopped",
        "mcts_sims": 30, "train_steps": 0,
        "buffer_size": 0, "last_loss": None,
    }
    with api_module._STATE_LOCK:
        api_module._STATE.update(defaults)
    yield


@pytest.fixture()
def client():
    return TestClient(app)


# ── get_state / update_state ──────────────────────────────────────────────────

class TestGetState:
    def test_returns_dict(self):
        state = get_state()
        assert isinstance(state, dict)

    def test_default_keys_present(self):
        state = get_state()
        for key in ("games", "wins", "losses", "ties", "winrate",
                    "status", "mcts_sims", "train_steps", "buffer_size", "last_loss"):
            assert key in state

    def test_returns_snapshot_not_reference(self):
        s1 = get_state()
        update_state(games=99)
        s2 = get_state()
        assert s1["games"] == 0
        assert s2["games"] == 99


class TestUpdateState:
    def test_updates_single_field(self):
        update_state(games=5)
        assert get_state()["games"] == 5

    def test_updates_multiple_fields(self):
        update_state(games=10, wins=7)
        s = get_state()
        assert s["games"] == 10
        assert s["wins"] == 7

    def test_winrate_recalculated_when_games_positive(self):
        update_state(games=4, wins=3)
        assert get_state()["winrate"] == pytest.approx(0.75)

    def test_winrate_zero_when_no_games(self):
        update_state(games=0, wins=0)
        assert get_state()["winrate"] == pytest.approx(0.0)

    def test_winrate_rounded_to_4_places(self):
        update_state(games=3, wins=1)
        # 1/3 = 0.3333...
        assert get_state()["winrate"] == pytest.approx(round(1 / 3, 4))

    def test_status_field_updated(self):
        update_state(status="running")
        assert get_state()["status"] == "running"


# ── GET /stats ────────────────────────────────────────────────────────────────

class TestRouteStats:
    def test_returns_200(self, client):
        r = client.get("/stats")
        assert r.status_code == 200

    def test_response_is_json_with_expected_keys(self, client):
        data = client.get("/stats").json()
        assert "games" in data
        assert "winrate" in data
        assert "status" in data

    def test_reflects_current_state(self, client):
        update_state(games=10, wins=6)
        data = client.get("/stats").json()
        assert data["games"] == 10
        assert data["wins"] == 6


# ── GET / (dashboard) ────────────────────────────────────────────────────────

class TestRouteDashboard:
    def test_404_when_dashboard_html_missing(self, client, tmp_path):
        """When dashboard.html doesn't exist the route raises 404."""
        non_existent = tmp_path / "dashboard.html"
        with patch("src.ml.api.Path") as mock_path_cls:
            # Make Path(__file__).parent / "dashboard.html" return a path that doesn't exist
            mock_path_cls.return_value.parent.__truediv__ = lambda self, other: non_existent
            r = client.get("/")
        assert r.status_code == 404

    def test_200_when_dashboard_html_exists(self, client, tmp_path):
        """When dashboard.html exists the route returns FileResponse."""
        html = tmp_path / "dashboard.html"
        html.write_text("<html>ok</html>")
        with patch("src.ml.api.Path") as mock_path_cls:
            mock_path_cls.return_value.parent.__truediv__ = lambda self, other: html
            r = client.get("/")
        assert r.status_code == 200


# ── POST /start ───────────────────────────────────────────────────────────────

class TestRouteStart:
    def test_starts_when_stopped(self, client):
        r = client.post("/start")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert get_state()["status"] == "running"

    def test_returns_false_when_already_running(self, client):
        update_state(status="running")
        r = client.post("/start")
        data = r.json()
        assert data["ok"] is False

    def test_message_present_on_success(self, client):
        data = client.post("/start").json()
        assert "message" in data

    def test_message_present_on_already_running(self, client):
        update_state(status="running")
        data = client.post("/start").json()
        assert "message" in data


# ── POST /stop ────────────────────────────────────────────────────────────────

class TestRouteStop:
    def test_stop_sets_status_stopped(self, client):
        update_state(status="running")
        r = client.post("/stop")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert get_state()["status"] == "stopped"

    def test_stop_idempotent_when_already_stopped(self, client):
        r = client.post("/stop")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_stop_response_has_message(self, client):
        assert "message" in client.post("/stop").json()


# ── POST /config ──────────────────────────────────────────────────────────────

class TestRouteConfig:
    def test_updates_mcts_sims(self, client):
        r = client.post("/config", json={"mcts_sims": 50})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["mcts_sims"] == 50
        assert get_state()["mcts_sims"] == 50

    def test_default_value_accepted(self, client):
        r = client.post("/config", json={"mcts_sims": 30})
        assert r.status_code == 200

    def test_boundary_value_1(self, client):
        r = client.post("/config", json={"mcts_sims": 1})
        assert r.status_code == 200
        assert get_state()["mcts_sims"] == 1

    def test_boundary_value_200(self, client):
        r = client.post("/config", json={"mcts_sims": 200})
        assert r.status_code == 200
        assert get_state()["mcts_sims"] == 200

    def test_out_of_range_low_rejected(self, client):
        r = client.post("/config", json={"mcts_sims": 0})
        assert r.status_code == 422

    def test_out_of_range_high_rejected(self, client):
        r = client.post("/config", json={"mcts_sims": 201})
        assert r.status_code == 422

    def test_missing_body_uses_default(self, client):
        r = client.post("/config", json={})
        assert r.status_code == 200
        assert r.json()["mcts_sims"] == 30
