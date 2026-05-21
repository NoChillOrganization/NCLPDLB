<!-- Generated: 2026-04-17 | Files scanned: ~15 | Token estimate: ~700 -->

# Data Layer

## SQLite Schema (src/data/db.py)

```sql
-- Active (in-progress) draft state
CREATE TABLE IF NOT EXISTS active_drafts (
    guild_id   TEXT PRIMARY KEY,
    draft_json TEXT NOT NULL,       -- Draft.model_dump_json()
    updated_at TEXT NOT NULL        -- ISO 8601 UTC
);

-- ELO ratings write-through cache
CREATE TABLE IF NOT EXISTS elo_ratings (
    guild_id     TEXT NOT NULL,
    player_id    TEXT NOT NULL,
    elo          INTEGER NOT NULL DEFAULT 1000,
    wins         INTEGER NOT NULL DEFAULT 0,
    losses       INTEGER NOT NULL DEFAULT 0,
    streak       INTEGER NOT NULL DEFAULT 0,
    display_name TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (guild_id, player_id)
);
```

## db.py API (async, aiosqlite)

```python
init_db()                         # Create tables; called from setup_hook
save_draft(guild_id, draft_json)  # Upsert active draft
delete_draft(guild_id)            # Remove completed/cancelled draft
load_all_drafts() -> list[tuple[str, str]]   # (guild_id, draft_json)
save_elo(guild_id, player_id, elo, wins, losses, streak, display_name)
load_all_elo() -> list[dict]      # All ELO rows as dicts
```

DB path: `settings.database_url` (default `sqlite+aiosqlite:///pokemon_draft.db`)

## Google Sheets (src/data/sheets.py)

Primary database. 17 tabs managed by `setup_google_sheet.py`.

Key access patterns:
- `sheets.find_row(tab, key, value)` → dict or None
- `sheets.upsert_standing(row_dict)` → writes ELO row
- `sheets.get_standings(guild_id)` → list of dicts
- All gspread calls are sync; must be run via `run_in_executor` from async code

## Pydantic Models (src/data/models.py)

| Model | Purpose |
|-------|---------|
| `Pokemon` | Pokedex entry + tier |
| `Draft` | Full draft state (teams, picks, bans, timer) |
| `DraftPick` | Single pick record |
| `PlayerElo` | Per-player ELO record |
| `MatchResult` | Winner/loser ELO change summary |
| `Team` | A league team (player + pokemon list) |

`Draft` serializes to/from JSON via `model_dump_json()` / `model_validate_json()` for SQLite round-trips.

## In-Memory Caches

| Variable | Location | Populated by |
|----------|----------|-------------|
| `_active_drafts` | `draft_service.py` | `restore_active_drafts()` on startup |
| `_elo_cache` | `elo_service.py` | `restore_ratings_from_db()` on startup |
| `pokemon_db` | `pokeapi.py` | `seed_pokemon_data.py` → Sheets → loaded at import |
