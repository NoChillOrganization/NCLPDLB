"""Limitless ingest tests — all httpx calls mocked with respx, no real network access."""

import json

import pytest
import respx
from httpx import Response

from config import settings
from tasks.ingest import limitless
from tasks.utils import RateLimitedClient
from tests.conftest import load_fixture


@pytest.fixture
def limitless_response() -> dict:
    return json.loads(load_fixture("sample_limitless_response.json"))


class TestParseRegulation:
    def test_parses_regulation_and_format(self):
        regulation, format_type = limitless.parse_regulation("VGC 2026 Regulation M-B Regional")
        assert regulation == "Reg M-B"
        assert format_type == "VGC"

    def test_no_regulation_match_returns_none(self):
        regulation, format_type = limitless.parse_regulation("Smogon Tour Finals")
        assert regulation is None
        assert format_type is None


@pytest.mark.asyncio
class TestSyncSingleTournament:
    @respx.mock
    async def test_sync_single_tournament_success(self, db_session, limitless_response):
        tid = limitless_response["id"]
        respx.get(f"{settings.limitless_api_base}/tournaments/{tid}").mock(
            return_value=Response(200, json=limitless_response)
        )
        respx.get(f"{settings.limitless_api_base}/tournaments/{tid}/standings").mock(
            return_value=Response(200, json=limitless_response["standings"])
        )
        respx.get("https://pokepast.es/abc123/raw").mock(
            return_value=Response(200, text=load_fixture("sample_vgc_team.txt"))
        )
        respx.get("https://pokepast.es/def456/raw").mock(
            return_value=Response(200, text=load_fixture("sample_partial_team.txt"))
        )
        # p3 has team_url=None -> fetch_player_team() is called and its endpoint is
        # intentionally left unmocked; the resulting respx error is caught internally
        # and treated as "no team data", matching the real 403/404 behavior.
        # classifier/validator microservice unreachable in tests -> both degrade gracefully
        respx.post(f"{settings.node_classifier_url}/classify").mock(side_effect=ConnectionError)
        respx.post(f"{settings.node_classifier_url}/validate").mock(side_effect=ConnectionError)

        from models.db import Source

        source = Source(platform="limitless", base_url=settings.limitless_api_base, api_available=True)
        db_session.add(source)
        await db_session.flush()

        async with RateLimitedClient() as client:
            result = await limitless._import_tournament(client, db_session, source, limitless_response)

        # 3 standings entries but p3 has no resolvable team and gets skipped
        assert result["teams_imported"] == 2

        from sqlalchemy import select

        from models.db import Tournament

        tournaments = (await db_session.execute(select(Tournament))).scalars().all()
        assert len(tournaments) == 1
        assert tournaments[0].regulation == "Reg M-B"

    async def test_sync_handles_missing_team_data(self, limitless_response):
        # player p3 has team_url=None -> must be skipped gracefully rather than crash the sync
        entry = limitless_response["standings"][2]
        assert entry["team_url"] is None

    @respx.mock
    async def test_idempotent_sync(self, db_session, limitless_response):
        tid = limitless_response["id"]
        respx.get(f"{settings.limitless_api_base}/tournaments/{tid}/standings").mock(
            return_value=Response(200, json=limitless_response["standings"])
        )
        respx.get("https://pokepast.es/abc123/raw").mock(
            return_value=Response(200, text=load_fixture("sample_vgc_team.txt"))
        )
        respx.get("https://pokepast.es/def456/raw").mock(
            return_value=Response(200, text=load_fixture("sample_partial_team.txt"))
        )
        respx.post(f"{settings.node_classifier_url}/classify").mock(side_effect=ConnectionError)
        respx.post(f"{settings.node_classifier_url}/validate").mock(side_effect=ConnectionError)

        from sqlalchemy import select

        from models.db import Source, Team, Tournament

        source = Source(platform="limitless", base_url=settings.limitless_api_base, api_available=True)
        db_session.add(source)
        await db_session.flush()

        async with RateLimitedClient() as client:
            await limitless._import_tournament(client, db_session, source, limitless_response)
            await limitless._import_tournament(client, db_session, source, limitless_response)

        tournaments = (await db_session.execute(select(Tournament))).scalars().all()
        teams = (await db_session.execute(select(Team))).scalars().all()
        assert len(tournaments) == 1
        assert len(teams) == 2  # same 2 pastes both times -> deduped, not doubled


@pytest.mark.asyncio
class TestRateLimitRetry:
    @respx.mock
    async def test_rate_limit_retry_honors_retry_after(self):
        route = respx.get("https://example.com/rate-limited")
        route.side_effect = [
            Response(429, headers={"Retry-After": "0"}),
            Response(200, json={"ok": True}),
        ]

        async with RateLimitedClient() as client:
            resp = await client.get("https://example.com/rate-limited")

        assert resp.status_code == 200
        assert route.call_count == 2
