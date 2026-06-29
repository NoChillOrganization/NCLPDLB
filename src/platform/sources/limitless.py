"""Limitless tournament adapter. Real public REST API (no key required for standings) —
confirmed live 2026-06-23: GET /tournaments, /tournaments/{id}/details, /tournaments/{id}/standings.
VGC standings include the full decklist inline (species id/name/item/ability/attacks/nature/tera).
"""
from __future__ import annotations

from typing import Iterable

import aiohttp

from src.platform.sources.base import RawRecord
from src.platform.sources.http import get_json
from src.platform.throttle import RateLimiter, get_limiter

BASE_URL = "https://play.limitlesstcg.com/api"


class LimitlessAdapter:
    source = "limitless"

    async def fetch(
        self, *, ids: list[str] | None = None, game: str = "VGC",
        limit: int = 50, page: int = 1, **kwargs,
    ) -> Iterable[RawRecord]:
        records = []
        limiter = get_limiter(self.source)
        async with aiohttp.ClientSession() as session:
            tournament_ids = ids if ids else await self._discover_ids(
                session, limiter, game=game, limit=limit, page=page,
            )
            for tid in tournament_ids:
                details = await self._get(session, limiter, f"{BASE_URL}/tournaments/{tid}/details")
                if details is None:
                    continue
                standings = await self._get(session, limiter, f"{BASE_URL}/tournaments/{tid}/standings")
                payload = {"event": details, "standings": standings or []}
                records.append(RawRecord(
                    route="tournament", natural_key=tid, payload=payload,
                    url=f"https://play.limitlesstcg.com/tournament/{tid}",
                ))
        return records

    async def _discover_ids(
        self, session: aiohttp.ClientSession, limiter: RateLimiter,
        *, game: str, limit: int, page: int,
    ) -> list[str]:
        data = await self._get(
            session, limiter, f"{BASE_URL}/tournaments",
            params={"game": game, "limit": limit, "page": page},
        )
        return [t["id"] for t in (data or [])]

    async def _get(
        self, session: aiohttp.ClientSession, limiter: RateLimiter,
        url: str, *, params: dict | None = None,
    ):
        return await get_json(session, url, params=params, limiter=limiter)
