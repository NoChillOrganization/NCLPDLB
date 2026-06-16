# Deployment Checklist

Quick reference for running the Pokemon Draft League Bot.

---

## Prerequisites

- [ ] Discord bot token from <https://discord.com/developers/applications>
- [ ] Google Sheets spreadsheet ID (set `GOOGLE_SHEETS_SPREADSHEET_ID` in `.env`)
- [ ] Google service account `credentials.json`
- [ ] Bot invited to Discord server with proper permissions

---

## Option A: Standalone .exe (Windows — Recommended)

**No Python installation required.**

### 1. Get the exe

Download `NCLPDLB.exe` from [Releases](https://github.com/NoChillOrganization/NCLPDLB/releases),
or build it yourself:

```bash
cd src/bot
pyinstaller NCLPDLB.spec
# Output: src/bot/dist/NCLPDLB.exe
```

### 2. Set up config files

Place these files in the same folder as `NCLPDLB.exe`:

- `.env` (copy from `.env.example`, fill in your tokens)
- `credentials.json` (Google service account JSON)

### 3. Run

Double-click `NCLPDLB.exe` — the bot connects to Discord.

---

## Option B: Run from Source (All Platforms)

### 1. Install dependencies

```bash
pip install uv
uv pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set DISCORD_TOKEN, DISCORD_CLIENT_ID, GOOGLE_SHEETS_SPREADSHEET_ID, etc.
```

### 3. Seed data (first run only)

```bash
python scripts/seed_pokemon_data.py
python scripts/setup_google_sheet.py
```

### 4. Run

```bash
python src/bot/main.py
```

---

## Post-Setup Tasks

### 1. Invite Bot to Discord Server

Generate an invite URL from the [Discord Developer Portal](https://discord.com/developers/applications)
for your application. Required permissions:

- Send Messages
- Embed Links
- Attach Files
- Manage Roles
- Use Slash Commands

### 2. Test Core Commands

In Discord:

```text
/draft-setup
/team
/standings
```

### 3. Share Spreadsheet

Share the Google Sheet with your service account email:

1. Open the spreadsheet
2. Click "Share"
3. Add the email from `credentials.json` (`client_email` field)
4. Grant "Editor" access

---

## ML Training (Optional — for /spar)

All commands work without ML. Only `/spar` requires a trained model.

```bash
# Trigger via GitHub Actions (recommended)
# Actions → Train ML Models → Run workflow

# Or run locally (requires local Showdown server on ws://localhost:8000):
python -m src.ml.run_training          # binds 127.0.0.1:8080 by default
python -m src.ml.run_training --host 0.0.0.0  # expose to LAN (not recommended)
```

The training API dashboard defaults to loopback (`127.0.0.1`) and is not reachable
from other machines unless you explicitly pass `--host 0.0.0.0`.

To protect the control endpoints (`/start`, `/stop`, `/config`), set `TRAIN_API_TOKEN`
in `.env`. If unset, endpoints are unauthenticated (local-only is acceptable for dev).

```bash
# .env
TRAIN_API_TOKEN=your-random-secret-here
```

Model saved to `src/ml/models/transformer_checkpoint.pt`.

---

## Troubleshooting

### Bot Not Responding

Check `logs/bot.log` for errors.

### Google Sheets Errors

1. Verify service account has Editor access
2. Check `GOOGLE_SHEETS_SPREADSHEET_ID` is correct in `.env`
3. Verify `credentials.json` is valid

### Commands Not Appearing

1. Ensure bot has `applications.commands` scope
2. Wait 5-10 minutes for Discord to sync commands
3. Restart the bot

### `/spar` Not Working

Model must exist at `src/ml/models/transformer_checkpoint.pt`. Run training first.
