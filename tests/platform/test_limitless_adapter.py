import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.platform.sources.limitless import LimitlessAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_fetch_by_ids_from_fixture():
    """Happy path: fetch tournament by ID, returns structured RawRecord."""
    details = json.loads((FIXTURES / "limitless_tournament_details.json").read_text())
    standings = json.loads(
        (FIXTURES / "limitless_tournament_standings.json").read_text()
    )

    with patch(
        "src.platform.sources.limitless.get_json",
        new=AsyncMock(side_effect=[details, standings]),
    ):
        records = list(await LimitlessAdapter().fetch(ids=["fixture-regional-2026"]))

    assert len(records) == 1
    rec = records[0]
    assert rec.natural_key == "fixture-regional-2026"
    assert rec.route == "tournament"
    assert rec.payload["event"]["name"] == "Fixture Regional 2026"
    assert rec.payload["event"]["game"] == "VGC"
    assert len(rec.payload["standings"]) == 2
    assert rec.payload["standings"][0]["placing"] == 1
    assert rec.payload["standings"][0]["name"] == "Ash Ketchum"
    assert len(rec.payload["standings"][0]["decklist"]) == 2


@pytest.mark.asyncio
async def test_fetch_multiple_ids():
    details = json.loads((FIXTURES / "limitless_tournament_details.json").read_text())
    standings = json.loads(
        (FIXTURES / "limitless_tournament_standings.json").read_text()
    )

    # Two tournaments: details+standings for each
    with patch(
        "src.platform.sources.limitless.get_json",
        new=AsyncMock(side_effect=[details, standings, details, standings]),
    ):
        records = list(await LimitlessAdapter().fetch(ids=["t1", "t2"]))

    assert len(records) == 2
    assert records[0].natural_key == "t1"
    assert records[1].natural_key == "t2"


@pytest.mark.asyncio
async def test_fetch_skips_missing_details():
    """None details (404) → tournament skipped entirely."""
    with patch(
        "src.platform.sources.limitless.get_json", new=AsyncMock(return_value=None)
    ):
        records = list(await LimitlessAdapter().fetch(ids=["missing-id"]))

    assert records == []


@pytest.mark.asyncio
async def test_fetch_empty_standings_still_produces_record():
    """Missing standings → empty list in payload, record still created."""
    details = json.loads((FIXTURES / "limitless_tournament_details.json").read_text())

    with patch(
        "src.platform.sources.limitless.get_json",
        new=AsyncMock(side_effect=[details, None]),
    ):
        records = list(await LimitlessAdapter().fetch(ids=["t1"]))

    assert len(records) == 1
    assert records[0].payload["standings"] == []
