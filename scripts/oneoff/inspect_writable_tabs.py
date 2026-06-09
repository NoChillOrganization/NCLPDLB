"""
Inspect the actual cell layout of tabs the bot reads/writes.
Check whether they have flat header rows or visual templates.
Run: py -3 scripts/inspect_writable_tabs.py
"""
# ruff: noqa: E401, E402, F841
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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

TABS_TO_CHECK = [
    "Setup", "Rules", "Schedule", "Match Stats",
    "Standings", "Transactions", "Playoffs", "Pokédex",
]

def main() -> None:
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(SPREADSHEET_ID)

    for tab_name in TABS_TO_CHECK:
        print(f"\n{'='*60}")
        print(f"TAB: '{tab_name}'")
        print(f"{'='*60}")
        try:
            ws = ss.worksheet(tab_name)
            # Get first 10 rows, columns A-Z
            result = ws.spreadsheet.values_get(
                f"'{tab_name}'!A1:Z10",
                params={"valueRenderOption": "FORMATTED_VALUE"}
            )
            vals = result.get("values", [])
            print(f"  Total rows: {ws.row_count}, Total cols: {ws.col_count}")
            for ri, row in enumerate(vals, 1):
                # Show all non-empty cells with their column letter
                non_empty = [(chr(64+ci) if ci<=26 else f"col{ci}", v)
                             for ci, v in enumerate(row, 1) if v.strip()]
                if non_empty:
                    print(f"  Row {ri:2d}: {non_empty}")
                else:
                    print(f"  Row {ri:2d}: (empty)")
        except gspread.WorksheetNotFound:
            print("  NOT FOUND")

    # Special: check Setup tab for the league config cells
    print(f"\n{'='*60}")
    print("SETUP TAB — Searching for key config labels (rows 1-50)")
    print(f"{'='*60}")
    ws = ss.worksheet("Setup")
    result = ws.spreadsheet.values_get(
        "'Setup'!A1:Z50",
        params={"valueRenderOption": "FORMATTED_VALUE"}
    )
    vals = result.get("values", [])
    keywords = {"league", "season", "format", "coach", "week", "round", "pool",
                "draft", "timer", "status", "commissioner"}
    for ri, row in enumerate(vals, 1):
        for ci, v in enumerate(row, 1):
            if any(kw in v.lower() for kw in keywords if v.strip()):
                col = chr(64+ci) if ci<=26 else f"col{ci}"
                print(f"  Row {ri:2d}, Col {col}: '{v}'")

    # Check how many rows of real data are in Transactions tab
    print(f"\n{'='*60}")
    print("TRANSACTIONS TAB — First 20 rows")
    print(f"{'='*60}")
    ws = ss.worksheet("Transactions")
    result = ws.spreadsheet.values_get(
        "'Transactions'!A1:M20",
        params={"valueRenderOption": "FORMATTED_VALUE"}
    )
    vals = result.get("values", [])
    for ri, row in enumerate(vals, 1):
        non_empty = [(chr(64+ci) if ci<=26 else f"col{ci}", v)
                     for ci, v in enumerate(row, 1) if v.strip()]
        if non_empty:
            print(f"  Row {ri:2d}: {non_empty}")

    # Check Standings tab structure
    print(f"\n{'='*60}")
    print("STANDINGS TAB — First 40 rows, cols A-L")
    print(f"{'='*60}")
    ws = ss.worksheet("Standings")
    result = ws.spreadsheet.values_get(
        "'Standings'!A1:L40",
        params={"valueRenderOption": "FORMATTED_VALUE"}
    )
    vals = result.get("values", [])
    for ri, row in enumerate(vals, 1):
        non_empty = [(chr(64+ci) if ci<=26 else f"col{ci}", v)
                     for ci, v in enumerate(row, 1) if v.strip()]
        if non_empty:
            print(f"  Row {ri:2d}: {non_empty}")


if __name__ == "__main__":
    main()
