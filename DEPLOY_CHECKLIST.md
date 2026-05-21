# Deployment Checklist

Quick reference for running the Pokemon Draft League Bot.

---

## Prerequisites

- [ ] Discord bot token from <https://discord.com/developers/applications>
- [ ] Google Sheets spreadsheet ID: `16F9FP5wkyzDdF8C7vD9xwY2j2JkcWYR1EUK_MtRt7zs`
- [ ] Google service account `credentials.json`
- [ ] Bot invited to Discord server with proper permissions

---

## Option A: Standalone .exe (Windows — Recommended)

**No Python installation required.**

### 1. Get the exe

Download `NCLPDLB.exe` from [Releases](https://github.com/NoChillModeOnline/NCLPDLB/releases),
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
# Edit .env with your Discord token and Google Sheets ID
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

```text
https://discord.com/api/oauth2/authorize?client_id=1178100227522171004&permissions=2147551232&scope=bot%20applications.commands
```

Required permissions:

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

All commands work without ML. Only `/spar` requires trained models.

```bash
# Requires x86 machine with Python 3.11 + PyTorch
python -m src.ml.train_all
```

Models saved to `data/ml/policy/` — place next to the exe or in the project root.

---

## Troubleshooting

### Bot Not Responding

Check `logs/bot.log` for errors.

### Google Sheets Errors

1. Verify service account has Editor access
2. Check `GOOGLE_SHEETS_SPREADSHEET_ID` is correct
3. Verify `credentials.json` is valid

### Commands Not Appearing

1. Ensure bot has `applications.commands` scope
2. Wait 5-10 minutes for Discord to sync commands
3. Restart the bot
