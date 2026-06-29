"""Upsert helpers. One job each: write raw, resolve species, upsert canonical rows."""
import json

import asyncpg

from src.platform.store.db import payload_hash


async def land_raw(
    conn: asyncpg.Connection, *, source: str, route: str, natural_key: str,
    payload: dict, url: str | None = None,
) -> int | None:
    """Insert into raw_ingest. Returns new row id, or None if identical payload already landed."""
    raw_bytes = json.dumps(payload, sort_keys=True).encode()
    row = await conn.fetchrow(
        """
        INSERT INTO raw_ingest (source_id, route, natural_key, url, payload, payload_hash)
        SELECT id, $2, $3, $4, $5::jsonb, $6 FROM source WHERE name = $1
        ON CONFLICT (source_id, natural_key, payload_hash) DO NOTHING
        RETURNING id
        """,
        source, route, natural_key, url, json.dumps(payload), payload_hash(raw_bytes),
    )
    return row["id"] if row else None


async def resolve_species(
    conn: asyncpg.Connection, *, source: str | None, raw_name: str, normalized_key: str,
) -> int | None:
    """raw_name -> canonical_species_id via species_alias. None if unresolved (caller should log)."""
    row = await conn.fetchrow(
        """
        SELECT sa.canonical_species_id FROM species_alias sa
        LEFT JOIN source s ON s.id = sa.source_id
        WHERE sa.normalized_key = $1 AND (s.name = $2 OR sa.source_id IS NULL)
        ORDER BY sa.source_id NULLS LAST LIMIT 1
        """,
        normalized_key, source,
    )
    return row["canonical_species_id"] if row else None


async def upsert_canonical_species(
    conn: asyncpg.Connection, *, slug: str, national_dex: int | None, display_name: str,
    base_forme_slug: str | None = None, is_forme: bool = False,
) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO canonical_species (slug, national_dex, display_name, base_forme_slug, is_forme)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (slug) DO UPDATE SET national_dex = EXCLUDED.national_dex,
            display_name = EXCLUDED.display_name
        RETURNING id
        """,
        slug, national_dex, display_name, base_forme_slug, is_forme,
    )
    return row["id"]


async def add_species_alias(
    conn: asyncpg.Connection, *, canonical_species_id: int, source: str | None,
    raw_name: str, normalized_key: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO species_alias (canonical_species_id, source_id, raw_name, normalized_key)
        SELECT $1::integer, id, $3::text, $4::text FROM source WHERE name = $2
        UNION ALL SELECT $1::integer, NULL::integer, $3::text, $4::text WHERE $2 IS NULL
        ON CONFLICT (source_id, normalized_key) DO NOTHING
        """,
        canonical_species_id, source, raw_name, normalized_key,
    )


async def upsert_replay(
    conn: asyncpg.Connection, *, source: str, replay_id: str, format_id: int | None,
    players: dict, rating: int | None, log_hash: str, raw_ingest_id: int | None,
) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO replay (source_id, replay_id, format_id, players, rating, log_hash, raw_ingest_id)
        SELECT id, $2, $3, $4::jsonb, $5, $6, $7 FROM source WHERE name = $1
        ON CONFLICT (replay_id) DO UPDATE SET log_hash = EXCLUDED.log_hash,
            raw_ingest_id = EXCLUDED.raw_ingest_id
        RETURNING id
        """,
        source, replay_id, format_id, json.dumps(players), rating, log_hash, raw_ingest_id,
    )
    return row["id"]


async def upsert_replay_battle(
    conn: asyncpg.Connection, *, replay_db_id: int, winner: str, turn_count: int,
    turns: list, parser_version: int,
) -> int:
    """UNIQUE(replay_id, parser_version) — re-parse with bumped parser_version is idempotent reprocess."""
    row = await conn.fetchrow(
        """
        INSERT INTO replay_battle (replay_id, winner, turn_count, turns, parser_version)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        ON CONFLICT (replay_id, parser_version) DO UPDATE SET winner = EXCLUDED.winner,
            turn_count = EXCLUDED.turn_count, turns = EXCLUDED.turns, normalized_at = now()
        RETURNING id
        """,
        replay_db_id, winner, turn_count, json.dumps(turns), parser_version,
    )
    return row["id"]


async def add_replay_team_member(
    conn: asyncpg.Connection, *, replay_battle_id: int, player_slot: int,
    canonical_species_id: int | None, brought: bool, lead: bool,
) -> None:
    await conn.execute(
        """
        INSERT INTO replay_team (replay_battle_id, player_slot, canonical_species_id, brought, lead)
        VALUES ($1, $2, $3, $4, $5)
        """,
        replay_battle_id, player_slot, canonical_species_id, brought, lead,
    )


async def upsert_canonical_format(
    conn: asyncpg.Connection, *, slug: str, label: str, generation: int,
    game_type: str, regulation: str | None = None,
) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO canonical_format (slug, label, generation, game_type, regulation)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (slug) DO UPDATE SET label = EXCLUDED.label, regulation = EXCLUDED.regulation
        RETURNING id
        """,
        slug, label, generation, game_type, regulation,
    )
    return row["id"]


async def upsert_usage_snapshot(
    conn: asyncpg.Connection, *, source: str, format_id: int, period, elo_cutoff: int | None,
    sample_size: int | None, raw_ingest_id: int | None,
) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO usage_snapshot (source_id, format_id, period, elo_cutoff, sample_size, raw_ingest_id)
        SELECT id, $2, $3, $4, $5, $6 FROM source WHERE name = $1
        ON CONFLICT (source_id, format_id, period, elo_cutoff)
            DO UPDATE SET sample_size = EXCLUDED.sample_size, raw_ingest_id = EXCLUDED.raw_ingest_id
        RETURNING id
        """,
        source, format_id, period, elo_cutoff, sample_size, raw_ingest_id,
    )
    return row["id"]


async def upsert_usage_entry(
    conn: asyncpg.Connection, *, snapshot_id: int, canonical_species_id: int | None,
    rank: int | None, usage_pct: float | None, raw_count: int | None,
) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO usage_entry (snapshot_id, canonical_species_id, rank, usage_pct, raw_count)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (snapshot_id, canonical_species_id) DO UPDATE SET
            rank = EXCLUDED.rank, usage_pct = EXCLUDED.usage_pct, raw_count = EXCLUDED.raw_count
        RETURNING id
        """,
        snapshot_id, canonical_species_id, rank, usage_pct, raw_count,
    )
    return row["id"]


async def upsert_usage_moveset(
    conn: asyncpg.Connection, *, usage_entry_id: int, moves: dict, items: dict,
    spreads: dict, abilities: dict, teammates: dict, checks: dict,
) -> None:
    """No unique constraint on usage_entry_id — caller (normalizer) must delete-before-insert
    on reprocess. Re-running normalize_usage_row on the same raw_id would otherwise duplicate.
    """
    await conn.execute("DELETE FROM usage_moveset WHERE usage_entry_id = $1", usage_entry_id)
    await conn.execute(
        """
        INSERT INTO usage_moveset (usage_entry_id, moves, items, spreads, abilities, teammates, checks)
        VALUES ($1, $2::jsonb, $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb)
        """,
        usage_entry_id, json.dumps(moves), json.dumps(items), json.dumps(spreads),
        json.dumps(abilities), json.dumps(teammates), json.dumps(checks),
    )


async def upsert_tournament_event(
    conn: asyncpg.Connection, *, source: str, external_id: str, name: str, format_id: int | None,
    event_date, level: str | None, url: str | None, raw_ingest_id: int | None,
) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO tournament_event (source_id, external_id, name, format_id, event_date, level, url, raw_ingest_id)
        SELECT id, $2, $3, $4, $5, $6, $7, $8 FROM source WHERE name = $1
        ON CONFLICT (source_id, external_id) DO UPDATE SET
            name = EXCLUDED.name, format_id = EXCLUDED.format_id, event_date = EXCLUDED.event_date,
            level = EXCLUDED.level, url = EXCLUDED.url, raw_ingest_id = EXCLUDED.raw_ingest_id
        RETURNING id
        """,
        source, external_id, name, format_id, event_date, level, url, raw_ingest_id,
    )
    return row["id"]


async def upsert_tournament_team(
    conn: asyncpg.Connection, *, event_id: int, placement: int | None, player_name: str | None,
    player_external_id: str | None, wins: int | None, losses: int | None, raw_ingest_id: int | None,
) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO tournament_team (event_id, placement, player_name, player_external_id, wins, losses, raw_ingest_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (event_id, placement, player_external_id) DO UPDATE SET
            player_name = EXCLUDED.player_name, wins = EXCLUDED.wins, losses = EXCLUDED.losses,
            raw_ingest_id = EXCLUDED.raw_ingest_id
        RETURNING id
        """,
        event_id, placement, player_name, player_external_id, wins, losses, raw_ingest_id,
    )
    return row["id"]


async def add_tournament_team_member(
    conn: asyncpg.Connection, *, team_id: int, canonical_species_id: int | None, slot: int,
    item: str | None, ability: str | None, tera_type: str | None, moves: list,
) -> None:
    """No unique constraint on tournament_team_member — delete-before-insert per team_id
    on reprocess, same precedent as upsert_usage_moveset.
    """
    if slot == 1:
        await conn.execute("DELETE FROM tournament_team_member WHERE team_id = $1", team_id)
    await conn.execute(
        """
        INSERT INTO tournament_team_member (team_id, canonical_species_id, slot, item, ability, tera_type, moves)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
        """,
        team_id, canonical_species_id, slot, item, ability, tera_type, json.dumps(moves),
    )


async def mark_raw_processed(conn: asyncpg.Connection, *, raw_id: int, normalizer_version: int) -> None:
    await conn.execute(
        "UPDATE raw_ingest SET status = 'normalized', processed_at = now(), normalizer_version = $2 WHERE id = $1",
        raw_id, normalizer_version,
    )


async def mark_raw_error(conn: asyncpg.Connection, *, raw_id: int) -> None:
    """Flip raw_ingest.status to 'error' when a normalize step fails permanently."""
    await conn.execute(
        "UPDATE raw_ingest SET status = 'error', processed_at = now() WHERE id = $1",
        raw_id,
    )


async def to_dead_letter(
    conn: asyncpg.Connection,
    *,
    source: str,
    route: str,
    natural_key: str | None,
    payload: dict | None,
    error: str,
    ingest_run_id: int | None = None,
) -> None:
    """Append one failure record to dead_letter (durable, operator-reviewable sink).

    Append-only by design — re-running the same batch may add another row.
    The idempotency guarantee lives in land_raw (ON CONFLICT DO NOTHING), not here.
    """
    await conn.execute(
        """
        INSERT INTO dead_letter (source_id, route, natural_key, payload, error, ingest_run_id)
        SELECT id, $2, $3, $4::jsonb, $5, $6 FROM source WHERE name = $1
        """,
        source,
        route,
        natural_key,
        json.dumps(payload) if payload is not None else None,
        error,
        ingest_run_id,
    )
