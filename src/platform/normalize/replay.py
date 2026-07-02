"""raw_ingest(route='replay') -> replay/replay_battle/replay_team. Reuses src.ml.replay_parser.

Batch path: builds a replay dict then calls ingest_replays_batch — team members land in
one bulk_upsert instead of N add_replay_team_member round-trips.
"""

from __future__ import annotations

import hashlib

import asyncpg

from src.ml.replay_parser import parse_replay_json
from src.platform.normalize.species import normalize_replay_pokemon
from src.platform.store.db_upserts import ingest_replays_batch
from src.platform.store.repositories import (
    mark_raw_processed,
    resolve_source_id,
    resolve_species,
)

PARSER_VERSION = 1


def _normalized_key(species: str) -> str:
    # ponytail: lowercase+alnum, not poke-env to_id. Swap in to_id() if aliasing breaks on real data.
    return "".join(c for c in species.lower() if c.isalnum())


async def normalize_replay_row(
    conn: asyncpg.Connection, *, raw_id: int, source: str, payload: dict
) -> int:
    """Parse one pending raw_ingest replay row, upsert canonical rows, mark processed. Returns replay_battle.id."""
    record = parse_replay_json(payload)
    log_hash = hashlib.sha256(record.to_dict().__repr__().encode()).hexdigest()
    source_id = await resolve_source_id(conn, source=source)

    first_turn = record.turns[0] if record.turns else None
    team_members = []
    for player_slot, team, active in (
        (1, record.p1_team, first_turn.p1_active if first_turn else ""),
        (2, record.p2_team, first_turn.p2_active if first_turn else ""),
    ):
        for species in team:
            ns = normalize_replay_pokemon(species)
            species_id = await resolve_species(
                conn,
                source=source,
                raw_name=ns["raw_name"],
                normalized_key=ns["canonical_slug"] or _normalized_key(species),
            )
            team_members.append(
                {
                    "player_slot": player_slot,
                    "canonical_species_id": species_id,
                    "brought": True,
                    "lead": species == active,
                }
            )

    replay_dict = {
        "source_id": source_id,
        "replay_id": record.replay_id,
        "format_id": None,
        "players": {"p1": record.p1_name, "p2": record.p2_name},
        "rating": record.rating,
        "log_hash": log_hash,
        "raw_ingest_id": raw_id,
        "raw_text": None,
        "battle": {
            "winner": record.winner,
            "turn_count": record.total_turns,
            "turns": record.to_dict()["turns"],
            "parser_version": PARSER_VERSION,
            "team_members": team_members,
            "moves": [],
        },
    }
    await ingest_replays_batch(conn, [replay_dict])

    row = await conn.fetchrow(
        """
        SELECT rb.id FROM replay_battle rb
        JOIN replay r ON r.id = rb.replay_id
        WHERE r.replay_id = $1 AND rb.parser_version = $2
        """,
        record.replay_id,
        PARSER_VERSION,
    )
    battle_id = row["id"]
    await mark_raw_processed(conn, raw_id=raw_id, normalizer_version=PARSER_VERSION)
    return battle_id
