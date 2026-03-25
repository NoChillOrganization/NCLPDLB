#!/usr/bin/env python3
"""
Pokemon Draft League Bot — Interactive Setup Script
Collects credentials, writes .env, and optionally runs setup scripts.

Usage:
    python setup.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
CREDS_DEST = ROOT / "credentials.json"
DATA_FILE = ROOT / "data" / "pokemon.json"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _print_header(text: str) -> None:
    width = 60
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def _ask(prompt: str, default: str = "", secret: bool = False) -> str:
    display = f"{prompt}" + (f" [{default}]" if default else "") + ": "
    if secret:
        import getpass
        val = getpass.getpass(display)
    else:
        val = input(display)
    return val.strip() or default


def _ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    val = input(f"{prompt} {hint}: ").strip().lower()
    if not val:
        return default
    return val.startswith("y")


def _write_env(values: dict[str, str]) -> None:
    """Write key=value pairs to .env, updating existing values."""
    lines: list[str] = []
    if ENV_FILE.exists():
        existing = ENV_FILE.read_text(encoding="utf-8").splitlines()
        seen: set[str] = set()
        for line in existing:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                key = stripped.split("=", 1)[0].strip()
                if key in values:
                    lines.append(f"{key}={values[key]}")
                    seen.add(key)
                    continue
            lines.append(line)
        # Append any new keys not already in file
        for k, v in values.items():
            if k not in seen:
                lines.append(f"{k}={v}")
    else:
        # Start from .env.example if available
        template = ENV_EXAMPLE.read_text(encoding="utf-8") if ENV_EXAMPLE.exists() else ""
        lines = template.splitlines()
        seen: set[str] = set()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in values:
                    lines[i] = f"{key}={values[key]}"
                    seen.add(key)
        for k, v in values.items():
            if k not in seen:
                lines.append(f"{k}={v}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run(cmd: list[str], desc: str) -> bool:
    print(f"\n  Running: {desc} ...")
    try:
        subprocess.run(cmd, check=True)
        print(f"  ✅ {desc} complete.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ {desc} failed (exit code {e.returncode}).")
        return False
    except FileNotFoundError:
        print(f"  ❌ Command not found: {cmd[0]}")
        return False


# ── Steps ────────────────────────────────────────────────────────────────────

def step_discord() -> dict[str, str]:
    _print_header("Step 1 — Discord Bot Credentials")
    print("""
  1. Go to https://discord.com/developers/applications
  2. Create or select your application
  3. Under "Bot", click "Reset Token" and copy it
  4. Under "OAuth2 > General", copy the Client ID
  5. Enable "Server Members Intent" and "Message Content Intent"
    """)
    token = _ask("Discord Bot Token", secret=True)
    client_id = _ask("Discord Application/Client ID")
    guild_id = _ask("Test Server Guild ID (right-click server → Copy ID, optional)", default="")
    bot_name = _ask("Bot display name", default="DraftBot")
    return {
        "DISCORD_TOKEN": token,
        "DISCORD_CLIENT_ID": client_id,
        "DISCORD_GUILD_ID": guild_id,
        "BOT_NAME": bot_name,
    }


def step_google_sheets() -> dict[str, str]:
    _print_header("Step 2 — Google Sheets")
    print("""
  1. Go to https://console.cloud.google.com
  2. Create a project → Enable "Google Sheets API" and "Google Drive API"
  3. Create a Service Account → Download JSON key → rename to credentials.json
  4. Create a blank Google Sheet → copy its ID from the URL
     (https://docs.google.com/spreadsheets/d/<THIS_PART>/edit)
  5. Share the Sheet with the service account email (Editor access)
    """)

    creds_path = _ask("Path to credentials.json", default=str(CREDS_DEST))
    src = Path(creds_path).expanduser()
    if src.exists() and src != CREDS_DEST:
        shutil.copy2(src, CREDS_DEST)
        print(f"  ✅ Copied credentials to {CREDS_DEST}")
    elif not src.exists():
        print(f"  ⚠️  File not found: {src} — you'll need to place credentials.json manually.")

    spreadsheet_id = _ask("Google Sheets Spreadsheet ID")
    return {
        "GOOGLE_SHEETS_CREDENTIALS_FILE": "credentials.json",
        "GOOGLE_SHEETS_SPREADSHEET_ID": spreadsheet_id,
    }


def step_optional() -> dict[str, str]:
    _print_header("Step 3 — Optional Settings")
    values: dict[str, str] = {}

    if _ask_yes_no("Configure Cloudflare R2 for video uploads?", default=False):
        values["R2_ACCOUNT_ID"] = _ask("R2 Account ID")
        values["R2_ACCESS_KEY_ID"] = _ask("R2 Access Key ID")
        values["R2_SECRET_ACCESS_KEY"] = _ask("R2 Secret Access Key", secret=True)
        values["R2_BUCKET_NAME"] = _ask("R2 Bucket Name", default="pokemon-draft-videos")
        values["R2_PUBLIC_URL"] = _ask("R2 Public URL (e.g. https://pub-xxxx.r2.dev)")

    api_secret = _ask("API Secret Key (random string for web dashboard)", default="change-me-in-production")
    values["API_SECRET_KEY"] = api_secret
    values["LOG_LEVEL"] = _ask("Log level", default="INFO")
    return values


def step_run_scripts() -> None:
    _print_header("Step 4 — Setup Google Sheet Tabs")
    if not _ask_yes_no("Run setup_google_sheet.py to create all 17 tabs?", default=True):
        print("  Skipped. Run manually: python scripts/setup_google_sheet.py")
        return
    _run([sys.executable, str(ROOT / "scripts" / "setup_google_sheet.py")], "Google Sheet setup")


def step_seed_pokemon() -> None:
    _print_header("Step 5 — Seed Pokemon Database")
    if DATA_FILE.exists():
        print(f"  ✅ {DATA_FILE} already exists ({DATA_FILE.stat().st_size // 1024} KB). Skipping.")
        return
    print("  This will fetch all 1025 Pokemon from PokéAPI (~5 minutes).")
    if not _ask_yes_no("Fetch Pokemon data now?", default=True):
        print("  Skipped. Run manually: python scripts/seed_pokemon_data.py")
        return
    _run([sys.executable, str(ROOT / "scripts" / "seed_pokemon_data.py")], "Pokemon data seeding")


def step_verify() -> None:
    _print_header("Step 6 — Verification")
    checks = {
        ".env file": ENV_FILE.exists(),
        "credentials.json": CREDS_DEST.exists(),
        "data/pokemon.json": DATA_FILE.exists(),
        "requirements.txt": (ROOT / "requirements.txt").exists(),
    }
    all_ok = True
    for label, ok in checks.items():
        icon = "✅" if ok else "❌"
        print(f"  {icon}  {label}")
        if not ok:
            all_ok = False
    if all_ok:
        print("\n  🎉 All checks passed!")
    else:
        print("\n  ⚠️  Some items are missing — see above.")

    print("""
  ── Next steps ───────────────────────────────────────────
  Install dependencies:
    pip install -r requirements.txt

  Start the bot:
    python src/bot/main.py

  Start the web API (optional):
    uvicorn src.api.app:app --host 0.0.0.0 --port 8000

  Run tests:
    pytest tests/

  ─────────────────────────────────────────────────────────
""")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    _print_header("Pokemon Draft League Bot — Setup Wizard")
    print("  This script will guide you through configuring the bot.\n")

    if ENV_FILE.exists():
        print(f"  Existing .env found at {ENV_FILE}.")
        if not _ask_yes_no("Overwrite / update it?", default=True):
            print("  Skipped .env configuration.")
            step_run_scripts()
            step_seed_pokemon()
            step_verify()
            return

    env_values: dict[str, str] = {}

    try:
        env_values.update(step_discord())
        env_values.update(step_google_sheets())
        env_values.update(step_optional())
    except KeyboardInterrupt:
        print("\n\n  Setup cancelled.")
        sys.exit(0)

    _write_env(env_values)
    print(f"\n  ✅ .env written to {ENV_FILE}")

    step_run_scripts()
    step_seed_pokemon()
    step_verify()


if __name__ == "__main__":
    main()
