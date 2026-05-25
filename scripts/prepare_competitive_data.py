"""
Seed competitive meta data into data/competitive/ for training consumption.

Run once on the self-hosted runner before training kicks off.  The script
reads the Showdown-export CSVs/JSON from ~/Documents/Showdown Exports/ (or
the path in COMPETITIVE_EXPORTS_DIR) and copies them into data/competitive/,
then emits a lightweight per-format JSON config so train_policy.py can log
usage context before each training run.

When local export files are absent, usage data for each Smogon tier is
fetched live from smogon.com/stats.

Usage:
    python scripts/prepare_competitive_data.py
    COMPETITIVE_EXPORTS_DIR=/some/other/path python scripts/prepare_competitive_data.py
"""
from __future__ import annotations

import csv
import json
import os
import re
import urllib.request
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

# Per-tier Smogon stats URLs (April 2026, 1630 Elo for OU, 1500 for others)
TIER_STATS_URLS: dict[str, str] = {
    "ou":    "https://www.smogon.com/stats/2026-04/gen9ou-1630.txt",
    "ubers": "https://www.smogon.com/stats/2026-04/gen9ubers-1500.txt",
    "uu":    "https://www.smogon.com/stats/2026-04/gen9uu-1500.txt",
    "ru":    "https://www.smogon.com/stats/2026-04/gen9ru-1500.txt",
    "nu":    "https://www.smogon.com/stats/2026-04/gen9nu-1500.txt",
    "pu":    "https://www.smogon.com/stats/2026-04/gen9pu-1500.txt",
    "lc":    "https://www.smogon.com/stats/2026-04/gen9lc-1500.txt",
}

# Map Showdown format ID → tier key (into TIER_STATS_URLS) or local CSV name
FORMAT_TIER_MAP: dict[str, str] = {
    "gen9ou":             "ou",
    "gen9ubers":          "ubers",
    "gen9uu":             "uu",
    "gen9ru":             "ru",
    "gen9nu":             "nu",
    "gen9pu":             "pu",
    "gen9zu":             "pu",       # no ZU stats file; closest is PU
    "gen9lc":             "lc",
    "gen9nationaldex":    "ou",       # no separate file; OU is best proxy
    "gen9monotype":       "ou",
    "gen9anythinggoes":   "ubers",
    # VGC formats: use local CSV when present, no live URL available
    "gen9doublesou":      "vgc",
    "gen9doublesubers":   "vgc",
    "gen9doublesuu":      "vgc",
    "gen9vgc2026regi":    "vgc",
    "gen9vgc2026regibo3": "vgc",
}

# Cache so each tier URL is only fetched once per run
_tier_cache: dict[str, list[dict]] = {}


def _fetch_smogon_stats(tier: str) -> list[dict]:
    """Fetch and parse a Smogon stats .txt file; return top-N rows."""
    if tier in _tier_cache:
        return _tier_cache[tier]

    url = TIER_STATS_URLS.get(tier)
    if not url:
        return []

    try:
        print(f"  [FETCH] {tier} <- {url}")
        with urllib.request.urlopen(url, timeout=15) as resp:
            text = resp.read().decode("utf-8")
    except Exception as exc:
        print(f"  [WARN]  Failed to fetch {tier} stats: {exc}")
        return []

    # Table rows look like:  | 1    | Great Tusk          |  25.12345%| ...
    rows: list[dict] = []
    for line in text.splitlines():
        m = re.match(
            r"\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*([\d.]+)%",
            line,
        )
        if m:
            rows.append({
                "rank":      m.group(1),
                "pokemon":   m.group(2).strip(),
                "usage_pct": m.group(3) + "%",
            })

    _tier_cache[tier] = rows
    return rows


def copy_source_files() -> int:
    """Copy raw export files; return count of files actually copied."""
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for fname in SOURCE_FILES:
        src = EXPORTS_DIR / fname
        if src.exists():
            import shutil
            shutil.copy2(src, DEST_DIR / fname)
            print(f"  [OK]  {fname}")
            copied += 1
        else:
            print(f"  [MISSING]  {fname}  (not found in {EXPORTS_DIR})")
    return copied


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _top10_from_smogon_rows(rows: list[dict]) -> list[dict]:
    return [{"pokemon": r["pokemon"], "usage_pct": r["usage_pct"]} for r in rows[:10]]


def _top10_from_vgc_csv() -> list[dict]:
    """Read VGC top-10 from local CSV if present."""
    path = DEST_DIR / "vgc_regulation_i_usage.csv"
    if not path.exists():
        return []
    rows = _read_csv(path)
    top10 = []
    for row in rows[:10]:
        entry: dict = {"pokemon": row.get("pokemon", "")}
        for key in ("usage_pct", "win_pct", "role"):
            if key in row:
                entry[key] = row[key]
        top10.append(entry)
    return top10


def build_format_configs() -> None:
    """Emit data/competitive/format_meta.json with per-format meta summaries."""
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    config: dict[str, dict] = {}

    for fmt, tier in FORMAT_TIER_MAP.items():
        if tier == "vgc":
            top10 = _top10_from_vgc_csv()
        else:
            rows = _fetch_smogon_stats(tier)
            top10 = _top10_from_smogon_rows(rows)

        if top10:
            config[fmt] = {"top10_usage": top10, "stats_tier": tier}

    # Merge archetype data from local CSVs when present
    for archetype_csv, scope in [
        ("top_team_archetypes.csv", "smogon"),
        ("vgc_team_archetypes.csv", "vgc"),
    ]:
        path = DEST_DIR / archetype_csv
        if not path.exists():
            continue
        for row in _read_csv(path):
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
        rows_data = _read_csv(path)
        if rows_data:
            col = next(iter(rows_data[0]))
            pokemon_list = [r[col] for r in rows_data]
            for vgc_fmt in ("gen9vgc2026regi", "gen9vgc2026regibo3"):
                if vgc_fmt in config:
                    config[vgc_fmt][key] = pokemon_list

    out = DEST_DIR / "format_meta.json"
    out.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"\n  -> format_meta.json written ({len(config)} formats)")


def main() -> None:
    print(f"[prepare_competitive_data] Source: {EXPORTS_DIR}")
    print(f"[prepare_competitive_data] Dest  : {DEST_DIR}\n")

    copied = copy_source_files()
    print(f"\nCopied {copied}/{len(SOURCE_FILES)} files.\n")

    print("[prepare_competitive_data] Building format configs...")
    build_format_configs()
    print("[prepare_competitive_data] Done.\n")


if __name__ == "__main__":
    main()
