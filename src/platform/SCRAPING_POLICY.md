# NCLPDLB Scraping Policy

Governs how the `src/platform/` sync layer interacts with external data sources.
All four sources are polled (none expose webhooks); this document codifies the
rate-limit policy, throttle strategy, and per-source recommendations.

---

## Rate-Limit Policy

**Principle**: never rely on receiving a 429 to learn the rate limit. Apply
a conservative min-interval per source at the call site, before the request
leaves the process. 429s are handled reactively (see §Throttle Strategy) but
should be rare if the proactive limits are correct.

### Per-source intervals

| Source | Min interval | Rationale |
|--------|-------------|-----------|
| smogon | 0.5 s | Monthly static JSON; ~3 requests per run. 0.5 s is generous — raise to 0 if it proves unnecessary. |
| pikalytics | 1.0 s | Paginated private API; no documented quota. 1.0 s is the most conservative default. Lower once the real limit is confirmed. |
| limitless | 0.75 s | Public REST API; up to ~100 requests per run (list + details + standings per tournament). |
| showdown | 0.5 s | Community-run server; ladder search + individual replay GETs can total hundreds of requests per run. 0.5 s keeps traffic low. |

Tune values in `src/platform/throttle.py::_LIMITS`.

### Concurrency

All source adapters loop **sequentially** — concurrency is 1 by design. Do not
introduce `asyncio.gather` across adapters without also adding a per-source
`asyncio.Semaphore` capped at the known concurrency limit (currently unknown
for all four sources).

---

## Throttle Strategy

Three complementary layers in order of application:

### 1. Proactive min-interval (`throttle.py`)

`RateLimiter.acquire()` is called before every HTTP request (including retries).
Implements a leaky-bucket with burst=1: requests are spaced at least
`min_interval` seconds apart within the same Python process.

```
get_json(session, url, limiter=get_limiter(source))
         ↓
   limiter.acquire()      # sleep if needed; claim next slot
         ↓
   session.get(url)
```

### 2. Reactive retry with full-jitter backoff (`retry.py`)

`retry_async` retries transient failures (429, 5xx, transport errors) up to
`max_tries=4` with full-jitter exponential backoff:

```
delay = random(0, base_delay × 2^attempt)
```

Default budget: 4 attempts, ~8 s ceiling at `base_delay=0.5`.

### 3. Retry-After header override (`http.py`)

On a 429 that carries a `Retry-After: <seconds>` header, `get_json` raises
`RateLimited(retry_after=N)`. `retry_async` then sleeps `max(jitter, N)` so
the server's own back-off window is always honoured:

```
hint = exc.retry_after          # seconds from Retry-After header, or None
delay = max(jitter, hint or 0)
```

Only delta-seconds form is parsed; HTTP-date strings fall back to plain jitter.

---

## Source-Specific Recommendations

### Smogon

- **Cadence**: monthly (run on the 1st of each month via cron).
- **Webhook / event-driven?** No. Stats are static files published to
  `smogon.com/stats/YYYY-MM/chaos/`. Polling is the correct strategy.
- **Recommendation**: keep 0.5 s interval; reduce to 0.1 s if Smogon's CDN
  proves insensitive (it almost certainly is — these are static files).

### Pikalytics

- **Cadence**: daily or weekly; run monthly aligned with Smogon.
- **Webhook / event-driven?** No public webhook or event feed documented.
- **Recommendation**: maintain 1.0 s interval until a documented quota is
  found. If `pages=1` consistently returns all data, the pagination loop
  fires only once and the interval is irrelevant.

### Limitless

- **Cadence**: daily (new tournaments posted throughout the season).
- **Webhook / event-driven?** No webhook documented in the public API.
- **Recommendation**: 0.75 s covers the worst-case burst (50 tournaments ×
  2 calls = 100 requests ≈ 75 s wall time). If response times are slow
  (>1 s), the natural latency already provides the gap and the throttle
  fires rarely. Consider reducing `limit` to 20 for non-peak periods.

### Showdown

- **Cadence**: daily replay sweep (ladder search + individual replay GETs).
- **Webhook / event-driven?** 
  **The only viable event path**: the Showdown websocket (used by
  `src.ml.replay_scraper`) emits `|win|` messages at battle end, which
  could trigger targeted replay fetches instead of periodic search.json
  polling. This would eliminate the burst problem entirely.
  **Recommended as a future migration** — not in scope for this change.
- **Current recommendation**: 0.5 s interval; limit `--pages` to 5–10 in
  production (50–100 replay IDs per day is adequate for VGC analytics).
  The replay GETs themselves are the heavy phase: with 0.5 s/request and
  100 replays, expect ~50 s wall time. This is acceptable in a background job.

---

## Stagger Between Sources (Schedule)

Sources run as **sequential steps** in `sync-prod.yml`. The two cron triggers
are at distinct times:

- `0 9 1 * *` — monthly: Smogon + Pikalytics (1st of month, 09:00 UTC)
- `0 6 * * *` — daily:   Limitless + Showdown (06:00 UTC every day)

No two sources run concurrently — stagger is achieved by execution order, not
by clock offsets. If the workflow is ever split into parallel jobs, add explicit
`cron` minute offsets (e.g., Limitless at 06:00, Showdown at 06:30) and
per-source `asyncio.Semaphore(1)` guards.
