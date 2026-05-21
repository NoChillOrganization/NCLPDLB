"""
Repair the #REF! formula errors in the spreadsheet.

Fixes applied:
1. Data!BT2  — extend sum range $BH$2:$BH$353 → $BH$2:$BH  (kills SUMIF)
2. Data!BU2  — extend sum range $BI$2:$BI$353 → $BI$2:$BI  (deaths SUMIF)
   (BV2, BW2 cascade from BT/BU and will auto-fix once BT/BU are corrected)

3. Pool B equivalent columns (CG2/CH2) — same fix if present

Run: py -3 scripts/repair_formulas.py
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


def get_formula(ws: gspread.Worksheet, cell: str) -> str:
    result = ws.spreadsheet.values_get(
        f"'{ws.title}'!{cell}",
        params={"valueRenderOption": "FORMULA"},
    )
    vals = result.get("values", [[]])
    return vals[0][0] if vals and vals[0] else ""


def set_formula(ws: gspread.Worksheet, cell: str, formula: str) -> None:
    ws.update(cell, [[formula]], value_input_option="USER_ENTERED")
    print(f"  ✓ Updated {ws.title}!{cell}")


def check_value(ws: gspread.Worksheet, cell: str) -> str:
    result = ws.spreadsheet.values_get(
        f"'{ws.title}'!{cell}",
        params={"valueRenderOption": "FORMATTED_VALUE"},
    )
    vals = result.get("values", [[]])
    return vals[0][0] if vals and vals[0] else ""


def main() -> None:
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(SPREADSHEET_ID)
    data = ss.worksheet("Data")

    print("=== BEFORE: BT178 and BV178 (Chi-Yu's stats) ===")
    print(f"  BT178 = {check_value(data, 'BT178')}")
    print(f"  BV178 = {check_value(data, 'BV178')}")
    print(f"  BW178 = {check_value(data, 'BW178')}")

    # ── Fix 1: BT2 (kills) ───────────────────────────────────
    print("\n--- Fix 1: Data!BT2 (SUMIF kills sum range) ---")
    bt2_formula = get_formula(data, "BT2")
    print(f"  Current formula (first 200 chars): {bt2_formula[:200]}")

    if "$BH$2:$BH$353" in bt2_formula:
        bt2_fixed = bt2_formula.replace("$BH$2:$BH$353", "$BH$2:$BH")
        set_formula(data, "BT2", bt2_fixed)
    else:
        print("  WARNING: Expected pattern not found in BT2. Skipping.")
        print(f"  Full formula: {bt2_formula}")

    # ── Fix 2: BU2 (deaths) ──────────────────────────────────
    print("\n--- Fix 2: Data!BU2 (SUMIF deaths sum range) ---")
    bu2_formula = get_formula(data, "BU2")
    print(f"  Current formula (first 200 chars): {bu2_formula[:200]}")

    if "$BI$2:$BI$353" in bu2_formula:
        bu2_fixed = bu2_formula.replace("$BI$2:$BI$353", "$BI$2:$BI")
        set_formula(data, "BU2", bu2_fixed)
    else:
        print("  WARNING: Expected pattern not found in BU2. Skipping.")
        print(f"  Full formula: {bu2_formula}")

    # ── Check Pool B equivalent (CG2/CH2 or similar) ─────────
    print("\n--- Checking Pool B stat columns CG2, CH2 for same issue ---")
    for cell in ["CG2", "CH2"]:
        formula = get_formula(data, cell)
        if formula:
            print(f"  {cell}: {formula[:200]}")
            if "$BH$2:$BH$353" in formula or "$BI$2:$BI$353" in formula:
                fixed = formula.replace("$BH$2:$BH$353", "$BH$2:$BH").replace("$BI$2:$BI$353", "$BI$2:$BI")
                set_formula(data, cell, fixed)
        else:
            print(f"  {cell}: empty/not a formula cell")

    # ── Verify fix ────────────────────────────────────────────
    import time
    print("\n--- Waiting 3 seconds for sheets to recalculate... ---")
    time.sleep(3)

    print("\n=== AFTER: BT178 and BV178 (Chi-Yu's stats) ===")
    print(f"  BT178 = {check_value(data, 'BT178')}")
    print(f"  BV178 = {check_value(data, 'BV178')}")
    print(f"  BW178 = {check_value(data, 'BW178')}")

    print("\n=== AFTER: MVP Race J6 (Chi-Yu record) ===")
    mvp = ss.worksheet("MVP Race")
    print(f"  J6 = {check_value(mvp, 'J6')}")

    print("\n=== AFTER: Pokémon Stats I33 ===")
    pks = ss.worksheet("Pokémon Stats")
    print(f"  I33 = {check_value(pks, 'I33')}")
    print(f"  K33 = {check_value(pks, 'K33')}")
    print(f"  I55 = {check_value(pks, 'I55')}")
    print(f"  K55 = {check_value(pks, 'K55')}")

    print("\n=== AFTER: Hannah4Ever U22, W22 ===")
    hf = ss.worksheet("Hannah4Ever")
    print(f"  U22 = {check_value(hf, 'U22')}")
    print(f"  W22 = {check_value(hf, 'W22')}")


if __name__ == "__main__":
    main()
