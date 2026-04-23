"""
Seed competitive meta data into data/competitive/ for training consumption.

Run once on the self-hosted runner before training kicks off.  The script
reads the Showdown-export CSVs/JSON from ~/Documents/Showdown Exports/ (or
the path in COMPETITIVE_EXPORTS_DIR) and copies them into data/competitive/,
then emits a lightweight per-format YAML config so train_policy.py can log
usage context before each training run.

Usage:
    python scripts/prepare_competitive_data.py
    COMPETITIVE_EXPORTS_DIR=/some/other/path python scripts/prepare_competitive_data.py
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path


EXPORTS_DIR = Path(
    os.getenv("COMPETITIVE_EXPORTS_DIR",
              Path.home() / "Documents" / "Showdown Exports")
)
DEST_DIR = Path("data/competitive")

# All files we want available during training
SOURCE_FILES = [
    "pokemon_competitive_data.json",
    "smogon_ou_usage_april2026.csv",
    "smogon_ou_usage.csv",
    "smogon_sv_formats.csv",
    "smogon_sv_ou_bans.csv",
    "top_team_archetypes.csv",
    "vgc_formats.csv",
    "vgc_sv_regulations.csv",
    "vgc_reg_i_banned.csv",
    "vgc_reg_i_restricted.csv",
    "vgc_regulation_i_usage.csv",
    "vgc_team_archetypes.csv",
    "limitless_vgc_usage.csv",
]

# Map Showdown format ID → usage CSV (for per-format context logs)
FORMAT_USAGE_MAP: dict[str, str] = {
    "gen9ou":              "smogon_ou_usage_april2026.csv",
    "gen9ubers":           "smogon_ou_usage_april2026.csv",
    "gen9uu":              "smogon_ou_usage_april2026.csv",
    "gen9ru":              "smogon_ou_usage_april2026.csv",
    "gen9nu":              "smogon_ou_usage_april2026.csv",
    "gen9pu":              "smogon_ou_usage_april2026.csv",
    "gen9zu":              "smogon_ou_usage_april2026.csv",
    "gen9lc":              "smogon_ou_usage_april2026.csv",
    "gen9nationaldex":     "smogon_ou_usage_april2026.csv",
    "gen9monotype":        "smogon_ou_usage_april2026.csv",
    "gen9anythinggoes":    "smogon_ou_usage_april2026.csv",
    "gen9doublesou":       "vgc_regulation_i_usage.csv",
    "gen9doublesubers":    "vgc_regulation_i_usage.csv",
    "gen9doublesuu":       "vgc_regulation_i_usage.csv",
    "gen9vgc2026regi":     "vgc_regulation_i_usage.csv",
    "gen9vgc2026regibo3":  "vgc_regulation_i_usage.csv",
    "gen9vgc2026regf":     "vgc_regulation_i_usage.csv",
    "gen9vgc2026regfbo3":  "vgc_regulation_i_usage.csv",
}


def copy_source_files() -> int:
    """Copy raw export files; return count of files actually copied."""
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for fname in SOURCE_FILES:
        src = EXPORTS_DIR / fname
        if src.exists():
            import shutil
            shutil.copy2(src, DEST_DIR / fname)
            print(f"  ✓  {fname}")
            copied += 1
        else:
            print(f"  ✗  {fname}  (not found in {EXPORTS_DIR})")
    return copied


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_format_configs() -> None:
    """Emit data/competitive/format_meta.json with per-format meta summaries."""
    config: dict[str, dict] = {}

    for fmt, csv_name in FORMAT_USAGE_MAP.items():
        csv_path = DEST_DIR / csv_name
        if not csv_path.exists():
            continue

        rows = _read_csv(csv_path)

        # Smogon usage CSV has: rank,pokemon,usage_pct,tier
        # VGC usage CSV has:    pokemon,tier_label,usage_pct,win_pct,role
        top10 = []
        for row in rows[:10]:
            entry: dict = {"pokemon": row.get("pokemon", "")}
            if "usage_pct" in row:
                entry["usage_pct"] = row["usage_pct"]
            if "win_pct" in row:
                entry["win_pct"] = row["win_pct"]
            if "role" in row:
                entry["role"] = row["role"]
            if "tier" in row:
                entry["tier"] = row["tier"]
            top10.append(entry)

        config[fmt] = {"top10_usage": top10}

    # Merge archetype data
    for archetype_csv, scope in [
        ("top_team_archetypes.csv", "smogon"),
        ("vgc_team_archetypes.csv", "vgc"),
    ]:
        path = DEST_DIR / archetype_csv
        if not path.exists():
            continue
        for row in _read_csv(path):
            # Smogon: format,archetype,core_pokemon,win_condition
            # VGC:    archetype,restricted,support,style,key_moves,notes
            fmt_key = row.get("format", "").lower().replace(" ", "")
            target: str | None = None
            if "smogon ou" in fmt_key or fmt_key == "smogon ou":
                target = "gen9ou"
            elif "vgc reg i" in fmt_key:
                target = "gen9vgc2026regi"
            if target and target in config:
                config[target].setdefault("archetypes", []).append(
                    {k: v for k, v in row.items() if v}
                )

    # Add VGC ban / restricted lists
    for list_csv, key in [
        ("vgc_reg_i_banned.csv", "banned_mythicals"),
        ("vgc_reg_i_restricted.csv", "restricted_pokemon"),
    ]:
        path = DEST_DIR / list_csv
        if not path.exists():
            continue
        col = next(iter(_read_csv(path)[0])) if _read_csv(path) else None
        if col:
            pokemon_list = [r[col] for r in _read_csv(path)]
            for fmt in ("gen9vgc2026regi", "gen9vgc2026regibo3",
                        "gen9vgc2026regf", "gen9vgc2026regfbo3"):
                if fmt in config:
                    config[fmt][key] = pokemon_list

    out = DEST_DIR / "format_meta.json"
    out.write_text(json.dumps(config, indent=2))
    print(f"\n  → format_meta.json written ({len(config)} formats)")


def main() -> None:
    print(f"[prepare_competitive_data] Source: {EXPORTS_DIR}")
    print(f"[prepare_competitive_data] Dest  : {DEST_DIR}\n")

    copied = copy_source_files()
    print(f"\nCopied {copied}/{len(SOURCE_FILES)} files.")

    if copied > 0:
        build_format_configs()
        print("[prepare_competitive_data] Done.\n")
    else:
        print(
            "[prepare_competitive_data] No source files found — "
            "set COMPETITIVE_EXPORTS_DIR to the correct path.\n"
        )


if __name__ == "__main__":
    main()
