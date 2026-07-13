"""Smogon Forum scraper — tournament result threads AND sample team threads. XenForo, BS4."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup
from sqlalchemy import select

from celery_app import app
from config import settings
from models.db import Player, Source, Tournament, TournamentPlacement, async_session_factory
from tasks.process.deduplicator import TeamDeduplicator
from tasks.process.parser import ShowdownPasteParser
from tasks.process.tagger import tag_and_update_team
from tasks.process.validator import validate_team
from tasks.utils import RateLimitedClient

logger = logging.getLogger(__name__)

# Pre-populated with major format threads. Fill real thread_urls before running in production.
SMOGON_THREAD_REGISTRY = [
    {
        "thread_url": f"{settings.smogon_forum_base}/threads/vgc-2026-ost-xxii.0/",
        "thread_type": "tournament",
        "format_type": "VGC",
        "regulation": "Reg M-B",
    },
    {
        "thread_url": f"{settings.smogon_forum_base}/threads/smogon-premier-league-xvii.0/",
        "thread_type": "tournament",
        "format_type": "OU",
        "regulation": None,
    },
    {
        "thread_url": f"{settings.smogon_forum_base}/threads/gen9-ou-sample-teams.0/",
        "thread_type": "sample",
        "format_type": "OU",
        "regulation": None,
    },
    {
        "thread_url": f"{settings.smogon_forum_base}/threads/vgc-2026-sample-teams.0/",
        "thread_type": "sample",
        "format_type": "VGC",
        "regulation": "Reg M-B",
    },
]

_PASTE_BLOCK_RE = re.compile(r"^\s*[A-Z][\w' -]*\s*(?:\(.*\))?\s*(?:@\s*.+)?\n(?:.+\n?)+", re.MULTILINE)
_POKEPASTE_URL_RE = re.compile(r"https?://pokepast\.es/[a-f0-9]+", re.IGNORECASE)


async def scrape_thread_pages(client: RateLimitedClient, thread_url: str) -> list[BeautifulSoup]:
    """Fetch all pages of an XenForo thread, following ?page=N pagination."""
    pages: list[BeautifulSoup] = []
    page_num = 1
    while True:
        url = thread_url if page_num == 1 else f"{thread_url.rstrip('/')}/page-{page_num}"
        try:
            resp = await client.get(url)
        except Exception as exc:  # noqa: BLE001 - out-of-range page = end of thread
            logger.debug("Stopped paginating %s at page %d: %s", thread_url, page_num, exc)
            break
        soup = BeautifulSoup(resp.text, "lxml")
        pages.append(soup)
        next_link = soup.select_one("a.pageNav-jump--next")
        if next_link is None:
            break
        page_num += 1
    return pages


async def extract_pastes_from_post(post_element) -> list[str]:
    """Find code/pre blocks matching a Showdown paste pattern, plus pokepast.es URLs in text."""
    results: list[str] = []
    for code_block in post_element.select("code, pre, .bbCodeBlock-content"):
        text = code_block.get_text("\n")
        if _PASTE_BLOCK_RE.search(text) and ("@" in text or "Ability:" in text):
            results.append(text.strip())

    post_text = post_element.get_text("\n")
    for match in _POKEPASTE_URL_RE.findall(post_text):
        results.append(match)

    return results


async def extract_tournament_results(soup_pages: list[BeautifulSoup]) -> list[dict]:
    results = []
    for round_number, soup in enumerate(soup_pages, start=1):
        for post in soup.select("article.message"):
            author_el = post.select_one(".message-name")
            author = author_el.get_text(strip=True) if author_el else "Unknown"
            pastes = await extract_pastes_from_post(post)
            for paste in pastes:
                results.append(
                    {
                        "player_name": author,
                        "raw_paste_or_url": paste,
                        "inferred_placing": None,  # inferred downstream from win/loss text if present
                        "round": round_number,
                    }
                )
    return results


async def extract_sample_teams(soup_pages: list[BeautifulSoup], format_type: str) -> list[dict]:
    results = []
    for soup in soup_pages:
        for post in soup.select("article.message"):
            author_el = post.select_one(".message-name")
            poster = author_el.get_text(strip=True) if author_el else "Unknown"
            body_el = post.select_one(".message-body")
            archetype_label = None
            if body_el:
                header_el = body_el.select_one("h2, h3, strong")
                archetype_label = header_el.get_text(strip=True) if header_el else None
            pastes = await extract_pastes_from_post(post)
            for paste in pastes:
                results.append(
                    {
                        "poster": poster,
                        "raw_paste_or_url": paste,
                        "archetype_label": archetype_label,
                        "format_type": format_type,
                    }
                )
    return results


async def _get_or_create_source(session) -> Source:
    result = await session.execute(select(Source).where(Source.platform == "smogon"))
    source = result.scalar_one_or_none()
    if source is None:
        source = Source(platform="smogon", base_url=settings.smogon_forum_base, api_available=False)
        session.add(source)
        await session.flush()
    return source


@app.task(bind=True, name="tasks.ingest.smogon.sync_tournament_threads")
def sync_tournament_threads(self) -> dict:
    import asyncio

    return asyncio.run(_sync_tournament_threads())


async def _sync_tournament_threads() -> dict:
    threads_processed = 0
    teams_imported = 0
    dedup = TeamDeduplicator()
    parser = ShowdownPasteParser()

    async with RateLimitedClient() as client, async_session_factory() as session:
        source = await _get_or_create_source(session)

        for entry in SMOGON_THREAD_REGISTRY:
            pages = await scrape_thread_pages(client, entry["thread_url"])
            if not pages:
                continue

            if entry["thread_type"] == "tournament":
                items = await extract_tournament_results(pages)
                provenance_tag = "smogon_tournament"
            else:
                items = await extract_sample_teams(pages, entry["format_type"])
                provenance_tag = "smogon_sample"

            result = await session.execute(
                select(Tournament).where(
                    Tournament.external_id == entry["thread_url"], Tournament.source_id == source.id
                )
            )
            tournament = result.scalar_one_or_none()
            if tournament is None:
                tournament = Tournament(
                    external_id=entry["thread_url"],
                    source_id=source.id,
                    name=entry["thread_url"].rstrip("/").rsplit("/", 1)[-1],
                    event_type=entry["thread_type"],
                    format_type=entry["format_type"],
                    regulation=entry["regulation"],
                )
                session.add(tournament)
                await session.flush()

            for item in items:
                raw_or_url = item.get("raw_paste_or_url", "")
                if raw_or_url.startswith("http"):
                    from tasks.process.parser import resolve_paste_url

                    raw_paste = await resolve_paste_url(raw_or_url)
                else:
                    raw_paste = raw_or_url

                parsed_json = parser.parse(raw_paste)
                if not parsed_json:
                    continue

                team, _ = await dedup.upsert_team(
                    session,
                    raw_paste=raw_paste,
                    parsed_json=parsed_json,
                    regulation=entry["regulation"],
                    format_type=entry["format_type"],
                    source_meta={
                        "source_id": source.id,
                        "source_url": f"{entry['thread_url']} [{provenance_tag}]",
                        "scrape_method": "scrape_requests",
                        "confidence": 70,
                        "raw_response": item,
                    },
                )
                teams_imported += 1

                validation = await validate_team(session, team.id, parsed_json, entry["format_type"], entry["regulation"])
                if not validation.is_valid:
                    logger.warning("Team %d failed validation: %s", team.id, validation.errors)
                await tag_and_update_team(session, team.id, parsed_json, entry["format_type"])

                if entry["thread_type"] == "tournament":
                    name = item.get("player_name", "Unknown")
                    player_result = await session.execute(select(Player).where(Player.name == name))
                    player = player_result.scalar_one_or_none()
                    if player is None:
                        player = Player(name=name)
                        session.add(player)
                        await session.flush()

                    placement_check = await session.execute(
                        select(TournamentPlacement).where(
                            TournamentPlacement.tournament_id == tournament.id,
                            TournamentPlacement.player_id == player.id,
                            TournamentPlacement.team_id == team.id,
                        )
                    )
                    if placement_check.scalar_one_or_none() is None:
                        session.add(
                            TournamentPlacement(
                                tournament_id=tournament.id,
                                player_id=player.id,
                                team_id=team.id,
                                final_placing=item.get("inferred_placing"),  # NULL if unknown
                            )
                        )
                # sample threads: placing=NULL, is_top16=FALSE by construction (no placement row)

            threads_processed += 1
            await session.commit()

    logger.info("smogon sync done: threads=%d teams=%d", threads_processed, teams_imported)
    return {"threads_processed": threads_processed, "teams_imported": teams_imported}
