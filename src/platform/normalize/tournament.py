"""raw_ingest(route='tournament') -> tournament_event/tournament_team/tournament_team_member.
Limitless API shape confirmed live 2026-06-23 (see sources/limitless.py).

Batch path: builds a single event dict then calls ingest_tournament_batch — all
team+member writes land in one transaction instead of looping single-row upserts.
"""

from __future__ import annotations

from datetime import datetime

from src.platform.normalize.replay import _normalized_key
from src.platform.normalize.species import normalize_team_member
from src.platform.store.db_upserts import ingest_tournament_batch
from src.platform.store.repositories import (
    mark_raw_processed,
    resolve_source_id,
    resolve_species,
    upsert_canonical_format,
)

NORMALIZER_VERSION = 2


async def normalize_tournament_row(
    conn, *, raw_id: int, source: str, natural_key: str, payload: dict
) -> int:
    event = payload.get("event", {})
    standings = payload.get("standings", [])

    fmt = event.get("format") or "unknown"
    slug = f"vgc-{fmt}".lower()
    format_id = await upsert_canonical_format(
        conn,
        slug=slug,
        label=f"VGC Reg {fmt}",
        generation=9,
        game_type="doubles",
        regulation=fmt,
    )

    event_date = None
    if event.get("date"):
        event_date = datetime.fromisoformat(event["date"].replace("Z", "+00:00")).date()

    # ponytail: level heuristic is online-vs-major only; "champions" tier needs a real signal
    # (e.g. event.organizer or name pattern) once seen in live data.
    level = "online" if event.get("isOnline") else "major"
    source_id = await resolve_source_id(conn, source=source)

    teams = []
    for entry in standings:
        record = entry.get("record", {})
        decklist = entry.get("decklist") or []
        members = []
        for slot, mon in enumerate(decklist, start=1):
            ns = normalize_team_member(mon)
            species_id = await resolve_species(
                conn,
                source=source,
                raw_name=ns["raw_name"],
                normalized_key=ns["canonical_slug"] or _normalized_key(ns["raw_name"]),
            )
            members.append(
                {
                    "canonical_species_id": species_id,
                    "slot": slot,
                    "item": ns["item"],
                    "ability": ns["ability"],
                    "tera_type": ns["tera_type"],
                    "moves": ns["moves"],
                }
            )
        teams.append(
            {
                "placement": entry.get("placing"),
                "player_name": entry.get("name"),
                "player_external_id": entry.get("player"),
                "wins": record.get("wins"),
                "losses": record.get("losses"),
                "raw_ingest_id": raw_id,
                "members": members,
                "matches": [],
            }
        )

    event_dict = {
        "source_id": source_id,
        "external_id": natural_key,
        "name": event.get("name", natural_key),
        "format_id": format_id,
        "event_date": event_date,
        "level": level,
        "url": f"https://play.limitlesstcg.com/tournament/{natural_key}",
        "raw_ingest_id": raw_id,
        "teams": teams,
    }
    await ingest_tournament_batch(conn, [event_dict])

    row = await conn.fetchrow(
        "SELECT id FROM tournament_event WHERE source_id=$1 AND external_id=$2",
        source_id,
        natural_key,
    )
    event_id = row["id"]
    await mark_raw_processed(conn, raw_id=raw_id, normalizer_version=NORMALIZER_VERSION)
    return event_id
