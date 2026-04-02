# Project Index: NCLPDLB (Pokemon Draft League Bot)

Generated: 2026-04-02

---

## Project Overview

Full-featured Discord bot for running Pokemon draft leagues. Supports Snake/Auction/Tiered/Adaptive
Banning drafts, Google Sheets integration (17 tabs), ELO matchmaking, and ML-powered Showdown
battles. Ships as a standalone Windows .exe — no server or Docker required.

- **GitHub**: <https://github.com/NoChillModeOnline/NCLPDLB>
- **Spreadsheet**: 16F9FP5wkyzDdF8C7vD9xwY2j2JkcWYR1EUK_MtRt7zs
- **Status**: 49/50 commands working. ML `/spar` blocked on ARM64 (needs x86 for training)

---

## Project Structure

```text
pokemon-draft-bot/
├── src/
│   ├── bot/          # Discord bot (cogs, views, entry point)
│   │   ├── cogs/     # admin, draft, league, misc, sheet, stats, team
│   │   ├── views/    # draft_view, team_view, team_import_view
│   │   ├── hooks/    # hook-pydantic.py
│   │   ├── constants.py
│   │   └── main.py   # Entry point: DraftLeagueBot class
│   ├── services/     # Business logic layer
│   ├── data/         # Persistence (SQLite, Sheets, APIs)
│   ├── ml/           # RL training pipeline (poke-env + SB3)
│   └── config.py     # pydantic-settings singleton
├── tests/
│   ├── unit/         # 35 unit test files
│   ├── integration/  # test_showdown_import.py
│   ├── e2e/          # test_full_draft.py
│   ├── performance/  # locustfile.py (Locust load tests)
│   └── conftest.py
├── scripts/          # Seed data, Sheets setup, maintenance/audit scripts
├── data/
│   ├── pokemon.json  # 1,025 Gen 1-9 Pokemon
│   ├── ml/           # Vocab + matchup metric JSON files per format
│   └── replays/      # Scraped replay JSON files by format/generation
├── docs/             # API.md, COMMANDS.md, DEPLOYMENT.md, AUDIT-REPORT.md, KNOWLEDGE_BASE.md
└── .planning/        # GSD roadmap + state (PROJECT.md, ROADMAP.md, STATE.md)
```

---

## Entry Points

| Entry Point | Path | Purpose |
|-------------|------|---------|
| **Bot** | `src/bot/main.py` | `DraftLeagueBot` class; loads cogs, syncs slash commands |
| **Config** | `src/config.py` | `Settings` singleton via pydantic-settings; reads `.env` |
| **ML Train All** | `src/ml/train_all.py` | Train PPO agents for all 10 formats sequentially |
| **ML Train Single** | `src/ml/train_policy.py` | `--format`, `--timesteps`, `--team-format` args |
| **Seed Data** | `scripts/seed_pokemon_data.py` | Fetch 1,025 Pokemon from PokéAPI → `data/pokemon.json` |
| **Sheets Setup** | `scripts/setup_google_sheet.py` | Create all 17 tabs in Google Sheets |

**Run bot**: `python src/bot/main.py`
**Build exe**: `cd src/bot && pyinstaller NCLPDLB.spec` → `src/bot/dist/NCLPDLB.exe`

---

## Core Modules

### Bot Cogs (`src/bot/cogs/`)

| Module | Key Commands |
|--------|-------------|
| `draft.py` | `/draft-setup`, `/draft-create`, `/draft-join`, `/draft-start`, `/pick`, `/ban`, `/bid` |
| `team.py` | `/team`, `/team-register`, `/teamimport`, `/teamexport`, `/trade`, `/legality` |
| `league.py` | `/league-create`, `/schedule`, `/result`, `/standings` |
| `stats.py` | `/analysis`, `/matchup`, `/replay`, `/match-upload`, `/spar` |
| `sheet.py` | `/sheet-setup`, `/sheet-standings`, `/sheet-schedule`, `/sheet-result`, etc. |
| `admin.py` | `/admin-skip`, `/admin-pause`, `/admin-resume`, `/admin-override-pick`, `/admin-reset` |
| `misc.py` | `/help` and utilities |

### Bot Views (`src/bot/views/`)

- `draft_view.py` — Draft pick UI components
- `team_view.py` — Team display embeds
- `team_import_view.py` — Showdown import modal

### Services (`src/services/`)

| Module | Purpose |
|--------|---------|
| `draft_service.py` | Draft state machine, pick validation, turn management |
| `analytics_service.py` | Type coverage, weakness analysis, archetypes, threat scores |
| `elo_service.py` | ELO ratings (K=32, default 1000) + standings + streak tracking |
| `battle_sim.py` | Heuristic matchup scoring; Showdown replay parsing |
| `team_service.py` | Team CRUD, Showdown import/export parsing |
| `notification_service.py` | Discord embed notifications |
| `video_service.py` | Video upload handling (Discord CDN links) |

### Data Layer (`src/data/`)

| Module | Purpose |
|--------|---------|
| `models.py` | Pydantic v2 models + enums: DraftFormat, DraftStatus, GameFormat, TeraType |
| `sheets.py` | Google Sheets client (gspread) — 17-tab structure |
| `pokeapi.py` | PokéAPI client (rate limited to 100 req/s) |
| `showdown.py` | Showdown format/tier data fetcher |
| `smogon.py` | Smogon tier data |

### ML Pipeline (`src/ml/`)

| Module | Purpose |
|--------|---------|
| `battle_env.py` | Gymnasium env for singles (BattleEnv) + doubles (BattleDoubleEnv) |
| `feature_extractor.py` | Custom CNN feature extractor for SB3 |
| `train_policy.py` | PPO training entry point (stable-baselines3) |
| `train_all.py` | Sequential training across 10 formats (500k steps each) |
| `train_matchup.py` | Matchup metric model training |
| `showdown_player.py` | poke-env player for live `/spar` battles |
| `replay_parser.py` | Parse Showdown replay JSON |
| `replay_scraper.py` | Scrape replays from Showdown |
| `type_chart.py` | Gen 9 type effectiveness chart |
| `teams.py` | 5 pre-built teams × 10 formats |
| `teambuilder.py` | RotatingTeambuilder for training |
| `showdown_modes.py` | Format mode definitions |
| `training_players.py` | Baseline opponent players for training |
| `training_doctor.py` | Training diagnostics |
| `browser_trainer.py` | Browser-based training helper |
| `self_play.py` | MCTS Self-Play Loop — AccountA vs AccountB via poke-env; feeds ReplayBuffer |
| `trainer.py` | ReplayBuffer (thread-safe circular buffer) + PolicyTrainer (BattleTransformer policy+value loss) |
| `run_training.py` | Local AI training runner — wires SelfPlayLoop + PolicyTrainer + FastAPI server |
| `api.py` | FastAPI backend: `/stats`, `/start`, `/stop`, `/config` endpoints + dashboard |

---

## Configuration

| File | Purpose |
|------|---------|
| `.env` | `DISCORD_TOKEN`, `DISCORD_CLIENT_ID`, `DISCORD_GUILD_ID`, `BOT_NAME`, `BOT_STATUS`, `GOOGLE_SHEETS_CREDENTIALS_FILE`, `GOOGLE_SHEETS_SPREADSHEET_ID`, `SHOWDOWN_USERNAME`, `SHOWDOWN_PASSWORD` |
| `credentials.json` | Google Cloud service account (do not commit) |
| `src/config.py` | `Settings` class — all env vars with defaults |
| `src/bot/NCLPDLB.spec` | PyInstaller build spec for standalone exe |
| `.env.example` | Template for required env vars |
| `pytest.ini` | `asyncio_mode=auto`, coverage from `src/`, `-v --tb=short` |

---

## Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `discord.py` | 2.x | Discord bot framework (slash commands, cogs, views) |
| `pydantic-settings` | — | Configuration management |
| `gspread` | — | Google Sheets client |
| `aiosqlite` | — | Async SQLite for local state |
| `poke-env` | — | Pokemon Showdown Python client |
| `stable-baselines3` | 2.7.1 | PPO RL training |
| `torch` | 2.10.0 | PyTorch (SB3 backend) — x86 only |
| `gymnasium` | 1.2.3 | Gym env base class |
| `httpx` | 0.28.1 | Async HTTP client |
| `beautifulsoup4` | — | HTML parsing |
| `numpy` / `pandas` | — | Data manipulation |

---

## Tests

**Run tests** (exclude slow perf): `.venv/Scripts/python -m pytest tests/ --ignore=tests/performance -q`

**Test suite**: 35 unit test files, 1 integration, 1 e2e, 1 performance (Locust).

| Category | Files | Notes |
|----------|-------|-------|
| Unit | 35 files | All core services, ML modules, cogs, bot main |
| Integration | `test_showdown_import.py` | Showdown team import flow |
| E2E | `test_full_draft.py` | Full draft lifecycle end-to-end |
| Performance | `locustfile.py` | Load testing — skip with `--ignore=tests/performance` |

**Key unit test coverage:**
`test_analytics.py`, `test_battle_sim.py`, `test_draft_service.py`, `test_elo.py`,
`test_team_service.py`, `test_models.py`, `test_pokeapi.py`, `test_sheets.py`,
`test_feature_extractor.py`, `test_replay_parser.py`, `test_battle_env.py`,
`test_training_players.py`, `test_training_doctor.py`, `test_train_policy.py`,
`test_bot_main.py`, `test_bot_cogs.py`, `test_notification_service.py`, `test_video_service.py`

---

## Scripts

| Script | Purpose |
|--------|---------|
| `seed_pokemon_data.py` | Fetch all 1,025 Pokemon from PokéAPI → `data/pokemon.json` |
| `setup_google_sheet.py` | Create all 17 Sheets tabs with headers + formatting |
| `sync_commands.py` | Force-sync Discord slash commands |
| `scrape_all_formats.py` | Scrape replay data for all ML formats |
| `audit_sheet.py` | Audit Google Sheets for data integrity |
| `deep_audit.py` | Deep audit of sheet formulas and structure |
| `patch_showdown_formats.py` | Patch Showdown format definitions |
| `repair_formulas.py` | Repair broken sheet formulas |
| Various `fix_*.py` / `inspect_*.py` | One-off maintenance and debugging tools |

---

## Google Sheets Structure (17 tabs)

Setup, Rules, Cover, Draft, Draft Board, Pool A Board, Pool B Board, Schedule, Match Stats,
Standings, Pokemon Stats, MVP Race, Transactions, Playoffs, Pokedex, Team Page Template, Data.

---

## ML: Supported Formats

| Format | Notes |
|--------|-------|
| gen9randombattle | Singles random |
| gen9ou | OU singles |
| gen9doublesou | Doubles |
| gen9nationaldex | National Dex |
| gen9monotype | Monotype |
| gen9anythinggoes | AG |
| gen9vgc2026regi | VGC 2026 Reg I |
| gen9vgc2026regf | VGC 2026 Reg F |
| gen7randombattle | Gen 7 random |
| gen6randombattle | Gen 6 random |

Models saved to: `data/ml/policy/<format>/final_model.zip`

**Training blocked on ARM64 Windows** — needs x86 Linux/Windows with PyTorch.

---

## Quick Start

```bash
# 1. Install deps
pip install uv && uv pip install -r requirements.txt

# 2. Seed Pokemon data (one-time)
python scripts/seed_pokemon_data.py

# 3. Set up Google Sheets (one-time)
python scripts/setup_google_sheet.py

# 4. Run bot
python src/bot/main.py

# 5. Run tests
.venv/Scripts/python -m pytest tests/ --ignore=tests/performance -q

# 6. Lint
.venv/Scripts/python -m ruff check src/ tests/
```
