"""End-to-end smoke test: raw paste -> parse -> dedup -> validate -> tag -> API response."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_db
from api.main import app
from models.db import Player, Source, Tournament, TournamentPlacement
from tasks.process.deduplicator import TeamDeduplicator
from tasks.process.parser import ShowdownPasteParser
from tasks.process.tagger import RuleBasedTagger
from tasks.process.validator import PreValidator


@pytest_asyncio.fixture
async def client(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_pipeline_smoke(client, db_session, sample_vgc_team):
    # 1. Insert a sample tournament into DB
    source = Source(platform="e2e_test", base_url="https://example.com", api_available=False)
    db_session.add(source)
    await db_session.flush()

    tournament = Tournament(
        external_id="e2e-1", source_id=source.id, name="E2E Test Cup", regulation="Reg M-B", format_type="VGC"
    )
    player = Player(name="E2EPlayer")
    db_session.add_all([tournament, player])
    await db_session.flush()

    # 2. Parse a raw paste
    parsed_json = ShowdownPasteParser().parse(sample_vgc_team)
    assert len(parsed_json) == 6

    # 3. Deduplicate / upsert
    dedup = TeamDeduplicator()
    team, was_created = await dedup.upsert_team(
        db_session,
        raw_paste=sample_vgc_team,
        parsed_json=parsed_json,
        regulation="Reg M-B",
        format_type="VGC",
        source_meta={"source_id": source.id, "scrape_method": "api", "source_url": "https://example.com/team"},
    )
    assert was_created is True

    # 4. Validate (pre-validation only — Node classifier is not running in the test env)
    result = PreValidator().validate(parsed_json, "VGC", "Reg M-B")
    assert result.is_valid is True

    from sqlalchemy import update

    from models.db import Team

    await db_session.execute(update(Team).where(Team.id == team.id).values(is_valid=result.is_valid))

    # 5. Tag (rule-based only, same reasoning as step 4)
    tags = RuleBasedTagger().tag_team(parsed_json, "VGC")
    await db_session.execute(update(Team).where(Team.id == team.id).values(archetype_tags=tags))
    await db_session.commit()

    db_session.add(
        TournamentPlacement(tournament_id=tournament.id, player_id=player.id, team_id=team.id, final_placing=1)
    )
    await db_session.commit()

    # 6. Query GET /teams via the API client
    resp = await client.get("/teams")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1

    # 7. Assert correct fields, tags, and provenance
    detail_resp = await client.get(f"/teams/{team.id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["regulation"] == "Reg M-B"
    assert "doubles_vgc" in detail["archetype_tags"]
    assert len(detail["provenance"]) == 1
    assert detail["provenance"][0]["source_platform"] == "e2e_test"
    assert len(detail["placements"]) == 1
    assert detail["placements"][0]["final_placing"] == 1
