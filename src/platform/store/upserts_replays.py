"""
Replay ingestion (Showdown replay logs).

Extracted from db_upserts.py (which had grown past the project's 800-line
guideline). Orchestrates replay -> replay_battle -> replay_team /
replay_move upserts using the generic bulk_upsert()/bulk_upsert_returning()
helpers.

Conflict-key notes live in db_upserts.py's module docstring.
"""

import json

import asyncpg

from src.platform.store.db_upserts import bulk_upsert, bulk_upsert_returning


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
