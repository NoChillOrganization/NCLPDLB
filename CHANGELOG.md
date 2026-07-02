# Changelog

All notable changes to NCLPDLB are documented here.

---

## [Unreleased] · June–July 2026

### Platform & Data Ingestion *(New)*

Competitive data pipeline is now live. The bot can ingest and normalize Pokémon usage
statistics, tournament results, and replay data from Limitless, Pikalytics, Showdown, and
Smogon automatically.

- **Retry-safe sync** — all four data sources retry failed requests with exponential backoff
  and Retry-After header support; transient errors no longer silently drop data
- **Dead-letter queue** — failed records are written to a dead-letter table with error context
  for manual review instead of being lost
- **Batch upserts** — tournament, match, and replay records insert efficiently with
  deduplication (no duplicate entries even on re-sync)
- **Species normalization** — Pokémon names and forms are canonicalized consistently across
  all sources (e.g. `Urshifu-Rapid-Strike` regardless of source spelling variation)
- **Monitoring & alerts** — structured pipeline health logs, monitoring views, and configurable
  alerts for sync failures and stale data
- **Per-source rate limiting** — each scraping target respects its own rate limit and backs
  off on 429 responses

### ML Training *(Improvement)*

- Added VGC 2026 format configurations for double-battle training

### Infrastructure

- **CI/CD pipeline** — automated data sync jobs run on schedule via GitHub Actions
- **CodeQL security scanning** added with correct workflow permissions
- Ruff formatting applied repo-wide; lint clean across all source files

### Bug Fixes

- Fixed malformed SQL in `bulk_upsert_returning` — double-wrapped `unnest` caused a runtime
  error on batch insert
- Fixed `PLATFORM_DATABASE_URL` empty-string guard — was passing empty string to asyncpg
  instead of `None`, causing auth failures
- Capped NumPy `<2.5.0` to keep Python 3.11 CI installable (NumPy 2.5 dropped 3.11 support)

### Security

- Updated pydantic-settings to `2.14.2` (patches GHSA-4xgf-cpjx-pc3j)

### Dependencies Updated

- asyncpg `≥0.31.0`
- FastAPI `≥0.138.2`
- google-auth `≥2.55.1`
- numpy `≥2.4.0,<2.5.0`
- playwright `≥1.61.0`
- pydantic-settings `2.14.2`
- pytest `≥9.1.1`
- ruff `≥0.15.20`
- actions/checkout v7
- actions/setup-python v6
- actions/github-script v9
