# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Tech Stack

- **Python 3.11+** with `discord.py 2.x` (slash commands via `app_commands`)
- **Pydantic v2** for all data models; `pydantic-settings` for config from `.env`
- **gspread** (sync, run in executor) for Google Sheets; **aiosqlite** for local SQLite
- **stable-baselines3 (PPO)** + **poke-env** for the RL battle agent (`/spar`)
- **PyInstaller** for producing the standalone `.exe` (spec: `src/bot/NCLPDLB.spec`)

## Commands

```bash
# Virtual environment (project uses .venv)
.venv/Scripts/python    # Windows
.venv/bin/python        # macOS/Linux

# Run the bot
.venv/Scripts/python src/bot/main.py

# Run all tests (skip slow performance tests)
.venv/Scripts/python -m pytest tests/ --ignore=tests/performance -q

# Run a single test file
.venv/Scripts/python -m pytest tests/unit/test_draft_service.py -v

# Run tests with coverage (default — see pytest.ini)
.venv/Scripts/python -m pytest tests/ --ignore=tests/performance

# Lint
.venv/Scripts/python -m ruff check src/ tests/

# Seed Pokemon data (one-time setup — fetches 1,025 mons from PokéAPI)
.venv/Scripts/python scripts/seed_pokemon_data.py

# Set up Google Sheets (one-time — creates all 17 tabs)
.venv/Scripts/python scripts/setup_google_sheet.py

# Train ML policy (all formats, ~8-12 hours; requires local Showdown server)
.venv/Scripts/python src/ml/train_all.py

# Build standalone .exe
cd src/bot && pyinstaller NCLPDLB.spec
```

## Architecture

### Layer Map

```
src/
  config.py              — Settings singleton (pydantic-settings, reads .env)
  data/
    models.py            — All Pydantic models (Pokemon, Draft, DraftPick, etc.)
    pokeapi.py           — PokéAPI client + in-memory pokemon_db cache
    sheets.py            — Google Sheets data layer (Tab constants, cell-specific writes)
    showdown.py          — Showdown format/tier fetching
    smogon.py            — Smogon tier scraping
  services/
    draft_service.py     — Core draft engine (snake/auction/tiered/ban formats)
                           In-memory _active_drafts dict (one active draft per guild)
    analytics_service.py — Team coverage, weakness, archetype, threat score
    battle_sim.py        — Heuristic head-to-head matchup scoring
    elo_service.py       — Per-league ELO (K=32, default 1000)
    team_service.py      — Team CRUD + Showdown import/export
    notification_service.py — Discord embed helpers
    video_service.py     — Match video URL storage
  bot/
    main.py              — DraftLeagueBot (commands.Bot subclass), cog loader,
                           hash-gated command sync (avoids rate limits)
    cogs/                — One cog per command group (draft, team, league, admin, stats, sheet, misc)
    views/               — discord.py UI views (draft_view, team_view, team_import_view)
    constants.py         — Shared embed colours, emoji, strings
  ml/
    battle_env.py        — Gymnasium wrapper (observation + action space defined here)
    train_policy.py      — PPO training loop for a single format
    train_all.py         — Trains all formats sequentially
    train_matchup.py     — Matchup metric training
    showdown_player.py   — poke-env player that uses the trained PPO model for /spar
    replay_parser.py     — Parses Showdown replay JSON
    replay_scraper.py    — Scrapes replay URLs from Showdown
    feature_extractor.py — Custom SB3 feature extractor
    teambuilder.py       — Constructs Showdown team strings for RL agents
    training_doctor.py   — Diagnoses training health
    showdown_client.py   — 3-layer WebSocket client for Showdown (P1)
    transformer_model.py — Transformer-based policy/value model (P2)
    mcts.py              — MCTS battle decision engine; integrates with showdown_player.py (P3)
    browser_trainer.py   — Browser-based self-play trainer
    teams.py             — Team management utilities for RL agents
    training_players.py  — Player wrappers used during training
    type_chart.py        — Gen 9 type effectiveness chart
    showdown_modes.py    — Format/mode definitions for Showdown battles
```

### Key Design Decisions

**Draft state is in-memory only.** `_active_drafts: dict[str, Draft]` in `draft_service.py` is keyed by guild ID. There is no persistence layer for live draft state — a bot restart loses in-progress drafts.

**Google Sheets is the database.** Completed drafts, standings, match history, and trades all write to a visual template spreadsheet. `sheets.py` uses gspread synchronously and must be called via `asyncio.get_event_loop().run_in_executor(None, ...)` from async contexts.

**Command sync is hash-gated.** `main.py` computes a fingerprint of registered commands and only calls `tree.sync()` when they change, avoiding the guild-commands rate limit (set `DISCORD_GUILD_ID` in `.env` for guild-scoped sync, or `SYNC_COMMANDS_ON_STARTUP=true` for global).

**Cogs are the public API.** Commands live in `src/bot/cogs/`; they delegate all logic to `src/services/`. Views (`src/bot/views/`) handle multi-step Discord UI interactions (modals, selects, buttons).

**ML requires a local Showdown server.** `battle_env.py` connects to `ws://localhost:8000`. See `scripts/setup_showdown_server.md` for setup. Training is independent of the Discord bot.

### Configuration (`.env`)

Required:
- `DISCORD_TOKEN`, `DISCORD_CLIENT_ID`
- `GOOGLE_SHEETS_CREDENTIALS_FILE` (path to service account JSON; default `credentials.json`)
- `GOOGLE_SHEETS_SPREADSHEET_ID` (bare ID or full URL — validator strips URL automatically)

Optional:
- `DISCORD_GUILD_ID` — guild-scoped sync (faster for dev)
- `SYNC_COMMANDS_ON_STARTUP=true` — force global command sync on startup
- `BOT_NAME`, `BOT_STATUS` — display name and activity text (defaults: "DraftBot", "Pokemon Draft League")
- `SHOWDOWN_USERNAME`, `SHOWDOWN_PASSWORD` — required for `/spar`
- `ML_LEARNING_SPREADSHEET_ID` — separate sheet for replay URL logging
- `DATABASE_URL` — SQLite path (default: `pokemon_draft.db` in project root)
- `LOG_LEVEL`, `LOG_FILE` — logging verbosity and output path

### Testing

Tests live in `tests/unit/`, `tests/integration/`, `tests/e2e/`, and `tests/performance/`.
`pytest.ini` sets `asyncio_mode = auto` and default coverage across `src/`.
Performance tests (`tests/performance/locustfile.py`) are excluded from normal runs.
The `conftest.py` at root and `tests/conftest.py` provide shared fixtures.
