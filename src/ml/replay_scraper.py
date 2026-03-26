"""
Replay Scraper — downloads battle replays from Pokemon Showdown.

Usage (CLI):
    python -m src.ml.replay_scraper --format gen9ou --pages 50 --min-rating 1600
    python -m src.ml.replay_scraper --format gen9vgc2024regh --pages 100

The scraper:
  1. Queries the Showdown search API for replay metadata
  2. Filters by optional minimum rating
  3. Downloads each replay's full JSON (including the battle log)
  4. Saves to data/replays/<format>/<id>.json
  5. Tracks already-downloaded IDs to avoid duplicates across runs
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import aiohttp

from src.config import PROJECT_ROOT

log = logging.getLogger(__name__)

REPLAYS_DIR = PROJECT_ROOT / "data" / "replays"
SEARCH_URL  = "https://replay.pokemonshowdown.com/search.json"
REPLAY_URL  = "https://replay.pokemonshowdown.com/{id}.json"

# Be respectful — Showdown is a free service
REQUEST_DELAY   = 0.3   # seconds between requests
MAX_CONCURRENCY = 5     # parallel downloads


# ── Data classes ──────────────────────────────────────────────────────────────

class ReplayMeta:
    """Lightweight metadata returned by the search API."""
    __slots__ = ("id", "format", "p1", "p2", "rating", "uploadtime")

    def __init__(self, data: dict[str, Any]) -> None:
        self.id         = data["id"]
        self.format     = data.get("format", "unknown")
        self.p1         = data.get("p1", "")
        self.p2         = data.get("p2", "")
        self.rating     = data.get("rating", 0) or 0
        self.uploadtime = data.get("uploadtime", 0)

    def __repr__(self) -> str:
        return f"<ReplayMeta {self.id} {self.p1} vs {self.p2} rating={self.rating}>"


# ── Scraper ───────────────────────────────────────────────────────────────────

class ReplayScraper:
    """Async scraper that downloads Showdown replays and saves them to disk."""

    def __init__(
        self,
        format: str = "gen9ou",
        min_rating: int = 0,
        output_dir: Path | None = None,
    ) -> None:
        self.format     = format
        self.min_rating = min_rating
        self.out_dir    = (output_dir or REPLAYS_DIR) / format
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = self._load_seen()

    def _load_seen(self) -> set[str]:
        """Load IDs of replays already on disk."""
        return {p.stem for p in self.out_dir.glob("*.json")}

    def _replay_path(self, replay_id: str) -> Path:
        return self.out_dir / f"{replay_id}.json"

    # ── Search API ────────────────────────────────────────────────

    async def _fetch_search_page(
        self,
        session: aiohttp.ClientSession,
        page: int,
    ) -> list[ReplayMeta]:
        """Fetch one page of replay metadata from the search API."""
        params = {"format": self.format, "page": page}
        try:
            async with session.get(SEARCH_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    log.warning(f"Search page {page} returned HTTP {resp.status}")
                    return []
                data = await resp.json(content_type=None)
        except Exception as exc:
            log.warning(f"Search page {page} failed: {exc}")
            return []

        if not isinstance(data, list):
            return []

        metas = [ReplayMeta(item) for item in data]
        if self.min_rating:
            metas = [m for m in metas if m.rating >= self.min_rating]
        return metas

    # ── Individual replay download ─────────────────────────────────

    async def _fetch_replay(
        self,
        session: aiohttp.ClientSession,
        meta: ReplayMeta,
        semaphore: asyncio.Semaphore,
    ) -> bool:
        """Download a single replay and save it. Returns True on success."""
        if meta.id in self._seen:
            return False  # already have it

        async with semaphore:
            url = REPLAY_URL.format(id=meta.id)
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        log.debug(f"Replay {meta.id} returned HTTP {resp.status}")
                        return False
                    data = await resp.json(content_type=None)
            except Exception as exc:
                log.debug(f"Replay {meta.id} download failed: {exc}")
                return False

            # Attach metadata we already know
            data.setdefault("format", self.format)
            data.setdefault("rating", meta.rating)

            path = self._replay_path(meta.id)
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self._seen.add(meta.id)
            await asyncio.sleep(REQUEST_DELAY)
            return True

    # ── Public entry point ─────────────────────────────────────────

    async def scrape(self, pages: int = 10) -> int:
        """
        Scrape `pages` pages of search results and download all new replays.
        Returns the number of newly downloaded replays.
        """
        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENCY)
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        downloaded = 0

        async with aiohttp.ClientSession(connector=connector) as session:
            for page in range(1, pages + 1):
                metas = await self._fetch_search_page(session, page)
                if not metas:
                    log.info(f"Page {page}: no results, stopping early")
                    break

                new_metas = [m for m in metas if m.id not in self._seen]
                log.info(f"Page {page}: {len(metas)} replays ({len(new_metas)} new)")

                if not new_metas:
                    await asyncio.sleep(REQUEST_DELAY)
                    continue

                tasks = [
                    self._fetch_replay(session, meta, semaphore)
                    for meta in new_metas
                ]
                results = await asyncio.gather(*tasks)
                batch = sum(results)
                downloaded += batch
                log.info(f"  Downloaded {batch}/{len(new_metas)} in batch (total: {downloaded})")
                await asyncio.sleep(REQUEST_DELAY)

        log.info(f"Scrape complete. {downloaded} new replays saved to {self.out_dir}")
        return downloaded


# ── Stats helper ──────────────────────────────────────────────────────────────

def replay_stats(format: str | None = None) -> dict[str, int]:
    """Return count of downloaded replays per format."""
    stats: dict[str, int] = {}
    base = REPLAYS_DIR
    if not base.exists():
        return stats
    dirs = [base / format] if format else [d for d in base.iterdir() if d.is_dir()]
    for d in dirs:
        stats[d.name] = len(list(d.glob("*.json")))
    return stats


# ── CLI ───────────────────────────────────────────────────────────────────────

async def _main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(description="Scrape Pokemon Showdown replays")
    parser.add_argument("--format",     default="gen9ou",  help="Showdown format ID")
    parser.add_argument("--pages",      type=int, default=10, help="Search pages to scrape")
    parser.add_argument("--min-rating", type=int, default=0,  help="Minimum player rating filter")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    scraper = ReplayScraper(format=args.format, min_rating=args.min_rating)
    start = time.monotonic()
    count = await scraper.scrape(pages=args.pages)
    elapsed = time.monotonic() - start
    log.info("Done: %d new replays in %.1fs", count, elapsed)
    log.info("Replay counts: %s", replay_stats())


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())
