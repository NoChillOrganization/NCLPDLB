# Platform Assembly Guide

Reference for contributors building on or debugging the `src/platform/` competitive
Pokémon data pipeline. Covers project layout, build order, layer contracts, and
day-to-day operations.

---

## Project Tree

```
src/platform/
├── config.py                  # DB URL from env (PLATFORM_DATABASE_URL)
├── seed.py                    # One-shot: seeds canonical_species + species_alias rows
├── monitoring.py              # Health-checker: queries alert views, exits 1 if firing
├── orchestrate.py             # Shared ingest loop (land_and_normalize, with_ingest_run)
├── retry.py                   # Async retry with full-jitter backoff + transient classifier
├── throttle.py                # Per-source rate limiter (asyncio.Semaphore wrappers)
│
├── sources/                   # Layer 1 — fetch external data → RawRecord
│   ├── base.py                # RawRecord dataclass + SourceAdapter ABC
│   ├── http.py                # Shared HTTP client with retry + throttle wiring
│   ├── smogon.py              # Smogon chaos JSON (monthly usage stats)
│   ├── pikalytics.py          # Pikalytics usage endpoint
│   ├── limitless.py           # Limitless VGC tournament standings API
│   └── showdown.py            # Pokémon Showdown replay search
│
├── normalize/                 # Layer 3 — RawRecord.payload → canonical DB rows
│   ├── species.py             # canonicalize_species, normalize_team_member, normalize_replay_pokemon
│   ├── usage.py               # route='usage' → usage_snapshot/entry/moveset
│   ├── tournament.py          # route='tournament' → tournament_event/team/member/match
│   └── replay.py              # route='replay' → replay/replay_battle/team_member
│
├── store/                     # Layer 2 — DB access
│   ├── db.py                  # asyncpg pool, migrate() runner
│   ├── db_upserts.py          # Bulk batch helpers: ingest_usage_batch, ingest_tournament_batch,
│   │                          #   ingest_replays_batch; generic bulk_upsert / bulk_upsert_returning
│   ├── repositories.py        # Single-row helpers: land_raw, resolve_species, resolve_source_id,
│   │                          #   mark_raw_processed, to_dead_letter, upsert_canonical_format
│   └── migrations/
│       ├── 0001_init.sql      # Core schema: source, raw_ingest, canonical tables, ingest_run
│       ├── 0002_analytics.sql # Analytics views + canonical_species / species_alias tables
│       ├── 0003_dead_letter.sql  # dead_letter table (append-only parse failure sink)
│       ├── 0004_monitoring.sql   # source_health, stale_sources, recent_dead_letters views
│       └── 0005_dedup_indexes.sql  # COALESCE functional indexes for NULL-safe tournament dedup
│
├── sync_all.py                # Multi-source orchestrator (primary entry point)
├── sync_smogon.py             # Targeted: smogon only
├── sync_pikalytics.py         # Targeted: pikalytics only
├── sync_limitless_vgc.py      # Targeted: limitless only
└── sync_replays.py            # Targeted: replays only
```

---

## Implementation Order

The platform was assembled in six phases. Run them in this order when rebuilding from
scratch or diagnosing a regression.

### Phase 0 — NULL-key dedup indexes

**Why first:** `tournament_team` and `match` have NULLable key columns. `NULL != NULL`
in SQL, so `ON CONFLICT` without a COALESCE expression silently inserts duplicates on
re-run. Fix this before bulk-writing tournament data.

```bash
# Applied automatically by migrate() — run once to confirm:
python -m src.platform.store.db   # or: python -m src.platform.sync_all --dry-run
```

Key indexes created by `0005_dedup_indexes.sql`:

```sql
CREATE UNIQUE INDEX uq_tournament_team_coalesce
    ON tournament_team (event_id, COALESCE(placement, -1), COALESCE(player_external_id, ''));

CREATE UNIQUE INDEX uq_match_coalesce
    ON match (event_id, COALESCE(round, -1), COALESCE(player1_team_id, -1), COALESCE(player2_team_id, -1));
```

`db_upserts.py` passes the matching expression via the `conflict_target` param so
`ON CONFLICT` hits the functional index rather than a bare column list.

### Phase 1 — Species canonicalization

`normalize/species.py` is the single species-resolution authority:

| Function | Used by |
|---|---|
| `canonicalize_species(raw)` | `usage.py` (via `_resolve_species_id`) |
| `normalize_team_member(mon)` | `tournament.py` |
| `normalize_replay_pokemon(species)` | `replay.py` |

Resolution steps (in order): exact match → form override table → base-strip → fuzzy →
unresolved. All three normalizers now go through this chain; there is no raw `_normalized_key`
fallback in the live path.

### Phase 2 — Bulk upserts wired

Each normalizer builds one batch dict and calls the corresponding batch helper. This
collapses N per-entry round-trips into one `unnest`-based statement per entity type.

```
normalize_usage_row     → ingest_usage_batch(conn, [snapshot])
normalize_tournament_row → ingest_tournament_batch(conn, [event_dict])
normalize_replay_row    → ingest_replays_batch(conn, [replay_dict])
```

`ingest_usage_batch` shape:

```python
{
    "source_id": int,
    "format_id": int,
    "period": "YYYY-MM-DD",
    "elo_cutoff": int | None,
    "sample_size": int | None,
    "raw_ingest_id": int | None,
    "entries": [
        {
            "canonical_species_id": int | None,
            "rank": int,
            "usage_pct": float | None,
            "raw_count": int | None,
            "moveset": {"moves": {}, "items": {}, "spreads": {}, "abilities": {}, "teammates": {}, "checks": {}},
        }
    ],
}
```

See `db_upserts.py` docstrings for `ingest_tournament_batch` and `ingest_replays_batch`
shapes.

### Phase 3 — Multi-source orchestrator

`sync_all.py` is the primary periodic entry point:

```bash
# All sources, 5-minute budget
python -m src.platform.sync_all

# Specific sources
python -m src.platform.sync_all --sources limitless replays

# Dry-run (fetch + validate, no DB writes)
python -m src.platform.sync_all --dry-run

# Custom deadline
python -m src.platform.sync_all --deadline-seconds 600
```

Sources run sequentially. One source failing does not abort the rest — errors are
collected and a non-zero exit code is returned at the end.

### Phase 4 — Legacy sync.py removed

`sync.py` (monolith with `seed|usage|event|replay` subcommands) is deleted. Its roles
are now split:

| Old subcommand | Replacement |
|---|---|
| `sync seed` | `python -m src.platform.seed` |
| `sync usage` | `python -m src.platform.sync_smogon` or `sync_all` |
| `sync event` | `python -m src.platform.sync_limitless_vgc` or `sync_all` |
| `sync replay` | `python -m src.platform.sync_replays` or `sync_all` |

### Phase 5 — DB test coverage in CI

`tests.yml` runs a `platform` job with a `postgres:16` service and
`PLATFORM_DATABASE_URL` set. This lifts the `@pytest.mark.skipif(not DATABASE_URL)`
guard on all DB-integration tests. `test_batch_idempotency.py` exercises:

- `ingest_usage_batch` idempotency (same snapshot twice → count stays 1)
- `ingest_tournament_batch` with NULL placement/player_external_id (COALESCE dedup)

### Phase 6 — This document

---

## Layer Contracts

### RawRecord (sources → store)

```python
@dataclass
class RawRecord:
    source: str       # matches source.name in DB
    route: str        # 'usage' | 'tournament' | 'replay'
    natural_key: str  # unique within source+route; used as idempotency key
    payload: dict     # raw JSON from the external API
    url: str | None   # origin URL for audit trail
```

Every adapter `yield`s `RawRecord` objects. No parsing happens in adapters — payload is
the raw API response.

### raw_ingest idempotency anchor

`raw_ingest` has `UNIQUE(source_id, natural_key, payload_hash)`. `land_raw` returns:

- `int` (the new row id) — first time this payload is seen
- `None` — exact duplicate; `land_and_normalize` skips normalization

Changing any field of the payload (even whitespace) counts as a new payload and triggers
re-normalization. This is intentional: schema changes in upstream APIs surface as new
payloads.

### raw_ingest_id lineage

Every canonical row that traces to a raw payload stores `raw_ingest_id`. This lets you
answer "which raw record produced this tournament team?" via a single join:

```sql
SELECT r.natural_key, r.payload
FROM tournament_team t
JOIN raw_ingest r ON r.id = t.raw_ingest_id
WHERE t.id = $1;
```

### Normalizer signature

```python
async def normalize_*_row(
    conn: asyncpg.Connection,
    *,
    raw_id: int,
    source: str,
    natural_key: str,
    payload: dict,
) -> int:  # canonical row id (snapshot_id / event_id / battle_id)
```

`land_and_normalize` in `orchestrate.py` calls this. Normalizers must call
`mark_raw_processed(conn, raw_id=raw_id, normalizer_version=N)` before returning.

---

## Adding a New Source

1. **Adapter** — create `sources/<name>.py`, implement `SourceAdapter.fetch()` returning
   `Iterable[RawRecord]`. Reuse `http.py::get_json` for HTTP + retry + throttle.

2. **Normalizer** — create `normalize/<name>.py` with a `normalize_<name>_row` function
   matching the normalizer signature above. Pick the correct batch helper from
   `db_upserts.py`.

3. **Register in sync_all** — add the source name to `ALL_SOURCES` in `sync_all.py`,
   add a branch in `_run_source`, wire adapter + normalizer + route.

4. **Seed row** — add the source to the seed fixture so `source.name` resolves in DB:
   ```sql
   INSERT INTO source (name, display_name, cadence) VALUES ('myname', 'My Source', 'daily');
   ```
   Or add to `seed.py` and re-run `python -m src.platform.seed`.

5. **Test** — add an integration test in `tests/platform/` guarded by
   `PLATFORM_DATABASE_URL`, following the pattern in `test_batch_idempotency.py`.

---

## Running and Re-running

### Periodic sync (CI)

```yaml
# .github/workflows/sync-prod.yml
- name: Sync daily sources
  run: python -m src.platform.sync_all --sources limitless replays ...

- name: Sync monthly sources
  run: python -m src.platform.sync_all --sources smogon pikalytics ...

- name: Check health
  run: python -m src.platform.monitoring
```

### Manual re-run

Re-running `sync_all` on already-ingested data is safe. `land_raw` skips exact
duplicates; normalizers are only called for new payloads.

To force re-normalization of a specific raw record (e.g., after a normalizer bug fix):

```sql
-- Reset processed flag so land_and_normalize calls the normalizer again
UPDATE raw_ingest SET processed_at = NULL, normalizer_version = NULL WHERE id = $1;
```

Then re-run the targeted sync script for that source.

### Dry-run validation

```bash
python -m src.platform.sync_all --dry-run
```

Fetches all sources and validates `RawRecord` shapes (non-empty `natural_key` and
`payload`) without any DB writes. Use this to smoke-test adapter changes or to verify
credentials work without touching production data.

### Deadline budget

`--deadline-seconds` (default 300) is a wall-clock budget shared across all selected
sources. Each source's `retry_async` call receives the remaining monotonic deadline.
When a source times out, it raises `TimeoutError` (caught per-source) and the next
source starts. Set `--deadline-seconds 0` for no limit.

---

## Observing the Pipeline

### Monitoring views (SQL)

`0004_monitoring.sql` creates four views:

| View | What it shows |
|---|---|
| `source_health` | Last ok run, last error run, total ok/error counts per source |
| `stale_sources` | Sources whose last ok run is older than their expected cadence |
| `recent_dead_letters` | Dead-letter rows with a natural_key in the last 24 h |
| `volume_baseline` | 30-day landing average per source (used by monitoring.py) |

Quick health check:

```sql
SELECT * FROM source_health;
SELECT * FROM stale_sources;
SELECT * FROM recent_dead_letters ORDER BY created_at DESC LIMIT 20;
```

### monitoring.py alerts

```bash
python -m src.platform.monitoring          # prints JSON alerts + exits 1 if any fire
python -m src.platform.monitoring --quiet  # exit code only (CI gate)
```

Four alert types: `STALE_SYNC`, `REPEATED_FAILURE`, `VOLUME_DROP`, `PARSE_ERRORS`.

### Dead-letter drain workflow

Dead-letter rows are parse failures that need operator attention:

```sql
-- List unresolved errors
SELECT source, route, natural_key, error, created_at
FROM dead_letter
WHERE resolved_at IS NULL
ORDER BY created_at DESC;

-- After fixing the normalizer and re-running, mark drained:
UPDATE dead_letter SET resolved_at = now() WHERE id IN (...);
```

Dead-letter rows are never deleted — they are the audit trail of every parse failure.

### ingest_run log

```sql
SELECT source_id, route, mode, status, stats, started_at, finished_at
FROM ingest_run
ORDER BY started_at DESC
LIMIT 20;
```

`stats` is JSONB: `{"landed": N, "normalized": M, "errored": K, "sync_duration_seconds": F}`.
