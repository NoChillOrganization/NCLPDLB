"""Unit tests for src.platform.sources.http.get_json — no DB, no real network."""
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from src.platform.sources.http import get_json


def _make_cm(status: int, body=None):
    """Return an async context manager wrapping a fake aiohttp response."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=body)
    # raise_for_status used when RETRY_STATUS exhausted on last attempt
    resp.raise_for_status = MagicMock(
        side_effect=aiohttp.ClientResponseError(MagicMock(), (), status=status)
    )
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_session(*cms):
    """Fake ClientSession whose .get() returns *cms in order."""
    session = MagicMock()
    if len(cms) == 1:
        session.get = MagicMock(return_value=cms[0])
    else:
        session.get = MagicMock(side_effect=list(cms))
    return session


# ---------------------------------------------------------------------------
# Retry: 503 then 200
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retries_on_transient_503_then_succeeds():
    """503 on first attempt, 200 on second → returns JSON body."""
    session = _make_session(
        _make_cm(503),
        _make_cm(200, {"ok": True}),
    )
    result = await get_json(session, "https://example.com", max_tries=2, base_delay=0)
    assert result == {"ok": True}
    assert session.get.call_count == 2


# ---------------------------------------------------------------------------
# Exhaustion: always 503 → raises
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_raises_after_max_tries_on_persistent_503():
    """Persistent 503 across all attempts → ClientResponseError raised."""
    session = _make_session(
        _make_cm(503),
        _make_cm(503),
    )
    with pytest.raises(aiohttp.ClientResponseError):
        await get_json(session, "https://example.com", max_tries=2, base_delay=0)
    assert session.get.call_count == 2


# ---------------------------------------------------------------------------
# Clean miss: 404 → None, no retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_returns_none_on_404_without_retry():
    """404 is a clean miss (unknown format slug) — returns None immediately."""
    session = _make_session(_make_cm(404))
    result = await get_json(session, "https://example.com", max_tries=4, base_delay=0)
    assert result is None
    assert session.get.call_count == 1  # no retry


# ---------------------------------------------------------------------------
# Transport error retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retries_on_transport_error():
    """aiohttp.ClientConnectionError on first attempt, 200 on second → returns JSON."""
    failing_cm = MagicMock()
    failing_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("timeout"))
    failing_cm.__aexit__ = AsyncMock(return_value=False)

    session = _make_session(
        failing_cm,
        _make_cm(200, {"data": "ok"}),
    )
    result = await get_json(session, "https://example.com", max_tries=2, base_delay=0)
    assert result == {"data": "ok"}


# ---------------------------------------------------------------------------
# 200 returns body on first try
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_returns_json_on_200():
    session = _make_session(_make_cm(200, [1, 2, 3]))
    result = await get_json(session, "https://example.com", max_tries=1, base_delay=0)
    assert result == [1, 2, 3]
    assert session.get.call_count == 1
