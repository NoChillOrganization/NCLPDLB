"""RateLimitedClient (all HTTP goes through this), robots.txt check, and small helpers."""

from __future__ import annotations

import asyncio
import datetime
import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

USER_AGENT = "pokemon-pipeline/0.1 (+contact: pipeline-admin@localhost; respectful research bot)"

_PER_DOMAIN_DELAY = {
    "play.limitlesstcg.com": 0.5,
    "labmaus.net": 3.0,
    "rk9.gg": 2.0,
    "smogon.com": 2.0,
}
_DEFAULT_DELAY = 1.0


class RateLimitedClient:
    """Wraps httpx.AsyncClient with per-domain delay, robots.txt check, and Retry-After handling."""

    def __init__(self):
        self._client = httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=15.0)
        self._last_request_at: dict[str, float] = {}
        self._robots_checked: set[str] = set()

    async def __aenter__(self) -> "RateLimitedClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aclose()

    async def _respect_delay(self, domain: str) -> None:
        delay = _PER_DOMAIN_DELAY.get(domain, _DEFAULT_DELAY)
        last = self._last_request_at.get(domain)
        loop = asyncio.get_event_loop()
        now = loop.time()
        if last is not None:
            elapsed = now - last
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)
        self._last_request_at[domain] = loop.time()

    async def _check_robots(self, url: str) -> None:
        domain = urlparse(url).netloc
        if domain in self._robots_checked:
            return
        self._robots_checked.add(domain)
        try:
            robots_url = f"{urlparse(url).scheme}://{domain}/robots.txt"
            resp = await self._client.get(robots_url, timeout=5.0)
            if resp.status_code == 200:
                parser = RobotFileParser()
                parser.parse(resp.text.splitlines())
                if not parser.can_fetch(USER_AGENT, url):
                    logger.warning("robots.txt disallows fetching %s", url)
        except Exception as exc:  # noqa: BLE001 - robots.txt check is best-effort
            logger.debug("robots.txt check failed for %s: %s", domain, exc)

    @retry(
        wait=wait_exponential(multiplier=2, min=2, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    )
    async def get(self, url: str, **kwargs) -> httpx.Response:
        domain = urlparse(url).netloc
        await self._check_robots(url)
        await self._respect_delay(domain)
        resp = await self._client.get(url, **kwargs)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait_s = float(retry_after) if retry_after and retry_after.isdigit() else 30.0
            logger.warning("429 from %s, sleeping %.1fs", domain, wait_s)
            await asyncio.sleep(wait_s)
            resp.raise_for_status()
        resp.raise_for_status()
        return resp

    @retry(
        wait=wait_exponential(multiplier=2, min=2, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    )
    async def post(self, url: str, **kwargs) -> httpx.Response:
        domain = urlparse(url).netloc
        await self._respect_delay(domain)
        resp = await self._client.post(url, **kwargs)
        resp.raise_for_status()
        return resp


def chunk_list(lst: list, n: int) -> list[list]:
    """Split lst into chunks of size n."""
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def date_filter(date_str: str | None, cutoff: str = "2026-04-01") -> bool:
    """True if date_str is on/after cutoff. Unparsable/missing dates are excluded (False)."""
    if not date_str:
        return False
    try:
        d = datetime.date.fromisoformat(date_str[:10])
    except ValueError:
        return False
    return d >= datetime.date.fromisoformat(cutoff)
