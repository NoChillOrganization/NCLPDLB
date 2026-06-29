"""Per-source async rate limiter for the sync pipeline.

Implements a leaky-bucket min-interval limiter (burst=1, concurrency=1 by
default). All adapters in the same process share one limiter per source via
the module-level registry, so cumulative request rate is bounded regardless
of how many coroutines call get_json concurrently.

Intervals are conservative for sources whose real quotas are unknown. Raise
or lower _LIMITS[source] once empirical data is available.

# ponytail: burst=1 leaky bucket. Add token-bucket burst + per-source
#           asyncio.Semaphore only when an adapter actually goes concurrent
#           (today all source loops are sequential).
"""
from __future__ import annotations

import asyncio
import time

# Minimum seconds between consecutive requests per source.
# smogon:     monthly static JSON, ~3 req/run — 0.5s is generous.
# pikalytics: paginated API, quota unknown — 1.0s is most cautious.
# limitless:  public REST, up to ~100 req/run — 0.75s.
# showdown:   community-run, hundreds of replay GETs — 0.5s stays polite.
_LIMITS: dict[str, float] = {
    "smogon":     0.5,
    "pikalytics": 1.0,
    "limitless":  0.75,
    "showdown":   0.5,
}
_DEFAULT_INTERVAL = 1.0

_registry: dict[str, "RateLimiter"] = {}


class RateLimiter:
    """Async leaky-bucket rate limiter — one request per min_interval seconds."""

    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._next_allowed: float = 0.0   # monotonic timestamp
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until the next request slot is available, then claim it."""
        async with self._lock:            # serialize concurrent callers
            now = time.monotonic()
            wait = self._next_allowed - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._next_allowed = max(time.monotonic(), self._next_allowed) + self._min_interval


def get_limiter(source: str) -> RateLimiter:
    """Return (or create) the shared RateLimiter for *source*."""
    return _registry.setdefault(
        source, RateLimiter(_LIMITS.get(source, _DEFAULT_INTERVAL))
    )


# ─── Self-check ──────────────────────────────────────────────────────────────

async def _demo() -> None:
    import time as _t

    limiter = RateLimiter(min_interval=0.05)  # 50 ms — fast enough for a test

    t0 = _t.monotonic()
    await limiter.acquire()
    await limiter.acquire()
    elapsed = _t.monotonic() - t0

    assert elapsed >= 0.05, f"Expected ≥0.05s between two acquires, got {elapsed:.3f}s"

    # Registry smoke-check
    a = get_limiter("smogon")
    b = get_limiter("smogon")
    assert a is b, "Same source should return same singleton"

    print("throttle self-check passed")


if __name__ == "__main__":
    asyncio.run(_demo())
