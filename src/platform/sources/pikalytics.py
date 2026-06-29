"""Pikalytics usage adapter. Endpoint /api/l/{format}/{page} confirmed live (returns [] when
empty/unknown format slug) — verified 2026-06-23. Exact non-empty payload shape NOT verified
(no live sample with data obtained); field names below are best-effort and may need adjustment
once a real payload is seen. Land raw is safe regardless — only normalize/usage.py needs the
field names to be exact.
# ponytail: paginates until an empty page; confirm `format` slugs against pikalytics.com URLs.
"""
from __future__ import annotations

from typing import Iterable

import aiohttp

from src.platform.sources.base import RawRecord
from src.platform.sources.http import get_json
from src.platform.throttle import get_limiter

LEADS_URL = "https://www.pikalytics.com/api/l/{format}/{page}"


class PikalyticsAdapter:
    source = "pikalytics"

    async def fetch(self, *, formats: list[str], max_pages: int = 10, **kwargs) -> Iterable[RawRecord]:
        records = []
        limiter = get_limiter(self.source)
        async with aiohttp.ClientSession() as session:
            for fmt in formats:
                pages = []
                for page in range(max_pages):
                    url = LEADS_URL.format(format=fmt, page=page)
                    data = await get_json(session, url, limiter=limiter)
                    if not data:  # None (clean miss / 404) or empty list → stop paginating
                        break
                    pages.extend(data)
                if pages:
                    records.append(RawRecord(
                        route="usage", natural_key=f"pikalytics-{fmt}",
                        payload={"format": fmt, "entries": pages}, url=LEADS_URL.format(format=fmt, page=0),
                    ))
        return records
