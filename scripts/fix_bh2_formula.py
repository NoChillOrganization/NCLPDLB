"""
Fix the literal #REF! embedded in Data!BH2 (and BG2, BI2) formula.

Root cause:
  Data!BH2 is a massive ARRAYFORMULA that stacks kill-count ranges from
  Match Stats using semicolons.  One entry was accidentally replaced with
  a bare #REF!  literal, which propagates to BH1442 and then to BT178
  (Chi-Yu's kill total), cascading to the MVP Race and Pokémon Stats tabs.

Fix:
  Replace  ;#REF!;  with  ;'Match Stats'!J9:J14;
  (Coach #2 Week 1 kill counts — the segment that got corrupted.)

Run: py -3 scripts/fix_bh2_formula.py
"""
# ruff: noqa: E401, E402, F841
import sys
import io
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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


def get_value(ws: gspread.Worksheet, cell: str) -> str:
    result = ws.spreadsheet.values_get(
        f"'{ws.title}'!{cell}",
        params={"valueRenderOption": "FORMATTED_VALUE"},
    )
    vals = result.get("values", [[]])
    return vals[0][0] if vals and vals[0] else ""


def set_formula(ws: gspread.Worksheet, cell: str, formula: str) -> None:
    ws.update([[formula]], cell, value_input_option="USER_ENTERED")
    print(f"  ✓ Updated {ws.title}!{cell}")


def show_context(formula: str, marker: str = "#REF!", window: int = 80) -> None:
    idx = formula.find(marker)
    if idx == -1:
        print(f"  '{marker}' NOT found in formula.")
        return
    start = max(0, idx - window)
    end = min(len(formula), idx + len(marker) + window)
    snippet = formula[start:end]
    arrow = " " * (idx - start) + "^" * len(marker)
    print(f"  ...{snippet}...")
    print(f"     {arrow}")


def main() -> None:
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(SPREADSHEET_ID)
    data = ss.worksheet("Data")

    # ── BEFORE snapshots ──────────────────────────────────────────────────────
    print("=== BEFORE snapshots ===")
    print(f"  Data!BH1442 = {get_value(data, 'BH1442')}")
    print(f"  Data!BT178  = {get_value(data, 'BT178')}")
    print(f"  Data!BV178  = {get_value(data, 'BV178')}")

    # ── Inspect BG2, BH2, BI2 ────────────────────────────────────────────────
    print("\n=== Inspecting BG2, BH2, BI2 for #REF! ===")
    for col in ["BG", "BH", "BI"]:
        cell = f"{col}2"
        formula = get_formula(data, cell)
        ref_count = formula.count("#REF!")
        print(f"\n  {cell}: length={len(formula)}, #REF! occurrences={ref_count}")
        if ref_count:
            show_context(formula, "#REF!")

    # ── Fix BH2 ───────────────────────────────────────────────────────────────
    print("\n=== Fixing Data!BH2 ===")
    bh2 = get_formula(data, "BH2")
    if "#REF!" not in bh2:
        print("  No #REF! found — BH2 is already clean.")
    else:
        replacement = "'Match Stats'!J9:J14"
        bh2_fixed = bh2.replace("#REF!", replacement)
        remaining = bh2_fixed.count("#REF!")
        print(f"  Replacing #REF! with {replacement}  (remaining after replace: {remaining})")
        set_formula(data, "BH2", bh2_fixed)

    # ── Fix BG2 if needed ────────────────────────────────────────────────────
    print("\n=== Fixing Data!BG2 ===")
    bg2 = get_formula(data, "BG2")
    if "#REF!" not in bg2:
        print("  No #REF! found — BG2 is clean.")
    else:
        # BG is the Pokémon name column; the same positional slot should map to
        # the Coach #2 Week 1 Pokémon-name range in Match Stats.
        replacement_bg = "'Match Stats'!E9:E14"
        bg2_fixed = bg2.replace("#REF!", replacement_bg)
        print(f"  Replacing #REF! with {replacement_bg}")
        set_formula(data, "BG2", bg2_fixed)

    # ── Fix BI2 if needed ────────────────────────────────────────────────────
    print("\n=== Fixing Data!BI2 ===")
    bi2 = get_formula(data, "BI2")
    if "#REF!" not in bi2:
        print("  No #REF! found — BI2 is clean.")
    else:
        # BI is the deaths column; Coach #2 Week 1 deaths range.
        replacement_bi = "'Match Stats'!K9:K14"
        bi2_fixed = bi2.replace("#REF!", replacement_bi)
        print(f"  Replacing #REF! with {replacement_bi}")
        set_formula(data, "BI2", bi2_fixed)

    # ── Wait for recalculation ────────────────────────────────────────────────
    print("\n  Waiting 5 seconds for Google Sheets to recalculate...")
    time.sleep(5)

    # ── AFTER snapshots ───────────────────────────────────────────────────────
    print("\n=== AFTER snapshots ===")
    print(f"  Data!BH1442 = {get_value(data, 'BH1442')}")
    print(f"  Data!BT178  = {get_value(data, 'BT178')}")
    print(f"  Data!BV178  = {get_value(data, 'BV178')}")
    print(f"  Data!BW178  = {get_value(data, 'BW178')}")

    mvp  = ss.worksheet("MVP Race")
    pks  = ss.worksheet("Pokémon Stats")
    hf   = ss.worksheet("Hannah4Ever")

    print(f"\n  MVP Race!J6     = {get_value(mvp, 'J6')}")
    print(f"  Pokémon Stats!I33 = {get_value(pks, 'I33')}")
    print(f"  Pokémon Stats!K33 = {get_value(pks, 'K33')}")
    print(f"  Hannah4Ever!U22 = {get_value(hf, 'U22')}")
    print(f"  Hannah4Ever!W22 = {get_value(hf, 'W22')}")

    # ── Quick full error scan ─────────────────────────────────────────────────
    print("\n=== Quick error scan (all tabs) ===")
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
        # Ignore #N/A in team pages (P5) — expected during playoffs
        real_errs = [
            e for e in errs
            if not (e[2] == "#N/A" and e[1] == 16)  # col 16 = P
        ]
        if real_errs:
            total += len(real_errs)
            print(f"  '{ws.title}': {len(real_errs)} error(s)")
            for row, col, val in real_errs[:5]:
                col_letter = ""
                n = col
                while n > 0:
                    n, rem = divmod(n - 1, 26)
                    col_letter = chr(65 + rem) + col_letter
                print(f"    {col_letter}{row}: {val}")

    if total == 0:
        print("  ✓ No unexpected formula errors found!")
    else:
        print(f"\n  {total} unexpected error(s) remain — review above.")


if __name__ == "__main__":
    main()
