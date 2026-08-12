"""
Bulk upsert helpers for platform source ingestion.

Two generic helpers for performance:
  - bulk_upsert()           — chunked executemany; no RETURNING (children, large sets)
  - bulk_upsert_returning() — single unnest statement with RETURNING (parents needing id maps)

The three domain orchestrators that use these helpers (extracted to separate modules to
keep this file under the 800-line guideline) enforce parent-before-child ordering and
idempotency:
  - upserts_usage.ingest_usage_batch()             — usage_snapshot → usage_entry → usage_moveset
  - upserts_replays.ingest_replays_batch()         — replay → replay_battle → replay_team / replay_move
  - upserts_tournament.ingest_tournament_batch()   — tournament_event → tournament_team → team_member / match

Conflict-key notes:
  - tournament_team and match use COALESCE-based functional unique indexes (0005_dedup_indexes.sql)
    so NULL-keyed rows deduplicate correctly on re-run. ON CONFLICT uses expression form.
  - replay_team has no unique constraint — full-rebuild (delete + insert) is used instead.
  - replay_move has a unique but move_name/player_slot are nullable → full-rebuild also used.
"""

from typing import Any

import asyncpg

# ─── Generic helpers ──────────────────────────────────────────────────────────


def _build_insert_sql(
    table: str,
    columns: list[str],
    *,
    conflict_cols: list[str] | None = None,
    conflict_target: str | None = None,
    update_cols: list[str] | None = None,
    jsonb_cols: set[str] | None = None,
) -> str:
    """Return parametric INSERT SQL for executemany (positional $1..$n placeholders).

    conflict_target, when supplied, overrides conflict_cols for the ON CONFLICT clause.
    Use it for functional unique indexes where COALESCE expressions are needed.
    """
    jsonb_cols = jsonb_cols or set()
    placeholders = ", ".join(
        f"${i + 1}::jsonb" if col in jsonb_cols else f"${i + 1}"
        for i, col in enumerate(columns)
    )
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    if conflict_target is not None:
        clause = f"ON CONFLICT ({conflict_target})"
        if update_cols:
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
            sql += f" {clause} DO UPDATE SET {updates}"
        else:
            sql += f" {clause} DO NOTHING"
    elif conflict_cols:
        conflict_clause = f"ON CONFLICT ({', '.join(conflict_cols)})"
        if update_cols:
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
            sql += f" {conflict_clause} DO UPDATE SET {updates}"
        else:
            sql += f" {conflict_clause} DO NOTHING"
    return sql


async def bulk_upsert(
    conn: asyncpg.Connection,
    table: str,
    columns: list[str],
    rows: list[tuple],
    *,
    conflict_cols: list[str] | None = None,
    conflict_target: str | None = None,
    update_cols: list[str] | None = None,
    jsonb_cols: set[str] | None = None,
    chunk: int = 1000,
) -> int:
    """
    Bulk insert rows via executemany in chunk-sized pages.

    Returns total row count attempted (not affected — executemany can't RETURNING).
    JSONB columns: caller must pre-serialize to str; SQL casts via ::jsonb.
    conflict_target overrides conflict_cols for functional unique index expressions.
    """
    if not rows:
        return 0
    sql = _build_insert_sql(
        table,
        columns,
        conflict_cols=conflict_cols,
        conflict_target=conflict_target,
        update_cols=update_cols,
        jsonb_cols=jsonb_cols,
    )
    total = 0
    for offset in range(0, len(rows), chunk):
        batch = rows[offset : offset + chunk]
        await conn.executemany(sql, batch)
        total += len(batch)
    return total


async def bulk_upsert_returning(
    conn: asyncpg.Connection,
    table: str,
    columns: list[str],
    rows: list[tuple],
    *,
    conflict_cols: list[str],
    conflict_target: str | None = None,
    update_cols: list[str],
    key_cols: list[str],
    col_types: dict[str, str],
    return_col: str = "id",
    jsonb_cols: set[str] | None = None,
) -> dict[tuple, Any]:
    """
    Single-statement unnest INSERT with RETURNING for FK wiring.

    Uses SELECT * FROM unnest($1::t[], $2::t[], ...) so all rows land in one round-trip.
    Returns {tuple(key_col values): return_col value}.

    col_types must supply a Postgres array type per column, e.g.:
        {"source_id": "int[]", "replay_id": "text[]", "period": "date[]", "payload": "jsonb[]"}

    conflict_target overrides conflict_cols for functional unique index expressions.
    """
    if not rows:
        return {}
    jsonb_cols = jsonb_cols or set()

    # Transpose rows to column-arrays for unnest
    by_col = [list(col) for col in zip(*rows)]
    params = by_col  # $1 = first column array, $2 = second, etc.

    unnest_args = ", ".join(
        f"${i + 1}::{col_types[col]}" for i, col in enumerate(columns)
    )
    col_list = ", ".join(columns)
    # Build: INSERT INTO t (c1,c2,...) SELECT * FROM unnest($1::t1[],$2::t2[],...)
    if conflict_target is not None:
        conflict_clause = f"ON CONFLICT ({conflict_target})"
    else:
        conflict_clause = f"ON CONFLICT ({', '.join(conflict_cols)})"
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    returning = f"{return_col}, {', '.join(key_cols)}"

    sql = (
        f"INSERT INTO {table} ({col_list})"
        f" SELECT * FROM unnest({unnest_args})"
        f" {conflict_clause} DO UPDATE SET {updates}"
        f" RETURNING {returning}"
    )
    result: dict[tuple, Any] = {}
    for rec in await conn.fetch(sql, *params):
        key = tuple(rec[k] for k in key_cols)
        result[key] = rec[return_col]
    return result
