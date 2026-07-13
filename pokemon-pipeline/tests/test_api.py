"""FastAPI endpoint tests. Uses ASGITransport directly (no lifespan) + a per-test SQLite session
overriding get_db, so tests never touch the real Postgres/Redis configured in settings."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_db
from api.main import app
from config import settings
from models.db import Source, Team


@pytest_asyncio.fixture
async def client(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _seed_team(db_session, regulation="Reg M-B", format_type="VGC", is_valid=True) -> Team:
    team = Team(
        content_hash=f"hash-{regulation}-{format_type}-{is_valid}",
        raw_paste="Incineroar @ Safety Goggles\nAbility: Intimidate\n- Fake Out",
        parsed_json=[{"species": "Incineroar", "moves": ["Fake Out"]}],
        regulation=regulation,
        format_type=format_type,
        archetype_tags=["doubles_vgc"],
        is_valid=is_valid,
    )
    db_session.add(team)
    await db_session.flush()
    await db_session.commit()
    return team


@pytest.mark.asyncio
class TestTeamsEndpoint:
    async def test_get_teams_empty(self, client):
        resp = await client.get("/teams")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_get_teams_with_filters(self, client, db_session):
        await _seed_team(db_session, regulation="Reg M-B")
        await _seed_team(db_session, regulation="Reg H")

        resp = await client.get("/teams", params={"regulation": "Reg M-B"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["regulation"] == "Reg M-B"

    async def test_get_team_by_id(self, client, db_session):
        team = await _seed_team(db_session)
        resp = await client.get(f"/teams/{team.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == team.id
        assert "placements" in body
        assert "provenance" in body

    async def test_get_team_paste(self, client, db_session):
        team = await _seed_team(db_session)
        resp = await client.get(f"/teams/{team.id}/paste")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        assert "Incineroar" in resp.text

    async def test_search_teams_by_species(self, client, db_session):
        from models.db import PokemonSet

        team = await _seed_team(db_session)
        db_session.add(PokemonSet(team_id=team.id, slot_index=0, species="Calyrex-Shadow"))
        await db_session.commit()

        resp = await client.get("/teams/search", params={"q": "Calyrex-Shadow"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1


@pytest.mark.asyncio
class TestExportEndpoint:
    async def test_export_training_data_jsonl(self, client, db_session):
        import json

        from models.db import Player, Tournament, TournamentPlacement

        source = Source(platform="test", base_url="https://x", api_available=False)
        db_session.add(source)
        await db_session.flush()
        tournament = Tournament(external_id="t1", source_id=source.id, name="Test Cup")
        player = Player(name="Player1")
        db_session.add_all([tournament, player])
        await db_session.flush()

        team = await _seed_team(db_session)
        db_session.add(
            TournamentPlacement(tournament_id=tournament.id, player_id=player.id, team_id=team.id, final_placing=1)
        )
        await db_session.commit()

        resp = await client.get("/export/training-data", params={"format_output": "jsonl", "top16_only": True})
        assert resp.status_code == 200
        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["is_top16"] is True
        assert record["regulation"] == "Reg M-B"


@pytest.mark.asyncio
class TestAdminEndpoint:
    async def test_admin_endpoint_requires_key(self, client):
        resp = await client.post("/admin/import/tournament", json={"source": "limitless", "external_id": "1"})
        assert resp.status_code == 401

    async def test_admin_trigger_import(self, client, monkeypatch):
        class _FakeResult:
            id = "fake-task-id"

        monkeypatch.setattr("api.routers.admin.celery_app.send_task", lambda *a, **k: _FakeResult())

        resp = await client.post(
            "/admin/import/tournament",
            json={"source": "limitless", "external_id": "1"},
            headers={"X-API-Key": settings.api_secret_key},
        )
        assert resp.status_code == 200
        assert resp.json()["task_id"] == "fake-task-id"
