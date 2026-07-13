"""LabMaus Playwright scraper — React-rendered site, no public API."""

from __future__ import annotations

import logging
import re

from playwright.async_api import Page, async_playwright
from sqlalchemy import select

from celery_app import app
from config import settings
from models.db import BackfillLog, Player, Source, Tournament, TournamentPlacement, async_session_factory
from tasks.process.deduplicator import TeamDeduplicator
from tasks.process.parser import ShowdownPasteParser, resolve_paste_url
from tasks.process.tagger import tag_and_update_team
from tasks.process.validator import validate_team
from tasks.utils import USER_AGENT, date_filter

logger = logging.getLogger(__name__)

_REGULATION_RE = re.compile(r"Reg(?:ulation)?\s+([A-Z](?:-[A-Z])?)", re.IGNORECASE)


def parse_regulation(title: str) -> str | None:
    m = _REGULATION_RE.search(title)
    return f"Reg {m.group(1)}" if m else None


async def scrape_tournament_list(page: Page) -> list[dict]:
    await page.goto(f"{settings.labmaus_base}/tournaments", wait_until="networkidle")
    rows = await page.query_selector_all("[data-testid='tournament-row'], .tournament-row")
    tournaments = []
    for row in rows:
        try:
            tid = await row.get_attribute("data-tournament-id")
            name_el = await row.query_selector(".tournament-name, [data-field='name']")
            date_el = await row.query_selector(".tournament-date, [data-field='date']")
            name = (await name_el.inner_text()).strip() if name_el else ""
            date_str = (await date_el.get_attribute("datetime") or await date_el.inner_text()).strip() if date_el else ""
            tournaments.append(
                {
                    "id": tid,
                    "name": name,
                    "date": date_str,
                    "event_type": "VGC",
                    "regulation": parse_regulation(name),
                }
            )
        except Exception as exc:  # noqa: BLE001 - one bad row shouldn't kill the whole scrape
            logger.warning("Failed to parse LabMaus tournament row: %s", exc)
    return [t for t in tournaments if date_filter(t["date"], settings.backfill_start_date)]


async def scrape_tournament_teams(page: Page, tournament_id: str) -> list[dict]:
    await page.goto(f"{settings.labmaus_base}/tournaments/{tournament_id}", wait_until="networkidle")
    try:
        await page.wait_for_selector(".standings, [data-testid='standings']", timeout=10000)
    except Exception:  # noqa: BLE001 - possible Cloudflare challenge or slow render
        if await _is_cloudflare_challenge(page):
            logger.warning("Cloudflare challenge detected for tournament %s, skipping", tournament_id)
            return []
        raise

    rows = await page.query_selector_all(".standings-row, [data-testid='standing-row']")
    players = []
    for row in rows[:16]:
        try:
            name_el = await row.query_selector(".player-name")
            placing_el = await row.query_selector(".placing")
            paste_el = await row.query_selector("a[href*='pokepast.es'], .team-paste-link")
            players.append(
                {
                    "name": (await name_el.inner_text()).strip() if name_el else "Unknown",
                    "placing": int((await placing_el.inner_text()).strip().lstrip("#")) if placing_el else None,
                    "team_url": (await paste_el.get_attribute("href")) if paste_el else None,
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse LabMaus standings row: %s", exc)
    return players


async def _is_cloudflare_challenge(page: Page) -> bool:
    content = await page.content()
    return "Checking your browser" in content or "cf-challenge" in content


async def _get_or_create_source(session) -> Source:
    result = await session.execute(select(Source).where(Source.platform == "labmaus"))
    source = result.scalar_one_or_none()
    if source is None:
        source = Source(platform="labmaus", base_url=settings.labmaus_base, api_available=False)
        session.add(source)
        await session.flush()
    return source


@app.task(bind=True, name="tasks.ingest.labmaus.sync_recent_tournaments")
def sync_recent_tournaments(self) -> dict:
    import asyncio

    return asyncio.run(_sync_recent_tournaments())


async def _sync_recent_tournaments() -> dict:
    tournaments_processed = 0
    teams_imported = 0
    dedup = TeamDeduplicator()
    parser = ShowdownPasteParser()

    browser = None
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()

            async with async_session_factory() as session:
                source = await _get_or_create_source(session)
                tournaments = await scrape_tournament_list(page)

                for t in tournaments:
                    result = await session.execute(
                        select(Tournament).where(
                            Tournament.external_id == str(t["id"]), Tournament.source_id == source.id
                        )
                    )
                    tournament = result.scalar_one_or_none()
                    if tournament is None:
                        tournament = Tournament(
                            external_id=str(t["id"]),
                            source_id=source.id,
                            name=t["name"],
                            event_type=t["event_type"],
                            format_type="VGC",
                            regulation=t["regulation"],
                            date_held=t["date"] or None,
                        )
                        session.add(tournament)
                        await session.flush()

                    players = await scrape_tournament_teams(page, t["id"])
                    for entry in players:
                        if not entry.get("team_url"):
                            continue
                        player_result = await session.execute(
                            select(Player).where(Player.name == entry["name"])
                        )
                        player = player_result.scalar_one_or_none()
                        if player is None:
                            player = Player(name=entry["name"])
                            session.add(player)
                            await session.flush()

                        raw_paste = await resolve_paste_url(entry["team_url"])
                        parsed_json = parser.parse(raw_paste)
                        team, _ = await dedup.upsert_team(
                            session,
                            raw_paste=raw_paste,
                            parsed_json=parsed_json,
                            regulation=tournament.regulation,
                            format_type=tournament.format_type,
                            source_meta={
                                "source_id": source.id,
                                "source_url": entry["team_url"],
                                "scrape_method": "scrape_playwright",
                                "confidence": 90,
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
                                    final_placing=entry.get("placing"),
                                )
                            )

                    bf = await session.execute(
                        select(BackfillLog).where(
                            BackfillLog.source == "labmaus", BackfillLog.external_id == str(t["id"])
                        )
                    )
                    if bf.scalar_one_or_none() is None:
                        session.add(BackfillLog(source="labmaus", external_id=str(t["id"]), status="done"))

                    tournaments_processed += 1
                    await session.commit()
                    await page.wait_for_timeout(settings.labmaus_delay * 1000)
    finally:
        if browser is not None:
            await browser.close()

    logger.info("labmaus sync done: tournaments=%d teams=%d", tournaments_processed, teams_imported)
    return {"tournaments_processed": tournaments_processed, "teams_imported": teams_imported}
