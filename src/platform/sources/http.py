"""Shared async HTTP GET helper with bounded retry for platform source adapters.

Every adapter that fetches remote JSON should use get_json() instead of calling
session.get() directly.  The retry loop lives in src.platform.retry.retry_async;
this module owns the HTTP-specific response handling (status dispatch, JSON decode,
Retry-After header parsing) and the per-source rate-limiter hook.

Retry budget: 4 attempts total (3 retries), ceiling ~8s at default base_delay=0.5.
# ponytail: tune max_tries / base_delay per call-site for rate-limited endpoints
#           (e.g. Pikalytics may need higher base_delay if bursts trigger 429s).
"""

from __future__ import annotations


import aiohttp

from src.platform.retry import RETRY_STATUS, RateLimited, retry_async
from src.platform.throttle import RateLimiter


def _parse_retry_after(headers: "aiohttp.CIMultiDictProxy[str]") -> float | None:
    """Return Retry-After value as seconds, or None if absent/unparseable.

    Only handles the integer delta-seconds form (by far the most common).
    # ponytail: add RFC-7231 HTTP-date parse (email.utils.parsedate_to_datetime)
    #           if a source returns a date-string instead.
    """
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None  # HTTP-date string or garbage — fall back to jitter


async def get_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    params: dict | None = None,
    timeout: float = 20.0,
    max_tries: int = 4,
    base_delay: float = 0.5,
    limiter: RateLimiter | None = None,
) -> dict | list | None:
    """GET *url* and return parsed JSON on success.

    Args:
        session:    Shared aiohttp ClientSession.
        url:        Full URL to GET.
        params:     Optional query-string parameters.
        timeout:    Total request timeout in seconds.
        max_tries:  Total attempts (passed to retry_async).
        base_delay: Base jitter delay (passed to retry_async).
        limiter:    Optional per-source RateLimiter. When provided, acquire()
                    is called before every attempt (including retries) so
                    the request rate stays within the source's quota.

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
        if limiter is not None:
            await limiter.acquire()
        async with session.get(
            url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status == 200:
                return await resp.json(content_type=None)
            if resp.status == 429:
                raise RateLimited(_parse_retry_after(resp.headers))
            if resp.status not in RETRY_STATUS:
                return None  # clean miss — 404, unknown format slug, etc.
            resp.raise_for_status()  # raises ClientResponseError (transient status)
        return None  # unreachable; satisfies type-checker

    return await retry_async(_attempt, max_tries=max_tries, base_delay=base_delay)
