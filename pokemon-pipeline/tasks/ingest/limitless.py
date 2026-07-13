"""Limitless VGC API ingestion — Phase 1 MVP source. Public REST API, no auth, top-16 only."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone

from sqlalchemy import select

from celery_app import app
from config import settings
from models.db import BackfillLog, Player, Source, Tournament, TournamentPlacement, async_session_factory
from tasks.process.deduplicator import TeamDeduplicator
from tasks.process.parser import ShowdownPasteParser, resolve_paste_url
from tasks.process.tagger import tag_and_update_team
from tasks.process.validator import validate_team
from tasks.utils import RateLimitedClient, date_filter

logger = logging.getLogger(__name__)

_REGULATION_RE = re.compile(r"Regulation\s+([A-Z](?:-[A-Z])?)", re.IGNORECASE)


def parse_regulation(tournament_name: str) -> tuple[str | None, str | None]:
    """"VGC 2026 Regulation M-B" -> ("Reg M-B", "VGC")."""
    format_type = "VGC" if "vgc" in tournament_name.lower() else None
    m = _REGULATION_RE.search(tournament_name)
    regulation = f"Reg {m.group(1)}" if m else None
    return regulation, format_type


async def fetch_tournaments(client: RateLimitedClient, page: int = 1) -> list[dict]:
    """Paginate GET /tournaments?game=VGC&page=N until empty or all results predate cutoff."""
    resp = await client.get(
        f"{settings.limitless_api_base}/tournaments", params={"game": "VGC", "page": page}
    )
    data = resp.json()
    return data if isinstance(data, list) else data.get("tournaments", [])


async def fetch_standings(client: RateLimitedClient, tournament_id: str) -> list[dict]:
    resp = await client.get(f"{settings.limitless_api_base}/tournaments/{tournament_id}/standings")
    data = resp.json()
    standings = data if isinstance(data, list) else data.get("standings", [])
    return [s for s in standings if (s.get("final_placing") or s.get("placing") or 999) <= 16]


async def fetch_player_team(
    client: RateLimitedClient, tournament_id: str, player_id: str
) -> str | None:
    try:
        resp = await client.get(
            f"{settings.limitless_api_base}/tournaments/{tournament_id}/players/{player_id}/team"
        )
    except Exception as exc:  # noqa: BLE001 - missing team data is expected, not fatal
        logger.info("No team data for player %s in tournament %s: %s", player_id, tournament_id, exc)
        return None
    data = resp.json()
    return data.get("team_url") or data.get("paste") or None


async def _get_or_create_source(session) -> Source:
    result = await session.execute(select(Source).where(Source.platform == "limitless"))
    source = result.scalar_one_or_none()
    if source is None:
        source = Source(platform="limitless", base_url=settings.limitless_api_base, api_available=True)
        session.add(source)
        await session.flush()
    return source


async def _get_or_create_player(session, name: str, external_id: str | None) -> Player:
    query = select(Player).where(Player.name == name)
    if external_id:
        query = select(Player).where(Player.external_id == external_id)
    result = await session.execute(query)
    player = result.scalar_one_or_none()
    if player is None:
        player = Player(name=name, external_id=external_id)
        session.add(player)
        await session.flush()
    return player


async def _get_or_create_tournament(session, source: Source, raw: dict) -> Tournament:
    external_id = str(raw["id"])
    result = await session.execute(
        select(Tournament).where(
            Tournament.external_id == external_id, Tournament.source_id == source.id
        )
    )
    tournament = result.scalar_one_or_none()
    regulation, format_type = parse_regulation(raw.get("name", ""))
    if tournament is None:
        tournament = Tournament(
            external_id=external_id,
            source_id=source.id,
            name=raw.get("name", ""),
            event_type=raw.get("event_type"),
            format_type=format_type,
            regulation=regulation,
            date_held=date.fromisoformat(raw["date"]) if raw.get("date") else None,
            location=raw.get("location"),
            player_count=raw.get("player_count"),
        )
        session.add(tournament)
        await session.flush()
    return tournament


async def _import_tournament(
    client: RateLimitedClient, session, source: Source, raw: dict, skip_validation: bool = False
) -> dict:
    tournament = await _get_or_create_tournament(session, source, raw)
    standings = await fetch_standings(client, tournament.external_id)

    teams_imported = 0
    teams_deduplicated = 0
    dedup = TeamDeduplicator()
    parser = ShowdownPasteParser()

    for entry in standings:
        player_name = entry.get("name", "Unknown")
        player_external_id = entry.get("player_id")
        player = await _get_or_create_player(session, player_name, player_external_id)

        team_url = entry.get("team_url") or await fetch_player_team(
            client, tournament.external_id, str(player_external_id or "")
        )
        if not team_url:
            logger.info("No team URL for %s in tournament %s, skipping", player_name, tournament.external_id)
            continue

        raw_paste = await resolve_paste_url(team_url)
        parsed_json = parser.parse(raw_paste)

        team, was_created = await dedup.upsert_team(
            session,
            raw_paste=raw_paste,
            parsed_json=parsed_json,
            regulation=tournament.regulation,
            format_type=tournament.format_type,
            source_meta={
                "source_id": source.id,
                "source_url": team_url,
                "scrape_method": "api",
                "confidence": 100,
                "raw_response": entry,
            },
        )
        teams_imported += 1
        if not was_created:
            teams_deduplicated += 1

        if not skip_validation:
            validation = await validate_team(session, team.id, parsed_json, tournament.format_type, tournament.regulation)
            if not validation.is_valid:
                logger.warning(
                    "Team %d failed validation: species=%s errors=%s",
                    team.id,
                    [m.get("species") for m in parsed_json],
                    validation.errors,
                )
        await tag_and_update_team(session, team.id, parsed_json, tournament.format_type)

        # Idempotent placement upsert
        existing_placement = await session.execute(
            select(TournamentPlacement).where(
                TournamentPlacement.tournament_id == tournament.id,
                TournamentPlacement.player_id == player.id,
            )
        )
        if existing_placement.scalar_one_or_none() is None:
            session.add(
                TournamentPlacement(
                    tournament_id=tournament.id,
                    player_id=player.id,
                    team_id=team.id,
                    final_placing=entry.get("final_placing") or entry.get("placing"),
                    win_count=entry.get("win_count", 0),
                    loss_count=entry.get("loss_count", 0),
                    bring_order=entry.get("bring_order"),
                )
            )

    await session.commit()
    return {
        "tournament_id": tournament.external_id,
        "teams_imported": teams_imported,
        "teams_deduplicated": teams_deduplicated,
    }


@app.task(bind=True, name="tasks.ingest.limitless.sync_all_tournaments")
def sync_all_tournaments(self, skip_validation: bool = False) -> dict:
    import asyncio

    return asyncio.run(_sync_all_tournaments(skip_validation))


async def _sync_all_tournaments(skip_validation: bool = False) -> dict:
    tournaments_processed = 0
    teams_imported = 0
    teams_deduplicated = 0

    async with RateLimitedClient() as client, async_session_factory() as session:
        source = await _get_or_create_source(session)
        page = 1
        while True:
            batch = await fetch_tournaments(client, page)
            if not batch:
                break
            qualifying = [t for t in batch if date_filter(t.get("date"), settings.backfill_start_date)]
            if not qualifying and page > 1:
                break
            for raw in qualifying:
                result = await _import_tournament(client, session, source, raw, skip_validation)
                tournaments_processed += 1
                teams_imported += result["teams_imported"]
                teams_deduplicated += result["teams_deduplicated"]

                bf = await session.execute(
                    select(BackfillLog).where(
                        BackfillLog.source == "limitless", BackfillLog.external_id == str(raw["id"])
                    )
                )
                if bf.scalar_one_or_none() is None:
                    session.add(
                        BackfillLog(
                            source="limitless",
                            external_id=str(raw["id"]),
                            status="done",
                            processed_at=datetime.now(timezone.utc),
                        )
                    )
            await session.commit()
            page += 1

    logger.info(
        "limitless sync_all_tournaments done: tournaments=%d teams=%d dedup=%d",
        tournaments_processed,
        teams_imported,
        teams_deduplicated,
    )
    return {
        "tournaments_processed": tournaments_processed,
        "teams_imported": teams_imported,
        "teams_deduplicated": teams_deduplicated,
    }


@app.task(bind=True, name="tasks.ingest.limitless.sync_single_tournament")
def sync_single_tournament(self, tournament_id: str, skip_validation: bool = False) -> dict:
    """Used by Discord bot !import tournament limitless {id} command."""
    import asyncio

    return asyncio.run(_sync_single_tournament(tournament_id, skip_validation))


async def _sync_single_tournament(tournament_id: str, skip_validation: bool = False) -> dict:
    async with RateLimitedClient() as client, async_session_factory() as session:
        source = await _get_or_create_source(session)
        resp = await client.get(f"{settings.limitless_api_base}/tournaments/{tournament_id}")
        raw = resp.json()
        return await _import_tournament(client, session, source, raw, skip_validation)
