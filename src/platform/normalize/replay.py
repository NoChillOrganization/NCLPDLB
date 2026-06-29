"""raw_ingest(route='replay') -> replay/replay_battle/replay_team. Reuses src.ml.replay_parser."""

from __future__ import annotations

import hashlib

import asyncpg

from src.ml.replay_parser import parse_replay_json
from src.platform.normalize.species import normalize_replay_pokemon
from src.platform.store.repositories import (
    add_replay_team_member,
    mark_raw_processed,
    resolve_species,
    upsert_replay,
    upsert_replay_battle,
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

    replay_db_id = await upsert_replay(
        conn,
        source=source,
        replay_id=record.replay_id,
        format_id=None,
        players={"p1": record.p1_name, "p2": record.p2_name},
        rating=record.rating,
        log_hash=log_hash,
        raw_ingest_id=raw_id,
    )

    battle_id = await upsert_replay_battle(
        conn,
        replay_db_id=replay_db_id,
        winner=record.winner,
        turn_count=record.total_turns,
        turns=record.to_dict()["turns"],
        parser_version=PARSER_VERSION,
    )

    first_turn = record.turns[0] if record.turns else None
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
            await add_replay_team_member(
                conn,
                replay_battle_id=battle_id,
                player_slot=player_slot,
                canonical_species_id=species_id,
                brought=True,
                lead=(species == active),
            )

    await mark_raw_processed(conn, raw_id=raw_id, normalizer_version=PARSER_VERSION)
    return battle_id
