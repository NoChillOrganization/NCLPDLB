"""
Google Sheets Setup Script — creates all 17 tabs with correct headers,
formatting, and data validation for the No Chill League spreadsheet.

Run once after creating a new Google Sheet:
  python scripts/setup_google_sheet.py

Requires GOOGLE_SHEETS_CREDENTIALS_FILE and GOOGLE_SHEETS_SPREADSHEET_ID in .env
"""
from __future__ import annotations

import sys
import time
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Clock skew fix ────────────────────────────────────────────
# If the local system clock is behind/ahead of Google's servers,
# JWT auth will fail with "invalid_grant". We fetch the real time
# from Google and patch google.auth._helpers.utcnow() before any
# auth call is made so the generated JWT has correct iat/exp values.
try:
    import urllib.request
    import email.utils
    with urllib.request.urlopen("https://accounts.google.com", timeout=5) as resp:
        date_header = resp.headers.get("Date", "")
    if date_header:
        server_dt = email.utils.parsedate_to_datetime(date_header)
        skew = server_dt.replace(tzinfo=None) - datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        if abs(skew.total_seconds()) > 10:
            import google.auth._helpers as _ga_helpers
            _orig_utcnow = _ga_helpers.utcnow
            _ga_helpers.utcnow = lambda: _orig_utcnow() + skew
            print(f"[clock-fix] Adjusted JWT clock by {skew.total_seconds():.0f}s to match Google servers")
except Exception:
    pass  # Best-effort; let auth fail naturally if unreachable

import gspread
from google.oauth2.service_account import Credentials
from src.config import settings
from src.data.sheets import Tab

# Column headers for each tab (empty list = visual template, skip header write)
HEADERS: dict[str, list[str]] = {
    Tab.SETUP:         ["key", "value", "description"],
    Tab.RULES:         [],   # visual template — commissioner managed
    Tab.COVER:         [],   # visual template
    Tab.DRAFT:         ["pick_number", "round", "player_id", "discord_name", "pokemon_name",
                        "types", "tier", "tera_type", "game_format", "notes", "timestamp"],
    Tab.DRAFT_BOARD:   ["player_id", "discord_name", "team_name",
                        "slot_1", "slot_2", "slot_3", "slot_4", "slot_5", "slot_6",
                        "slot_7", "slot_8", "slot_9", "slot_10"],
    Tab.POOL_A:        ["player_id", "discord_name", "team_name",
                        "slot_1", "slot_2", "slot_3", "slot_4", "slot_5", "slot_6"],
    Tab.POOL_B:        ["player_id", "discord_name", "team_name",
                        "slot_1", "slot_2", "slot_3", "slot_4", "slot_5", "slot_6"],
    Tab.SCHEDULE:      [],   # visual template
    Tab.MATCH_STATS:   [],   # visual template (168-col)
    Tab.STANDINGS:     [],   # visual template
    Tab.POKEMON_STATS: [],   # formula-driven
    Tab.MVP_RACE:      [],   # formula-driven
    Tab.TRANSACTIONS:  ["#", "week", "event", "coach1", "pokemon1", "separator",
                        "pokemon2", "separator2", "coach2", "notes"],
    Tab.PLAYOFFS:      ["match_id", "round", "player1_id", "player1_name",
                        "player2_id", "player2_name", "winner_id", "score", "replay_url", "date"],
    Tab.POKEDEX:       ["github_name", "smogon_name", "pmd_ref", "separator",
                        "pts", "separator2", "separator3",
                        "pokemon", "type1", "type2",
                        "hp", "atk", "def", "spa", "spd", "spe",
                        "bst_0ev", "bst_252", "bst_252plus", "separator4", "sprite_url"],
    Tab.TEAM_TEMPLATE: ["team_id", "player_id", "discord_name", "team_name",
                        "team_logo_url", "color_hex", "league_id", "created_at"],
    Tab.DATA:          ["match_id", "league_id", "week", "player1_id", "player1_name",
                        "player2_id", "player2_name", "winner_id", "score",
                        "replay_url", "video_url", "format", "date", "notes"],
}

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Tab order in the spreadsheet
TAB_ORDER = [
    Tab.SETUP, Tab.RULES, Tab.COVER,
    Tab.DRAFT, Tab.DRAFT_BOARD,
    Tab.POOL_A, Tab.POOL_B,
    Tab.SCHEDULE, Tab.MATCH_STATS, Tab.STANDINGS,
    Tab.POKEMON_STATS, Tab.MVP_RACE, Tab.TRANSACTIONS,
    Tab.PLAYOFFS, Tab.POKEDEX, Tab.TEAM_TEMPLATE, Tab.DATA,
]

# Header row background colors (hex) per tab
TAB_COLORS = {
    Tab.SETUP:         (0.18, 0.31, 0.56),   # Dark blue
    Tab.RULES:         (0.56, 0.18, 0.18),   # Dark red
    Tab.COVER:         (0.18, 0.56, 0.18),   # Dark green
    Tab.DRAFT:         (0.40, 0.18, 0.56),   # Purple
    Tab.DRAFT_BOARD:   (0.40, 0.18, 0.56),
    Tab.POOL_A:        (0.18, 0.45, 0.56),   # Teal
    Tab.POOL_B:        (0.18, 0.45, 0.56),
    Tab.SCHEDULE:      (0.56, 0.40, 0.18),   # Orange
    Tab.MATCH_STATS:   (0.56, 0.40, 0.18),
    Tab.STANDINGS:     (0.18, 0.56, 0.40),   # Green-teal
    Tab.POKEMON_STATS: (0.30, 0.56, 0.18),
    Tab.MVP_RACE:      (0.56, 0.53, 0.18),   # Gold
    Tab.TRANSACTIONS:  (0.56, 0.18, 0.40),   # Pink
    Tab.PLAYOFFS:      (0.56, 0.30, 0.18),   # Brown-orange
    Tab.POKEDEX:       (0.18, 0.18, 0.56),   # Navy
    Tab.TEAM_TEMPLATE: (0.35, 0.18, 0.56),
    Tab.DATA:          (0.40, 0.40, 0.40),   # Grey
}

# Tera types for data validation in Draft tab
TERA_TYPES = [
    "Normal", "Fire", "Water", "Electric", "Grass", "Ice",
    "Fighting", "Poison", "Ground", "Flying", "Psychic",
    "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy", "Stellar",
]

DRAFT_FORMATS = ["snake", "auction", "tiered", "custom"]
GAME_FORMATS = ["showdown", "sv", "swsh", "bdsp", "legends", "vgc"]
POOLS = ["A", "B"]
STATUSES = ["setup", "ban_phase", "active", "paused", "completed"]
TRANSACTION_TYPES = ["trade", "drop", "add", "waiver"]
TRANSACTION_STATUSES = ["pending", "accepted", "declined", "cancelled"]


def rgb(r: float, g: float, b: float) -> dict:
    return {"red": r, "green": g, "blue": b}


def connect() -> gspread.Spreadsheet:
    creds_path = settings.google_sheets_credentials_file
    if not creds_path.exists():
        print(f"ERROR: credentials file not found at {creds_path}")
        sys.exit(1)
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(settings.google_sheets_spreadsheet_id)
    print(f"Connected to: '{sheet.title}'")
    return sheet


def get_or_create_tab(sheet: gspread.Spreadsheet, name: str, index: int) -> gspread.Worksheet:
    existing = {ws.title: ws for ws in sheet.worksheets()}
    if name in existing:
        ws = existing[name]
        print(f"  [existing] {name}")
    else:
        ws = sheet.add_worksheet(title=name, rows=1000, cols=30, index=index)
        print(f"  [created]  {name}")
        time.sleep(0.5)   # Avoid rate limits
    return ws


def write_headers(ws: gspread.Worksheet, headers: list[str], color: tuple) -> None:
    if not headers:
        return
    # Check if header row already exists
    existing_row = ws.row_values(1)
    if existing_row and existing_row[0] == headers[0]:
        return  # Already set up

    ws.append_row(headers, value_input_option="USER_ENTERED")
    # Format header row: bold, colored background, freeze
    sheet_id = ws._properties["sheetId"]
    requests = [
        # Bold + background color
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0, "endRowIndex": 1,
                    "startColumnIndex": 0, "endColumnIndex": len(headers),
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": rgb(*color),
                        "textFormat": {"bold": True, "foregroundColor": rgb(1, 1, 1)},
                        "horizontalAlignment": "CENTER",
                        "wrapStrategy": "CLIP",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,wrapStrategy)",
            }
        },
        # Freeze first row
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
        # Auto-resize columns
        {
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": len(headers),
                }
            }
        },
    ]
    ws.spreadsheet.batch_update({"requests": requests})


def add_data_validation(ws: gspread.Worksheet, col_index: int, values: list[str], rows: int = 999) -> None:
    """Add dropdown validation to a column."""
    sheet_id = ws._properties["sheetId"]
    request = {
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1, "endRowIndex": rows + 1,
                "startColumnIndex": col_index, "endColumnIndex": col_index + 1,
            },
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": v} for v in values],
                },
                "showCustomUi": True,
                "strict": False,
            },
        }
    }
    ws.spreadsheet.batch_update({"requests": [request]})
    time.sleep(0.3)


def setup_draft_tab(ws: gspread.Worksheet) -> None:
    """Add data validation dropdowns to the Draft tab."""
    headers = HEADERS[Tab.DRAFT]
    tera_col = headers.index("tera_type")
    format_col_name = "game_format"
    format_col = headers.index(format_col_name) if format_col_name in headers else -1

    add_data_validation(ws, tera_col, TERA_TYPES)
    if format_col >= 0:
        add_data_validation(ws, format_col, GAME_FORMATS)
    print(f"    -> Tera type dropdown on col {tera_col + 1} (column {chr(65 + tera_col)})")


def setup_setup_tab(ws: gspread.Worksheet) -> None:
    headers = HEADERS[Tab.SETUP]
    format_col = headers.index("format") if "format" in headers else -1
    status_col = headers.index("status") if "status" in headers else -1
    if format_col >= 0:
        add_data_validation(ws, format_col, DRAFT_FORMATS)
    if status_col >= 0:
        add_data_validation(ws, status_col, STATUSES)


def setup_transactions_tab(ws: gspread.Worksheet) -> None:
    headers = HEADERS[Tab.TRANSACTIONS]
    type_col = headers.index("type") if "type" in headers else -1
    status_col = headers.index("status") if "status" in headers else -1
    if type_col >= 0:
        add_data_validation(ws, type_col, TRANSACTION_TYPES)
    if status_col >= 0:
        add_data_validation(ws, status_col, TRANSACTION_STATUSES)


def add_team_template_image_formula(ws: gspread.Worksheet) -> None:
    """Add an IMAGE() formula to col 4 (team_logo_url) header note."""
    # Just add a note explaining that URLs in this column will show logo in embeds
    sheet_id = ws._properties["sheetId"]
    headers = HEADERS[Tab.TEAM_TEMPLATE]
    logo_col = headers.index("team_logo_url") if "team_logo_url" in headers else -1
    if logo_col < 0:
        return
    request = {
        "updateCells": {
            "rows": [{
                "values": [{
                    "note": (
                        "Discord CDN URL for team logo.\n"
                        "Automatically filled by /team-register.\n"
                        "Use IMAGE() formula in adjacent cell to display."
                    )
                }]
            }],
            "fields": "note",
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0, "endRowIndex": 1,
                "startColumnIndex": logo_col, "endColumnIndex": logo_col + 1,
            },
        }
    }
    ws.spreadsheet.batch_update({"requests": [request]})


def main() -> None:
    print("=== Pokemon Draft League — Google Sheets Setup ===\n")
    sheet = connect()
    print(f"\nSetting up {len(TAB_ORDER)} tabs...\n")

    for idx, tab_name in enumerate(TAB_ORDER):
        ws = get_or_create_tab(sheet, tab_name, idx)
        color = TAB_COLORS.get(tab_name, (0.3, 0.3, 0.3))
        headers = HEADERS.get(tab_name, [])
        write_headers(ws, headers, color)

        # Tab-specific validation
        if tab_name == Tab.DRAFT:
            setup_draft_tab(ws)
        elif tab_name == Tab.SETUP:
            setup_setup_tab(ws)
        elif tab_name == Tab.TRANSACTIONS:
            setup_transactions_tab(ws)
        elif tab_name == Tab.TEAM_TEMPLATE:
            add_team_template_image_formula(ws)

        time.sleep(0.4)  # Stay under Sheets API quota

    print(f"\nOK All {len(TAB_ORDER)} tabs ready!")
    print(f"Spreadsheet URL: https://docs.google.com/spreadsheets/d/{settings.google_sheets_spreadsheet_id}")
    print("\nNext steps:")
    print("  1. Share the spreadsheet with your service account email (from credentials.json)")
    print("  2. Run: python scripts/seed_pokemon_data.py  (fetch all 1025 Pokemon)")
    print("  3. Run: python -c \"from src.data.sheets import sheets; from scripts.seed_pokemon_data import OUTPUT_FILE; import json; sheets.bulk_write_pokedex(json.load(open(OUTPUT_FILE)))\"")
    print("  4. Start the bot: python src/bot/main.py")


if __name__ == "__main__":
    main()
