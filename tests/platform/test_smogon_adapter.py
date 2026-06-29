"""Fixture-based parser tests for SmogonAdapter."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.platform.sources.smogon import SmogonAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_fetch_from_fixture():
    data = json.loads((FIXTURES / "smogon_usage_gen9vgc.json").read_text())
    with patch(
        "src.platform.sources.smogon.get_json", new=AsyncMock(return_value=data)
    ):
        records = list(
            await SmogonAdapter().fetch(
                period="2026-05",
                formats=["gen9vgc2025regi"],
                cutoff=1500,
            )
        )
    assert len(records) == 1
    rec = records[0]
    assert rec.natural_key == "gen9vgc2025regi-1500-2026-05"
    assert rec.route == "usage"
    assert "data" in rec.payload
    assert "Urshifu-Rapid-Strike" in rec.payload["data"]
    assert "Flutter Mane" in rec.payload["data"]


@pytest.mark.asyncio
async def test_fetch_multiple_formats():
    data = json.loads((FIXTURES / "smogon_usage_gen9vgc.json").read_text())
    with patch(
        "src.platform.sources.smogon.get_json", new=AsyncMock(return_value=data)
    ):
        records = list(
            await SmogonAdapter().fetch(
                period="2026-05",
                formats=["gen9vgc2025regi", "gen9ou"],
                cutoff=1500,
            )
        )
    assert len(records) == 2
    keys = {r.natural_key for r in records}
    assert "gen9vgc2025regi-1500-2026-05" in keys
    assert "gen9ou-1500-2026-05" in keys


@pytest.mark.asyncio
async def test_fetch_skips_missing_format():
    """get_json returns None (404) → no record for that format."""
    with patch(
        "src.platform.sources.smogon.get_json", new=AsyncMock(return_value=None)
    ):
        records = list(
            await SmogonAdapter().fetch(
                period="2026-05",
                formats=["gen9vgc2025regi"],
                cutoff=1500,
            )
        )
    assert records == []


@pytest.mark.asyncio
async def test_fetch_skips_malformed_response():
    """Response missing 'data' key → not wrapped as RawRecord."""
    bad_data = {"info": {"metagame": "gen9vgc2025regi"}}  # no 'data' key
    with patch(
        "src.platform.sources.smogon.get_json", new=AsyncMock(return_value=bad_data)
    ):
        records = list(
            await SmogonAdapter().fetch(
                period="2026-05",
                formats=["gen9vgc2025regi"],
                cutoff=1500,
            )
        )
    assert records == []
