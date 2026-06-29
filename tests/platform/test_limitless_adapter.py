from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.platform.sources.limitless import LimitlessAdapter


def _fake_get_cm(payload):
    fake_resp = MagicMock()
    fake_resp.status = 200
    fake_resp.json = AsyncMock(return_value=payload)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_fetch_by_ids():
    details = {"name": "Regional", "format": "I", "date": "2026-01-01", "isOnline": False}
    standings = [{"placing": 1, "name": "Ash", "player": "p1", "decklist": []}]

    fake_session = MagicMock()
    fake_session.get = MagicMock(side_effect=[_fake_get_cm(details), _fake_get_cm(standings)])
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=fake_session_cm):
        records = await LimitlessAdapter().fetch(ids=["123"])

    assert len(records) == 1
    assert records[0].natural_key == "123"
    assert records[0].payload["event"]["name"] == "Regional"
    assert records[0].payload["standings"][0]["name"] == "Ash"


@pytest.mark.asyncio
async def test_fetch_skips_missing_details():
    fake_resp = MagicMock()
    fake_resp.status = 404
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_resp)
    cm.__aexit__ = AsyncMock(return_value=False)

    fake_session = MagicMock()
    fake_session.get = MagicMock(return_value=cm)
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=fake_session_cm):
        records = await LimitlessAdapter().fetch(ids=["404"])

    assert records == []
