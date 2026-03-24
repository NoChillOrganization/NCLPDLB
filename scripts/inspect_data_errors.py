"""
Inspect the #REF! cells in the Data tab to understand the broken formulas.
Run: py -3 scripts/inspect_data_errors.py
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
    """Convert 1-based column number to letter(s). e.g. 1→A, 27→AA"""
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def main() -> None:
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(SPREADSHEET_ID)

    data_ws = ss.worksheet("Data")
    print(f"Data tab: {data_ws.row_count} rows × {data_ws.col_count} cols")

    # Get the formulas for the broken cells
    error_cells = [
        (2, 99, "CU2"),
        (2, 101, "CW2"),
        (2, 102, "CX2"),
        (178, 72, "BT178"),
        (178, 74, "BV178"),
        (178, 75, "BW178"),
        (354, 72, "BT354"),
        (354, 74, "BV354"),
        (354, 75, "BW354"),
        (1442, 60, "BH1442"),
    ]

    print("\n=== Formulas for #REF! cells in Data tab ===")
    for row, col_num, cell_ref in error_cells:
        # Calculate actual column letter
        actual_col = col_letter(col_num)
        cell = f"{actual_col}{row}"
        try:
            result = data_ws.spreadsheet.values_get(
                f"'Data'!{cell}",
                params={"valueRenderOption": "FORMULA"}
            )
            formula = result.get("values", [[""]])[0][0] if result.get("values") else ""
            print(f"  {cell}: {formula[:150]}")
        except Exception as e:
            print(f"  {cell}: ERROR getting formula: {e}")

    # Get context around row 2 of Data tab (first data row)
    print("\n=== Data tab row 2, columns CQ-CZ (cols 95-104) ===")
    result = data_ws.spreadsheet.values_get(
        "'Data'!CQ2:CZ2",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = result.get("values", [[]])
    if vals:
        for i, v in enumerate(vals[0], 95):
            if v:
                print(f"  Col {col_letter(i)} ({i}): {str(v)[:120]}")

    # Get context around row 178 of Data tab
    print("\n=== Data tab row 178, columns BQ-BZ (cols 69-78) ===")
    result = data_ws.spreadsheet.values_get(
        "'Data'!BQ178:BZ178",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = result.get("values", [[]])
    if vals:
        for i, v in enumerate(vals[0], 69):
            if v:
                print(f"  Col {col_letter(i)} ({i}): {str(v)[:120]}")

    # Check the Hannah4Ever tab U22 and W22
    print("\n=== Hannah4Ever tab - rows 20-25 ===")
    hf = ss.worksheet("Hannah4Ever")
    result = hf.spreadsheet.values_get(
        "'Hannah4Ever'!A20:Z25",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = result.get("values", [[]])
    for i, row in enumerate(vals, 20):
        non_empty = [(j+1, v) for j, v in enumerate(row) if v]
        if non_empty:
            print(f"  Row {i}: {non_empty[:8]}")

    # Check MVP Race formula context
    print("\n=== MVP Race tab - row 6, surrounding formulas ===")
    mvp = ss.worksheet("MVP Race")
    result = mvp.spreadsheet.values_get(
        "'MVP Race'!A6:Z6",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = result.get("values", [[]])
    if vals:
        for i, v in enumerate(vals[0], 1):
            if v:
                print(f"  Col {col_letter(i)} ({i}): {str(v)[:150]}")

    # Check the Pokémon Stats errors
    print("\n=== Pokémon Stats - row 33, cols H-L ===")
    pks = ss.worksheet("Pokémon Stats")
    result = pks.spreadsheet.values_get(
        "'Pokémon Stats'!H33:L33",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = result.get("values", [[]])
    if vals:
        for i, v in enumerate(vals[0], 8):
            if v:
                print(f"  Col {col_letter(i)} ({i}): {str(v)[:150]}")

    print("\n=== Pokémon Stats - row 55, cols H-L ===")
    result = pks.spreadsheet.values_get(
        "'Pokémon Stats'!H55:L55",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = result.get("values", [[]])
    if vals:
        for i, v in enumerate(vals[0], 8):
            if v:
                print(f"  Col {col_letter(i)} ({i}): {str(v)[:150]}")

    # Check Team Page Template P5
    print("\n=== Team Page Template P5 formula ===")
    tpt = ss.worksheet("Team Page Template")
    result = tpt.spreadsheet.values_get(
        "'Team Page Template'!N5:R5",
        params={"valueRenderOption": "FORMULA"}
    )
    vals = result.get("values", [[]])
    if vals:
        for i, v in enumerate(vals[0], 14):
            if v:
                print(f"  Col {col_letter(i)} ({i}): {str(v)[:200]}")


if __name__ == "__main__":
    main()
