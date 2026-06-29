"""Shared async HTTP GET helper with bounded retry for platform source adapters.

Every adapter that fetches remote JSON should use get_json() instead of calling
session.get() directly.  The retry loop lives in src.platform.retry.retry_async;
this module owns the HTTP-specific response handling (status dispatch, JSON decode).

Retry budget: 4 attempts total (3 retries), ceiling ~8s at default base_delay=0.5.
# ponytail: tune max_tries / base_delay per call-site for rate-limited endpoints
#           (e.g. Pikalytics may need higher base_delay if bursts trigger 429s).
"""
from __future__ import annotations

import asyncio

import aiohttp

from src.platform.retry import RETRY_STATUS, retry_async


async def get_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    params: dict | None = None,
    timeout: float = 20.0,
    max_tries: int = 4,
    base_delay: float = 0.5,
) -> dict | list | None:
    """GET *url* and return parsed JSON on success.

    Returns:
        Parsed JSON (dict or list) on HTTP 200.
        None on a clean non-retryable miss (404, 410, …) — callers use this
        as a "stop paginating" / "format not found" signal.

    Raises:
        aiohttp.ClientResponseError: when a RETRY_STATUS code persists for all
            *max_tries* attempts.
        aiohttp.ClientError / asyncio.TimeoutError: when a transport error
            persists for all *max_tries* attempts.

    Only transient conditions (RETRY_STATUS + transport errors) are retried;
    all other non-200 responses return None immediately.
    """
    async def _attempt() -> dict | list | None:
        async with session.get(
            url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status == 200:
                return await resp.json(content_type=None)
            if resp.status not in RETRY_STATUS:
                return None  # clean miss — 404, unknown format slug, etc.
            resp.raise_for_status()  # raises ClientResponseError (transient status)
        return None  # unreachable; satisfies type-checker

    return await retry_async(_attempt, max_tries=max_tries, base_delay=base_delay)
