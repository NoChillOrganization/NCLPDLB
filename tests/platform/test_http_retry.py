"""Unit tests for src.platform.sources.http.get_json — no DB, no real network."""

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from src.platform.retry import RateLimited
from src.platform.sources.http import _parse_retry_after, get_json


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
    failing_cm.__aenter__ = AsyncMock(
        side_effect=aiohttp.ClientConnectionError("timeout")
    )
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


# ---------------------------------------------------------------------------
# 429 → RateLimited raised after exhaustion
# ---------------------------------------------------------------------------


def _make_cm_429(retry_after: str | None = None):
    resp = MagicMock()
    resp.status = 429
    headers = MagicMock()
    headers.get = MagicMock(return_value=retry_after)
    resp.headers = headers
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_raises_rate_limited_after_max_tries_on_429():
    """Persistent 429 exhausts retries → RateLimited propagates."""
    session = _make_session(_make_cm_429(), _make_cm_429())
    with pytest.raises(RateLimited):
        await get_json(session, "https://example.com", max_tries=2, base_delay=0)
    assert session.get.call_count == 2


@pytest.mark.asyncio
async def test_429_with_retry_after_header_propagates_value():
    """RateLimited carries the parsed Retry-After seconds from the header."""
    session = _make_session(_make_cm_429("5"), _make_cm_429("5"))
    with pytest.raises(RateLimited) as exc_info:
        await get_json(session, "https://example.com", max_tries=2, base_delay=0)
    assert exc_info.value.retry_after == 5.0


# ---------------------------------------------------------------------------
# _parse_retry_after — ValueError branch (non-float string)
# ---------------------------------------------------------------------------


def test_parse_retry_after_returns_none_for_http_date_string():
    """Non-numeric Retry-After header (HTTP-date) → None, not ValueError."""
    headers = MagicMock()
    headers.get = MagicMock(return_value="Wed, 01 Jan 2025 00:00:00 GMT")
    assert _parse_retry_after(headers) is None


def test_parse_retry_after_returns_none_when_absent():
    headers = MagicMock()
    headers.get = MagicMock(return_value=None)
    assert _parse_retry_after(headers) is None


def test_parse_retry_after_returns_float_for_delta_seconds():
    headers = MagicMock()
    headers.get = MagicMock(return_value="30")
    assert _parse_retry_after(headers) == 30.0


# ---------------------------------------------------------------------------
# limiter.acquire() called when limiter provided
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_limiter_acquire_called_before_each_attempt():
    """When limiter is provided, acquire() is awaited once per attempt."""
    limiter = MagicMock()
    limiter.acquire = AsyncMock()
    session = _make_session(_make_cm(503), _make_cm(200, {"ok": True}))
    result = await get_json(
        session, "https://example.com", max_tries=2, base_delay=0, limiter=limiter
    )
    assert result == {"ok": True}
    assert limiter.acquire.call_count == 2
