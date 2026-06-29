"""Smogon usage-stats adapter. Chaos JSON endpoint — stable, public, no auth, unchanged ~10y."""
from __future__ import annotations

from typing import Iterable

import aiohttp

from src.platform.sources.base import RawRecord
from src.platform.sources.http import get_json

STATS_URL = "https://www.smogon.com/stats/{period}/chaos/{format}-{cutoff}.json"


class SmogonAdapter:
    source = "smogon"

    async def fetch(
        self, *, period: str, formats: list[str], cutoff: int = 1500, **kwargs,
    ) -> Iterable[RawRecord]:
        """period: 'YYYY-MM'. One RawRecord per format — payload covers every species
        in that snapshot (matches usage_snapshot's one-row-per-format-period-cutoff grain).
        """
        records = []
        async with aiohttp.ClientSession() as session:
            for fmt in formats:
                url = STATS_URL.format(period=period, format=fmt, cutoff=cutoff)
                data = await get_json(session, url, timeout=30.0)
                if isinstance(data, dict) and "data" in data:
                    records.append(RawRecord(
                        route="usage", natural_key=f"{fmt}-{cutoff}-{period}", payload=data, url=url,
                    ))
        return records
