"""YouTube Data API v3 creator ingestion — pastes extracted from video descriptions."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select, update

from celery_app import app
from models.db import CreatorRegistry, Source, async_session_factory
from tasks.ingest.youtube_client import YouTubeClient, YouTubeQuotaExceeded
from tasks.process.deduplicator import TeamDeduplicator
from tasks.process.parser import ShowdownPasteParser, resolve_paste_url
from tasks.process.tagger import tag_and_update_team
from tasks.process.validator import validate_team

logger = logging.getLogger(__name__)

_POKEPASTE_RE = re.compile(r"https?://pokepast\.es/[a-f0-9]+", re.IGNORECASE)
_PASTEBIN_RE = re.compile(r"https?://pastebin\.com/[A-Za-z0-9]+")
_GDOCS_RE = re.compile(r"https?://docs\.google\.com/document/d/[\w-]+/pub\S*")
_RAW_SHOWDOWN_RE = re.compile(
    r"(?:[A-Z][\w' .-]+(?:\s*\([MF]\))?\s*(?:@\s*.+)?\n(?:Ability:.+\n)?(?:-\s*.+\n?){2,4})",
    re.MULTILINE,
)


def extract_pastes_from_description(description: str, creator_regex: str | None = None) -> list[str]:
    found: list[str] = []
    found.extend(_POKEPASTE_RE.findall(description))
    found.extend(_PASTEBIN_RE.findall(description))
    found.extend(_GDOCS_RE.findall(description))
    found.extend(m.strip() for m in _RAW_SHOWDOWN_RE.findall(description))
    if creator_regex:
        try:
            found.extend(re.findall(creator_regex, description))
        except re.error as exc:
            logger.warning("Invalid creator regex %r: %s", creator_regex, exc)
    # de-dup preserving order
    seen: set[str] = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


async def _get_or_create_source(session) -> Source:
    result = await session.execute(select(Source).where(Source.platform == "youtube"))
    source = result.scalar_one_or_none()
    if source is None:
        source = Source(
            platform="youtube", base_url="https://www.googleapis.com/youtube/v3", api_available=True
        )
        session.add(source)
        await session.flush()
    return source


@app.task(bind=True, name="tasks.ingest.youtube.sync_all_creators")
def sync_all_creators(self) -> dict:
    import asyncio

    return asyncio.run(_sync_all_creators())


async def _sync_all_creators() -> dict:
    creators_synced = 0
    videos_scanned_total = 0
    pastes_found_total = 0
    teams_imported_total = 0

    dedup = TeamDeduplicator()
    parser = ShowdownPasteParser()

    try:
        client = YouTubeClient()
    except Exception as exc:  # noqa: BLE001 - missing/invalid API key must not crash Beat
        logger.error("YouTubeClient init failed (missing YOUTUBE_API_KEY?): %s", exc)
        return {"error": str(exc), "creators_synced": 0}

    async with async_session_factory() as session:
        source = await _get_or_create_source(session)
        creators = (
            await session.execute(select(CreatorRegistry).where(CreatorRegistry.is_active.is_(True)))
        ).scalars().all()

        for creator in creators:
            try:
                playlist_id = creator.youtube_playlist_id
                if not playlist_id and creator.youtube_channel_id:
                    playlist_id = client.get_uploads_playlist_id(creator.youtube_channel_id)
                    await session.execute(
                        update(CreatorRegistry)
                        .where(CreatorRegistry.id == creator.id)
                        .values(youtube_playlist_id=playlist_id)
                    )
                if not playlist_id:
                    logger.warning("Creator %s has no channel_id/playlist_id, skipping", creator.name)
                    continue

                published_after = (
                    creator.last_scraped_at.isoformat() if creator.last_scraped_at else None
                )
                videos = client.get_playlist_videos(playlist_id, published_after)
                videos_scanned_total += len(videos)

                video_ids = [v["video_id"] for v in videos]
                descriptions = client.get_video_descriptions(video_ids) if video_ids else {}

                pastes_found = 0
                teams_imported = 0
                for video_id, description in descriptions.items():
                    pastes = extract_pastes_from_description(
                        description, creator.description_paste_regex
                    )
                    pastes_found += len(pastes)
                    for raw_or_url in pastes:
                        raw_paste = (
                            await resolve_paste_url(raw_or_url)
                            if raw_or_url.startswith("http")
                            else raw_or_url
                        )
                        parsed_json = parser.parse(raw_paste)
                        if not parsed_json:
                            continue
                        team, _ = await dedup.upsert_team(
                            session,
                            raw_paste=raw_paste,
                            parsed_json=parsed_json,
                            regulation=None,
                            format_type=None,
                            source_meta={
                                "source_id": source.id,
                                "source_url": f"https://youtube.com/watch?v={video_id}",
                                "scrape_method": "youtube_api",
                                "confidence": 60,
                                "raw_response": {"creator": creator.name, "video_id": video_id},
                            },
                        )
                        teams_imported += 1

                        validation = await validate_team(session, team.id, parsed_json, None, None)
                        if not validation.is_valid:
                            logger.warning("Team %d failed validation: %s", team.id, validation.errors)
                        await tag_and_update_team(session, team.id, parsed_json, None)

                pastes_found_total += pastes_found
                teams_imported_total += teams_imported

                await session.execute(
                    update(CreatorRegistry)
                    .where(CreatorRegistry.id == creator.id)
                    .values(last_scraped_at=datetime.now(timezone.utc))
                )
                await session.commit()
                creators_synced += 1
                logger.info(
                    "youtube creator=%s videos=%d pastes=%d teams=%d",
                    creator.name,
                    len(videos),
                    pastes_found,
                    teams_imported,
                )
            except YouTubeQuotaExceeded as exc:
                logger.error("YouTube quota exceeded, stopping task gracefully: %s", exc)
                break
            except Exception as exc:  # noqa: BLE001 - one creator failing must not kill the rest
                logger.error("Failed syncing creator %s: %s", creator.name, exc)
                await session.rollback()

    return {
        "creators_synced": creators_synced,
        "videos_scanned": videos_scanned_total,
        "pastes_found": pastes_found_total,
        "teams_imported": teams_imported_total,
    }
