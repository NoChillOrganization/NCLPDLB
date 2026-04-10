# Project Structure — NCLPDLB

## Root Directory

```
NCLPDLB/
├── src/                    — Core source code
│   ├── config.py           — Settings singleton (pydantic-settings, reads .env)
│   ├── bot/                — Discord bot
│   ├── data/               — Data layer (models, API clients, Sheets)
│   ├── services/           — Business logic
│   └── ml/                 — Machine learning / battle AI
├── tests/                  — Test suite (unit, integration, e2e, performance)
├── scripts/                — One-time setup scripts
├── docs/                   — Documentation and guides
├── Pokemon Showdown/       — Local Showdown server (for ML training)
├── requirements.txt
├── pytest.ini
├── CLAUDE.md               — Claude Code guidance for this repo
└── README.md
```

## Source Code (`src/`)

### `src/bot/` — Discord Bot

```
bot/
├── main.py            — DraftLeagueBot (commands.Bot), cog loader, hash-gated sync
├── constants.py       — Embed colours, emoji, shared strings
├── cogs/              — One cog per command group (delegates to services)
│   ├── draft.py       — /draft-setup, /draft-create, /draft-join, /pick, /ban, /bid
│   ├── team.py        — /team, /team-register, /teamimport, /teamexport, /trade
│   ├── stats.py       — /analysis, /matchup, /standings, /replay, /match-upload
│   ├── league.py      — /league-create, /schedule, /result
│   ├── sheet.py       — /sheet-* commands (Manage Server only)
│   ├── admin.py       — /admin-skip, /admin-pause, /admin-override-pick, /admin-reset
│   └── misc.py        — /spar and miscellaneous commands
└── views/             — discord.py UI (modals, selects, buttons)
    ├── draft_view.py
    ├── team_view.py
    └── team_import_view.py
```

### `src/data/` — Data Layer

```
data/
├── models.py          — All Pydantic v2 models (Pokemon, Draft, DraftPick, etc.)
├── pokeapi.py         — PokéAPI client + in-memory pokemon_db cache (1,025 mons)
├── sheets.py          — gspread sync wrapper; Tab constants, cell-specific writes
├── showdown.py        — Showdown format/tier fetching
└── smogon.py          — Smogon tier scraping
```

### `src/services/` — Business Logic

```
services/
├── draft_service.py       — Core draft engine (snake/auction/tiered/ban formats)
│                            In-memory _active_drafts dict keyed by guild ID
├── analytics_service.py   — Type coverage, weaknesses, speed tiers, threat score
├── battle_sim.py          — Heuristic head-to-head matchup scoring
├── elo_service.py         — Per-league ELO (K=32, default 1000)
├── team_service.py        — Team CRUD + Showdown import/export
├── notification_service.py — Discord embed helpers
└── video_service.py       — Match video URL storage
```

### `src/ml/` — Machine Learning / Battle AI

The battle AI uses an **AlphaZero-style** architecture: a Transformer-based
policy+value network trained via MCTS self-play against itself.

```
ml/
├── run_training.py        — Main runner: wires self-play + trainer + FastAPI dashboard
│                            Dashboard at http://localhost:8080
├── self_play.py           — SelfPlayLoop: AccountA vs AccountB via poke-env
│                            Pushes (obs, action, reward) to ReplayBuffer
├── trainer.py             — ReplayBuffer (thread-safe) + PolicyTrainer
│                            Trains BattleTransformer from self-play experience
├── transformer_model.py   — BattleTransformer: Transformer policy + value heads
├── mcts.py                — Monte Carlo Tree Search decision engine
│                            MCTSPlayer uses BattleTransformer to guide search
├── showdown_player.py     — poke-env player using trained model for /spar
├── showdown_client.py     — 3-layer WebSocket client for Showdown (local server)
├── battle_env.py          — Gymnasium wrapper (observation + action space)
├── feature_extractor.py   — Custom SB3-compatible feature extractor
├── api.py                 — FastAPI server: /stats, /start, /stop, /config
├── pretrain.py            — Behavioral cloning pre-training stub (planned)
├── replay_parser.py       — Parses Showdown replay JSON
├── replay_scraper.py      — Scrapes replay URLs from Showdown
├── teambuilder.py         — Constructs Showdown team strings for RL agents
├── training_doctor.py     — Diagnoses training health metrics
├── training_players.py    — Player wrappers used during training
├── train_policy.py        — PPO training loop (legacy, single format)
├── train_all.py           — Trains all formats sequentially (legacy)
├── train_matchup.py       — Matchup metric training (legacy)
├── browser_trainer.py     — Browser-based self-play trainer (experimental)
├── teams.py               — Team management utilities for RL agents
├── type_chart.py          — Gen 9 type effectiveness chart
├── showdown_modes.py      — Format/mode definitions
└── models/                — Saved model artifacts
    └── latest.pt          — Trained BattleTransformer weights
```

**Training flow:**

```
1. Set SHOWDOWN_USERNAME, SHOWDOWN_PASSWORD, SHOWDOWN_USERNAME_B, SHOWDOWN_PASSWORD_B in .env
2. python -m src.ml.run_training   (self-play on play.pokemonshowdown.com + training + dashboard)
3. open http://localhost:8080      (click Start)
```

## Tests (`tests/`)

```
tests/
├── conftest.py            — Shared fixtures
├── unit/                  — Unit tests (fast, no I/O)
├── integration/           — Integration tests (Sheets, DB)
├── e2e/                   — End-to-end Discord bot tests
└── performance/           — Locust load tests (excluded from normal runs)
```

Run with: `python -m pytest tests/ --ignore=tests/performance -q`

## Scripts (`scripts/`)

| Script | Purpose |
|--------|---------|
| `seed_pokemon_data.py` | Fetches all 1,025 Pokemon from PokéAPI into SQLite |
| `setup_google_sheet.py` | Creates all 17 tabs in Google Sheets with headers + formatting |

## Key Design Notes

- **Draft state is in-memory.** `_active_drafts` in `draft_service.py` is lost on restart.
- **Google Sheets is the database.** All completed data writes to Sheets via gspread (sync, run in executor).
- **Command sync is hash-gated.** `main.py` fingerprints commands and only calls `tree.sync()` on change.
- **ML model path:** `src/ml/models/latest.pt` (PyTorch checkpoint).
- **Local Showdown required for ML.** `battle_env.py` connects to `ws://localhost:8000`.
