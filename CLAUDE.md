# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Obsidian Vault

Project notes, issues, and documentation live in the **No Chill Draft League Vault**:
- Path: `~/Documents/Obsidian/No Chill Draft League Vault`
- Use `obsidian vault="No Chill Draft League Vault" <cmd>` to interact (requires Obsidian open + CLI installed)

## Tech Stack

- **Python 3.12** (CI target; 3.11+ supported locally) with `discord.py 2.x` (slash commands via `app_commands`)
- **Pydantic v2** for all data models; `pydantic-settings` for config from `.env`
- **gspread** (sync, run in executor) for Google Sheets; **aiosqlite** for local SQLite
- **Two ML stacks coexist** for the battle agent:
  - **PPO/stable-baselines3 + poke-env** — per-format self-play (`/spar`, `train_policy.py`,
    `train_all.py`; CI `train-models.yml`). README marks this legacy, but it's still trained/shipped.
  - **Transformer + MCTS (AlphaZero-style)** — `BattleTransformer` policy/value model via MCTS
    ladder self-play (`run_training.py`, `self_play.py`, `mcts.py`, `trainer.py`; CI
    `train-transformer.yml`). Dashboard + FastAPI at `127.0.0.1:8080`.
- **PyInstaller** for producing the standalone `.exe` (spec: `src/bot/NCLPDLB.spec`)

## Commands

```bash
# First-time setup
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt          # Windows
.venv/bin/pip install -r requirements.txt              # macOS/Linux
# torch must be installed separately (CPU wheel — avoids large CUDA download):
.venv/Scripts/pip install torch --index-url https://download.pytorch.org/whl/cpu
# playwright requires browser binaries after pip install:
.venv/Scripts/python -m playwright install chromium
```

```bash
# Virtual environment (project uses .venv)
.venv/Scripts/python    # Windows
.venv/bin/python        # macOS/Linux

# Run the bot
.venv/Scripts/python src/bot/main.py

# Run all tests (skip slow performance tests)
.venv/Scripts/python -m pytest tests/ --ignore=tests/performance -q

# CI entrypoint (wrapper os._exit()s after run to avoid interpreter-shutdown
# hangs from leaked native child procs)
.venv/Scripts/python scripts/ci_pytest.py -m "not integration"

# Run a single test file
.venv/Scripts/python -m pytest tests/unit/test_draft_service.py -v

# Run a single test
.venv/Scripts/python -m pytest tests/unit/test_battle_env.py::test_name

# Filter by name pattern
.venv/Scripts/python -m pytest -k pattern

# Integration marker — requires a live local Showdown server (Node, port 8000)
.venv/Scripts/python -m pytest -m integration

# Run tests with coverage (default — see pytest.ini)
.venv/Scripts/python -m pytest tests/ --ignore=tests/performance

# Lint / format / type-check
.venv/Scripts/python -m ruff check src/ tests/
.venv/Scripts/python -m ruff format src/ tests/   # auto-format
.venv/Scripts/python -m mypy src/                 # type-check (authoritative; pyrightconfig.json sets typeCheckingMode: "off" — config-only, not enforced)

# Seed Pokemon data (one-time setup — fetches 1,025 mons from PokéAPI)
.venv/Scripts/python scripts/seed_pokemon_data.py

# Set up Google Sheets (one-time — creates all 17 tabs)
.venv/Scripts/python scripts/setup_google_sheet.py

# Prepare competitive meta data (Showdown CSV exports → data/competitive/format_meta.json)
.venv/Scripts/python scripts/prepare_competitive_data.py

# Set up ML learning spreadsheet tabs (one-time — creates Replays, Training Runs, per-format tabs)
.venv/Scripts/python scripts/setup_ml_sheet.py

# Train ML policy (all formats, ~8-12 hours; requires local Showdown server)
.venv/Scripts/python -m src.ml.train_all

# Train a single format (PPO/stable-baselines3)
.venv/Scripts/python -m src.ml.train_policy --format gen9ou --timesteps 500000

# Run Transformer+MCTS live-ladder trainer + dashboard
.venv/Scripts/python -m src.ml.run_training --port 8080

# Scrape replays for BC pre-training
.venv/Scripts/python -m src.ml.replay_scraper --format gen9ou --pages 50 --min-rating 1600

# Behavioural Cloning pre-training from scraped replays
.venv/Scripts/python -m src.ml.pretrain data/replays/gen9ou --format gen9ou --output bc_actor.pt

# Build standalone .exe
cd src/bot && pyinstaller NCLPDLB.spec

# Windows one-click bot launcher (wraps .venv\Scripts\python src\bot\main.py)
run_bot.bat

# Force Discord command re-sync without restarting the bot
.venv/Scripts/python scripts/sync_commands.py
```

## Gotchas

**`torch` installs from a custom index.** `pip install -r requirements.txt` alone will pull torch from PyPI (wrong wheel or missing on some platforms). Always install separately: `pip install torch --index-url https://download.pytorch.org/whl/cpu`

**`playwright` needs browser binaries.** After pip install run: `python -m playwright install chromium`

**BC pre-training (`imitation`) requires a separate venv.** `imitation` conflicts with `poke-env==0.12.1` over gymnasium versions. For local BC pre-training: `pip install "imitation>=1.0.0" "gymnasium~=0.29" "stable-baselines3>=1.7"`

**`actions-runner/` at repo root is the self-hosted CI runner installation.** Do not edit files inside it; they are runner binaries and config, not project source.

**Draft state is not persisted across bot restarts.** In-progress drafts live only in `_active_drafts` in memory — a restart loses them. See Key Design Decisions below.

**Observation-space break (ISS-007/008).** `OBS_DIM` changed 48→78 in `battle_env.py`; `OBS_DIM_DOUBLES = 140`. Checkpoints trained before the change are incompatible and must be retrained. (Source: `STATUS.md`, `docs/design/ISS-007*`, `ISS-008*`.)

## Architecture

### Layer Map

```
src/
  config.py              — Settings singleton (pydantic-settings, reads .env)
  data/
    models.py            — All Pydantic models (Pokemon, Draft, DraftPick, etc.)
    db.py                — Async SQLite layer (aiosqlite); active_drafts + elo_ratings tables
    pokeapi.py           — PokéAPI client + in-memory pokemon_db cache
    sheets.py            — Google Sheets data layer (Tab constants, cell-specific writes)
                           LearningSheets singleton: writes replays + training runs, reads win
                           rate / checkpoint stats for /ml-stats
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
    cogs/                — One cog per command group (draft, team, league, admin, stats, sheet,
                           misc, ml)
    views/               — discord.py UI views (draft_view, team_view, team_import_view)
    constants.py         — Shared embed colours, emoji, strings
    permissions.py       — `require_role()` app_commands.check decorator; enforces named
                           Discord roles (commissioner/captain/etc.) on commands
    hooks/
      hook-pydantic.py   — PyInstaller hook; suppresses pydantic V1 compat warning on Python 3.14+
  ml/
    battle_env.py        — Gymnasium wrapper (OBS_DIM=78, OBS_DIM_DOUBLES=140, N_ACTIONS_GEN9=26)
    train_policy.py      — PPO training loop for a single format
    train_all.py         — Trains all formats sequentially
    train_matchup.py     — Matchup metric training
    trainer.py           — High-level training orchestrator (wraps train_policy.py)
    self_play.py         — Async self-play loop for continuous improvement
    pretrain.py          — Behavioural Cloning pre-training using imitation library
    run_training.py      — FastAPI + uvicorn server to trigger/monitor training via HTTP
    api.py               — FastAPI app exposing training status endpoints (used by run_training.py)
    showdown_player.py   — poke-env player that uses the trained PPO model for /spar
    replay_parser.py     — Parses Showdown replay JSON
    replay_scraper.py    — Scrapes replay URLs from Showdown
    feature_extractor.py — BattleRecord → numpy team/state features (the SB3 feature extractor
                           itself is `BattleTransformerExtractor` inside train_policy.py)
    teambuilder.py       — Constructs Showdown team strings for RL agents
    training_doctor.py   — Diagnoses training health
    showdown_client.py   — 3-layer WebSocket client for Showdown (P1)
    transformer_model.py — Transformer-based policy/value model (P2)
    train_transformer.py — Training loop for the Transformer policy
    mcts.py              — MCTS battle decision engine; integrates with showdown_player.py (P3)
    browser_trainer.py   — Browser-based self-play trainer
    teams.py             — Team management utilities for RL agents
    training_players.py  — Player wrappers used during training
    type_chart.py        — Gen 9 type effectiveness chart
    showdown_modes.py    — Format/mode definitions for Showdown battles
```

### ML Format Routing

Four structures govern which ML format goes where — central to any ML format work:

- **`FORMAT_TEAMS`** (`src/ml/teams.py`) — format → curated Showdown team strings; consumed by
  `RotatingTeambuilder` and `--team-format`.
- **`TRAINING_FORMAT_ALIASES`** (`src/ml/train_policy.py:193`) — maps unsupported formats (BO3
  series, Champions) to a real trainable format (e.g. `gen9championsou→gen9ou`,
  `gen9championsvgc2026regma→gen9vgc2026regi`), since poke-env/the server can't run them directly.
- **`DOUBLES_FORMATS`** (`src/ml/train_policy.py:168`) — formats routed to `BattleDoubleEnv`.
- **`TRAINING_MAP`** (`src/ml/train_all.py:58`) — the canonical format list; mirrors the
  `train-models.yml` CI matrix. `SPAR_FORMATS` (bot) derives from it.

### Key Design Decisions

**Draft state is in-memory only.** `_active_drafts: dict[str, Draft]` in `draft_service.py` is keyed by guild ID. There is no persistence layer for live draft state — a bot restart loses in-progress drafts.

**Google Sheets is the database.** Completed drafts, standings, match history, and trades all write to a visual template spreadsheet. `sheets.py` uses gspread synchronously and must be called via `asyncio.get_event_loop().run_in_executor(None, ...)` from async contexts.

**Command sync is hash-gated.** `main.py` computes a fingerprint of registered commands and only calls `tree.sync()` when they change, avoiding the guild-commands rate limit (set `DISCORD_GUILD_ID` in `.env` for guild-scoped sync, or `SYNC_COMMANDS_ON_STARTUP=true` for global).

**Cogs are the public API.** Commands live in `src/bot/cogs/`; they delegate all logic to `src/services/`. Views (`src/bot/views/`) handle multi-step Discord UI interactions (modals, selects, buttons).

**ML requires a local Showdown server.** `battle_env.py` connects to `ws://localhost:8000`. See `scripts/setup_showdown_server.md` for setup. Training is independent of the Discord bot.

**ML training API is loopback-only.** `run_training.py`/`api.py` bind to `127.0.0.1` by default and support optional bearer-token auth via `TRAIN_API_TOKEN` env var. Don't change the default bind address without adding auth in front of it.

### CI Workflows

5 workflows in `.github/workflows/`:
- `tests.yml` — unit test matrix (Python 3.11-3.14) + integration job
- `train-models.yml` — PPO format training matrix, self-hosted Windows runner
- `train-transformer.yml` — offline MCTS self-play smoke test
- `codeql.yml` — CodeQL security scanning
- `dependency-submission.yml` — dependency graph submission

Dependabot blocks minor/major auto-PRs for `poke-env`/`stable-baselines3`/`torch` (tight
coupling + CPU wheel requirement).

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
- `DATABASE_URL` — SQLAlchemy URL (default: `sqlite+aiosqlite:///./pokemon_draft.db`)
- `LOG_LEVEL`, `LOG_FILE` — logging verbosity and output path

### Testing

Tests live in `tests/unit/`, `tests/integration/`, `tests/e2e/`, and `tests/performance/`.
Shared test data lives in `tests/fixtures/`.
`pytest.ini` sets `asyncio_mode = auto` and default coverage across `src/`.
Performance tests (`tests/performance/locustfile.py`) are excluded from normal runs.
The `conftest.py` at root and `tests/conftest.py` provide shared fixtures.
CI enforces a coverage gate of ≥80% on `src.ml.self_play`.
