"""
Check columns BE-BH in the Data tab (the SUMIF source columns).
Also check for any #REF! values in those helper columns.
Run: py -3 scripts/check_be_bh.py
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

    # Get formulas for columns BE-BH rows 1-10
    print("=== Data tab columns BA-BK, rows 1-5 (formulas) ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!BA1:BK5",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = r.get("values", [[]])
    for ri, row in enumerate(vals, 1):
        for ci, v in enumerate(row, col_num("BA")):
            if v:
                print(f"  Row {ri}, Col {col_letter(ci)} ({ci}): {str(v)[:200]}")

    # Get VALUES for columns BE-BH rows 1-20
    print("\n=== Data tab columns BE-BJ, rows 1-20 (values) ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!BE1:BJ20",
        params={"valueRenderOption": "FORMATTED_VALUE"}
    )
    vals = r.get("values", [[]])
    for ri, row in enumerate(vals, 1):
        if any(v for v in row):
            display = [(col_letter(i + col_num("BE")), v) for i, v in enumerate(row) if v]
            print(f"  Row {ri}: {display}")

    # Check for #REF! in the BE-BH range (entire column up to row 400)
    print("\n=== Scanning BE-BH rows 1-400 for #REF! errors ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!BE1:BJ400",
        params={"valueRenderOption": "FORMATTED_VALUE"}
    )
    vals = r.get("values", [[]])
    errors_found = []
    for ri, row in enumerate(vals, 1):
        for ci, v in enumerate(row, col_num("BE")):
            if v == "#REF!":
                errors_found.append((ri, col_letter(ci), ci, v))
    if errors_found:
        print(f"  Found {len(errors_found)} errors:")
        for r, cl, ci, v in errors_found[:20]:
            print(f"    Row {r}, Col {cl} ({ci}): {v}")
    else:
        print("  No #REF! errors in BE-BJ range (rows 1-400)")

    # Check what the BH column looks like around the Hannah4Ever data
    # Hannah4Ever is Pool B coach #1, so her data would start at a specific row in BH
    # Let's find rows where BG matches "Chi-Yu"
    print("\n=== Find 'Chi-Yu' in BG column ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!BE1:BJ500",
        params={"valueRenderOption": "FORMATTED_VALUE"}
    )
    vals = r.get("values", [[]])
    bg_idx = col_num("BG") - col_num("BE")  # Index within the fetched range
    bh_idx = col_num("BH") - col_num("BE")
    be_idx = col_num("BE") - col_num("BE")
    for ri, row in enumerate(vals, 1):
        if len(row) > bg_idx and "chi-yu" in str(row[bg_idx]).lower():
            print(f"  Row {ri}: {[(col_letter(ci + col_num('BE')), v) for ci, v in enumerate(row) if v]}")

    # Get the complete BH column values to understand the sum range
    print("\n=== Data tab BH column, rows 1-10 (to understand its format) ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!BE1:BK10",
        params={"valueRenderOption": "FORMATTED_VALUE"}
    )
    vals = r.get("values", [[]])
    for ri, row in enumerate(vals, 1):
        non_empty = [(col_letter(ci + col_num("BE")), v) for ci, v in enumerate(row) if v]
        if non_empty:
            print(f"  Row {ri}: {non_empty}")

    # Check the formula at BT2 more carefully - get the full formula
    print("\n=== Full formula at Data!BT2 ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!BT2",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = r.get("values", [[]])
    if vals and vals[0]:
        print(f"  {vals[0][0]}")

    # Check the formula at BS2 (games played)
    print("\n=== Full formula at Data!BS2 ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!BS2",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = r.get("values", [[]])
    if vals and vals[0]:
        print(f"  {vals[0][0]}")

    # Check BV formula (diff = kills - deaths)
    print("\n=== Full formula at Data!BV2 ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!BV2",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = r.get("values", [[]])
    if vals and vals[0]:
        print(f"  {vals[0][0]}")

    # Let's check what's in BV for rows around 178 (where Chi-Yu is in Pool A stats)
    print("\n=== Data tab BT-BW at rows 175-182 (VALUES - to see the actual #REF!) ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!BS175:BW182",
        params={"valueRenderOption": "FORMATTED_VALUE"}
    )
    vals = r.get("values", [[]])
    for ri, row in enumerate(vals, 175):
        display = [(col_letter(ci + col_num("BS")), v) for ci, v in enumerate(row) if v]
        if display:
            print(f"  Row {ri}: {display}")

    # Check what BO column (Pokémon names) contains around row 178
    print("\n=== Data tab BO column around row 178 (Pool A stats Pokémon names) ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!BM175:BO185",
        params={"valueRenderOption": "FORMATTED_VALUE"}
    )
    vals = r.get("values", [[]])
    for ri, row in enumerate(vals, 175):
        display = [(col_letter(ci + col_num("BM")), v) for ci, v in enumerate(row) if v]
        if display:
            print(f"  Row {ri}: {display}")


if __name__ == "__main__":
    main()
