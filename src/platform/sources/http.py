"""Shared async HTTP GET helper with bounded retry for platform source adapters.

Every adapter that fetches remote JSON should use get_json() instead of calling
session.get() directly.  The policy here mirrors src/data/sheets.py::_with_retry:
full-jitter exponential backoff, retry only transient server errors + transport
failures, raise loud on persistent outage rather than silently returning None.

Retry budget: 4 attempts total (3 retries), ceiling ~8s at default base_delay=0.5.
# ponytail: tune max_tries / base_delay per call-site for rate-limited endpoints
#           (e.g. Pikalytics may need higher base_delay if bursts trigger 429s).
"""
from __future__ import annotations

import asyncio
import random

import aiohttp

# Server-side transient conditions worth retrying.  4xx except 429 are client
# errors (bad URL / missing resource) — do not retry.
RETRY_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})


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
    last_exc: BaseException | None = None
    for attempt in range(max_tries):
        try:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                if resp.status not in RETRY_STATUS:
                    return None  # clean miss — 404, unknown format slug, etc.
                if attempt == max_tries - 1:
                    resp.raise_for_status()  # raises ClientResponseError
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_exc = exc
            if attempt == max_tries - 1:
                raise

        # full-jitter exponential backoff: random in [0, base_delay * 2**attempt]
        delay = base_delay * (2 ** attempt) + random.uniform(0, base_delay)
        await asyncio.sleep(delay)

    # unreachable when max_tries >= 1, but keeps type-checkers happy
    if last_exc is not None:
        raise last_exc  # type: ignore[misc]
    return None  # pragma: no cover
