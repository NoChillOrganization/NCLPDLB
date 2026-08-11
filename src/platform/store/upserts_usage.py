"""
Usage-snapshot ingestion (Smogon/Pikalytics usage stats).

Extracted from db_upserts.py (which had grown past the project's 800-line
guideline). Orchestrates usage_snapshot -> usage_entry -> usage_moveset
upserts using the generic bulk_upsert()/bulk_upsert_returning() helpers.

Conflict-key notes live in db_upserts.py's module docstring.
"""

import json
from datetime import date

import asyncpg

from src.platform.store.db_upserts import bulk_upsert, bulk_upsert_returning


# ─── Usage ingestion ──────────────────────────────────────────────────────────


async def ingest_usage_batch(
    conn: asyncpg.Connection,
    snapshots: list[dict],
) -> int:
    """
    Bulk-ingest usage data. Parent-before-child order: snapshot → entry → moveset.

    Each dict in snapshots:
        source_id int, format_id int, period date, elo_cutoff int|None,
        sample_size int|None, raw_ingest_id int|None,
        entries: list[dict]  # rank, usage_pct, raw_count, canonical_species_id,
                             #   moveset: dict(moves,items,spreads,abilities,teammates,checks)
    """
    if not snapshots:
        return 0

    # asyncpg encodes date[] client-side: elements must be datetime.date, not str.
    for s in snapshots:
        if isinstance(s["period"], str):
            s["period"] = date.fromisoformat(s["period"])

    async with conn.transaction():
        # 1. Upsert usage_snapshot → get id map keyed by (source_id, format_id, period, elo_cutoff)
        snap_rows = [
            (
                s["source_id"],
                s["format_id"],
                s["period"],
                s.get("elo_cutoff"),
                s.get("sample_size"),
                s.get("raw_ingest_id"),
            )
            for s in snapshots
        ]
        snap_id_map = await bulk_upsert_returning(
            conn,
            "usage_snapshot",
            [
                "source_id",
                "format_id",
                "period",
                "elo_cutoff",
                "sample_size",
                "raw_ingest_id",
            ],
            snap_rows,
            conflict_cols=["source_id", "format_id", "period", "elo_cutoff"],
            update_cols=["sample_size", "raw_ingest_id"],
            key_cols=["source_id", "format_id", "period", "elo_cutoff"],
            col_types={
                "source_id": "int[]",
                "format_id": "int[]",
                "period": "date[]",
                "elo_cutoff": "int[]",
                "sample_size": "int[]",
                "raw_ingest_id": "bigint[]",
            },
        )

        # 2. Upsert usage_entry for all snapshots
        entry_rows: list[tuple] = []
        for s in snapshots:
            snap_key = (
                s["source_id"],
                s["format_id"],
                s["period"],
                s.get("elo_cutoff"),
            )
            snapshot_id = snap_id_map[snap_key]
            for e in s.get("entries", []):
                entry_rows.append(
                    (
                        snapshot_id,
                        e.get("canonical_species_id"),
                        e.get("rank"),
                        e.get("usage_pct"),
                        e.get("raw_count"),
                    )
                )

        entry_id_map = await bulk_upsert_returning(
            conn,
            "usage_entry",
            ["snapshot_id", "canonical_species_id", "rank", "usage_pct", "raw_count"],
            entry_rows,
            conflict_cols=["snapshot_id", "canonical_species_id"],
            update_cols=["rank", "usage_pct", "raw_count"],
            key_cols=["snapshot_id", "canonical_species_id"],
            col_types={
                "snapshot_id": "int[]",
                "canonical_species_id": "int[]",
                "rank": "int[]",
                "usage_pct": "float8[]",
                "raw_count": "int[]",
            },
        )

        # 3. usage_moveset — no unique key; delete-before-insert per entry
        moveset_entry_ids: list[int] = []
        moveset_rows: list[tuple] = []
        for s in snapshots:
            snap_key = (
                s["source_id"],
                s["format_id"],
                s["period"],
                s.get("elo_cutoff"),
            )
            snapshot_id = snap_id_map[snap_key]
            for e in s.get("entries", []):
                entry_key = (snapshot_id, e.get("canonical_species_id"))
                entry_id = entry_id_map.get(entry_key)
                ms = e.get("moveset")
                if entry_id and ms:
                    moveset_entry_ids.append(entry_id)
                    moveset_rows.append(
                        (
                            entry_id,
                            json.dumps(ms.get("moves", {})),
                            json.dumps(ms.get("items", {})),
                            json.dumps(ms.get("spreads", {})),
                            json.dumps(ms.get("abilities", {})),
                            json.dumps(ms.get("teammates", {})),
                            json.dumps(ms.get("checks", {})),
                        )
                    )

        if moveset_entry_ids:
            await conn.execute(
                "DELETE FROM usage_moveset WHERE usage_entry_id = ANY($1::int[])",
                moveset_entry_ids,
            )
        await bulk_upsert(
            conn,
            "usage_moveset",
            [
                "usage_entry_id",
                "moves",
                "items",
                "spreads",
                "abilities",
                "teammates",
                "checks",
            ],
            moveset_rows,
            jsonb_cols={
                "moves",
                "items",
                "spreads",
                "abilities",
                "teammates",
                "checks",
            },
        )

    return len(snapshots)

