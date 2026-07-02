"""raw_ingest(route='usage') -> usage_snapshot/usage_entry/usage_moveset.
Smogon chaos JSON shape confirmed stable (public ~10y). Pikalytics field names are
best-effort (see sources/pikalytics.py) — adjust _from_pikalytics once a live non-empty
payload is seen.

Batch path: builds a snapshot dict then calls ingest_usage_batch (one round-trip per
species set) instead of looping single-row upserts.
"""

from __future__ import annotations

from datetime import date

from src.platform.normalize.replay import _normalized_key
from src.platform.normalize.species import canonicalize_species
from src.platform.store.db_upserts import ingest_usage_batch
from src.platform.store.repositories import (
    mark_raw_processed,
    resolve_source_id,
    resolve_species,
    upsert_canonical_format,
)

NORMALIZER_VERSION = 2


def _guess_format(slug: str) -> tuple[int, str]:
    """'gen9ou' -> (9, 'singles'); 'gen9vgc2026regi' -> (9, 'doubles')."""
    gen = int(slug[3]) if slug[:3] == "gen" and slug[3:4].isdigit() else 9
    game_type = "doubles" if "vgc" in slug or "doubles" in slug else "singles"
    return gen, game_type


async def normalize_usage_row(
    conn, *, raw_id: int, source: str, natural_key: str, payload: dict
) -> int:
    if source == "smogon":
        snapshot_id = await _from_smogon(
            conn, source=source, natural_key=natural_key, payload=payload, raw_id=raw_id
        )
    elif source == "pikalytics":
        snapshot_id = await _from_pikalytics(
            conn, source=source, payload=payload, raw_id=raw_id
        )
    else:
        raise ValueError(f"no usage normalizer for source={source!r}")
    await mark_raw_processed(conn, raw_id=raw_id, normalizer_version=NORMALIZER_VERSION)
    return snapshot_id


async def _resolve_species_id(conn, *, source: str, species_name: str) -> int | None:
    """Canonicalize then resolve to DB id. Uses form-override + fuzzy before plain slugify."""
    ns = canonicalize_species(species_name)
    normalized_key = ns.canonical_slug or _normalized_key(species_name)
    return await resolve_species(
        conn,
        source=source,
        raw_name=species_name,
        normalized_key=normalized_key,
    )


async def _from_smogon(
    conn, *, source: str, natural_key: str, payload: dict, raw_id: int
) -> int:
    fmt_slug, cutoff_str, period_str = natural_key.rsplit("-", 2)
    gen, game_type = _guess_format(fmt_slug)
    format_id = await upsert_canonical_format(
        conn,
        slug=fmt_slug,
        label=fmt_slug.upper(),
        generation=gen,
        game_type=game_type,
    )
    source_id = await resolve_source_id(conn, source=source)
    info = payload.get("info", {})

    species_data = payload.get("data", {})
    ranked = sorted(
        species_data.items(), key=lambda kv: kv[1].get("usage", 0), reverse=True
    )
    entries = []
    for rank, (species_name, stats) in enumerate(ranked, start=1):
        species_id = await _resolve_species_id(
            conn, source=source, species_name=species_name
        )
        entries.append(
            {
                "canonical_species_id": species_id,
                "rank": rank,
                "usage_pct": stats.get("usage"),
                "raw_count": stats.get("Raw count"),
                "moveset": {
                    "moves": stats.get("Moves", {}),
                    "items": stats.get("Items", {}),
                    "spreads": stats.get("Spreads", {}),
                    "abilities": stats.get("Abilities", {}),
                    "teammates": stats.get("Teammates", {}),
                    "checks": stats.get("Checks and Counters", {}),
                },
            }
        )

    period = date.fromisoformat(f"{period_str}-01")
    snapshot = {
        "source_id": source_id,
        "format_id": format_id,
        "period": period,
        "elo_cutoff": int(cutoff_str),
        "sample_size": info.get("number of battles"),
        "raw_ingest_id": raw_id,
        "entries": entries,
    }
    await ingest_usage_batch(conn, [snapshot])

    # Return snapshot id via the unique key used by the batch helper
    row = await conn.fetchrow(
        "SELECT id FROM usage_snapshot WHERE source_id=$1 AND format_id=$2 AND period=$3 AND elo_cutoff=$4",
        source_id,
        format_id,
        period,
        int(cutoff_str),
    )
    return row["id"]


async def _from_pikalytics(conn, *, source: str, payload: dict, raw_id: int) -> int:
    fmt_slug = payload["format"]
    gen, game_type = _guess_format(fmt_slug)
    format_id = await upsert_canonical_format(
        conn,
        slug=fmt_slug,
        label=fmt_slug.upper(),
        generation=gen,
        game_type=game_type,
    )
    source_id = await resolve_source_id(conn, source=source)
    raw_entries = payload.get("entries", [])
    # ponytail: pikalytics endpoint carries no period field — use ingest date as the snapshot
    # period instead. Re-running on the same day re-hits the unique constraint and updates in place.
    period = date.today()

    entries = []
    for rank, entry in enumerate(raw_entries, start=1):
        # ponytail: key names guessed (name/usage/raw_count) — fix against a live sample.
        species_name = entry.get("name") or entry.get("pokemon") or ""
        species_id = await _resolve_species_id(
            conn, source=source, species_name=species_name
        )
        entries.append(
            {
                "canonical_species_id": species_id,
                "rank": rank,
                "usage_pct": entry.get("usage"),
                "raw_count": entry.get("raw_count"),
                "moveset": {
                    "moves": entry.get("moves", {}),
                    "items": entry.get("items", {}),
                    "spreads": entry.get("spreads", {}),
                    "abilities": entry.get("abilities", {}),
                    "teammates": entry.get("teammates", {}),
                    "checks": entry.get("checks", {}),
                },
            }
        )

    snapshot = {
        "source_id": source_id,
        "format_id": format_id,
        "period": period,
        "elo_cutoff": None,
        "sample_size": len(raw_entries) or None,
        "raw_ingest_id": raw_id,
        "entries": entries,
    }
    await ingest_usage_batch(conn, [snapshot])

    row = await conn.fetchrow(
        "SELECT id FROM usage_snapshot WHERE source_id=$1 AND format_id=$2 AND period=$3 AND elo_cutoff IS NULL",
        source_id,
        format_id,
        period,
    )
    return row["id"]
