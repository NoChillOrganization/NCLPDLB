"""
Tournament ingestion (Limitless VGC tournament results).

Extracted from db_upserts.py (which had grown past the project's 800-line
guideline). Orchestrates tournament_event -> tournament_team -> team_member
/ match upserts using the generic bulk_upsert()/bulk_upsert_returning()
helpers.

Conflict-key notes live in db_upserts.py's module docstring.
"""

import json

import asyncpg

from src.platform.store.db_upserts import bulk_upsert, bulk_upsert_returning


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
