<!-- Generated: 2026-04-17 | Files scanned: ~80 | Token estimate: ~900 -->

# NCLPDLB Architecture

## System Overview

Pokemon Draft League Discord bot with RL battle agent.

```
Discord Users
    │
    ▼
discord.py Bot (src/bot/main.py)
    │
    ├── Cogs (slash commands)   ─────► Services (business logic)
    │     draft, team, league,         draft_service, elo_service,
    │     admin, stats, sheet, misc    team_service, analytics_service
    │
    ├── Services ───────────────────► Data Layer
    │                                  sheets.py (Google Sheets, primary DB)
    │                                  db.py (SQLite, write-through cache)
    │                                  pokeapi.py (in-memory pokemon_db)
    │
    └── ML Pipeline (independent)
          train_policy.py ──► PPO model (.zip)
          showdown_player.py ─► poke-env Player
          mcts.py ──────────► tree search at inference
```

## Startup Sequence (setup_hook in main.py)

1. Load cogs
2. `init_db()` — create SQLite tables if missing
3. `DraftService.restore_active_drafts()` — reload in-progress drafts from SQLite
4. `EloService.restore_ratings_from_db()` — warm `_elo_cache` from SQLite
5. Hash-gated command sync (avoids Discord rate limits)

## Persistence Model

| Data | Primary | Cache / Fallback |
|------|---------|-----------------|
| Completed drafts, standings, trades | Google Sheets | — |
| Active (in-progress) drafts | SQLite `active_drafts` | in-memory `_active_drafts` |
| ELO ratings | Google Sheets | SQLite `elo_ratings` + in-memory `_elo_cache` |
| Pokemon data | PokéAPI (seed script) | in-memory `pokemon_db` |

## ML Pipeline

```
battle_env.py          — Gymnasium env (obs: OBS_DIM floats, actions: N_ACTIONS_GEN9)
train_policy.py        — PPO training; optional BattleTransformerExtractor feature extractor
transformer_model.py   — BattleTransformer (policy priors + value estimates)
mcts.py                — MCTS over transformer model (30 simulations default)
showdown_player.py     — poke-env Player: PPO path (default) or MCTS path (opt-in)
training_players.py    — MaxBasePowerPlayer, SimpleHeuristicPlayer (curriculum opponents)
```

## Key Entry Points

| Purpose | File |
|---------|------|
| Run bot | `src/bot/main.py` |
| Train all formats | `src/ml/train_all.py` |
| Challenge on Showdown | `src/ml/showdown_player.py` (CLI) |
| Seed Pokemon data | `scripts/seed_pokemon_data.py` |
| Setup Google Sheets | `scripts/setup_google_sheet.py` |
| Build .exe | `src/bot/NCLPDLB.spec` |
