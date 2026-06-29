"""Transport-agnostic async retry with full-jitter backoff and job-level deadline.

Used by get_json (HTTP) and the sync entry points (whole-fetch retry).
Transient/Permanent sentinel exceptions let callers signal the loop without
the classify function seeing every exception type.

Retry budget defaults: 4 attempts, ~8 s ceiling at base_delay=0.5.
# ponytail: tune max_tries/base_delay at call-site for rate-limited sources.
"""
from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

import aiohttp

# HTTP status codes worth retrying (429 = rate-limited, 5xx = server fault).
# 4xx except 429 are client errors — wrong URL / missing resource, do not retry.
RETRY_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})

T = TypeVar("T")


class Transient(Exception):
    """Wrap any cause in this to force a retry without editing is_transient."""


class Permanent(Exception):
    """Wrap any cause in this to suppress retry and re-raise immediately."""


class RateLimited(Transient):
    """Raised by get_json when a 429 carries a Retry-After header.

    retry_async uses retry_after (seconds) as the sleep floor so the caller
    obeys the server's own back-off window instead of guessing.
    # ponytail: delta-seconds only; add RFC-7231 HTTP-date parse if needed.
    """

    def __init__(self, retry_after: float | None) -> None:
        self.retry_after = retry_after
        super().__init__("rate limited")


def is_transient(exc: BaseException) -> bool:
    """Return True for conditions that may resolve on a subsequent attempt.

    Transient:  transport errors, timeouts, server 5xx, rate-limit 429.
    Permanent:  parse errors (ValueError, KeyError, TypeError, json.JSONDecodeError),
                client 4xx (except 429), explicit Permanent wrapper, anything else.
    """
    if isinstance(exc, Permanent):
        return False
    if isinstance(exc, Transient):
        return True
    if isinstance(exc, aiohttp.ClientResponseError):
        return exc.status in RETRY_STATUS
    if isinstance(exc, (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError, OSError)):
        return True
    return False


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    max_tries: int = 4,
    base_delay: float = 0.5,
    deadline: float | None = None,
    classify: Callable[[BaseException], bool] = is_transient,
) -> T:
    """Call *fn()* up to *max_tries* times with full-jitter exponential backoff.

    Args:
        fn:         Zero-argument async callable to attempt.
        max_tries:  Total attempts (not retries). Must be >= 1.
        base_delay: Base sleep in seconds; actual delay is uniform in
                    [0, base_delay * 2**attempt].
        deadline:   Absolute monotonic time (from time.monotonic()) after which
                    no further attempts are made. None = no job-level deadline.
        classify:   Predicate — True means retry, False means raise immediately.
                    Defaults to is_transient; override per call-site if needed.

    Returns:
        Whatever *fn()* returns on success.

    Raises:
        The last exception when all attempts are exhausted, deadline is exceeded,
        or classify() returns False (permanent failure).
    """
    last_exc: BaseException | None = None
    for attempt in range(max_tries):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if not classify(exc):
                raise  # permanent — give up immediately
            if attempt == max_tries - 1:
                raise  # exhausted

        # Check deadline AFTER the attempt, before sleeping — guarantees ≥1 attempt.
        if deadline is not None and time.monotonic() >= deadline:
            break

        # Full-jitter: random in [0, base_delay * 2**attempt].
        # If the exception carries a Retry-After hint, use it as the floor
        # so we honour the server's own back-off window.
        # Note: `exc` is deleted by Python after the except block; use last_exc.
        hint = getattr(last_exc, "retry_after", None)
        delay = max(random.uniform(0, base_delay * (2 ** attempt)), hint or 0.0)
        await asyncio.sleep(delay)

    # Deadline exceeded mid-loop
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("retry_async: max_tries must be >= 1")  # pragma: no cover


# ─── Self-check ──────────────────────────────────────────────────────────────

async def _demo() -> None:
    import time as _time

    call_log: list[int] = []

    # (a) transient: fails twice then succeeds
    async def flaky() -> str:
        call_log.append(1)
        if len(call_log) < 3:
            raise aiohttp.ServerConnectionError("boom")
        return "ok"

    result = await retry_async(flaky, base_delay=0.0)
    assert result == "ok", result
    assert len(call_log) == 3, call_log

    # (b) permanent: raises immediately, no sleep
    call_log.clear()

    async def bad_parse() -> None:
        call_log.append(1)
        raise ValueError("invalid json")

    try:
        await retry_async(bad_parse, base_delay=0.0)
        assert False, "should have raised"
    except ValueError:
        pass
    assert len(call_log) == 1, call_log  # no retry

    # (c) deadline: aborts before all tries consumed
    call_log.clear()
    past = _time.monotonic() - 1.0  # already expired

    async def slow() -> None:
        call_log.append(1)
        raise aiohttp.ServerConnectionError("transient")

    try:
        await retry_async(slow, max_tries=10, base_delay=0.0, deadline=past)
    except aiohttp.ServerConnectionError:
        # Expected: deadline is already expired, so the transient error is re-raised.
        pass
    assert len(call_log) == 1, call_log  # deadline caught before second attempt

    print("retry_async self-check passed")


if __name__ == "__main__":
    asyncio.run(_demo())
