"""Tests for dry_run_normalize and with_ingest_run in orchestrate.py."""

from unittest.mock import AsyncMock

import pytest

from src.platform.orchestrate import dry_run_normalize, with_ingest_run
from src.platform.sources.base import RawRecord


def _rec(natural_key="k1", payload=None):
    return RawRecord(
        route="usage", natural_key=natural_key, payload=payload or {"x": 1}
    )


@pytest.mark.asyncio
async def test_dry_run_normalize_valid():
    records = [_rec("k1"), _rec("k2", {"data": [1, 2]})]
    stats = await dry_run_normalize(records)
    assert stats == {"fetched": 2, "normalized": 2, "errored": 0}


@pytest.mark.asyncio
async def test_dry_run_normalize_empty_key():
    records = [_rec(""), _rec("ok")]
    stats = await dry_run_normalize(records)
    assert stats["errored"] == 1
    assert stats["normalized"] == 1
    assert stats["fetched"] == 2


@pytest.mark.asyncio
async def test_dry_run_normalize_empty_payload():
    records = [RawRecord(route="usage", natural_key="k1", payload={})]
    stats = await dry_run_normalize(records)
    assert stats == {"fetched": 1, "normalized": 0, "errored": 1}


@pytest.mark.asyncio
async def test_dry_run_normalize_empty_list():
    stats = await dry_run_normalize([])
    assert stats == {"fetched": 0, "normalized": 0, "errored": 0}


@pytest.mark.asyncio
async def test_dry_run_normalize_writes_nothing(monkeypatch):
    """Confirm no DB functions are called during dry_run_normalize."""
    import src.platform.store.repositories as repos

    called = []
    monkeypatch.setattr(repos, "land_raw", lambda *a, **kw: called.append("land_raw"))
    monkeypatch.setattr(
        repos, "to_dead_letter", lambda *a, **kw: called.append("dead_letter")
    )
    await dry_run_normalize([_rec()])
    assert called == [], "dry_run_normalize must not touch DB"


@pytest.mark.asyncio
async def test_with_ingest_run_raises_on_unregistered_source():
    """Regression for CI run #29008635041: an unregistered `source` name must
    fail loudly, not silently no-op the INSERT...SELECT and let fn() run with
    no health-tracking row (which froze showdown's STALE_SYNC monitor)."""
    conn = AsyncMock()
    conn.fetchval.return_value = None  # SELECT ... WHERE name = $1 matched nothing

    fn_called = []

    async def fn():
        fn_called.append(True)
        return {"landed": 1}

    with pytest.raises(ValueError, match="no `source` row named"):
        await with_ingest_run(
            conn, source="not_a_real_source", route="replay", mode="periodic", fn=fn
        )
    assert fn_called == [], "fn() must not run when the source row wasn't created"
