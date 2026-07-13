# pokemon-pipeline

Production-grade, live-updating Pokémon competitive team import and analysis pipeline.

Ingests team data from multiple tournament sources and content creators, stores teams in dual
format (raw Showdown paste + parsed JSON), serves data via REST API, feeds a Discord bot, and
powers AI/ML team analysis models.

## Architecture

```
                         ┌─────────────────────────────────────────┐
                         │            INGESTION LAYER               │
                         │  Limitless API │ LabMaus │ RK9 │ Smogon   │
                         │        YouTube API │ Creator Registry     │
                         │       (Celery tasks, one queue/source)    │
                         └───────────────────┬───────────────────────┘
                                              │
                         ┌───────────────────▼───────────────────────┐
                         │            PROCESSING LAYER                │
                         │ Paste Parser │ pokepast.es Resolver         │
                         │ Deduplicator │ Validator │ Archetype Tagger │
                         │            Provenance Logger                │
                         └───────────────────┬───────────────────────┘
                                              │
                         ┌───────────────────▼───────────────────────┐
                         │              STORAGE LAYER                  │
                         │   PostgreSQL 16 + pgvector (SQLAlchemy)     │
                         │  teams, pokemon_sets, tournaments, sources, │
                         │  players, creator_registry, provenance,     │
                         │  tournament_placements, backfill_log,       │
                         │  team_embeddings                            │
                         └───────────────────┬───────────────────────┘
                                              │
                         ┌───────────────────▼───────────────────────┐
                         │     FastAPI REST + WebSocket │ Discord Bot  │
                         │           ml/ training pipeline             │
                         └─────────────────────────────────────────────┘
```

## Quickstart

```bash
cp .env.example .env
# fill in DISCORD_BOT_TOKEN, YOUTUBE_API_KEY, API_SECRET_KEY

docker compose up --build
docker compose exec fastapi alembic upgrade head
docker compose exec fastapi python -m models.seed
docker compose exec fastapi python -m models.seed_creators
```

- FastAPI docs: http://localhost:8000/docs
- Flower (Celery monitoring): http://localhost:5555
- Classifier microservice: http://localhost:3001/health

## Roadmap

| Phase | Scope |
|-------|-------|
| 1 | DB schema, Limitless API ingest, paste parser, FastAPI skeleton |
| 2 | LabMaus + RK9 scrapers, Celery Beat, backfill system |
| 3 | Smogon forum scraper, YouTube API, creator registry |
| 4 | Discord bot, archetype tagger, legality validator |
| 5 | AI training pipeline — embeddings, classifier, Ollama fine-tune |
| 6 | Web UI, monitoring, production deploy |

## Notes

- 8 Docker Compose services, not 7: the original spec's 7 (postgres, redis, fastapi,
  celery-worker, celery-beat, classifier-node, flower) omitted a runtime for the Discord bot
  built in prompt 16. Added `discord-bot` as an 8th service so `bot/main.py` actually runs.
- Postgres runs as the `pgvector/pgvector:pg16` image (not plain `postgres:16-alpine`) so the
  `vector` extension is available out of the box for `team_embeddings` — no native pgvector
  install needed. Host port mapped to `5433` to avoid colliding with a native local Postgres.
- Redis host port mapped to `6380` for the same reason.
- All env vars are read via `pydantic-settings`, never `os.environ` directly.
- All ingest tasks are idempotent — safe to re-run.
