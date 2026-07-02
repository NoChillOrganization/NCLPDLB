"""
Bulk upsert helpers for platform source ingestion.

Two generic helpers for performance:
  - bulk_upsert()           — chunked executemany; no RETURNING (children, large sets)
  - bulk_upsert_returning() — single unnest statement with RETURNING (parents needing id maps)

Three orchestrators enforce parent-before-child ordering and idempotency:
  - ingest_usage_batch()       — usage_snapshot → usage_entry → usage_moveset
  - ingest_replays_batch()     — replay → replay_battle → replay_team / replay_move
  - ingest_tournament_batch()  — tournament_event → tournament_team → team_member / match

Conflict-key notes:
  - tournament_team and match use COALESCE-based functional unique indexes (0005_dedup_indexes.sql)
    so NULL-keyed rows deduplicate correctly on re-run. ON CONFLICT uses expression form.
  - replay_team has no unique constraint — full-rebuild (delete + insert) is used instead.
  - replay_move has a unique but move_name/player_slot are nullable → full-rebuild also used.
"""

import json
from datetime import date
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


# ─── Replay ingestion ─────────────────────────────────────────────────────────


async def ingest_replays_batch(
    conn: asyncpg.Connection,
    replays: list[dict],
) -> int:
    """
    Bulk-ingest replay data. Order: replay → replay_battle → replay_team + replay_move.

    replay_team and replay_move use full-rebuild (delete by replay_battle_id + bulk insert)
    because neither has a reliable unique key suitable for ON CONFLICT.

    Each dict in replays:
        source_id int, replay_id str, format_id int|None, players dict,
        rating int|None, log_hash str, raw_ingest_id int|None, raw_text str|None,
        battle: dict  # winner str, turn_count int, turns list, parser_version int
                      #   team_members: list[dict]  (player_slot, canonical_species_id,
                      #                              brought, lead, item, ability, tera_type,
                      #                              moves list, + 0002 EV/IV cols)
                      #   moves: list[dict]  (turn, occurred_at, player_slot, actor_species_id,
                      #                       move_name, target_slot, raw_text, raw_json)
    """
    if not replays:
        return 0

    async with conn.transaction():
        # 1. Upsert replay → id map keyed by replay_id
        replay_rows = [
            (
                r["source_id"],
                r["replay_id"],
                r.get("format_id"),
                json.dumps(r.get("players", {})),
                r.get("rating"),
                r.get("log_hash"),
                r.get("raw_ingest_id"),
                r.get("raw_text"),
            )
            for r in replays
        ]
        replay_id_map = await bulk_upsert_returning(
            conn,
            "replay",
            [
                "source_id",
                "replay_id",
                "format_id",
                "players",
                "rating",
                "log_hash",
                "raw_ingest_id",
                "raw_text",
            ],
            replay_rows,
            conflict_cols=["replay_id"],
            update_cols=["log_hash", "raw_ingest_id", "raw_text"],
            key_cols=["replay_id"],
            col_types={
                "source_id": "int[]",
                "replay_id": "text[]",
                "format_id": "int[]",
                "players": "jsonb[]",
                "rating": "int[]",
                "log_hash": "text[]",
                "raw_ingest_id": "bigint[]",
                "raw_text": "text[]",
            },
            jsonb_cols={"players"},
        )

        # 2. Upsert replay_battle → id map keyed by (replay_id db id, parser_version)
        battle_rows = []
        for r in replays:
            b = r.get("battle")
            if not b:
                continue
            replay_db_id = replay_id_map.get((r["replay_id"],))
            if replay_db_id is None:
                continue
            battle_rows.append(
                (
                    replay_db_id,
                    b.get("winner"),
                    b.get("turn_count"),
                    json.dumps(b.get("turns", [])),
                    b.get("parser_version", 1),
                )
            )

        battle_id_map = await bulk_upsert_returning(
            conn,
            "replay_battle",
            ["replay_id", "winner", "turn_count", "turns", "parser_version"],
            battle_rows,
            conflict_cols=["replay_id", "parser_version"],
            update_cols=["winner", "turn_count", "turns"],
            key_cols=["replay_id", "parser_version"],
            col_types={
                "replay_id": "int[]",
                "winner": "text[]",
                "turn_count": "int[]",
                "turns": "jsonb[]",
                "parser_version": "int[]",
            },
            jsonb_cols={"turns"},
        )

        # Collect all replay_battle_ids so we can DELETE children cleanly
        battle_db_ids: list[int] = list(battle_id_map.values())
        if not battle_db_ids:
            return len(replays)

        # 3a. Full-rebuild replay_team (delete + insert; no unique key)
        team_rows: list[tuple] = []
        for r in replays:
            b = r.get("battle")
            if not b:
                continue
            replay_db_id = replay_id_map.get((r["replay_id"],))
            if replay_db_id is None:
                continue
            battle_db_id = battle_id_map.get((replay_db_id, b.get("parser_version", 1)))
            if battle_db_id is None:
                continue
            for m in b.get("team_members", []):
                team_rows.append(
                    (
                        battle_db_id,
                        m.get("player_slot"),
                        m.get("canonical_species_id"),
                        bool(m.get("brought", False)),
                        bool(m.get("lead", False)),
                        m.get("item"),
                        m.get("ability"),
                        m.get("tera_type"),
                        json.dumps(m.get("moves", [])),
                        m.get("nature"),
                        m.get("level"),
                        m.get("ev_hp"),
                        m.get("ev_atk"),
                        m.get("ev_def"),
                        m.get("ev_spa"),
                        m.get("ev_spd"),
                        m.get("ev_spe"),
                        m.get("iv_hp"),
                        m.get("iv_atk"),
                        m.get("iv_def"),
                        m.get("iv_spa"),
                        m.get("iv_spd"),
                        m.get("iv_spe"),
                    )
                )

        await conn.execute(
            "DELETE FROM replay_team WHERE replay_battle_id = ANY($1::int[])",
            battle_db_ids,
        )
        replay_team_cols = [
            "replay_battle_id",
            "player_slot",
            "canonical_species_id",
            "brought",
            "lead",
            "item",
            "ability",
            "tera_type",
            "moves",
            "nature",
            "level",
            "ev_hp",
            "ev_atk",
            "ev_def",
            "ev_spa",
            "ev_spd",
            "ev_spe",
            "iv_hp",
            "iv_atk",
            "iv_def",
            "iv_spa",
            "iv_spd",
            "iv_spe",
        ]
        await bulk_upsert(
            conn,
            "replay_team",
            replay_team_cols,
            team_rows,
            jsonb_cols={"moves"},
        )

        # 3b. Full-rebuild replay_move (delete + insert)
        move_rows: list[tuple] = []
        for r in replays:
            b = r.get("battle")
            if not b:
                continue
            replay_db_id = replay_id_map.get((r["replay_id"],))
            if replay_db_id is None:
                continue
            battle_db_id = battle_id_map.get((replay_db_id, b.get("parser_version", 1)))
            if battle_db_id is None:
                continue
            for mv in b.get("moves", []):
                move_rows.append(
                    (
                        battle_db_id,
                        mv.get("turn"),
                        mv.get("occurred_at"),
                        mv.get("player_slot"),
                        mv.get("actor_species_id"),
                        mv.get("move_name"),
                        mv.get("target_slot"),
                        mv.get("raw_text"),
                        json.dumps(mv.get("raw_json"))
                        if mv.get("raw_json") is not None
                        else None,
                    )
                )

        await conn.execute(
            "DELETE FROM replay_move WHERE replay_battle_id = ANY($1::int[])",
            battle_db_ids,
        )
        replay_move_cols = [
            "replay_battle_id",
            "turn",
            "occurred_at",
            "player_slot",
            "actor_species_id",
            "move_name",
            "target_slot",
            "raw_text",
            "raw_json",
        ]
        await bulk_upsert(
            conn,
            "replay_move",
            replay_move_cols,
            move_rows,
            jsonb_cols={"raw_json"},
        )

    return len(replays)


# ─── Tournament ingestion ─────────────────────────────────────────────────────


async def ingest_tournament_batch(
    conn: asyncpg.Connection,
    events: list[dict],
) -> int:
    """
    Bulk-ingest tournament data. Order: event → team (standing) → team_member + match.

    ⚠ tournament_team conflict key (event_id, placement, player_external_id) contains NULLable
    columns. Rows where placement or player_external_id is NULL will not deduplicate on re-run.
    See module docstring for recommended fix (0003_*.sql COALESCE unique index).

    Each dict in events:
        source_id int, external_id str, name str, format_id int|None, event_date date,
        level str|None, url str|None, raw_ingest_id int|None,
        teams: list[dict]   # placement, player_name, player_external_id, wins, losses,
                            #   raw_ingest_id, members: list[dict], matches: list[dict]
    """
    if not events:
        return 0

    async with conn.transaction():
        # 1. Upsert tournament_event → id map keyed by (source_id, external_id)
        event_rows = [
            (
                e["source_id"],
                e["external_id"],
                e.get("name"),
                e.get("format_id"),
                e.get("event_date"),
                e.get("level"),
                e.get("url"),
                e.get("raw_ingest_id"),
            )
            for e in events
        ]
        event_id_map = await bulk_upsert_returning(
            conn,
            "tournament_event",
            [
                "source_id",
                "external_id",
                "name",
                "format_id",
                "event_date",
                "level",
                "url",
                "raw_ingest_id",
            ],
            event_rows,
            conflict_cols=["source_id", "external_id"],
            update_cols=[
                "name",
                "format_id",
                "event_date",
                "level",
                "url",
                "raw_ingest_id",
            ],
            key_cols=["source_id", "external_id"],
            col_types={
                "source_id": "int[]",
                "external_id": "text[]",
                "name": "text[]",
                "format_id": "int[]",
                "event_date": "date[]",
                "level": "text[]",
                "url": "text[]",
                "raw_ingest_id": "bigint[]",
            },
        )

        # 2. Upsert tournament_team → id map keyed by (event_id, placement, player_external_id)
        team_rows = []
        for e in events:
            event_key = (e["source_id"], e["external_id"])
            event_db_id = event_id_map.get(event_key)
            if event_db_id is None:
                continue
            for t in e.get("teams", []):
                team_rows.append(
                    (
                        event_db_id,
                        t.get("placement"),
                        t.get("player_name"),
                        t.get("player_external_id"),
                        t.get("wins"),
                        t.get("losses"),
                        t.get("raw_ingest_id"),
                    )
                )

        team_id_map = await bulk_upsert_returning(
            conn,
            "tournament_team",
            [
                "event_id",
                "placement",
                "player_name",
                "player_external_id",
                "wins",
                "losses",
                "raw_ingest_id",
            ],
            team_rows,
            conflict_cols=["event_id", "placement", "player_external_id"],
            conflict_target="event_id, COALESCE(placement, -1), COALESCE(player_external_id, '')",
            update_cols=["player_name", "wins", "losses", "raw_ingest_id"],
            key_cols=["event_id", "placement", "player_external_id"],
            col_types={
                "event_id": "int[]",
                "placement": "int[]",
                "player_name": "text[]",
                "player_external_id": "text[]",
                "wins": "int[]",
                "losses": "int[]",
                "raw_ingest_id": "bigint[]",
            },
        )

        # 3. tournament_team_member — ON CONFLICT (team_id, slot) from 0002 unique
        member_rows: list[tuple] = []
        for e in events:
            event_key = (e["source_id"], e["external_id"])
            event_db_id = event_id_map.get(event_key)
            if event_db_id is None:
                continue
            for t in e.get("teams", []):
                team_key = (
                    event_db_id,
                    t.get("placement"),
                    t.get("player_external_id"),
                )
                team_db_id = team_id_map.get(team_key)
                if team_db_id is None:
                    continue
                for m in t.get("members", []):
                    member_rows.append(
                        (
                            team_db_id,
                            m.get("canonical_species_id"),
                            m.get("slot"),
                            m.get("item"),
                            m.get("ability"),
                            m.get("tera_type"),
                            json.dumps(m.get("moves", [])),
                            m.get("nature"),
                            m.get("level"),
                            m.get("ev_hp"),
                            m.get("ev_atk"),
                            m.get("ev_def"),
                            m.get("ev_spa"),
                            m.get("ev_spd"),
                            m.get("ev_spe"),
                            m.get("iv_hp"),
                            m.get("iv_atk"),
                            m.get("iv_def"),
                            m.get("iv_spa"),
                            m.get("iv_spd"),
                            m.get("iv_spe"),
                        )
                    )

        ttm_cols = [
            "team_id",
            "canonical_species_id",
            "slot",
            "item",
            "ability",
            "tera_type",
            "moves",
            "nature",
            "level",
            "ev_hp",
            "ev_atk",
            "ev_def",
            "ev_spa",
            "ev_spd",
            "ev_spe",
            "iv_hp",
            "iv_atk",
            "iv_def",
            "iv_spa",
            "iv_spd",
            "iv_spe",
        ]
        await bulk_upsert(
            conn,
            "tournament_team_member",
            ttm_cols,
            member_rows,
            conflict_cols=["team_id", "slot"],
            update_cols=[
                "canonical_species_id",
                "item",
                "ability",
                "tera_type",
                "moves",
                "nature",
                "level",
                "ev_hp",
                "ev_atk",
                "ev_def",
                "ev_spa",
                "ev_spd",
                "ev_spe",
                "iv_hp",
                "iv_atk",
                "iv_def",
                "iv_spa",
                "iv_spd",
                "iv_spe",
            ],
            jsonb_cols={"moves"},
        )

        # 4. match — schema-only; wires player team ids from team_id_map
        #    ⚠ conflict key (event_id, round, player1_team_id, player2_team_id) is NULLable.
        match_rows: list[tuple] = []
        for e in events:
            event_key = (e["source_id"], e["external_id"])
            event_db_id = event_id_map.get(event_key)
            if event_db_id is None:
                continue
            for t in e.get("teams", []):
                team_key = (
                    event_db_id,
                    t.get("placement"),
                    t.get("player_external_id"),
                )
                for mx in t.get("matches", []):
                    p1_key = (
                        event_db_id,
                        mx.get("p1_placement"),
                        mx.get("p1_external_id"),
                    )
                    p2_key = (
                        event_db_id,
                        mx.get("p2_placement"),
                        mx.get("p2_external_id"),
                    )
                    winner_key = (
                        event_db_id,
                        mx.get("winner_placement"),
                        mx.get("winner_external_id"),
                    )
                    match_rows.append(
                        (
                            event_db_id,
                            mx.get("round"),
                            mx.get("table_number"),
                            team_id_map.get(p1_key),
                            team_id_map.get(p2_key),
                            team_id_map.get(winner_key),
                            mx.get("score"),
                            mx.get("raw_text"),
                            json.dumps(mx.get("raw_json"))
                            if mx.get("raw_json") is not None
                            else None,
                            mx.get("raw_ingest_id"),
                        )
                    )

        await bulk_upsert(
            conn,
            "match",
            [
                "event_id",
                "round",
                "table_number",
                "player1_team_id",
                "player2_team_id",
                "winner_team_id",
                "score",
                "raw_text",
                "raw_json",
                "raw_ingest_id",
            ],
            match_rows,
            conflict_target="event_id, COALESCE(round, -1), COALESCE(player1_team_id, -1), COALESCE(player2_team_id, -1)",
            update_cols=[
                "winner_team_id",
                "score",
                "raw_text",
                "raw_json",
                "raw_ingest_id",
            ],
            jsonb_cols={"raw_json"},
        )

    return len(events)
