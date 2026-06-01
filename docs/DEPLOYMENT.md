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

Only needed for the `/spar` command. All other 49+ commands work without ML.

PyTorch + stable-baselines3 **cannot be installed on ARM64 Windows** (macOS Apple Silicon is
also affected). Training must run on an x86-64 Linux machine — a local VirtualBox VM, WSL2,
or a cloud VM all work. See **[ML Training Environment](#ml-training-environment-x86-linux)**
below for the full setup.

Quick reference (once the environment is ready):

```bash
# On the x86 Linux machine, inside the project root:
python -m src.ml.train_all --formats gen9randombattle --server localhost
```

All 22 formats sequentially takes 8-12 hours on adequate hardware.
Models land in `data/ml/policy/<format>/final_model.zip`.

If running from source on the same machine as the training, models are found automatically.
For the standalone `.exe`, copy the `data/ml/policy/` tree next to the exe.

---

## ML Training Environment (x86 Linux)

The `/spar` RL agent requires PyTorch + stable-baselines3, which **cannot be installed on
ARM64 Windows or Apple Silicon macOS**. Training must run on an x86-64 Linux machine.

### Option 1: VirtualBox VM (recommended for local dev)

The project was validated with a VirtualBox "Discord Bot" VM (Ubuntu 22.04 x86-64, 6 vCPU,
20 GB RAM). A VirtualBox shared folder mounts the Windows project directly into the guest
so trained models appear on the host immediately — no file copying.

**VirtualBox setup:**

1. Create Ubuntu 22.04 x86-64 VM. Allocate ≥4 vCPU, ≥8 GB RAM.
2. Add a shared folder: `Machine → Settings → Shared Folders → Add`.
   - Host path: `F:\NCLPDLB` (or wherever the project lives)
   - Mount point: `NCLPDLB`
   - Auto-mount: ✓, Permanent: ✓
3. In the guest, add your user to `vboxsf`:
   ```bash
   sudo usermod -aG vboxsf $USER && newgrp vboxsf
   # Project now visible at /media/sf_NCLPDLB
   ```
4. Enable SSH access from the host (NAT port-forward):
   `Machine → Settings → Network → Adapter 1 → Port Forwarding`
   - Rule: host port `2222` → guest port `22`
   - Connect: `ssh -p 2222 <user>@127.0.0.1`

### Option 2: WSL2 (Windows x86-64 only)

```bash
# In WSL2 (Ubuntu):
cd /mnt/f/NCLPDLB
python3 -m venv .venv-linux && source .venv-linux/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install stable-baselines3 poke-env
```

### Option 3: Cloud VM

Any x86-64 Linux VM (AWS EC2, GCP, Azure) with Python 3.11+. Pull the repo, install deps,
run training, then `scp` `data/ml/policy/` back to the project root.

---

### Installing dependencies (x86 Linux venv)

```bash
python3 -m venv nclpdlb-venv
source nclpdlb-venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install stable-baselines3 poke-env
pip install -r requirements.txt
```

Verify:

```bash
python -c "import torch, stable_baselines3; print('OK')"
```

### Starting the local Showdown server

Training uses a local Showdown server so it never touches the public sim:

```bash
cd /path/to/NCLPDLB/pokemon-showdown
node pokemon-showdown start --no-security &
# Server listens on ws://localhost:8000
```

The `pokemon-showdown/` directory is already included in the repo.
Node.js 18+ required (`sudo apt install nodejs npm` or use nvm).

### Running training

```bash
cd /path/to/NCLPDLB
export PYTHONPATH=/path/to/NCLPDLB

# Single format — quick validation (~5 min with --timesteps 5000):
python -m src.ml.train_all \
  --formats gen9randombattle \
  --timesteps 5000 --swap-every 2500 \
  --server localhost

# All 22 formats — production quality (~8-12 hours):
nohup python -m src.ml.train_all \
  --timesteps 500000 --swap-every 50000 \
  --server localhost \
  > /tmp/train_all.log 2>&1 &

tail -f /tmp/train_all.log   # monitor progress
```

**Output paths:**

| File | Purpose |
|------|---------|
| `data/ml/policy/<fmt>/final_model.zip` | Model loaded by `/spar` at runtime |
| `data/ml/policy/<fmt>/latest.zip` | Latest in-progress checkpoint (auto-resume) |
| `data/ml/results/<fmt>_<date>.zip` | Dated copy — marks format as "done" so reruns skip it |

`train_all` auto-skips formats with an existing dated model in `data/ml/results/`. Use
`--force` to retrain a format even if a dated model exists.

### Resuming interrupted training

`train_all` auto-resumes from `latest.zip` if an in-progress checkpoint exists. Just rerun
the same command — it detects `data/ml/policy/<fmt>/latest.zip` and passes `--resume` to
the subprocess automatically.

### Shared folder note (VirtualBox)

With a VirtualBox shared folder, models written in the guest at
`/media/sf_NCLPDLB/data/ml/policy/` appear on the host at `F:\NCLPDLB\data\ml\policy\`
immediately. The bot running on Windows reads models from the project root, so no copying
is needed.

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
