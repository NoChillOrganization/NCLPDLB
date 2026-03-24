"""
Fix #N/A in P5 on all 17 team-page tabs (Team Page Template + 16 coach tabs).

Root cause:
  P5 formula: ="vs. "&ARRAYFORMULA(VLOOKUP(Setup!H18&$F$3,...))
  When Setup!H18 = "Playoffs", VLOOKUP finds no match → #N/A.

Fix:
  Wrap with IFERROR so P5 shows "" (blank) when no schedule match exists
  (e.g., during Playoffs or off-season).

Run: py -3 scripts/fix_p5_na.py
"""
# ruff: noqa: E401, E402, F841
import sys
import io
import time
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

OLD_INNER = 'ARRAYFORMULA(VLOOKUP(Setup!H18&$F$3,{Data!$L$2:$L$481&Data!$O$2:$O$481,Data!$U$2:$U$481},2,0))'
NEW_FORMULA = '=IFERROR("vs. "&ARRAYFORMULA(VLOOKUP(Setup!H18&$F$3,{Data!$L$2:$L$481&Data!$O$2:$O$481,Data!$U$2:$U$481},2,0)),"")'


def get_formula(ws: gspread.Worksheet, cell: str) -> str:
    r = ws.spreadsheet.values_get(
        f"'{ws.title}'!{cell}",
        params={"valueRenderOption": "FORMULA"},
    )
    vals = r.get("values", [[]])
    return vals[0][0] if vals and vals[0] else ""


def set_formula(ws: gspread.Worksheet, cell: str, formula: str) -> None:
    ws.update([[formula]], cell, value_input_option="USER_ENTERED")


def get_value(ws: gspread.Worksheet, cell: str) -> str:
    r = ws.spreadsheet.values_get(
        f"'{ws.title}'!{cell}",
        params={"valueRenderOption": "FORMATTED_VALUE"},
    )
    vals = r.get("values", [[]])
    return vals[0][0] if vals and vals[0] else ""


def main() -> None:
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(SPREADSHEET_ID)

    # Collect all tabs that have a #N/A or the old formula at P5
    team_tabs = ["Team Page Template"] + [
        ws.title for ws in ss.worksheets()
        if ws.title not in {
            "Setup", "Rules", "Cover", "Draft", "Draft Board",
            "Pool A Board", "Pool B Board", "Schedule", "Match Stats",
            "Standings", "Pokémon Stats", "MVP Race", "Transactions",
            "Playoffs", "Pokédex", "Team Page Template", "Data",
            "Tera Type Symbols",
        }
    ]
    print(f"Team tabs to fix: {team_tabs}\n")

    fixed = []
    skipped = []
    for tab_name in team_tabs:
        try:
            ws = ss.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            print(f"  SKIP (not found): {tab_name}")
            skipped.append(tab_name)
            continue

        current = get_formula(ws, "P5")
        current_val = get_value(ws, "P5")

        if OLD_INNER in current and not current.startswith("=IFERROR"):
            print(f"  Fixing '{tab_name}'!P5  (was: {current_val!r})")
            set_formula(ws, "P5", NEW_FORMULA)
            fixed.append(tab_name)
            time.sleep(0.5)  # gentle rate-limit buffer
        elif current_val == "#N/A":
            # Formula is different but still producing #N/A — inspect and fix
            print(f"  '{tab_name}'!P5 = #N/A with unexpected formula: {current[:120]}")
            print("    → Wrapping with IFERROR anyway")
            wrapped = f"=IFERROR({current.lstrip('=')},\"\")" if current.startswith("=") else current
            set_formula(ws, "P5", wrapped)
            fixed.append(tab_name)
            time.sleep(0.5)
        else:
            print(f"  OK (no fix needed): '{tab_name}'!P5 = {current_val!r}")
            skipped.append(tab_name)

    print(f"\nFixed {len(fixed)} tabs: {fixed}")
    print(f"Skipped {len(skipped)} tabs")

    # Verify
    print("\n--- Verifying P5 values after fix ---")
    time.sleep(3)
    all_ok = True
    for tab_name in team_tabs:
        try:
            ws = ss.worksheet(tab_name)
            val = get_value(ws, "P5")
            ok = val != "#N/A"
            icon = "✓" if ok else "✗"
            print(f"  {icon} '{tab_name}'!P5 = {val!r}")
            if not ok:
                all_ok = False
        except gspread.WorksheetNotFound:
            pass

    if all_ok:
        print("\n✓ All P5 cells fixed — no more #N/A errors!")
    else:
        print("\n✗ Some P5 cells still show #N/A — check above")

    # Final full error scan
    print("\n--- Full error scan ---")
    error_markers = {"#REF!", "#VALUE!", "#N/A", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!"}
    total = 0
    for ws in ss.worksheets():
        vals = ws.get_all_values()
        errs = [
            (r + 1, c + 1, v)
            for r, row in enumerate(vals)
            for c, v in enumerate(row)
            if v in error_markers
        ]
        if errs:
            total += len(errs)
            print(f"  '{ws.title}': {len(errs)} error(s)")
            for row, col, val in errs[:5]:
                n, col_ltr = col, ""
                while n > 0:
                    n, rem = divmod(n - 1, 26)
                    col_ltr = chr(65 + rem) + col_ltr
                print(f"    {col_ltr}{row}: {val}")

    if total == 0:
        print("  ✓ Zero formula errors across all tabs!")
    else:
        print(f"  {total} errors remain")


if __name__ == "__main__":
    main()
