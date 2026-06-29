"""Fixture-based parser tests for PikalyticsAdapter.

NOTE: The Pikalytics API payload shape is best-effort (no verified live sample
as of 2026-06-23). These tests document the expected structure and will catch
any drift once a real payload is confirmed.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.platform.sources.pikalytics import PikalyticsAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_fetch_single_page_from_fixture():
    page_data = json.loads((FIXTURES / "pikalytics_gen9vgc.json").read_text())
    # page 0 returns data; page 1 returns None → stop paginating
    with patch(
        "src.platform.sources.pikalytics.get_json",
        new=AsyncMock(side_effect=[page_data, None]),
    ):
        records = list(
            await PikalyticsAdapter().fetch(
                formats=["gen9vgc2025regi"],
                max_pages=2,
            )
        )
    assert len(records) == 1
    rec = records[0]
    assert rec.natural_key == "pikalytics-gen9vgc2025regi"
    assert rec.route == "usage"
    assert rec.payload["format"] == "gen9vgc2025regi"
    assert len(rec.payload["entries"]) == 5  # 5 entries in fixture
    assert rec.payload["entries"][0]["name"] == "Urshifu-Rapid-Strike"


@pytest.mark.asyncio
async def test_fetch_paginates_across_pages():
    page_data = json.loads((FIXTURES / "pikalytics_gen9vgc.json").read_text())
    page2 = page_data[:2]  # second page has 2 entries
    # page 0: 5 entries, page 1: 2 entries, page 2: None → stop
    with patch(
        "src.platform.sources.pikalytics.get_json",
        new=AsyncMock(side_effect=[page_data, page2, None]),
    ):
        records = list(
            await PikalyticsAdapter().fetch(
                formats=["gen9vgc2025regi"],
                max_pages=3,
            )
        )
    assert len(records) == 1
    assert len(records[0].payload["entries"]) == 7  # 5 + 2


@pytest.mark.asyncio
async def test_fetch_multiple_formats():
    page_data = json.loads((FIXTURES / "pikalytics_gen9vgc.json").read_text())
    with patch(
        "src.platform.sources.pikalytics.get_json",
        new=AsyncMock(side_effect=[page_data, None, page_data, None]),
    ):
        records = list(
            await PikalyticsAdapter().fetch(
                formats=["gen9vgc2025regi", "gen9ou"],
                max_pages=2,
            )
        )
    assert len(records) == 2
    keys = {r.natural_key for r in records}
    assert "pikalytics-gen9vgc2025regi" in keys
    assert "pikalytics-gen9ou" in keys


@pytest.mark.asyncio
async def test_fetch_empty_format_produces_no_record():
    """Empty response (unknown format) → no record."""
    with patch(
        "src.platform.sources.pikalytics.get_json", new=AsyncMock(return_value=None)
    ):
        records = list(
            await PikalyticsAdapter().fetch(
                formats=["unknown-format"],
                max_pages=2,
            )
        )
    assert records == []
