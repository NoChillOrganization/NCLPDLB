"""
Unit tests for retry.py (no DB, no network).
Integration dead-letter tests are guarded by PLATFORM_DATABASE_URL.
"""

from __future__ import annotations

import asyncio
import os
import time

import aiohttp
import pytest

from src.platform.retry import (
    RETRY_STATUS,
    Permanent,
    Transient,
    is_transient,
    retry_async,
)


# ─── is_transient classification ─────────────────────────────────────────────


def test_transient_sentinel():
    assert is_transient(Transient("rate limit")) is True


def test_permanent_sentinel():
    assert is_transient(Permanent("bad schema")) is False


def test_connection_error_transient():
    assert is_transient(aiohttp.ServerConnectionError("connection reset")) is True


def test_timeout_transient():
    assert is_transient(asyncio.TimeoutError()) is True


def test_os_error_transient():
    assert is_transient(OSError("ECONNREFUSED")) is True


def test_parse_error_permanent():
    assert is_transient(ValueError("invalid json")) is False


def test_key_error_permanent():
    assert is_transient(KeyError("missing field")) is False


def test_client_response_error_5xx_transient():
    exc = aiohttp.ClientResponseError(None, (), status=503)  # type: ignore[arg-type]
    assert is_transient(exc) is True


def test_client_response_error_429_transient():
    exc = aiohttp.ClientResponseError(None, (), status=429)  # type: ignore[arg-type]
    assert is_transient(exc) is True


def test_client_response_error_404_permanent():
    exc = aiohttp.ClientResponseError(None, (), status=404)  # type: ignore[arg-type]
    assert is_transient(exc) is False


def test_client_response_error_400_permanent():
    exc = aiohttp.ClientResponseError(None, (), status=400)  # type: ignore[arg-type]
    assert is_transient(exc) is False


def test_all_retry_statuses_transient():
    for status in RETRY_STATUS:
        exc = aiohttp.ClientResponseError(None, (), status=status)  # type: ignore[arg-type]
        assert is_transient(exc) is True, f"expected {status} transient"


# ─── retry_async behaviour ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_success_on_first_attempt():
    calls = []

    async def fn() -> str:
        calls.append(1)
        return "ok"

    result = await retry_async(fn, base_delay=0.0)
    assert result == "ok"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_retries_then_succeeds():
    calls = []

    async def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise aiohttp.ServerConnectionError("boom")
        return "ok"

    result = await retry_async(flaky, max_tries=4, base_delay=0.0)
    assert result == "ok"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_permanent_raises_immediately():
    """A permanent error should not trigger any retry (single attempt)."""
    calls = []

    async def bad() -> None:
        calls.append(1)
        raise ValueError("parse error")

    with pytest.raises(ValueError):
        await retry_async(bad, max_tries=4, base_delay=0.0)

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_explicit_permanent_sentinel_no_retry():
    calls = []

    async def bad() -> None:
        calls.append(1)
        raise Permanent("give up")

    with pytest.raises(Permanent):
        await retry_async(bad, max_tries=4, base_delay=0.0)

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_exhausted_all_tries():
    calls = []

    async def always_fail() -> None:
        calls.append(1)
        raise aiohttp.ServerConnectionError("always")

    with pytest.raises(aiohttp.ServerConnectionError):
        await retry_async(always_fail, max_tries=3, base_delay=0.0)

    assert len(calls) == 3


@pytest.mark.asyncio
async def test_deadline_aborts():
    """An already-expired deadline should allow only one attempt."""
    calls = []
    past = time.monotonic() - 1.0  # already expired

    async def fail() -> None:
        calls.append(1)
        raise aiohttp.ServerConnectionError("transient")

    with pytest.raises(aiohttp.ServerConnectionError):
        await retry_async(fail, max_tries=10, base_delay=0.0, deadline=past)

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_custom_classifier():
    """Custom classify= allows caller-side override."""
    calls = []

    async def fail() -> None:
        calls.append(1)
        raise RuntimeError("custom transient")

    # By default RuntimeError is NOT transient — but with custom classify:
    def always_transient(_exc: BaseException) -> bool:
        return True

    with pytest.raises(RuntimeError):
        await retry_async(fail, max_tries=2, base_delay=0.0, classify=always_transient)

    assert len(calls) == 2  # was retried once


# ─── Integration — guarded by PLATFORM_DATABASE_URL ──────────────────────────

SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("PLATFORM_DATABASE_URL"),
    reason="PLATFORM_DATABASE_URL not set — skipping live DB tests",
)


@SKIP_INTEGRATION
@pytest.mark.asyncio
async def test_dead_letter_on_parse_failure():
    """
    Simulate a normalize parse failure:
    - land_raw should produce a raw_ingest row (status='error' after failure)
    - dead_letter should receive a row with the payload and error text
    - Re-running the same record produces no new raw_ingest row (idempotent)
    """
    import asyncpg

    from src.platform.store.repositories import land_raw, mark_raw_error, to_dead_letter

    url = os.environ["PLATFORM_DATABASE_URL"]
    conn = await asyncpg.connect(url)
    try:
        source = "smogon"
        route = "usage"
        key = "dead_letter_test_unique_key_9999"
        payload = {"test": True, "key": key}

        # Land the raw record
        raw_id = await land_raw(
            conn, source=source, route=route, natural_key=key, payload=payload
        )
        assert raw_id is not None, "First land should return an id"

        # Simulate parse failure
        await mark_raw_error(conn, raw_id=raw_id)
        await to_dead_letter(
            conn,
            source=source,
            route=route,
            natural_key=key,
            payload=payload,
            error="ValueError: test error",
        )

        # Verify raw_ingest status flipped
        status = await conn.fetchval(
            "SELECT status FROM raw_ingest WHERE id = $1", raw_id
        )
        assert status == "error", f"expected 'error', got {status!r}"

        # Verify dead_letter row exists
        dl_count = await conn.fetchval(
            "SELECT COUNT(*) FROM dead_letter WHERE natural_key = $1", key
        )
        assert dl_count >= 1, "dead_letter row not found"

        # Idempotency: re-landing the same payload returns None (no new row)
        raw_id2 = await land_raw(
            conn, source=source, route=route, natural_key=key, payload=payload
        )
        assert raw_id2 is None, "Second land of identical payload should return None"

    finally:
        # Cleanup test rows
        await conn.execute("DELETE FROM dead_letter WHERE natural_key = $1", key)
        await conn.execute("DELETE FROM raw_ingest WHERE natural_key = $1", key)
        await conn.close()
