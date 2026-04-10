# Pokemon Draft League Bot

A full-featured Discord bot for running Pokemon draft leagues — supporting Pokemon Showdown and
console games (Scarlet/Violet, Sword/Shield), with Google Sheets integration, ELO matchmaking,
and a standalone Windows executable (no server required).

---

## Features

| Category | Details |
|----------|---------|
| **Draft Formats** | Snake, Auction, Tiered, Adaptive Banning — fully customizable |
| **Tera Captains** | Per-team tera captain limit + tera type assignment per pick |
| **Team Logos** | Upload PNG/JPG logos via `/team-register` — saved to Discord CDN + Sheets |
| **Pokemon Data** | All 1,025 Gen 1-9 Pokemon with animated sprites (Showdown CDN) |
| **Analytics** | Type coverage, weaknesses, speed tiers, team archetype, threat score |
| **ELO** | Per-league ratings (K=32), standings, streak tracking |
| **Battle Sim** | Heuristic matchup scoring, Showdown replay parsing |
| **Spreadsheet** | 17-tab Google Sheets backend (Setup, Draft, Standings, MVP Race, etc.) |
| **Deployment** | Standalone .exe — double-click to run, no server or Docker needed |
| **Platform** | Windows 10+ / macOS 11+ / Linux — fully cross-platform |

---

## Quick Start

### Option A: Run the standalone .exe (Windows — easiest)

1. Download `NCLPDLB.exe` from the [Releases](https://github.com/NoChillModeOnline/NCLPDLB/releases) page
2. Create a `.env` file next to the exe (copy from `.env.example`, fill in your tokens)
3. Place your `credentials.json` next to the exe
4. Double-click `NCLPDLB.exe` — the bot connects to Discord

### Option B: Run from source (all platforms)

#### Prerequisites

- Python 3.11+
- Google Cloud service account JSON (`credentials.json`)
- Discord bot token

#### 1. Clone & configure

```bash
git clone https://github.com/NoChillModeOnline/NCLPDLB.git
cd NCLPDLB
cp .env.example .env
# Edit .env with your tokens
```

#### 2. Install Python dependencies

```bash
pip install uv
uv pip install -r requirements.txt
```

#### 3. Seed Pokemon data

```bash
python scripts/seed_pokemon_data.py
```

This fetches all 1,025 Gen 1-9 Pokemon from PokéAPI and saves animated GIF sprite URLs.

#### 4. Set up Google Sheets

```bash
python scripts/setup_google_sheet.py
```

Creates all 17 tabs with correct headers, formatting, and data validation dropdowns.

#### 5. Run the bot

```bash
python src/bot/main.py
```

#### 6. Build your own .exe (optional)

```bash
cd src/bot
pyinstaller NCLPDLB.spec
# Output: src/bot/dist/NCLPDLB.exe
```

---

## Discord Commands

### Draft Setup

| Command | Description | Permission |
|---------|-------------|------------|
| `/draft-setup` | Interactive wizard: league name, format, game mode, player count, tera captains | Manage Server |
| `/draft-create` | Quick create with inline options | Manage Server |
| `/draft-join [team_name] [pool] [logo]` | Join draft, set team name and upload logo | Anyone |
| `/draft-start` | Start the draft when all players are registered | Commissioner |
| `/draft-status` | Show current round, active player, pick count | Anyone |

### Picking

| Command | Description |
|---------|-------------|
| `/pick <pokemon> [tera_type] [is_tera_captain]` | Pick a Pokemon; optionally assign tera type and mark as captain |
| `/ban <pokemon>` | Ban a Pokemon during the ban phase |
| `/bid <amount>` | Place a bid during auction drafts |

### Team Management

| Command | Description |
|---------|-------------|
| `/team [user]` | View your or another player's team with analytics |
| `/team-register <team_name> [pool] [logo]` | Set team name, pool, and upload a logo image |
| `/teamimport` | Import a Pokemon Showdown team export (modal) |
| `/teamexport` | Export your team to Showdown format |
| `/trade <user> <offer> <want>` | Propose a trade |
| `/trade-accept <trade_id>` | Accept a pending trade |
| `/legality <pokemon> <game>` | Check if a Pokemon is legal in a format |

### Stats & Analysis

| Command | Description |
|---------|-------------|
| `/analysis [user]` | Full team analysis (coverage, weaknesses, archetypes, threat score) |
| `/matchup <user1> <user2>` | Compare two teams head-to-head |
| `/standings [pool]` | View league standings with ELO |
| `/replay <url>` | Submit a Showdown replay — auto-parses result and records to Sheets |
| `/match-upload <opponent> <file>` | Record a match video (Discord CDN URL saved to Sheets) |

### League

| Command | Description |
|---------|-------------|
| `/league-create <name>` | Create a new league |
| `/schedule` | View this week's suggested matchups |
| `/result <opponent> <winner>` | Report a match result (updates ELO) |

### Spreadsheet Management (Manage Server only)

| Command | Description |
|---------|-------------|
| `/sheet-setup view/edit` | View or edit Setup tab values |
| `/sheet-standings` | Recalculate standings and write to Standings tab |
| `/sheet-schedule` | Add a match to the Schedule tab |
| `/sheet-result` | Record a match result to Match Stats tab |
| `/sheet-transaction` | Log a trade/drop/add to Transactions tab |
| `/sheet-rule` | Add a rule to the Rules tab |
| `/sheet-player` | Update a player's team name, pool, or logo |
| `/sheet-pokedex` | Sync all Pokemon data to the Pokedex tab |
| `/sheet-playoff` | Add a playoff match to Playoffs tab |

### Admin

| Command | Description |
|---------|-------------|
| `/admin-skip [player]` | Force-skip a player's turn |
| `/admin-pause` | Pause the draft |
| `/admin-resume` | Resume a paused draft |
| `/admin-override-pick <player> <pokemon>` | Override a pick as commissioner |
| `/admin-reset` | Reset the entire draft (with confirmation) |

### Machine Learning / Showdown

| Command | Description |
|---------|-------------|
| `/spar <format> [username]` | Battle the trained AI agent live on Pokemon Showdown |

**Supported formats:**

- Gen 9: Random Battle, OU, Doubles OU, National Dex, Monotype, Anything Goes, VGC 2026 Reg I/F
- Gen 7/6: Random Battle

**ML Architecture:**

The battle AI uses an **AlphaZero-style pipeline** — a custom Transformer-based policy+value network trained via MCTS self-play, not a standard PPO agent.

```
BattleTransformer (policy head + value head)
        ↑ trains from
ReplayBuffer  ←  MCTS Ladder Play (bot vs real opponents on play.pokemonshowdown.com)
                        ↑ guided by
                   MCTSConfig (simulations, exploration)
```

**Training the agent:**

```bash
# 1. Set a Showdown account in .env:
#    SHOWDOWN_USERNAME=YourBotAccount
#    SHOWDOWN_PASSWORD=...

# 2. Start the training system (ladder training on play.pokemonshowdown.com + trainer + dashboard)
python -m src.ml.run_training

# 3. Open the training dashboard
open http://localhost:8080
# Click "Start" to begin ladder training
```

The bot queues the ranked ladder on [play.pokemonshowdown.com](https://play.pokemonshowdown.com) — no local server needed. It plays against real human opponents and learns from those games.

**CLI options:**

```bash
python -m src.ml.run_training \
  --format gen9randombattle \   # battle format (default: gen9randombattle)
  --mcts-sims 30 \              # MCTS simulations per move
  --buffer 50000 \              # replay buffer capacity
  --lr 3e-4 \                   # transformer learning rate
  --train-every 5               # train after N games
```

Models are saved to `src/ml/models/latest.pt`. The bot loads this when a user runs `/spar`.

---

## Architecture

```text
┌──────────────────────────────────────────────────────┐
│                    NCLPDLB.exe                        │
│            (standalone — no server needed)            │
│                                                       │
│  Discord Bot (discord.py)  ──► Google Sheets (17 tabs)│
│  SQLite (pokemon_draft.db)                            │
│  poke-env (Showdown client) ──► play.pokemonshowdown.com
│  ML model (src/ml/models/latest.pt)                  │
└──────────────────────────────────────────────────────┘

ML Pipeline (AlphaZero-style):

  LadderLoop (poke-env → play.pokemonshowdown.com)
      │  game experience
      ▼
  ReplayBuffer (thread-safe)
      │  batches
      ▼
  PolicyTrainer ──► BattleTransformer (policy + value heads)
                          │  model weights
                          ▼
                    MCTSPlayer (battle decisions)

Training Dashboard: FastAPI + HTML served at http://localhost:8080
```

**Key components:**

- **Discord Bot** — Commands, modals, views, embeds; cogs for draft/team/stats/admin/league
- **SQLite** — Local state database, no server needed
- **poke-env** — Python Showdown client for `/spar` battles with trained AI agents
- **Google Sheets** — Single source of truth for league data (no SQL migrations needed)
- **ML Pipeline** — AlphaZero-style: BattleTransformer (policy+value) trained via MCTS self-play
  - `showdown_client.py` — WebSocket client for Showdown (layer 1)
  - `transformer_model.py` — Transformer-based policy/value network (layer 2)
  - `mcts.py` — Monte Carlo Tree Search decision engine (layer 3)
  - `self_play.py` — AccountA vs AccountB self-play loop
  - `trainer.py` — ReplayBuffer + PolicyTrainer
  - `run_training.py` — Wires all layers + FastAPI dashboard

---

## Google Sheets Structure

The bot connects to a spreadsheet with 17 tabs:

| Tab | Purpose |
|-----|---------|
| **Setup** | League config: name, format, pools, tera rules, commissioner |
| **Rules** | Rule reference (Tera Captains, trading rules, etc.) |
| **Cover** | Title/intro page |
| **Draft** | Full pick log: round, pick, pool, player, Pokemon, tera type, tier |
| **Draft Board** | Visual board summary (populated by bot) |
| **Pool A Board** | Pool A rosters |
| **Pool B Board** | Pool B rosters |
| **Schedule** | Match schedule with results |
| **Match Stats** | Full match records: teams used, replays, videos |
| **Standings** | W/L/ELO/streak per pool |
| **Pokemon Stats** | Per-Pokemon performance stats |
| **MVP Race** | Most impactful Pokemon leaderboard |
| **Transactions** | All trades, drops, adds |
| **Playoffs** | Bracket results |
| **Pokedex** | All 1,025 Pokemon reference data |
| **Team Page Template** | Per-player team page with logo URL |
| **Data** | Internal key/value store |

### Connecting the Bot to Your Spreadsheet

1. Create a Google Cloud project and enable the Sheets API
2. Create a service account and download `credentials.json`
3. Share your spreadsheet with the service account email
4. Add the spreadsheet ID to `.env`:

   ```text
   GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id_here
   ```

5. Run `python scripts/setup_google_sheet.py` to initialize all tabs

---

## Environment Variables

See [.env.example](.env.example) for all variables. Key ones:

```env
DISCORD_TOKEN=         # Bot token from Discord Developer Portal
DISCORD_CLIENT_ID=     # Application ID
DISCORD_GUILD_ID=      # Test server ID (for instant slash command sync)
BOT_NAME=DraftBot      # Display name in embeds and logs
BOT_STATUS=Pokemon Draft League

GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id

# Showdown — used for /spar and ladder training
SHOWDOWN_USERNAME=YourBotAccount
SHOWDOWN_PASSWORD=...
```

---

## Development

```bash
# Run tests
pytest tests/ -v

# Run specific suite
pytest tests/unit/ -v
pytest tests/e2e/ -v

# Lint + type check
ruff check src/
mypy src/
```

---

## Troubleshooting

### Bot not responding to slash commands

- **Symptom:** Commands don't appear in Discord autocomplete
- **Fix:**
  1. Verify `DISCORD_TOKEN` and `DISCORD_CLIENT_ID` in `.env`
  2. Ensure bot has `applications.commands` scope when invited
  3. For instant sync, set `DISCORD_GUILD_ID` to your test server
  4. Restart the bot — slash commands register on startup

### Google Sheets permission denied

- **Symptom:** `gspread.exceptions.APIError: Insufficient permissions`
- **Fix:**
  1. Share the spreadsheet with the service account email (found in `credentials.json` → `client_email`)
  2. Grant **Editor** access, not Viewer
  3. Verify `GOOGLE_SHEETS_SPREADSHEET_ID` matches your sheet

### `/spar` command fails with "Model not found"

- **Symptom:** `/spar gen9ou` returns "No trained model found"
- **Fix:** Train the model first:

  ```bash
  # Start the local Showdown server, then:
  python -m src.ml.run_training --format gen9ou
  ```

  The model must exist at `src/ml/models/latest.pt`

### Video uploads fail

- **Symptom:** `/match-upload` returns "Upload failed"
- **Fix:** Check file size (max 100MB). Videos are stored as Discord CDN links.
  For permanent storage, share a YouTube or Twitch link instead.

### Draft hangs after `/draft-start`

- **Symptom:** No pick prompt appears
- **Fix:**
  1. Check bot has `Send Messages` + `Embed Links` permissions in the draft channel
  2. Verify player count matches setup (all slots filled)
  3. Check logs: `tail -f logs/bot.log`

---

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Run tests (`pytest tests/ -v`) and linter (`ruff check src/`)
4. Commit with clear messages
5. Open a pull request

---

## License

MIT
