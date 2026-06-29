"""
Seed competitive meta data into data/competitive/ for training consumption.

Run once on the self-hosted runner before training kicks off.  The script
reads the Showdown-export CSVs/JSON from ~/Documents/Showdown Exports/ (or
the path in COMPETITIVE_EXPORTS_DIR) and copies them into data/competitive/,
then emits a lightweight per-format JSON config so train_policy.py can log
usage context before each training run.

When local export files are absent, usage data for each Smogon tier is
fetched live from smogon.com/stats.

Optional live-URL flags (all non-fatal — fall back to bundled CSVs on error):
  --smogon-stats-index URL    smogon.com/stats/ for month discovery
  --smogon-api-base URL       pkmn.github.io/smogon/data/stats mirror
  --champions-rules-url URL   victoryroad.pro Champions Reg M-A rules
  --champions-online-events-url URL   limitlesstcg.com completed events
  --champions-major-events-url URL    labmaus.net major events
  --champions-usage-url URL   pokekipe.com Champions VGC usage page
  --champions-usage-api-docs URL      pokekipe.com/openapi.json spec
  --champions-tournament-data-url URL pikalytics.com Champions tournament data (Reg M-B)
  --champions-regmb-ranked-data-url URL pikalytics.com Reg M-B ranked ladder data

Usage:
    python scripts/prepare_competitive_data.py
    python scripts/prepare_competitive_data.py \\
        --smogon-stats-index https://www.smogon.com/stats/ \\
        --smogon-api-base https://pkmn.github.io/smogon/data/stats \\
        --champions-usage-url https://pokekipe.com/champions/vgc2026regma \\
        --champions-usage-api-docs https://pokekipe.com/openapi.json \\
        --champions-tournament-data-url https://www.pikalytics.com/pokedex/championstournaments \\
        --champions-regmb-ranked-data-url https://www.pikalytics.com/pokedex/battledataregmbs3
    COMPETITIVE_EXPORTS_DIR=/some/other/path python scripts/prepare_competitive_data.py
"""

from __future__ import annotations

import argparse
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

# httpx for live URL fetchers; graceful fallback if unavailable.
try:
    import httpx as _httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


_exports_env = os.getenv("COMPETITIVE_EXPORTS_DIR")
EXPORTS_DIR: Path | None = Path(_exports_env) if _exports_env else None
DEST_DIR = Path("data/competitive")

# All files we want available during training.
# SV VGC Regulation I files (vgc_reg_i_banned.csv, vgc_reg_i_restricted.csv,
# vgc_regulation_i_usage.csv, vgc_sv_regulations.csv, vgc_team_archetypes.csv)
# are intentionally excluded — SV VGC is phased out; Champions VGC uses Reg M-A.
SOURCE_FILES = [
    "pokemon_competitive_data.json",
    "FormatID-Label-Type.csv",
    "smogon_format_pokemon_champions.csv",
    "smogon_sv_formats.csv",
    "smogon_sv_ou_bans.csv",
    "smogon_ou_usage.csv",
    "smogon_ou_usage_april2026.csv",
    "smogon_april2026_tier_shifts.csv",
    "smogon_tier_ou.csv",
    "smogon_tier_ubers.csv",
    "smogon_tier_uu.csv",
    "smogon_tier_ru.csv",
    "smogon_tier_nu.csv",
    "smogon_tier_pu.csv",
    "smogon_tier_zu.csv",
    "smogon_tier_lc.csv",
    "top_team_archetypes.csv",
    "vgc_formats.csv",
    "limitless_vgc_usage.csv",
    "champions_reg_ma_usage.csv",
    "champions_reg_ma_archetypes.csv",
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

# Map Showdown format ID → tier key (into TIER_STATS_URLS) or special tier name.
# "champions" tier reads champions_reg_ma_usage.csv (Reg M-A non-restricted pool).
# Smogon Doubles formats are intentionally absent: no Smogon-DOU usage export
# exists, and meta is optional/non-fatal — training proceeds without it.
# SV VGC (gen9vgc2026regi/bo3) removed — format phased out.
FORMAT_TIER_MAP: dict[str, str] = {
    "gen9ou": "ou",
    "gen9ubers": "ubers",
    "gen9uu": "uu",
    "gen9ru": "ru",
    "gen9nu": "nu",
    "gen9pu": "pu",
    "gen9zu": "zu",
    "gen9lc": "lc",
    "gen9nationaldex": "ou",  # no separate file; OU is best proxy
    "gen9monotype": "ou",
    "gen9anythinggoes": "ubers",
    # Champions formats
    "gen9championsou": "ou",
    "gen9championsbssregma": "bssregi",
    "gen9championsbssregmb": "bssregi",
    "gen9championsvgc2026regma": "champions",
    "gen9championsvgc2026regmabo3": "champions",
    "gen9championsvgc2026regmb": "championsmb",
    "gen9championsvgc2026regmbbo3": "championsmb",
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
            req = urllib.request.Request(
                url, headers={"User-Agent": "NCLPDLB/1.0 (competitive data seeder)"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                text = resp.read().decode("utf-8")
            break
        except Exception as exc:
            print(f"  [WARN]  {tier} {url} failed: {exc}")

    if text is None:
        print(
            f"  [WARN]  No stats available for tier '{tier}' - skipping",
            file=sys.stderr,
        )
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
            rows.append(
                {
                    "rank": m.group(1),
                    "pokemon": m.group(2).strip(),
                    "usage_pct": m.group(3) + "%",
                }
            )

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
        print(
            f"  [SKIP] COMPETITIVE_EXPORTS_DIR not set - {present}/{len(SOURCE_FILES)} files already in {DEST_DIR}"
        )
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


def _top10_from_csv(filename: str) -> list[dict]:
    """Read top-10 from any local usage CSV.  Extracts pokemon + all available stats columns."""
    path = DEST_DIR / filename
    if not path.exists():
        return []
    rows = _read_csv(path)
    top10 = []
    for row in rows[:10]:
        entry: dict = {"pokemon": row.get("pokemon", "")}
        for key in ("usage_pct", "win_pct", "role", "tier", "avg_rating"):
            if key in row and row[key]:
                entry[key] = row[key]
        top10.append(entry)
    return top10


def _load_champions_archetypes(
    filename: str = "champions_reg_ma_archetypes.csv",
) -> list[dict]:
    """Load top archetypes from a Champions archetypes CSV.

    Columns: rank, core, size, usage_pct, win_pct, avg_rating
    Returns up to 15 entries, each as a dict of non-empty fields.
    """
    path = DEST_DIR / filename
    if not path.exists():
        return []
    rows = _read_csv(path)
    result = []
    for row in rows[:15]:
        entry = {k: v for k, v in row.items() if v}
        if entry:
            result.append(entry)
    return result


# ── Live-URL fetchers ─────────────────────────────────────────────────────────
# All functions are non-fatal: any exception → warn + keep bundled CSV.


def fetch_smogon_usage(api_base: str, stats_index: str) -> None:
    """Refresh smogon_tier_*.csv files from the pkmn.github.io Smogon mirror.

    Uses stats_index (smogon.com/stats/) for month discovery, then pulls per-tier
    JSON from api_base (pkmn.github.io/smogon/data/stats).  Writes top-100 rows per
    tier to smogon_tier_{tier}.csv with columns: pokemon, usage_pct.
    """
    if not _HTTPX_AVAILABLE:
        print("  [WARN] httpx not available — skipping live Smogon fetch")
        return
    try:
        # Discover latest available month from the Smogon stats index page.
        resp = _httpx.get(stats_index, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        months = sorted(re.findall(r'href="(\d{4}-\d{2})/"', resp.text))
        if not months:
            print(
                f"  [WARN] No month directories found at {stats_index} — skipping Smogon fetch"
            )
            return
        latest_month = months[-1]
        print(f"  [SMOGON] Latest month: {latest_month}")

        tiers_to_fetch = ["ou", "ubers", "uu", "ru", "nu", "pu", "zu", "lc"]
        for tier in tiers_to_fetch:
            try:
                # pkmn.github.io/smogon format: .../YYYY-MM/gen9{tier}-{elo}.json
                # Try 1760 cutoff first (tier-accurate); fall back to 0 (all ratings).
                fetched = False
                for elo_suffix in ("-1760", "-1630", "-0", ""):
                    url = f"{api_base.rstrip('/')}/{latest_month}/gen9{tier}{elo_suffix}.json"
                    try:
                        r = _httpx.get(url, timeout=15, follow_redirects=True)
                        if r.is_success:
                            fetched = True
                            break
                    except Exception:
                        continue
                if not fetched:
                    print(
                        f"  [WARN] Smogon {tier}: no JSON found at {api_base}/{latest_month}/"
                    )
                    continue

                data = r.json()
                # pkmn.github.io format: {"info": {...}, "data": {"PokemonName": {"usage": 0.25, ...}}}
                pokemon_data = data.get("data", {})
                if not pokemon_data:
                    print(f"  [WARN] Smogon {tier}: empty data in response")
                    continue

                rows_out = sorted(
                    [
                        {
                            "pokemon": name,
                            "usage_pct": f"{stats.get('usage', 0) * 100:.4f}%",
                        }
                        for name, stats in pokemon_data.items()
                    ],
                    key=lambda x: float(x["usage_pct"].rstrip("%")),
                    reverse=True,
                )
                csv_path = DEST_DIR / f"smogon_tier_{tier}.csv"
                with csv_path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=["pokemon", "usage_pct"])
                    writer.writeheader()
                    writer.writerows(rows_out[:100])
                print(f"  [SMOGON] {tier}: {len(rows_out)} pokemon → {csv_path.name}")
            except Exception as exc:
                print(f"  [WARN] Smogon {tier} fetch failed: {exc}")
    except Exception as exc:
        print(f"  [WARN] Smogon usage fetch failed: {exc}")


def fetch_champions_usage(usage_url: str, api_docs: str) -> None:
    """Refresh champions_reg_ma_usage.csv and champions_reg_ma_archetypes.csv.

    Uses the pokekipe.com OpenAPI spec (api_docs) to discover the usage endpoint,
    then fetches structured data.  Columns written:
      usage:      rank, tier, pokemon, usage_pct, win_pct, avg_rating
      archetypes: rank, core, size, usage_pct, win_pct, avg_rating
    Falls back silently if the API schema doesn't match expectations.
    """
    if not _HTTPX_AVAILABLE:
        print("  [WARN] httpx not available — skipping live Champions usage fetch")
        return
    try:
        # Discover the usage API endpoint from the OpenAPI spec.
        usage_endpoint: str | None = None
        archetypes_endpoint: str | None = None
        api_base_url = api_docs.rsplit("/openapi.json", 1)[0].rstrip("/")
        try:
            r = _httpx.get(api_docs, timeout=15, follow_redirects=True)
            r.raise_for_status()
            openapi = r.json()
            paths = openapi.get("paths", {})
            for path in paths:
                pl = path.lower()
                if "champion" in pl and "archetype" in pl:
                    archetypes_endpoint = archetypes_endpoint or path
                elif "champion" in pl and "usage" in pl:
                    usage_endpoint = usage_endpoint or path
                elif "vgc2026regma" in pl and "archetype" in pl:
                    archetypes_endpoint = archetypes_endpoint or path
                elif "vgc2026regma" in pl:
                    usage_endpoint = usage_endpoint or path
        except Exception as exc:
            print(f"  [WARN] Champions OpenAPI discovery failed: {exc}")

        # Fetch usage data.
        usage_data: list | None = None
        if usage_endpoint:
            try:
                r = _httpx.get(
                    f"{api_base_url}{usage_endpoint}", timeout=20, follow_redirects=True
                )
                r.raise_for_status()
                body = r.json()
                usage_data = (
                    body
                    if isinstance(body, list)
                    else body.get("data") or body.get("results")
                )
            except Exception as exc:
                print(f"  [WARN] Champions usage API call failed: {exc}")

        if usage_data and isinstance(usage_data, list):
            rows_out = []
            for i, item in enumerate(usage_data, 1):
                if not isinstance(item, dict):
                    continue
                pokemon = item.get("pokemon") or item.get("name") or item.get("mon", "")
                if not pokemon:
                    continue
                rows_out.append(
                    {
                        "rank": item.get("rank", i),
                        "tier": item.get("tier", ""),
                        "pokemon": pokemon,
                        "usage_pct": item.get("usage_pct") or item.get("usage", ""),
                        "win_pct": item.get("win_pct") or item.get("winrate", ""),
                        "avg_rating": item.get("avg_rating") or item.get("rating", ""),
                    }
                )
            if rows_out:
                csv_path = DEST_DIR / "champions_reg_ma_usage.csv"
                with csv_path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=[
                            "rank",
                            "tier",
                            "pokemon",
                            "usage_pct",
                            "win_pct",
                            "avg_rating",
                        ],
                    )
                    writer.writeheader()
                    writer.writerows(rows_out)
                print(
                    f"  [CHAMPIONS] Usage: {len(rows_out)} pokemon → champions_reg_ma_usage.csv"
                )
        else:
            print(
                "  [INFO] Champions usage: API data unavailable — keeping bundled CSV"
            )

        # Fetch archetypes data.
        archetypes_data: list | None = None
        if archetypes_endpoint:
            try:
                r = _httpx.get(
                    f"{api_base_url}{archetypes_endpoint}",
                    timeout=20,
                    follow_redirects=True,
                )
                r.raise_for_status()
                body = r.json()
                archetypes_data = (
                    body
                    if isinstance(body, list)
                    else body.get("data") or body.get("results")
                )
            except Exception as exc:
                print(f"  [WARN] Champions archetypes API call failed: {exc}")

        if archetypes_data and isinstance(archetypes_data, list):
            rows_out = []
            for i, item in enumerate(archetypes_data, 1):
                if not isinstance(item, dict):
                    continue
                core = item.get("core") or item.get("team") or item.get("archetype", "")
                if not core:
                    continue
                rows_out.append(
                    {
                        "rank": item.get("rank", i),
                        "core": core,
                        "size": item.get("size", ""),
                        "usage_pct": item.get("usage_pct") or item.get("usage", ""),
                        "win_pct": item.get("win_pct") or item.get("winrate", ""),
                        "avg_rating": item.get("avg_rating") or item.get("rating", ""),
                    }
                )
            if rows_out:
                csv_path = DEST_DIR / "champions_reg_ma_archetypes.csv"
                with csv_path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=[
                            "rank",
                            "core",
                            "size",
                            "usage_pct",
                            "win_pct",
                            "avg_rating",
                        ],
                    )
                    writer.writeheader()
                    writer.writerows(rows_out)
                print(
                    f"  [CHAMPIONS] Archetypes: {len(rows_out)} → champions_reg_ma_archetypes.csv"
                )
    except Exception as exc:
        print(f"  [WARN] Champions usage fetch failed: {exc}")


def fetch_champions_regmb(ranked_url: str, tournament_url: str) -> None:
    """Refresh champions_reg_mb_usage.csv and champions_reg_mb_archetypes.csv.

    Sources from pikalytics.com Reg M-B ranked/tournament HTML pages (no JSON
    API like pokekipe). Selectors are best-effort — pikalytics' markup shape
    isn't known ahead of a live fetch, so this does a generic regex scan for
    pokemon-name/usage-percent pairs and falls back silently (keep bundled
    CSV, log INFO) if nothing recognizable is found.
    """
    if not _HTTPX_AVAILABLE:
        print("  [WARN] httpx not available — skipping live Champions Reg M-B fetch")
        return
    try:
        usage_rows: list[dict] = []
        if ranked_url:
            try:
                r = _httpx.get(ranked_url, timeout=20, follow_redirects=True)
                r.raise_for_status()
                html = r.text
                # Best-effort: pokemon name + adjacent usage percentage.
                for i, m in enumerate(
                    re.finditer(
                        r'data-pokemon="([A-Za-z0-9\-]+)"[^>]*>.*?([\d.]+)%', html
                    ),
                    1,
                ):
                    usage_rows.append(
                        {
                            "rank": i,
                            "tier": "regmb",
                            "pokemon": m.group(1),
                            "usage_pct": m.group(2),
                            "win_pct": "",
                            "avg_rating": "",
                        }
                    )
            except Exception as exc:
                print(f"  [WARN] Champions Reg M-B ranked fetch failed: {exc}")

        if usage_rows:
            csv_path = DEST_DIR / "champions_reg_mb_usage.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "rank",
                        "tier",
                        "pokemon",
                        "usage_pct",
                        "win_pct",
                        "avg_rating",
                    ],
                )
                writer.writeheader()
                writer.writerows(usage_rows)
            print(
                f"  [CHAMPIONS] Reg M-B usage: {len(usage_rows)} pokemon → champions_reg_mb_usage.csv"
            )
        else:
            print(
                "  [INFO] Champions Reg M-B usage: no parseable rows — keeping bundled CSV"
            )

        archetype_rows: list[dict] = []
        if tournament_url:
            try:
                r = _httpx.get(tournament_url, timeout=20, follow_redirects=True)
                r.raise_for_status()
                html = r.text
                for i, m in enumerate(
                    re.finditer(r'data-core="([^"]+)"[^>]*>.*?([\d.]+)%', html), 1
                ):
                    archetype_rows.append(
                        {
                            "rank": i,
                            "core": m.group(1),
                            "size": "",
                            "usage_pct": m.group(2),
                            "win_pct": "",
                            "avg_rating": "",
                        }
                    )
            except Exception as exc:
                print(f"  [WARN] Champions Reg M-B tournament fetch failed: {exc}")

        if archetype_rows:
            csv_path = DEST_DIR / "champions_reg_mb_archetypes.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "rank",
                        "core",
                        "size",
                        "usage_pct",
                        "win_pct",
                        "avg_rating",
                    ],
                )
                writer.writeheader()
                writer.writerows(archetype_rows)
            print(
                f"  [CHAMPIONS] Reg M-B archetypes: {len(archetype_rows)} → champions_reg_mb_archetypes.csv"
            )
        else:
            print(
                "  [INFO] Champions Reg M-B archetypes: no parseable rows — keeping bundled CSV"
            )
    except Exception as exc:
        print(f"  [WARN] Champions Reg M-B fetch failed: {exc}")


def fetch_champions_rules(rules_url: str) -> None:
    """Fetch Champions Reg M-A legality rules from victoryroad.pro.  Non-fatal; logs only."""
    if not _HTTPX_AVAILABLE:
        print("  [WARN] httpx not available — skipping Champions rules fetch")
        return
    try:
        r = _httpx.get(rules_url, timeout=15, follow_redirects=True)
        r.raise_for_status()
        # Extract regulation name mentions for corroboration logging.
        regs_found = re.findall(
            r"Reg(?:ulation)?\s*[A-Z][-\s]?[A-Z]?", r.text, re.IGNORECASE
        )
        reg_set = sorted({re.sub(r"\s+", " ", x.strip()) for x in regs_found})
        print(
            f"  [CHAMPIONS] Rules page fetched ({len(r.text)} chars); regulations found: {reg_set or '(none parsed)'}"
        )
        # Warn if Regulation I is mentioned — would indicate stale rules page.
        if any("reg i" in x.lower() or "regulation i" in x.lower() for x in reg_set):
            print(
                "  [WARN] Champions rules page mentions Regulation I — verify page is current Reg M-A",
                file=sys.stderr,
            )
    except Exception as exc:
        print(f"  [WARN] Champions rules fetch failed: {exc}")


def fetch_events(online_url: str, major_url: str) -> None:
    """Fetch Champions event corroboration data.  Non-fatal; writes optional champions_events.csv."""
    if not _HTTPX_AVAILABLE:
        print("  [WARN] httpx not available — skipping events fetch")
        return

    events: list[dict] = []

    if online_url:
        try:
            r = _httpx.get(online_url, timeout=20, follow_redirects=True)
            r.raise_for_status()
            # Rough count of tournament rows from limitlesstcg.com table HTML.
            count = len(re.findall(r"<tr\b", r.text, re.IGNORECASE))
            print(f"  [EVENTS] Online events page fetched — ~{max(0, count - 1)} rows")
            events.append(
                {"source": "limitlesstcg", "url": online_url, "approx_rows": count}
            )
        except Exception as exc:
            print(f"  [WARN] Online events fetch failed: {exc}")

    if major_url:
        try:
            r = _httpx.get(major_url, timeout=20, follow_redirects=True)
            r.raise_for_status()
            count = len(re.findall(r"<tr\b", r.text, re.IGNORECASE))
            print(f"  [EVENTS] Major events page fetched — ~{max(0, count - 1)} rows")
            events.append({"source": "labmaus", "url": major_url, "approx_rows": count})
        except Exception as exc:
            print(f"  [WARN] Major events fetch failed: {exc}")

    if events:
        csv_path = DEST_DIR / "champions_events.csv"
        try:
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["source", "url", "approx_rows"])
                writer.writeheader()
                writer.writerows(events)
            print(f"  [EVENTS] champions_events.csv written ({len(events)} sources)")
        except OSError as exc:
            print(f"  [WARN] Could not write champions_events.csv: {exc}")


# ── Core pipeline ─────────────────────────────────────────────────────────────


def build_format_configs() -> None:
    """Emit data/competitive/format_meta.json with per-format meta summaries."""
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    config: dict[str, dict] = {}

    for fmt, tier in FORMAT_TIER_MAP.items():
        if tier == "champions":
            # Champions VGC Reg M-A — read from local CSV (Garchomp/Basculegion pool,
            # NOT Calyrex/Koraidon/Miraidon which appeared in the old Reg I file).
            top10 = _top10_from_csv("champions_reg_ma_usage.csv")
        elif tier == "championsmb":
            top10 = _top10_from_csv("champions_reg_mb_usage.csv")
        else:
            rows = _fetch_smogon_stats(tier)
            top10 = _top10_from_smogon_rows(rows)

        if top10:
            config[fmt] = {"top10_usage": top10, "stats_tier": tier}

    # Merge archetype data from local CSVs when present.

    # Smogon OU archetypes (top_team_archetypes.csv — format column uses "smogon ou")
    path = DEST_DIR / "top_team_archetypes.csv"
    if path.exists():
        for row in _read_csv(path):
            fmt_key = row.get("format", "").lower().replace(" ", "")
            if "smogon ou" in fmt_key or fmt_key == "smogon ou":
                if "gen9ou" in config:
                    config["gen9ou"].setdefault("archetypes", []).append(
                        {k: v for k, v in row.items() if v}
                    )

    # Champions VGC archetypes (champions_reg_ma_archetypes.csv — core column)
    champ_archetypes = _load_champions_archetypes("champions_reg_ma_archetypes.csv")
    if champ_archetypes:
        for champ_fmt in ("gen9championsvgc2026regma", "gen9championsvgc2026regmabo3"):
            if champ_fmt in config:
                config[champ_fmt]["archetypes"] = champ_archetypes

    # Champions VGC Reg M-B archetypes (champions_reg_mb_archetypes.csv)
    champ_mb_archetypes = _load_champions_archetypes("champions_reg_mb_archetypes.csv")
    if champ_mb_archetypes:
        for champ_fmt in ("gen9championsvgc2026regmb", "gen9championsvgc2026regmbbo3"):
            if champ_fmt in config:
                config[champ_fmt]["archetypes"] = champ_mb_archetypes

    # Sanity-check: warn if multiple non-alias formats share identical top-3.
    # (Indicates URL 404s or tier-cache collision — not a genuine data divergence.)
    top3_by_fmt = {
        fmt: tuple(e["pokemon"] for e in v.get("top10_usage", [])[:3])
        for fmt, v in config.items()
        if v.get("stats_tier") not in ("champions",)
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
    parser = argparse.ArgumentParser(
        description="Seed competitive meta data into data/competitive/ for training consumption.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # All flags optional — absent means use bundled CSVs unchanged (offline parity).
    parser.add_argument(
        "--smogon-stats-index",
        default="",
        metavar="URL",
        help="Smogon stats index URL for month discovery (e.g. https://www.smogon.com/stats/)",
    )
    parser.add_argument(
        "--smogon-api-base",
        default="",
        metavar="URL",
        help="pkmn.github.io Smogon stats mirror base URL",
    )
    parser.add_argument(
        "--champions-rules-url",
        default="",
        metavar="URL",
        help="Champions Reg M-A rules URL (victoryroad.pro)",
    )
    parser.add_argument(
        "--champions-online-events-url",
        default="",
        metavar="URL",
        help="Online events URL (e.g. limitlesstcg.com/tournaments/completed)",
    )
    parser.add_argument(
        "--champions-major-events-url",
        default="",
        metavar="URL",
        help="Major events URL (e.g. labmaus.net)",
    )
    parser.add_argument(
        "--champions-usage-url",
        default="",
        metavar="URL",
        help="Champions VGC usage stats URL (pokekipe.com)",
    )
    parser.add_argument(
        "--champions-usage-api-docs",
        default="",
        metavar="URL",
        help="pokekipe.com OpenAPI spec URL for endpoint discovery",
    )
    parser.add_argument(
        "--champions-tournament-data-url",
        default="",
        metavar="URL",
        help="pikalytics.com Champions tournament data URL (Reg M-B archetypes)",
    )
    parser.add_argument(
        "--champions-regmb-ranked-data-url",
        default="",
        metavar="URL",
        help="pikalytics.com Reg M-B ranked ladder data URL (Reg M-B usage)",
    )
    args = parser.parse_args()

    src_label = (
        str(EXPORTS_DIR) if EXPORTS_DIR else "(not set - using files already in dest)"
    )
    print(f"[prepare_competitive_data] Source: {src_label}")
    print(f"[prepare_competitive_data] Dest  : {DEST_DIR}\n")

    copied = copy_source_files()
    print(f"\nCopied {copied}/{len(SOURCE_FILES)} files.\n")

    # ── Live fetch phase — run before build_format_configs() so refreshed CSVs ──
    # ── are consumed immediately.  Every fetcher is non-fatal.               ──

    if args.smogon_stats_index or args.smogon_api_base:
        print("[prepare_competitive_data] Fetching Smogon usage (live)...")
        fetch_smogon_usage(
            api_base=args.smogon_api_base or "https://pkmn.github.io/smogon/data/stats",
            stats_index=args.smogon_stats_index or "https://www.smogon.com/stats/",
        )

    if args.champions_usage_url or args.champions_usage_api_docs:
        print("[prepare_competitive_data] Fetching Champions usage (live)...")
        fetch_champions_usage(
            usage_url=args.champions_usage_url
            or "https://pokekipe.com/champions/vgc2026regma",
            api_docs=args.champions_usage_api_docs
            or "https://pokekipe.com/openapi.json",
        )

    if args.champions_tournament_data_url or args.champions_regmb_ranked_data_url:
        print("[prepare_competitive_data] Fetching Champions Reg M-B (live)...")
        fetch_champions_regmb(
            ranked_url=args.champions_regmb_ranked_data_url,
            tournament_url=args.champions_tournament_data_url,
        )

    if args.champions_rules_url:
        print("[prepare_competitive_data] Fetching Champions rules (live)...")
        fetch_champions_rules(args.champions_rules_url)

    if args.champions_online_events_url or args.champions_major_events_url:
        print("[prepare_competitive_data] Fetching Champions events (live)...")
        fetch_events(
            online_url=args.champions_online_events_url,
            major_url=args.champions_major_events_url,
        )

    print("[prepare_competitive_data] Building format configs...")
    build_format_configs()
    print("[prepare_competitive_data] Done.\n")


if __name__ == "__main__":
    main()
