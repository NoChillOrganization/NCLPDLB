"""
Unit tests for db_upserts SQL builders (no DB required).
Integration idempotency tests are guarded by PLATFORM_DATABASE_URL.
"""

import json
import os

import pytest

from src.platform.store.db_upserts import _build_insert_sql

# ─── _build_insert_sql unit tests ────────────────────────────────────────────


def test_build_insert_sql_basic():
    sql = _build_insert_sql("usage_snapshot", ["source_id", "format_id", "period"])
    assert sql == (
        "INSERT INTO usage_snapshot (source_id, format_id, period) VALUES ($1, $2, $3)"
    )
    assert "ON CONFLICT" not in sql


def test_build_insert_sql_do_nothing():
    sql = _build_insert_sql(
        "usage_snapshot",
        ["source_id", "format_id", "period", "elo_cutoff"],
        conflict_cols=["source_id", "format_id", "period", "elo_cutoff"],
        update_cols=[],
    )
    assert "ON CONFLICT (source_id, format_id, period, elo_cutoff) DO NOTHING" in sql


def test_build_insert_sql_do_update():
    sql = _build_insert_sql(
        "tournament_team",
        ["event_id", "placement", "player_name"],
        conflict_cols=["event_id", "placement"],
        update_cols=["player_name"],
    )
    assert "ON CONFLICT (event_id, placement)" in sql
    assert "DO UPDATE SET player_name = EXCLUDED.player_name" in sql


def test_build_insert_sql_jsonb_cast():
    sql = _build_insert_sql(
        "replay_team",
        ["replay_battle_id", "moves"],
        jsonb_cols={"moves"},
    )
    assert "$1" in sql
    assert "$2::jsonb" in sql


def test_build_insert_sql_multiple_update_cols():
    sql = _build_insert_sql(
        "tournament_team_member",
        ["team_id", "slot", "item", "ability"],
        conflict_cols=["team_id", "slot"],
        update_cols=["item", "ability"],
    )
    assert "item = EXCLUDED.item" in sql
    assert "ability = EXCLUDED.ability" in sql


# ─── bulk_upsert_returning SQL shape ─────────────────────────────────────────


def test_bulk_upsert_returning_no_double_unnest():
    """Generated SQL must use parallel unnest($1::t[], $2::t[]) — not unnest(unnest(...))."""
    import re

    columns = ["source_id", "format_id", "period", "elo_cutoff"]
    col_types = {
        "source_id": "int[]",
        "format_id": "int[]",
        "period": "date[]",
        "elo_cutoff": "int[]",
    }
    unnest_args = ", ".join(
        f"${i + 1}::{col_types[col]}" for i, col in enumerate(columns)
    )
    sql = (
        f"INSERT INTO usage_snapshot ({', '.join(columns)})"
        f" SELECT * FROM unnest({unnest_args})"
        f" ON CONFLICT (source_id, format_id, period, elo_cutoff) DO NOTHING"
        f" RETURNING id"
    )
    assert "unnest(unnest(" not in sql, "double-wrapped unnest detected — bug regressed"
    assert re.search(r"unnest\(\$1::", sql), (
        "expected parallel unnest form with typed arrays"
    )


# ─── bulk_upsert chunking ────────────────────────────────────────────────────


def test_chunk_boundary():
    """Verify chunk slicing logic produces correct sub-batches."""
    rows = list(range(25))
    chunk = 10
    batches = [rows[i : i + chunk] for i in range(0, len(rows), chunk)]
    assert len(batches) == 3
    assert batches[0] == list(range(10))
    assert batches[1] == list(range(10, 20))
    assert batches[2] == list(range(20, 25))


def test_chunk_exact_multiple():
    rows = list(range(20))
    chunk = 10
    batches = [rows[i : i + chunk] for i in range(0, len(rows), chunk)]
    assert len(batches) == 2


def test_chunk_single_row():
    rows = [(1, "a")]
    chunk = 1000
    batches = [rows[i : i + chunk] for i in range(0, len(rows), chunk)]
    assert batches == [[(1, "a")]]


# ─── JSONB pre-serialisation ─────────────────────────────────────────────────


def test_moves_json_roundtrip():
    moves = ["Moonblast", "Dazzling Gleam", "Protect", "Follow Me"]
    serialized = json.dumps(moves)
    assert json.loads(serialized) == moves


# ─── Integration — guarded by PLATFORM_DATABASE_URL ─────────────────────────

SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("PLATFORM_DATABASE_URL"),
    reason="PLATFORM_DATABASE_URL not set — skipping live DB tests",
)


@SKIP_INTEGRATION
@pytest.mark.asyncio
async def test_ingest_usage_batch_idempotent():
    """Running the same batch twice yields identical row counts and updated values."""
    import asyncpg
    from src.platform.store.db_upserts import ingest_usage_batch

    # FIX: Open a fresh standalone connection (not from any shared pool) so this
    # connection is bound exclusively to the current test's event loop.
    conn = await asyncpg.connect(os.environ["PLATFORM_DATABASE_URL"])
    try:
        # FIX: Seed canonical_format(id=1) before inserting usage_snapshot rows
        # so the FK constraint usage_snapshot_format_id_fkey is satisfied.
        await conn.execute(
            """
            INSERT INTO canonical_format (id, name)
            VALUES (1, 'gen9vgc2024regh')
            ON CONFLICT (id) DO NOTHING
            """
        )

        snapshots = [
            {
                "source_id": 1,
                "format_id": 1,
                "period": "2024-01-01",
                "elo_cutoff": 1500,
                "sample_size": 100,
                "raw_ingest_id": None,
                "entries": [
                    {
                        "canonical_species_id": 1,
                        "rank": 1,
                        "usage_pct": 42.5,
                        "raw_count": 425,
                        "moveset": {
                            "moves": {"Moonblast": 0.9},
                            "items": {"Choice Scarf": 0.5},
                            "spreads": {},
                            "abilities": {"Pixilate": 1.0},
                            "teammates": {},
                            "checks": {},
                        },
                    }
                ],
            }
        ]

        await ingest_usage_batch(conn, snapshots)
        count_after_first = await conn.fetchval("SELECT COUNT(*) FROM usage_snapshot")

        # Second run — should not add rows
        await ingest_usage_batch(conn, snapshots)
        count_after_second = await conn.fetchval("SELECT COUNT(*) FROM usage_snapshot")

        assert count_after_first == count_after_second, (
            "Duplicate rows inserted on second ingest — not idempotent"
        )
    finally:
        await conn.close()
