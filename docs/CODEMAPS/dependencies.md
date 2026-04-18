<!-- Generated: 2026-04-17 | Files scanned: requirements.txt | Token estimate: ~500 -->

# External Dependencies

## Core

| Package | Purpose | Notes |
|---------|---------|-------|
| `discord.py 2.x` | Discord bot framework | Slash commands via `app_commands` |
| `pydantic v2` | Data models + config | `pydantic-settings` for `.env` |
| `gspread` | Google Sheets client | Sync; wrapped in `run_in_executor` |
| `aiosqlite` | Async SQLite | Write-through cache for drafts + ELO |

## ML / RL

| Package | Purpose | Notes |
|---------|---------|-------|
| `stable-baselines3` | PPO training | `SB3_OK` guard throughout |
| `poke-env ≥0.8.1` | Pokemon Showdown env | `POKE_ENV_AVAILABLE` guard |
| `torch` | Neural networks | BattleTransformer, MCTS inference |
| `gymnasium` | RL environment wrapper | `battle_env.py` |

## Optional / Dev

| Package | Purpose |
|---------|---------|
| `PyInstaller` | Build standalone .exe |
| `pytest`, `pytest-asyncio` | Testing (`asyncio_mode = auto`) |
| `ruff` | Linting |
| `aiohttp` | HTTP in ML scraper/client |

## External Services

| Service | Used for | Config key |
|---------|----------|-----------|
| Google Sheets API | Primary database | `GOOGLE_SHEETS_CREDENTIALS_FILE`, `GOOGLE_SHEETS_SPREADSHEET_ID` |
| Pokemon Showdown | RL battle environment | `SHOWDOWN_USERNAME`, `SHOWDOWN_PASSWORD` |
| PokéAPI | Pokemon data seeding | No key needed |
| Discord API | Bot platform | `DISCORD_TOKEN`, `DISCORD_CLIENT_ID` |

## Optional Integrations

| Service | Purpose | Config key |
|---------|---------|-----------|
| ML Learning Sheet | Replay URL logging | `ML_LEARNING_SPREADSHEET_ID` |
| Local Showdown server | RL training (`ws://localhost:8000`) | — |
