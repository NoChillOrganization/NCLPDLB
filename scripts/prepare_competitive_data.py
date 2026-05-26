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
import sys
import urllib.request
from pathlib import Path

# Ensure Unicode output works on Windows CI runners (cp1252 codepage → UTF-8).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


_exports_env = os.getenv("COMPETITIVE_EXPORTS_DIR")
EXPORTS_DIR: Path | None = Path(_exports_env) if _exports_env else None
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

# Per-tier Smogon stats URLs.  Try most recent month first; fall back one month.
# 1760 is the highest available cut for most tiers; OU uses 1695 (no 1760 exists).
_STATS_MONTH_PRIMARY = "2026-04"
_STATS_MONTH_FALLBACK = "2026-03"

def _tier_url(tier: str, month: str, elo: int = 1500) -> str:
    return f"https://www.smogon.com/stats/{month}/gen9{tier}-{elo}.txt"

TIER_STATS_URLS: dict[str, list[str]] = {
    # OU: no 1760 file exists; 1695 is the highest available cut
    "ou": [
        _tier_url("ou", _STATS_MONTH_PRIMARY, 1695),
        _tier_url("ou", _STATS_MONTH_FALLBACK, 1695),
        _tier_url("ou", _STATS_MONTH_PRIMARY, 1500),
        _tier_url("ou", _STATS_MONTH_FALLBACK, 1500),
    ],
    # All other tiers: prefer 1760 for tier-accurate data (avoids OU-mon bleed at 1500)
    **{
        tier: [
            _tier_url(tier, _STATS_MONTH_PRIMARY, 1760),
            _tier_url(tier, _STATS_MONTH_FALLBACK, 1760),
            _tier_url(tier, _STATS_MONTH_PRIMARY, 1630),
            _tier_url(tier, _STATS_MONTH_FALLBACK, 1630),
            _tier_url(tier, _STATS_MONTH_PRIMARY),
            _tier_url(tier, _STATS_MONTH_FALLBACK),
        ]
        for tier in ("ubers", "uu", "ru", "nu", "pu", "zu", "lc", "bssregi")
    },
}

# Map Showdown format ID -> tier key (into TIER_STATS_URLS) or local CSV name
FORMAT_TIER_MAP: dict[str, str] = {
    "gen9ou":             "ou",
    "gen9ubers":          "ubers",
    "gen9uu":             "uu",
    "gen9ru":             "ru",
    "gen9nu":             "nu",
    "gen9pu":             "pu",
    "gen9zu":             "zu",
    "gen9lc":             "lc",
    "gen9nationaldex":    "ou",       # no separate file; OU is best proxy
    "gen9monotype":       "ou",
    "gen9anythinggoes":   "ubers",
    # Champions formats
    "gen9championsou":              "ou",
    "gen9championsbssregma":        "bssregi",
    "gen9championsvgc2026regma":    "vgc",
    "gen9championsvgc2026regmabo3": "vgc",
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

    urls = TIER_STATS_URLS.get(tier, [])
    if not urls:
        _tier_cache[tier] = []
        return []

    text: str | None = None
    for url in urls:
        try:
            print(f"  [FETCH] {tier} <- {url}")
            with urllib.request.urlopen(url, timeout=15) as resp:
                text = resp.read().decode("utf-8")
            break
        except Exception as exc:
            print(f"  [WARN]  {tier} {url} failed: {exc}")

    if text is None:
        print(f"  [WARN]  No stats available for tier '{tier}' - skipping", file=sys.stderr)
        _tier_cache[tier] = []
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
    """Copy export files from EXPORTS_DIR into DEST_DIR; return count present in DEST_DIR."""
    try:
        DEST_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"  [ERROR] Cannot create dest dir {DEST_DIR}: {exc}", file=sys.stderr)
        return 0

    if EXPORTS_DIR is None:
        present = sum(1 for f in SOURCE_FILES if (DEST_DIR / f).exists())
        print(f"  [SKIP] COMPETITIVE_EXPORTS_DIR not set - {present}/{len(SOURCE_FILES)} files already in {DEST_DIR}")
        return present

    import shutil

    copied = 0
    already = 0
    for fname in SOURCE_FILES:
        dest = DEST_DIR / fname
        if dest.exists():
            already += 1
            continue
        src = EXPORTS_DIR / fname
        if src.exists():
            shutil.copy2(src, dest)
            print(f"  [OK]  {fname}")
            copied += 1
        else:
            print(f"  [MISSING]  {fname}  (not in {EXPORTS_DIR})")

    if already:
        print(f"  [SKIP] {already} files already present in {DEST_DIR}")
    return copied + already


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

    # Sanity-check: warn if multiple non-alias formats share identical top-3.
    # (Indicates URL 404s or tier-cache collision — not a genuine data divergence.)
    top3_by_fmt = {
        fmt: tuple(e["pokemon"] for e in v.get("top10_usage", [])[:3])
        for fmt, v in config.items()
        if v.get("stats_tier") not in ("vgc",)
    }
    top3_seen: dict[tuple, list[str]] = {}
    for fmt, top3 in top3_by_fmt.items():
        top3_seen.setdefault(top3, []).append(fmt)
    for top3, fmts in top3_seen.items():
        # Only warn when genuinely different tiers share identical top-3
        tiers = {FORMAT_TIER_MAP.get(f) for f in fmts}
        if len(tiers) > 1 and len(fmts) > 2:
            print(
                f"  [WARN] {len(fmts)} formats share identical top-3 {list(top3)}: {fmts}\n"
                f"         Check that Smogon stats URLs resolve for each tier.",
                file=sys.stderr,
            )

    out = DEST_DIR / "format_meta.json"
    try:
        out.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"  [ERROR] Failed to write {out}: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"\n  -> format_meta.json written ({len(config)} formats)")


def main() -> None:
    src_label = str(EXPORTS_DIR) if EXPORTS_DIR else "(not set - using files already in dest)"
    print(f"[prepare_competitive_data] Source: {src_label}")
    print(f"[prepare_competitive_data] Dest  : {DEST_DIR}\n")

    copied = copy_source_files()
    print(f"\nCopied {copied}/{len(SOURCE_FILES)} files.\n")

    print("[prepare_competitive_data] Building format configs...")
    build_format_configs()
    print("[prepare_competitive_data] Done.\n")


if __name__ == "__main__":
    main()
