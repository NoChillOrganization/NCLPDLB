"""
Audit the Google Spreadsheet — list all tabs, their headers, and row counts.
Run from the project root: py -3 scripts/audit_sheet.py
"""
import json
import sys
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

CREDS_FILE = Path(__file__).parent.parent / "credentials.json"
SPREADSHEET_ID = "16F9FP5wkyzDdF8C7vD9xwY2j2JkcWYR1EUK_MtRt7zs"

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

EXPECTED_TABS = [
    "Setup", "Rules", "Cover", "Draft", "Draft Board",
    "Pool A Board", "Pool B Board", "Schedule", "Match Stats",
    "Standings", "Pokemon Stats", "MVP Race", "Transactions",
    "Playoffs", "Pokedex", "Team Page Template", "Data",
]


def main() -> None:
    if not CREDS_FILE.exists():
        print(f"ERROR: credentials.json not found at {CREDS_FILE}", file=sys.stderr)
        sys.exit(1)

    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    gc = gspread.authorize(creds)
    print("Connected to Google Sheets API")

    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    print(f"\nSpreadsheet: '{spreadsheet.title}'")
    print(f"URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}\n")

    worksheets = spreadsheet.worksheets()
    print(f"{'='*60}")
    print(f"ACTUAL TABS ({len(worksheets)} found):")
    print(f"{'='*60}")

    actual_names = []
    tab_info = {}
    for ws in worksheets:
        actual_names.append(ws.title)
        try:
            all_vals = ws.get_all_values()
            row_count = len(all_vals)
            # Find first non-empty row as header
            header_row = []
            for row in all_vals[:5]:
                non_empty = [c for c in row if c.strip()]
                if non_empty:
                    header_row = row
                    break
            tab_info[ws.title] = {
                "rows": row_count,
                "cols": ws.col_count,
                "header": [c for c in header_row if c.strip()][:10],
                "gid": ws.id,
            }
            print(f"\n  Tab: '{ws.title}' (GID: {ws.id})")
            print(f"    Rows: {row_count}, Cols: {ws.col_count}")
            if header_row:
                print(f"    First headers: {[c for c in header_row if c.strip()][:8]}")
        except Exception as e:
            print(f"  Tab: '{ws.title}' — Error reading: {e}")
            tab_info[ws.title] = {"error": str(e), "gid": ws.id}

    print(f"\n{'='*60}")
    print("MISSING TABS (expected by bot but not in sheet):")
    print(f"{'='*60}")
    missing = [t for t in EXPECTED_TABS if t not in actual_names]
    if missing:
        for t in missing:
            print(f"  MISSING: '{t}'")
    else:
        print("  All expected tabs present!")

    print(f"\n{'='*60}")
    print("EXTRA TABS (in sheet but not expected by bot):")
    print(f"{'='*60}")
    extra = [t for t in actual_names if t not in EXPECTED_TABS]
    if extra:
        for t in extra:
            print(f"  EXTRA: '{t}'")
    else:
        print("  No extra tabs.")

    # Save audit results to JSON
    audit_out = Path(__file__).parent.parent / "scripts" / "audit_result.json"
    with audit_out.open("w") as f:
        json.dump({
            "spreadsheet_title": spreadsheet.title,
            "actual_tabs": actual_names,
            "missing_tabs": missing,
            "extra_tabs": extra,
            "tab_info": tab_info,
        }, f, indent=2)
    print(f"\nAudit saved to: {audit_out}")


if __name__ == "__main__":
    main()
