# Watching Bot Battles

Two ways to watch the NCLPDLB bot battle in real time.

---

## Option 1 — Watch Live on Pokémon Showdown

The bot connects to the **public Pokémon Showdown server** using two registered accounts and battles itself. You can spectate from any browser.

### Requirements
- Two free Pokémon Showdown accounts → register at https://play.pokemonshowdown.com
- Python dependencies installed: `pip install -r requirements.txt`

### Setup

**Step 1 — Register two Showdown accounts**

Go to https://play.pokemonshowdown.com, click "Choose Name", then register.
Create two accounts — e.g. `NCLPDLBAgent1` and `NCLPDLBAgent2`.

**Step 2 — Set credentials**

```bash
export SHOWDOWN_TRAIN_USER1="NCLPDLBAgent1"
export SHOWDOWN_TRAIN_PASS1="your-password-1"
export SHOWDOWN_TRAIN_USER2="NCLPDLBAgent2"
export SHOWDOWN_TRAIN_PASS2="your-password-2"
```

On Windows (PowerShell):
```powershell
$env:SHOWDOWN_TRAIN_USER1 = "NCLPDLBAgent1"
$env:SHOWDOWN_TRAIN_PASS1 = "your-password-1"
$env:SHOWDOWN_TRAIN_USER2 = "NCLPDLBAgent2"
$env:SHOWDOWN_TRAIN_PASS2 = "your-password-2"
```

**Step 3 — Run the bot**

```bash
python scripts/run_on_showdown.py --format gen9randombattle --timesteps 500
```

**Step 4 — Watch**

1. Go to https://play.pokemonshowdown.com
2. In the search bar, type one of your bot account names
3. Click their active battle to spectate — you'll see every move in real time

---

## Option 2 — Save & Replay Battles Offline

Every battle is saved as an **HTML replay file** you can open in any browser.

### Usage

Add `--save-replays <directory>` to any training command:

```bash
# Local training (requires local Showdown server)
python -m src.ml.train_policy --format gen9randombattle --timesteps 500 --save-replays replays/

# Public Showdown training
python scripts/run_on_showdown.py --format gen9randombattle --timesteps 500 --save-replays replays/
```

### Watching replays

After training, open any `.html` file in `replays/` in your browser:

```bash
# macOS
open replays/*.html

# Windows
start replays\<filename>.html

# Linux
xdg-open replays/<filename>.html
```

Each replay shows the full battle with all moves, damage calculations, and switching — just like the official Showdown replay viewer.

---

## Tip — Combining Both

```bash
python scripts/run_on_showdown.py \
    --format gen9ou \
    --timesteps 1000 \
    --save-replays replays/gen9ou/
```

Watch live on the website AND save every battle for review afterwards.
