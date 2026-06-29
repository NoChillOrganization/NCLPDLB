"""Batch path idempotency: running normalize_*_row twice on the same raw payload must
produce stable canonical row counts (no duplicate accumulation).

Guarded by PLATFORM_DATABASE_URL — skipped in unit CI, run in the platform job.
"""

from __future__ import annotations

import os

import pytest

SKIP = pytest.mark.skipif(
    not os.environ.get("PLATFORM_DATABASE_URL"),
    reason="PLATFORM_DATABASE_URL not set — skipping live DB tests",
)


# ─── Unit tests (no DB) ───────────────────────────────────────────────────────


def test_conflict_target_expression_in_sql():
    """COALESCE conflict targets land correctly in generated SQL."""
    from src.platform.store.db_upserts import _build_insert_sql

    sql = _build_insert_sql(
        "tournament_team",
        ["event_id", "placement", "player_external_id"],
        conflict_target="event_id, COALESCE(placement, -1), COALESCE(player_external_id, '')",
        update_cols=["player_name"],
    )
    assert "COALESCE(placement, -1)" in sql
    assert "COALESCE(player_external_id, '')" in sql
    assert "DO UPDATE SET" in sql


def test_conflict_target_overrides_conflict_cols():
    """conflict_target param takes precedence over conflict_cols."""
    from src.platform.store.db_upserts import _build_insert_sql

    sql = _build_insert_sql(
        "match",
        ["event_id", "round"],
        conflict_cols=["event_id", "round"],
        conflict_target="event_id, COALESCE(round, -1)",
        update_cols=["winner_team_id"],
    )
    # Only the COALESCE form should appear, not the bare column list
    assert "COALESCE(round, -1)" in sql
    assert "ON CONFLICT (event_id, round)" not in sql


def test_conflict_target_do_nothing():
    from src.platform.store.db_upserts import _build_insert_sql

    sql = _build_insert_sql(
        "match",
        ["event_id", "round"],
        conflict_target="event_id, COALESCE(round, -1)",
    )
    assert "DO NOTHING" in sql


# ─── Integration — requires live DB ──────────────────────────────────────────


@SKIP
@pytest.mark.asyncio
async def test_ingest_usage_batch_idempotent():
    """Two runs of ingest_usage_batch on identical payload → same snapshot count."""
    import asyncpg

    from src.platform.store.db import migrate
    from src.platform.store.db_upserts import ingest_usage_batch

    await migrate()
    conn = await asyncpg.connect(os.environ["PLATFORM_DATABASE_URL"])
    try:
        snapshot = {
            "source_id": 1,
            "format_id": 1,
            "period": "2025-01-01",
            "elo_cutoff": 1500,
            "sample_size": 10,
            "raw_ingest_id": None,
            "entries": [
                {
                    "canonical_species_id": None,
                    "rank": 1,
                    "usage_pct": 25.0,
                    "raw_count": 25,
                    "moveset": {
                        "moves": {"Protect": 0.9},
                        "items": {},
                        "spreads": {},
                        "abilities": {},
                        "teammates": {},
                        "checks": {},
                    },
                },
            ],
        }
        await ingest_usage_batch(conn, [snapshot])
        count_after_first = await conn.fetchval(
            "SELECT COUNT(*) FROM usage_snapshot WHERE source_id=1 AND format_id=1 AND period='2025-01-01' AND elo_cutoff=1500"
        )
        await ingest_usage_batch(conn, [snapshot])
        count_after_second = await conn.fetchval(
            "SELECT COUNT(*) FROM usage_snapshot WHERE source_id=1 AND format_id=1 AND period='2025-01-01' AND elo_cutoff=1500"
        )
        assert count_after_first == 1
        assert count_after_second == 1, "Second run must not insert duplicate snapshot"
    finally:
        await conn.close()


@SKIP
@pytest.mark.asyncio
async def test_ingest_tournament_batch_null_key_idempotent():
    """tournament_team rows with NULL placement must deduplicate on re-run (0005 fix)."""
    import asyncpg

    from src.platform.store.db import migrate
    from src.platform.store.db_upserts import ingest_tournament_batch

    await migrate()
    conn = await asyncpg.connect(os.environ["PLATFORM_DATABASE_URL"])
    try:
        event = {
            "source_id": 3,  # limitless
            "external_id": "idempotency-test-001",
            "name": "Idempotency Test Event",
            "format_id": 1,
            "event_date": None,
            "level": "online",
            "url": None,
            "raw_ingest_id": None,
            "teams": [
                {
                    "placement": None,
                    "player_name": "TestPlayer",
                    "player_external_id": None,
                    "wins": 3,
                    "losses": 2,
                    "raw_ingest_id": None,
                    "members": [],
                    "matches": [],
                }
            ],
        }
        await ingest_tournament_batch(conn, [event])
        count_first = await conn.fetchval(
            "SELECT COUNT(*) FROM tournament_team WHERE player_name='TestPlayer'"
        )
        await ingest_tournament_batch(conn, [event])
        count_second = await conn.fetchval(
            "SELECT COUNT(*) FROM tournament_team WHERE player_name='TestPlayer'"
        )
        assert count_first == 1
        assert count_second == 1, "NULL-key team row must not accumulate on re-run"
    finally:
        await conn.close()
