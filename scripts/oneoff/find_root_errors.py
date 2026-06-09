"""
Find the root cause of the #REF! errors in the Data tab.
Gets a wider context around broken cells to find the originating formula.
Run: py -3 scripts/find_root_errors.py
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


def get_range_formulas(ss, tab: str, cell_range: str) -> list:
    try:
        r = ss.worksheet(tab).spreadsheet.values_get(
            f"'{tab}'!{cell_range}",
            params={"valueRenderOption": "FORMULA"}
        )
        return r.get("values", [[]])
    except Exception as e:
        return [[str(e)]]


def main() -> None:
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(SPREADSHEET_ID)

    data_ws = ss.worksheet("Data")

    # Scan row 1 of Data tab to see all column headers (what each column represents)
    print("=== Data tab row 1 (headers) - cols CI onwards (col 87+) ===")
    r = ss.worksheet("Data").spreadsheet.values_get(
        "'Data'!CI1:CZ1",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = r.get("values", [[]])
    if vals:
        for i, v in enumerate(vals[0], col_num("CI")):
            print(f"  Col {col_letter(i)} ({i}): {v!r}")

    # Look wider around the CU-CX error area - get entire rows 1-3 for cols CL-CZ
    print("\n=== Data tab rows 1-3, cols CL-CZ (formulas) ===")
    r = ss.worksheet("Data").spreadsheet.values_get(
        "'Data'!CL1:CZ3",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = r.get("values", [[]])
    for ri, row in enumerate(vals, 1):
        for ci, v in enumerate(row, col_num("CL")):
            if v:
                print(f"  Row {ri}, Col {col_letter(ci)} ({ci}): {str(v)[:150]}")

    # Check the column header area around BS-BX
    print("\n=== Data tab row 1, cols BL-BZ ===")
    r = ss.worksheet("Data").spreadsheet.values_get(
        "'Data'!BL1:BZ1",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = r.get("values", [[]])
    if vals:
        for i, v in enumerate(vals[0], col_num("BL")):
            if v:
                print(f"  Col {col_letter(i)} ({i}): {v!r}")

    # Look at rows 175-180 in BS-BX to find the source formula
    print("\n=== Data tab rows 175-180, cols BQ-BX (formulas) ===")
    r = ss.worksheet("Data").spreadsheet.values_get(
        "'Data'!BQ175:BX180",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = r.get("values", [[]])
    for ri, row in enumerate(vals, 175):
        for ci, v in enumerate(row, col_num("BQ")):
            if v:
                print(f"  Row {ri}, Col {col_letter(ci)} ({ci}): {str(v)[:150]}")

    # Get actual values (not formulas) to see what the #REF! cells contain
    print("\n=== Data tab actual values, cols CU-CX, rows 1-5 ===")
    r = ss.worksheet("Data").spreadsheet.values_get(
        "'Data'!CU1:CX5",
        params={"valueRenderOption": "FORMATTED_VALUE"}
    )
    vals = r.get("values", [[]])
    for ri, row in enumerate(vals, 1):
        for ci, v in enumerate(row, col_num("CU")):
            if v:
                print(f"  Row {ri}, Col {col_letter(ci)} ({ci}): {v!r}")

    # Check the Match Stats tab structure to understand what feeds the Data tab
    print("\n=== Match Stats tab - rows 3-10 (formulas around key area) ===")
    ms = ss.worksheet("Match Stats")
    r = ms.spreadsheet.values_get(
        "'Match Stats'!A3:N10",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = r.get("values", [[]])
    for ri, row in enumerate(vals, 3):
        for ci, v in enumerate(row, 1):
            if v:
                print(f"  Row {ri}, Col {col_letter(ci)} ({ci}): {str(v)[:100]}")

    # Look at a working row 7 of Match Stats (Zen vs Hannah4Ever with data)
    print("\n=== Match Stats tab row 7, full row values ===")
    r = ms.spreadsheet.values_get(
        "'Match Stats'!A7:Z7",
        params={"valueRenderOption": "FORMATTED_VALUE"}
    )
    vals = r.get("values", [[]])
    if vals:
        for ci, v in enumerate(vals[0], 1):
            if v:
                print(f"  Col {col_letter(ci)} ({ci}): {v!r}")

    # Check what data the Pokémon Stats errors reference at Data!BS178:BV189
    print("\n=== Data tab values at BS178:BV189 (source of Pokémon Stats error) ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!BS178:BV189",
        params={"valueRenderOption": "FORMATTED_VALUE"}
    )
    vals = r.get("values", [[]])
    print(f"  Found {len(vals)} rows")
    for ri, row in enumerate(vals, 178):
        if any(v for v in row):
            print(f"  Row {ri}: {row}")

    # Check the Data tab columns just before BS to understand context
    print("\n=== Data tab row 178, cols BO-BZ (values) ===")
    r = data_ws.spreadsheet.values_get(
        "'Data'!BO178:BZ178",
        params={"valueRenderOption": "FORMATTED_VALUE"}
    )
    vals = r.get("values", [[]])
    if vals:
        for ci, v in enumerate(vals[0], col_num("BO")):
            if v:
                print(f"  Col {col_letter(ci)} ({ci}): {v!r}")


if __name__ == "__main__":
    main()
