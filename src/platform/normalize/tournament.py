"""raw_ingest(route='tournament') -> tournament_event/tournament_team/tournament_team_member.
Limitless API shape confirmed live 2026-06-23 (see sources/limitless.py).
"""
from __future__ import annotations

from datetime import datetime

from src.platform.normalize.replay import _normalized_key
from src.platform.normalize.species import normalize_team_member
from src.platform.store.repositories import (
    add_tournament_team_member,
    mark_raw_processed,
    resolve_species,
    upsert_canonical_format,
    upsert_tournament_event,
    upsert_tournament_team,
)

NORMALIZER_VERSION = 1


async def normalize_tournament_row(conn, *, raw_id: int, source: str, natural_key: str, payload: dict) -> int:
    event = payload.get("event", {})
    standings = payload.get("standings", [])

    fmt = event.get("format") or "unknown"
    slug = f"vgc-{fmt}".lower()
    format_id = await upsert_canonical_format(
        conn, slug=slug, label=f"VGC Reg {fmt}", generation=9, game_type="doubles", regulation=fmt,
    )

    event_date = None
    if event.get("date"):
        event_date = datetime.fromisoformat(event["date"].replace("Z", "+00:00")).date()

    # ponytail: level heuristic is online-vs-major only; "champions" tier needs a real signal
    # (e.g. event.organizer or name pattern) once seen in live data.
    level = "online" if event.get("isOnline") else "major"

    event_id = await upsert_tournament_event(
        conn, source=source, external_id=natural_key, name=event.get("name", natural_key),
        format_id=format_id, event_date=event_date, level=level,
        url=f"https://play.limitlesstcg.com/tournament/{natural_key}", raw_ingest_id=raw_id,
    )

    for entry in standings:
        record = entry.get("record", {})
        team_id = await upsert_tournament_team(
            conn, event_id=event_id, placement=entry.get("placing"),
            player_name=entry.get("name"), player_external_id=entry.get("player"),
            wins=record.get("wins"), losses=record.get("losses"), raw_ingest_id=raw_id,
        )

        decklist = entry.get("decklist") or []
        for slot, mon in enumerate(decklist, start=1):
            ns = normalize_team_member(mon)
            species_id = await resolve_species(
                conn, source=source, raw_name=ns["raw_name"],
                normalized_key=ns["canonical_slug"] or _normalized_key(ns["raw_name"]),
            )
            await add_tournament_team_member(
                conn, team_id=team_id, canonical_species_id=species_id, slot=slot,
                item=ns["item"], ability=ns["ability"], tera_type=ns["tera_type"],
                moves=ns["moves"],
            )

    await mark_raw_processed(conn, raw_id=raw_id, normalizer_version=NORMALIZER_VERSION)
    return event_id
