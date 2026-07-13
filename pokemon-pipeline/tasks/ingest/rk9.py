"""RK9.gg scraper — official Play! Pokemon platform, server-rendered HTML."""

from __future__ import annotations

import logging

from bs4 import BeautifulSoup
from sqlalchemy import select

from celery_app import app
from config import settings
from models.db import BackfillLog, Player, Source, Tournament, TournamentPlacement, async_session_factory
from tasks.process.deduplicator import TeamDeduplicator
from tasks.process.parser import ShowdownPasteParser
from tasks.process.tagger import tag_and_update_team
from tasks.process.validator import validate_team
from tasks.utils import RateLimitedClient, date_filter

logger = logging.getLogger(__name__)

_STAT_COLUMNS = ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]


async def scrape_event_list(client: RateLimitedClient) -> list[dict]:
    resp = await client.get(f"{settings.rk9_base}/events")
    soup = BeautifulSoup(resp.text, "lxml")
    events = []
    for row in soup.select(".event-row, [data-event-id]"):
        event_id = row.get("data-event-id")
        name_el = row.select_one(".event-name")
        date_el = row.select_one(".event-date time, .event-date")
        name = name_el.get_text(strip=True) if name_el else ""
        date_str = (date_el.get("datetime") or date_el.get_text(strip=True)) if date_el else ""
        if event_id and "vgc" in name.lower():
            events.append({"id": event_id, "name": name, "date": date_str})
    return [e for e in events if date_filter(e["date"], settings.backfill_start_date)]


async def scrape_event_standings(client: RateLimitedClient, event_id: str) -> list[dict]:
    resp = await client.get(f"{settings.rk9_base}/events/{event_id}/standings")
    soup = BeautifulSoup(resp.text, "lxml")
    standings = []
    for row in soup.select(".standings-row, tr[data-player-id]"):
        player_id = row.get("data-player-id")
        name_el = row.select_one(".player-name")
        placing_el = row.select_one(".placing")
        record_el = row.select_one(".record")
        if not name_el:
            continue
        placing = None
        if placing_el:
            try:
                placing = int(placing_el.get_text(strip=True).lstrip("#"))
            except ValueError:
                pass
        win, loss = 0, 0
        if record_el:
            parts = record_el.get_text(strip=True).split("-")
            if len(parts) >= 2:
                win, loss = int(parts[0] or 0), int(parts[1] or 0)
        standings.append(
            {
                "player_id": player_id,
                "name": name_el.get_text(strip=True),
                "placing": placing,
                "win_count": win,
                "loss_count": loss,
            }
        )
    return [s for s in standings if (s["placing"] or 999) <= 16]


async def scrape_player_team(client: RateLimitedClient, event_id: str, player_id: str) -> str | None:
    try:
        resp = await client.get(f"{settings.rk9_base}/events/{event_id}/players/{player_id}/team")
    except Exception as exc:  # noqa: BLE001 - 403/404/not public -> None, not an error
        logger.info("RK9 team data unavailable for player %s event %s: %s", player_id, event_id, exc)
        return None
    if resp.status_code in (403, 404):
        return None
    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.select_one(".team-table, table.team")
    if table is None:
        return None
    return await reconstruct_paste_from_table(table)


async def reconstruct_paste_from_table(table_element) -> str:
    """Build a Showdown paste string from an RK9 HTML team table."""
    blocks = []
    for mon_row in table_element.select("tr.pokemon-row, .pokemon-entry"):
        species_el = mon_row.select_one(".species")
        item_el = mon_row.select_one(".item")
        ability_el = mon_row.select_one(".ability")
        nature_el = mon_row.select_one(".nature")
        ev_el = mon_row.select_one(".evs")
        move_els = mon_row.select(".move")

        if species_el is None:
            logger.warning("Unmapped RK9 team row, skipping: %s", mon_row)
            continue

        lines = [species_el.get_text(strip=True) + (f" @ {item_el.get_text(strip=True)}" if item_el else "")]
        if ability_el:
            lines.append(f"Ability: {ability_el.get_text(strip=True)}")
        if ev_el:
            lines.append(f"EVs: {ev_el.get_text(strip=True)}")
        if nature_el:
            lines.append(f"{nature_el.get_text(strip=True)} Nature")
        for move_el in move_els[:4]:
            lines.append(f"- {move_el.get_text(strip=True)}")

        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


async def _get_or_create_source(session) -> Source:
    result = await session.execute(select(Source).where(Source.platform == "rk9"))
    source = result.scalar_one_or_none()
    if source is None:
        source = Source(platform="rk9", base_url=settings.rk9_base, api_available=False)
        session.add(source)
        await session.flush()
    return source


@app.task(bind=True, name="tasks.ingest.rk9.sync_recent_events")
def sync_recent_events(self) -> dict:
    import asyncio

    return asyncio.run(_sync_recent_events())


async def _sync_recent_events() -> dict:
    events_processed = 0
    teams_imported = 0
    dedup = TeamDeduplicator()
    parser = ShowdownPasteParser()

    async with RateLimitedClient() as client, async_session_factory() as session:
        source = await _get_or_create_source(session)
        events = await scrape_event_list(client)

        for e in events:
            result = await session.execute(
                select(Tournament).where(
                    Tournament.external_id == str(e["id"]), Tournament.source_id == source.id
                )
            )
            tournament = result.scalar_one_or_none()
            if tournament is None:
                tournament = Tournament(
                    external_id=str(e["id"]),
                    source_id=source.id,
                    name=e["name"],
                    event_type="VGC",
                    format_type="VGC",
                    date_held=e["date"] or None,
                )
                session.add(tournament)
                await session.flush()

            standings = await scrape_event_standings(client, e["id"])
            had_team_data = False
            for entry in standings:
                raw_paste = await scrape_player_team(client, e["id"], entry["player_id"])
                if not raw_paste:
                    logger.info("No public team data for %s at event %s", entry["name"], e["id"])
                    continue
                had_team_data = True

                player_result = await session.execute(select(Player).where(Player.name == entry["name"]))
                player = player_result.scalar_one_or_none()
                if player is None:
                    player = Player(name=entry["name"], external_id=entry["player_id"])
                    session.add(player)
                    await session.flush()

                parsed_json = parser.parse(raw_paste)
                team, _ = await dedup.upsert_team(
                    session,
                    raw_paste=raw_paste,
                    parsed_json=parsed_json,
                    regulation=tournament.regulation,
                    format_type=tournament.format_type,
                    source_meta={
                        "source_id": source.id,
                        "source_url": f"{settings.rk9_base}/events/{e['id']}/players/{entry['player_id']}/team",
                        "scrape_method": "scrape_requests",
                        "confidence": 85,
                        "raw_response": entry,
                    },
                )
                teams_imported += 1

                validation = await validate_team(session, team.id, parsed_json, tournament.format_type, tournament.regulation)
                if not validation.is_valid:
                    logger.warning("Team %d failed validation: %s", team.id, validation.errors)
                await tag_and_update_team(session, team.id, parsed_json, tournament.format_type)

                placement_check = await session.execute(
                    select(TournamentPlacement).where(
                        TournamentPlacement.tournament_id == tournament.id,
                        TournamentPlacement.player_id == player.id,
                    )
                )
                if placement_check.scalar_one_or_none() is None:
                    session.add(
                        TournamentPlacement(
                            tournament_id=tournament.id,
                            player_id=player.id,
                            team_id=team.id,
                            final_placing=entry["placing"],
                            win_count=entry["win_count"],
                            loss_count=entry["loss_count"],
                        )
                    )

            # Mark processed even with no team data anywhere — never fail the whole event
            bf = await session.execute(
                select(BackfillLog).where(BackfillLog.source == "rk9", BackfillLog.external_id == str(e["id"]))
            )
            if bf.scalar_one_or_none() is None:
                session.add(
                    BackfillLog(
                        source="rk9",
                        external_id=str(e["id"]),
                        status="done",
                        error_message=None if had_team_data else "no public team data",
                    )
                )
            events_processed += 1
            await session.commit()

    logger.info("rk9 sync done: events=%d teams=%d", events_processed, teams_imported)
    return {"events_processed": events_processed, "teams_imported": teams_imported}
