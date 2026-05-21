# Deployment Guide

How to run the Pokemon Draft League Bot — standalone exe or from source.

---

## Prerequisites

1. **Discord Bot Setup:**
   - Create application at <https://discord.com/developers/applications>
   - Create bot user and copy token
   - Enable **Message Content Intent** and **Server Members Intent**
   - Invite bot with scopes: `bot` + `applications.commands`
   - Required permissions: Send Messages, Embed Links, Attach Files, Manage Roles

2. **Google Sheets Setup:**
   - Create Google Cloud project: <https://console.cloud.google.com>
   - Enable **Google Sheets API**
   - Create service account → download `credentials.json`
   - Create a new Google Sheet
   - Share it with the service account email (Editor access)
   - Copy the spreadsheet ID from the URL

3. **Pokemon Data Seed (first run only):**

   ```bash
   python scripts/seed_pokemon_data.py
   python scripts/setup_google_sheet.py
   ```

---

## Option A: Standalone .exe (Windows)

The simplest way to run — no Python or Docker required.

### 1. Build the exe

```bash
cd src/bot
pyinstaller NCLPDLB.spec
```

Output: `src/bot/dist/NCLPDLB.exe` (~100–200 MB)

### 2. Distribute

Copy these files to the target machine:

```text
NCLPDLB.exe
.env              ← fill in from .env.example
credentials.json  ← Google service account JSON
```

All other files (SQLite DB, Pokemon data) are bundled inside the exe or created automatically.

### 3. Run

Double-click `NCLPDLB.exe` or run from terminal:

```bash
./NCLPDLB.exe
```

The bot connects to Discord, registers slash commands, and is ready.

### 4. Logs

Logs are written to `logs/bot.log` next to the exe.

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
# Edit .env with your tokens
```

### 3. Run (Python)

```bash
python src/bot/main.py
```

---

## Post-Deployment

### 1. Test bot commands

In Discord:

```text
/draft-setup
/team
/standings
```

### 2. Train ML models (optional)

Only needed for the `/spar` command. All other commands work without ML.

```bash
# Requires x86 machine with PyTorch installed
python -m src.ml.train_all
```

This takes 8-12 hours and creates models in `data/ml/policy/`.

Place the `data/ml/policy/` directory next to the exe (or in the project root when running
from source) so the bot can find the trained models.

---

## Troubleshooting

### Bot not connecting to Discord

Verify `DISCORD_TOKEN` is set correctly in `.env`.

### Google Sheets permission denied

Verify service account email has Editor access to the spreadsheet.

### Commands not appearing in Discord

1. Ensure bot has `applications.commands` scope when invited
2. Wait 5–10 minutes for Discord to sync
3. Restart the bot

### Video uploads

Match videos are recorded as Discord CDN attachment URLs. For permanent storage,
users should share YouTube or Twitch links instead of uploading files directly.

---

## Updating

Pull the latest code or download the new exe from Releases:

```bash
git pull origin main
python src/bot/main.py

# Or rebuild the exe:
cd src/bot && pyinstaller NCLPDLB.spec
```
