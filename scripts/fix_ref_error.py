"""
Investigate and fix the #REF! error in the MVP Race tab.
Also scan all tabs for any formula errors.
Run: py -3 scripts/fix_ref_error.py
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


def find_errors(ws: gspread.Worksheet) -> list[tuple[int, int, str]]:
    """Return (row, col, value) for all cells containing formula errors."""
    vals = ws.get_all_values()
    errors = []
    error_markers = {"#REF!", "#VALUE!", "#N/A", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!"}
    for r, row in enumerate(vals, 1):
        for c, cell in enumerate(row, 1):
            if cell in error_markers:
                errors.append((r, c, cell))
    return errors


def main() -> None:
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(SPREADSHEET_ID)

    print("Scanning all tabs for formula errors...\n")
    all_errors: dict[str, list] = {}

    for ws in ss.worksheets():
        errs = find_errors(ws)
        if errs:
            all_errors[ws.title] = errs
            print(f"  Tab '{ws.title}': {len(errs)} error(s)")
            for r, c, v in errs[:10]:
                cell_ref = f"{chr(64 + c)}{r}" if c <= 26 else f"col{c}row{r}"
                print(f"    {cell_ref}: {v}")

    if not all_errors:
        print("No formula errors found in any tab.")

    # Deep dive: MVP Race tab - get surrounding context for the #REF! cell
    print("\n\n=== MVP Race tab deep dive ===")
    mvp = ss.worksheet("MVP Race")
    vals = mvp.get_all_values()
    print(f"Dimensions: {len(vals)} rows × {mvp.col_count} cols")
    print("\nRows 3-15 (non-empty cells):")
    for i, row in enumerate(vals[2:15], 3):
        non_empty = [(j+1, v) for j, v in enumerate(row) if v.strip()]
        if non_empty:
            print(f"  Row {i:3d}: {non_empty[:12]}")

    # Get formulas from the MVP Race tab using the cell_feed
    print("\n\nTrying to get formulas (not values) from MVP Race row 6:")
    try:
        # Get raw formulas by specifying value_render_option
        result = mvp.spreadsheet.values_get(
            "'MVP Race'!A6:Z6",
            params={"valueRenderOption": "FORMULA"}
        )
        print(f"  Row 6 formulas: {result.get('values', [])}")
    except Exception as e:
        print(f"  Could not get formulas: {e}")

    # Also check the Standings tab for any issues
    print("\n\n=== Standings tab - full data ===")
    st = ss.worksheet("Standings")
    vals = st.get_all_values()
    for i, row in enumerate(vals[:37], 1):
        non_empty = [(j+1, v) for j, v in enumerate(row) if v.strip()]
        if non_empty:
            print(f"  Row {i:3d}: {non_empty[:8]}")


if __name__ == "__main__":
    main()
