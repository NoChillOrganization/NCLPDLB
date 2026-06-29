from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.platform.sources.showdown import ShowdownAdapter


@pytest.mark.asyncio
async def test_fetch_by_ids():
    fake_resp = MagicMock()
    fake_resp.status = 200
    fake_resp.json = AsyncMock(return_value={"id": "gen9ou-1", "log": "|j|p1"})
    fake_get_cm = MagicMock()
    fake_get_cm.__aenter__ = AsyncMock(return_value=fake_resp)
    fake_get_cm.__aexit__ = AsyncMock(return_value=False)

    fake_session = MagicMock()
    fake_session.get = MagicMock(return_value=fake_get_cm)
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=fake_session_cm):
        records = await ShowdownAdapter().fetch(ids=["gen9ou-1"])

    assert len(records) == 1
    assert records[0].natural_key == "gen9ou-1"
    assert records[0].payload["log"] == "|j|p1"
