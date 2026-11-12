"""Regression tests for sync_all (key->DB-name mapping now pinned in test_source_spec.py).

Covers the bug from CI run #29008635041: sync_all.py's "replays" branch
passed the raw CLI arg "replays" into with_ingest_run/land_and_normalize
instead of the `source` table's canonical name "showdown", so the daily
replay sync landed data fine but never recorded a health row (silent
INSERT...SELECT no-op in orchestrate.with_ingest_run), leaving showdown's
STALE_SYNC monitor frozen at its last manually-run success.
"""

import argparse

import asyncpg

from src.platform import sync_all


async def test_db_connect_error_returns_one_line_failure(monkeypatch, capsys):
    async def boom():
        raise asyncpg.InvalidCatalogNameError('database "x" does not exist')

    monkeypatch.setattr(sync_all, "migrate", boom)
    args = argparse.Namespace(sources=["limitless"], deadline_seconds=0, dry_run=False)

    assert await sync_all._run(args) == 1
    assert "[db] FAILED: InvalidCatalogNameError" in capsys.readouterr().err
