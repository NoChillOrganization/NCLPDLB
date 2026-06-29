"""Tests for src.platform.throttle and Retry-After integration in retry_async."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.platform.throttle import RateLimiter, get_limiter
from src.platform.retry import RateLimited, retry_async


# ─── RateLimiter ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limiter_enforces_min_interval():
    """Two consecutive acquires should be separated by at least min_interval."""
    limiter = RateLimiter(min_interval=0.05)
    t0 = time.monotonic()
    await limiter.acquire()
    await limiter.acquire()
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.05, f"Expected ≥0.05s, got {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_rate_limiter_first_acquire_immediate():
    """First acquire on a fresh limiter should return without sleeping."""
    limiter = RateLimiter(min_interval=1.0)
    t0 = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - t0
    # Should be well under 0.1s (no sleep path taken)
    assert elapsed < 0.1, f"First acquire took {elapsed:.3f}s — expected immediate"


def test_get_limiter_returns_singleton():
    """Same source key → same object (module-level registry)."""
    # Use a unique source name to avoid cross-test contamination
    a = get_limiter("_test_source_singleton_")
    b = get_limiter("_test_source_singleton_")
    assert a is b


def test_get_limiter_default_interval_for_unknown_source():
    """Unknown source falls back to _DEFAULT_INTERVAL (1.0s)."""
    from src.platform.throttle import _DEFAULT_INTERVAL
    lim = get_limiter("_unknown_source_xyz_")
    assert lim._min_interval == _DEFAULT_INTERVAL


def test_get_limiter_known_sources_have_configured_intervals():
    """Known sources use their configured intervals."""
    from src.platform.throttle import _LIMITS
    for source, expected in _LIMITS.items():
        lim = get_limiter(source)
        assert lim._min_interval == expected, (
            f"source={source}: expected {expected}, got {lim._min_interval}"
        )


# ─── RateLimited sentinel ────────────────────────────────────────────────────

def test_rate_limited_carries_retry_after():
    exc = RateLimited(retry_after=5.0)
    assert exc.retry_after == 5.0


def test_rate_limited_none_retry_after():
    exc = RateLimited(retry_after=None)
    assert exc.retry_after is None


# ─── retry_async respects Retry-After hint ───────────────────────────────────

@pytest.mark.asyncio
async def test_retry_async_uses_retry_after_as_floor():
    """When the exception carries retry_after, retry_async should sleep at least that long."""
    sleep_calls: list[float] = []
    attempt = 0

    async def flaky():
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            raise RateLimited(retry_after=2.5)
        return "ok"

    with patch("src.platform.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await retry_async(flaky, base_delay=0.0)

    assert result == "ok"
    assert mock_sleep.call_count == 1
    actual_delay = mock_sleep.call_args[0][0]
    assert actual_delay >= 2.5, f"Expected sleep ≥ 2.5s (Retry-After), got {actual_delay}"


@pytest.mark.asyncio
async def test_retry_async_jitter_when_no_retry_after():
    """Without retry_after hint, sleep is random in [0, base * 2^attempt]."""
    attempt = 0

    async def flaky():
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            import aiohttp
            raise aiohttp.ServerConnectionError("boom")
        return "done"

    with patch("src.platform.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await retry_async(flaky, base_delay=1.0)

    assert result == "done"
    assert mock_sleep.call_count == 1
    actual_delay = mock_sleep.call_args[0][0]
    # full-jitter: [0, 1.0 * 2^0] = [0, 1.0]
    assert 0.0 <= actual_delay <= 1.0


# ─── http.py Retry-After parse ───────────────────────────────────────────────

def test_parse_retry_after_integer():
    from src.platform.sources.http import _parse_retry_after
    headers = MagicMock()
    headers.get = lambda k: "30"
    assert _parse_retry_after(headers) == 30.0


def test_parse_retry_after_float():
    from src.platform.sources.http import _parse_retry_after
    headers = MagicMock()
    headers.get = lambda k: "1.5"
    assert _parse_retry_after(headers) == 1.5


def test_parse_retry_after_absent():
    from src.platform.sources.http import _parse_retry_after
    headers = MagicMock()
    headers.get = lambda k: None
    assert _parse_retry_after(headers) is None


def test_parse_retry_after_http_date_falls_back_to_none():
    from src.platform.sources.http import _parse_retry_after
    headers = MagicMock()
    headers.get = lambda k: "Wed, 21 Oct 2015 07:28:00 GMT"
    assert _parse_retry_after(headers) is None


def test_parse_retry_after_negative_clamped_to_zero():
    from src.platform.sources.http import _parse_retry_after
    headers = MagicMock()
    headers.get = lambda k: "-5"
    assert _parse_retry_after(headers) == 0.0
