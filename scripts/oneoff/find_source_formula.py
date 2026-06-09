"""
Find the originating ARRAYFORMULA that generates Data!BT178 and Data!CU2.
These are populated by an array formula that starts somewhere in the Data tab.
Run: py -3 scripts/find_source_formula.py
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

def col_letter(n: int) -> str:
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result

def col_num(s: str) -> int:
    result = 0
    for ch in s.upper():
        result = result * 26 + (ord(ch) - 64)
    return result


def main() -> None:
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(SPREADSHEET_ID)
    data_ws = ss.worksheet("Data")

    # Scan the top rows of columns BL-BW (Pool A stats section) to find the source formula
    print("=== Looking for source formula in Pool A stats columns BL-BW, rows 2-20 ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!BL2:BW20",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = r.get("values", [[]])
    for ri, row in enumerate(vals, 2):
        for ci, v in enumerate(row, col_num("BL")):
            if v and v not in ["0", "1", "2", "3", "4", "5", "6", "7", "8"]:
                print(f"  Row {ri}, Col {col_letter(ci)} ({ci}): {str(v)[:200]}")

    # Check rows 2-20 for cols CL-CX (MVP Race source)
    print("\n=== Looking for source formula in MVP Race cols CL-CX, rows 2-20 ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!CL2:CX20",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = r.get("values", [[]])
    for ri, row in enumerate(vals, 2):
        for ci, v in enumerate(row, col_num("CL")):
            if v and v not in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "#REF!"]:
                print(f"  Row {ri}, Col {col_letter(ci)} ({ci}): {str(v)[:200]}")

    # Look at what's in the Match Stats tab that corresponds to the Chi-Yu #REF! error
    # Chi-Yu is Hannah4Ever's pick. Let's look at all weeks for that match
    print("\n=== Match Stats - Check Chi-Yu (Hannah4Ever) across all weeks ===")
    ms = ss.worksheet("Match Stats")
    # Week 1 is at cols D-M (rows 7-16), Week 2 at cols O-X, etc.
    # Actually the structure is different. Let me get the first 20 rows of each week column block
    ms_vals = ms.get_all_values()
    print(f"Match Stats dimensions: {len(ms_vals)} rows × {ms.col_count} cols")

    # Find Chi-Yu in Match Stats
    for ri, row in enumerate(ms_vals, 1):
        for ci, v in enumerate(row):
            if "Chi-Yu" in str(v):
                print(f"  Found 'Chi-Yu' at row {ri}, col {col_letter(ci+1)} ({ci+1}): {v!r}")
                # Print surrounding context
                ctx = [(j+1, row[j]) for j in range(max(0,ci-3), min(len(row), ci+8)) if row[j]]
                print(f"    Context: {ctx}")

    # Check the formula that generates Pool A stats
    # Look at rows around 178 to see what generates those stats
    print("\n=== Data tab Pool A stats area - scanning for source formulas ===")
    # Try rows 2, 7, 8, 18, 178 for cols BL-BW
    for row_num in [2, 7, 8, 10, 18, 34, 66, 130, 178]:
        r = data_ws.spreadsheet.values_get(
            f"'Data'!BL{row_num}:BW{row_num}",
            params={"valueRenderOption": "FORMULA"}
        )
        vals = r.get("values", [[]])
        if vals and any(v for v in vals[0]):
            non_empty = [(col_letter(i + col_num("BL")), str(v)[:100]) for i, v in enumerate(vals[0]) if v]
            if non_empty:
                print(f"  Row {row_num}: {non_empty}")

    # Get Data tab row 7-20 for BL-BW to see if formula is there
    print("\n=== Data tab BL7:BW20 (FORMULA render) ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!BL7:BW20",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = r.get("values", [[]])
    for ri, row in enumerate(vals, 7):
        non_empty = [(col_letter(i + col_num("BL")), str(v)[:120]) for i, v in enumerate(row) if v]
        if non_empty:
            print(f"  Row {ri}: {non_empty}")

    # Specifically look at what reference BT in Pool A stats would be
    # Check which cells in Match Stats have the Zen vs Hannah4Ever data
    print("\n=== Match Stats Week 1 area: rows 6-17 ALL values ===")
    r = ms.spreadsheet.values_get(
        "'Match Stats'!A6:O17",
        params={"valueRenderOption": "FORMATTED_VALUE"}
    )
    vals = r.get("values", [[]])
    for ri, row in enumerate(vals, 6):
        non_empty = [(col_letter(i+1), v) for i, v in enumerate(row) if v]
        if non_empty:
            print(f"  Row {ri}: {non_empty[:12]}")

    # Check what scores Chi-Yu has across the Match Stats for all 8 weeks
    # The Match Stats structure: week 1 at col D, week 2 at col O (col 15), etc.
    # Each week is 11 columns apart (E-O is 11 columns)
    print("\n=== Checking Chi-Yu's kill data entries in Match Stats across all weeks ===")
    ms_all = ms.get_all_values()
    for ri, row in enumerate(ms_all, 1):
        for ci, v in enumerate(row):
            if str(v).strip() == "Chi-Yu":
                print(f"\n  Chi-Yu found at row {ri}, col {col_letter(ci+1)}:")
                # Get kills (F/G columns for that match)
                start = max(0, ci - 2)
                end = min(len(row), ci + 8)
                ctx = [(col_letter(j+1), row[j]) for j in range(start, end)]
                print(f"    Context: {ctx}")


if __name__ == "__main__":
    main()
