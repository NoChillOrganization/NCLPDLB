"""
ML Learning Sheet Setup — pre-creates all tabs with headers.

Run once after setting ML_LEARNING_SPREADSHEET_ID in .env:
  python scripts/setup_ml_sheet.py

Creates:
  Replays       — all battle results (every format)
  Training Runs — PPO checkpoint metrics
  <format>      — one tab per SPAR_FORMATS entry

All tabs are safe to run again — existing tabs are skipped.

Requires ML_LEARNING_SPREADSHEET_ID and GOOGLE_SHEETS_CREDENTIALS_FILE in .env
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Clock skew fix ────────────────────────────────────────────
# Shared helper — see scripts/_clock_skew.py for details (M33)
from _clock_skew import apply_google_clock_skew
apply_google_clock_skew()

from src.config import settings
from src.data.sheets import REPLAY_HEADERS, TRAINING_RUN_HEADERS

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# All formats that may have per-format tabs (mirrors SPAR_FORMATS in stats.py)
SPAR_FORMATS = [
    "gen9randombattle", "gen9monorandom", "gen9randomdoublesbattle",
    "gen7randombattle", "gen6randombattle",
    "gen9ou", "gen9ubers", "gen9uu", "gen9ru", "gen9nu", "gen9pu", "gen9zu",
    "gen9lc", "gen9monotype", "gen9nationaldex", "gen9anythinggoes",
    "gen9doublesou", "gen9doublesubers", "gen9doublesuu", "gen9doublesnu",
    "gen9vgc2025regg", "gen9vgc2025regh", "gen9vgc2025regi",
    "gen9vgc2025reggbo3", "gen9vgc2025reghbo3", "gen9vgc2025regibo3",
    "gen9vgc2026regi", "gen9vgc2026regibo3",
    "gen9championsou", "gen9championsbssregma",
    "gen9championsvgc2026regma", "gen9championsvgc2026regmabo3",
]


def _get_or_create(spreadsheet: gspread.Spreadsheet, title: str, headers: list[str]) -> str:
    """Return 'existing' or 'created' for a tab."""
    try:
        spreadsheet.worksheet(title)
        return "existing"
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=10000, cols=len(headers))
        ws.append_row(headers, value_input_option="USER_ENTERED")
        return "created"


def main() -> None:
    if not settings.ml_learning_spreadsheet_id:
        print("ERROR: ML_LEARNING_SPREADSHEET_ID not set in .env")
        sys.exit(1)

    creds_path = settings.google_sheets_credentials_file
    if not creds_path.exists():
        print(f"ERROR: credentials file not found: {creds_path}")
        sys.exit(1)

    print(f"Connecting to sheet: {settings.ml_learning_spreadsheet_id}")
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(settings.ml_learning_spreadsheet_id)
    print(f"Connected: '{spreadsheet.title}'\n")

    # Core tabs
    for title, headers in [
        ("Replays",       REPLAY_HEADERS),
        ("Training Runs", TRAINING_RUN_HEADERS),
    ]:
        status = _get_or_create(spreadsheet, title, headers)
        print(f"  [{status:8s}] {title}")
        time.sleep(0.5)  # avoid rate limit

    print()

    # Per-format tabs
    created = skipped = 0
    for fmt in SPAR_FORMATS:
        status = _get_or_create(spreadsheet, fmt, REPLAY_HEADERS)
        if status == "created":
            print(f"  [created  ] {fmt}")
            created += 1
        else:
            skipped += 1
        time.sleep(0.3)

    print(f"\nFormat tabs: {created} created, {skipped} already existed.")
    print("\nDone. ML sheet is ready.")


if __name__ == "__main__":
    main()
