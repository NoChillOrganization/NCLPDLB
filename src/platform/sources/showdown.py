"""Showdown replay adapter. Fetches replay JSON by id or via ladder search. No disk writes."""
from __future__ import annotations

from typing import Iterable

import aiohttp

from src.platform.sources.base import RawRecord
from src.platform.sources.http import get_json

REPLAY_URL = "https://replay.pokemonshowdown.com/{id}.json"
SEARCH_URL = "https://replay.pokemonshowdown.com/search.json"


class ShowdownAdapter:
    source = "showdown"

    async def fetch(
        self,
        *,
        ids: list[str] | None = None,
        format: str | None = None,
        pages: int = 10,
        min_rating: int = 0,
        **kwargs,
    ) -> Iterable[RawRecord]:
        """Fetch replay JSON records.

        Two modes — exactly one of *ids* or *format* should be supplied:

        replay_targeted (``ids`` given):
            Fetch each replay by its explicit ID. Used by sync_replays --ids.

        periodic / ladder (``format`` given):
            Discover recent replays for *format* via search.json (same endpoint
            as src.ml.replay_scraper), filter by *min_rating* client-side, then
            fetch each replay's JSON. Disk-free — emits RawRecord only.

        # ponytail: rating filter is client-side (search API has no rating param),
        #           matching replay_scraper.py behaviour.
        """
        records: list[RawRecord] = []
        async with aiohttp.ClientSession() as session:
            if ids is not None:
                await self._fetch_by_ids(session, ids, records)
            elif format is not None:
                await self._fetch_ladder(session, format, pages, min_rating, records)
        return records

    async def _fetch_by_ids(
        self,
        session: aiohttp.ClientSession,
        ids: list[str],
        records: list[RawRecord],
    ) -> None:
        for replay_id in ids:
            url = REPLAY_URL.format(id=replay_id)
            data = await get_json(session, url)
            if isinstance(data, dict):
                records.append(RawRecord(
                    route="replay", natural_key=replay_id, payload=data, url=url,
                ))

    async def _fetch_ladder(
        self,
        session: aiohttp.ClientSession,
        format: str,
        pages: int,
        min_rating: int,
        records: list[RawRecord],
    ) -> None:
        collected_ids: list[str] = []
        for page in range(1, pages + 1):
            results = await get_json(session, SEARCH_URL, params={"format": format, "page": page})
            if not results:
                break
            for entry in results:
                if not isinstance(entry, dict):
                    continue
                if min_rating and (entry.get("rating") or 0) < min_rating:
                    continue
                if "id" in entry:
                    collected_ids.append(entry["id"])
        await self._fetch_by_ids(session, collected_ids, records)
