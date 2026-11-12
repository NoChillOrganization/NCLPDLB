"""Pins per-Source facts every entry point must share (see source_spec.py)."""

import argparse
import dataclasses

import pytest

from src.platform import source_spec, sync_all
from src.platform.source_spec import SOURCES, run_standalone, sync_source
from src.platform.sources.base import RawRecord


def test_db_names_and_routes():
    assert {k: (s.db_name, s.route) for k, s in SOURCES.items()} == {
        "smogon": ("smogon", "usage"),
        "pikalytics": ("pikalytics", "usage"),
        "limitless": ("limitless", "tournament"),
        "replays": ("showdown", "replay"),
    }


def test_ingest_mode_rules():
    ids = {"ids": ["a"]}
    assert SOURCES["limitless"].mode(ids) == "event"
    assert SOURCES["limitless"].mode({"ids": None}) == "periodic"
    assert SOURCES["replays"].mode(ids) == "replay_targeted"
    assert SOURCES["replays"].mode({"ids": None}) == "periodic"
    for key in ("smogon", "pikalytics"):
        assert SOURCES[key].mode({}) == "periodic"


def _fake_spec(key, records):
    class Fake:
        async def fetch(self, **kw):
            return records

    return dataclasses.replace(SOURCES[key], adapter=Fake)


def _bad(route):
    return [RawRecord(route=route, natural_key="", payload={"x": 1})]


async def test_sync_source_records_db_name_and_mode(monkeypatch):
    seen = {}

    async def fake_run(conn, *, source, route, mode, fn):
        seen.update(source=source, route=route, mode=mode)
        return {}

    monkeypatch.setattr(source_spec, "with_ingest_run", fake_run)
    await sync_source(_fake_spec("replays", []), object(), ids=["x"])
    assert seen == {"source": "showdown", "route": "replay", "mode": "replay_targeted"}


async def test_standalone_dry_run_exits_nonzero_on_errored():
    with pytest.raises(SystemExit) as e:
        await run_standalone(_fake_spec("smogon", _bad("usage")), dry_run=True)
    assert e.value.code == 1


async def test_standalone_dry_run_ok_returns():
    ok = [RawRecord(route="usage", natural_key="k", payload={"x": 1})]
    await run_standalone(_fake_spec("smogon", ok), dry_run=True)


def test_replay_cli_uses_production_defaults(monkeypatch):
    from src.platform import sync_replays

    captured = {}

    async def fake(spec, **kw):
        captured.update(kw)

    monkeypatch.setattr(sync_replays, "run_standalone", fake)
    monkeypatch.setattr("sys.argv", ["sync_replays", "--format", "gen9ou"])
    sync_replays.main()
    assert captured["pages"] == 5
    assert captured["min_rating"] == 1500


async def test_sync_all_dry_run_exits_nonzero_on_errored(monkeypatch):
    monkeypatch.setitem(
        sync_all.SOURCES, "limitless", _fake_spec("limitless", _bad("tournament"))
    )

    class _Conn:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Conn()

    async def fake_pool():
        return _Pool()

    monkeypatch.setattr(sync_all, "get_pool", fake_pool)
    args = argparse.Namespace(
        sources=["limitless"], deadline_seconds=0, dry_run=True, game="VGC", limit=50
    )
    assert await sync_all._run(args) == 1
