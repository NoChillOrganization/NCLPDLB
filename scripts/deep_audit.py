"""
Deep-audit each key tab: print first 5 rows with indices so we know
exactly what cells to read/write.
Run: py -3 scripts/deep_audit.py
"""
import json
import sys
import io
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CREDS_FILE = Path(__file__).parent.parent / "credentials.json"
SPREADSHEET_ID = "16F9FP5wkyzDdF8C7vD9xwY2j2JkcWYR1EUK_MtRt7zs"
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

KEY_TABS = [
    "Setup", "Rules", "Draft", "Schedule", "Match Stats", "Standings",
    "Pokémon Stats", "MVP Race", "Transactions", "Playoffs", "Pokédex",
    "Team Page Template", "Data",
]


def show_tab(ws: gspread.Worksheet, rows: int = 8) -> None:
    vals = ws.get_all_values()
    print(f"\n  Dimensions: {len(vals)} rows × {ws.col_count} cols")
    for i, row in enumerate(vals[:rows]):
        non_empty = [(j, v) for j, v in enumerate(row) if v.strip()]
        if non_empty:
            print(f"  Row {i+1:3d}: {non_empty[:10]}")


def main() -> None:
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(SPREADSHEET_ID)

    results = {}
    for tab in KEY_TABS:
        print(f"\n{'='*60}")
        print(f"TAB: '{tab}'")
        print(f"{'='*60}")
        try:
            ws = ss.worksheet(tab)
            show_tab(ws, rows=10)
            vals = ws.get_all_values()
            results[tab] = {
                "rows": len(vals),
                "cols": ws.col_count,
                "sample": vals[:10],
            }
        except gspread.WorksheetNotFound:
            print("  NOT FOUND")
            results[tab] = {"error": "not found"}

    out = Path(__file__).parent / "deep_audit.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n\nDeep audit saved to: {out}")


if __name__ == "__main__":
    main()
