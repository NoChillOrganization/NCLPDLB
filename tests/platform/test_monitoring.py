"""Unit tests for monitoring.check_alerts — uses a mock asyncpg connection."""
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta

import pytest

from src.platform.monitoring import check_alerts


def _conn(fetch_results: list[list]) -> AsyncMock:
    """Mock asyncpg connection whose fetch() returns successive lists."""
    conn = AsyncMock()
    conn.fetch.side_effect = fetch_results
    return conn


def _row(name, last_ok=None):
    r = MagicMock()
    r.__getitem__ = lambda self, k: {"name": name, "last_ok": last_ok}[k]
    return r


@pytest.mark.asyncio
async def test_no_alerts_all_healthy():
    now = datetime.now(timezone.utc)
    # source_health row: smogon succeeded 1 day ago (well within 35d threshold)
    smogon_row = {"name": "smogon", "last_ok": now - timedelta(days=1)}
    conn = _conn([
        [smogon_row],   # stale query
        [],              # repeated failure query
        [],              # volume drop query
        [],              # parse errors query
    ])
    conn.fetch.side_effect = [
        [smogon_row], [], [], [],
    ]
    alerts = await check_alerts(conn)
    assert alerts == []


@pytest.mark.asyncio
async def test_stale_sync_fires_when_no_ok_run():
    row = MagicMock()
    row.__getitem__ = lambda self, k: {"name": "showdown", "last_ok": None}[k]
    conn = AsyncMock()
    conn.fetch.side_effect = [[row], [], [], []]
    alerts = await check_alerts(conn)
    assert len(alerts) == 1
    assert alerts[0]["type"] == "STALE_SYNC"
    assert alerts[0]["source"] == "showdown"
    assert "action" in alerts[0]


@pytest.mark.asyncio
async def test_stale_sync_fires_when_overdue():
    now = datetime.now(timezone.utc)
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "name": "limitless",
        "last_ok": now - timedelta(days=5),  # > 2d threshold for daily source
    }[k]
    conn = AsyncMock()
    conn.fetch.side_effect = [[row], [], [], []]
    alerts = await check_alerts(conn)
    stale = [a for a in alerts if a["type"] == "STALE_SYNC"]
    assert len(stale) == 1
    assert stale[0]["age_days"] > 2


@pytest.mark.asyncio
async def test_repeated_failure_alert():
    row = MagicMock()
    row.__getitem__ = lambda self, k: {"name": "smogon", "error_count": 3}[k]
    conn = AsyncMock()
    conn.fetch.side_effect = [[], [row], [], []]
    alerts = await check_alerts(conn)
    assert len(alerts) == 1
    assert alerts[0]["type"] == "REPEATED_FAILURE"
    assert alerts[0]["consecutive_errors"] == 3


@pytest.mark.asyncio
async def test_volume_drop_alert():
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "name": "pikalytics", "last_landed": 3, "avg_30d": 50,
    }[k]
    conn = AsyncMock()
    conn.fetch.side_effect = [[], [], [row], []]
    alerts = await check_alerts(conn)
    assert len(alerts) == 1
    assert alerts[0]["type"] == "VOLUME_DROP"
    assert alerts[0]["last_landed"] == 3


@pytest.mark.asyncio
async def test_parse_errors_alert():
    row = MagicMock()
    row.__getitem__ = lambda self, k: {"name": "limitless", "dl_count": 12}[k]
    conn = AsyncMock()
    conn.fetch.side_effect = [[], [], [], [row]]
    alerts = await check_alerts(conn)
    assert len(alerts) == 1
    assert alerts[0]["type"] == "PARSE_ERRORS"
    assert alerts[0]["dead_letter_24h"] == 12


@pytest.mark.asyncio
async def test_multiple_alerts_accumulate():
    now = datetime.now(timezone.utc)
    stale_row = MagicMock()
    stale_row.__getitem__ = lambda self, k: {
        "name": "showdown", "last_ok": now - timedelta(days=10),
    }[k]
    fail_row = MagicMock()
    fail_row.__getitem__ = lambda self, k: {"name": "smogon", "error_count": 3}[k]
    conn = AsyncMock()
    conn.fetch.side_effect = [[stale_row], [fail_row], [], []]
    alerts = await check_alerts(conn)
    types = {a["type"] for a in alerts}
    assert "STALE_SYNC" in types
    assert "REPEATED_FAILURE" in types
