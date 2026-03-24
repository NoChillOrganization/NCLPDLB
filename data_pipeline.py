"""
data_pipeline.py — Replay Pipeline Orchestrator (Phase 10, RPLY-01)

Scrapes Pokemon Showdown replays for all supported formats, parses them into
BattleRecord objects, extracts ML features, saves per-format .npy files, and
maintains a manifest.json dataset registry.

Usage:
    python data_pipeline.py --formats gen9ou gen9vgc2024regh --pages 20 --min-rating 1500
    python data_pipeline.py --formats all --pages 20 --min-rating 1500

CRITICAL: Do NOT import from src.config — Settings() raises ValidationError
without a .env file. All paths are computed from Path(__file__).parent.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths — all computed from this file's location (project root)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
DATA_DIR     = PROJECT_ROOT / "data"
REPLAYS_DIR  = DATA_DIR / "replays"
ML_DIR       = DATA_DIR / "ml"
VOCAB_DIR    = ML_DIR / "vocab"
SCRAPER_PATH = PROJECT_ROOT / "src" / "ml" / "replay_scraper.py"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("data_pipeline")

# ---------------------------------------------------------------------------
# Format constants
# ---------------------------------------------------------------------------

ALL_FORMATS = [
    # Smogon Gen 9 (9 formats)
    "gen9ou", "gen9ubers", "gen9uu", "gen9ru", "gen9nu",
    "gen9pu", "gen9lc", "gen9monotype", "gen9doublesou",
    # VGC Gen 9 Regulations (8 formats — Reg A through H)
    "gen9vgc2023regulationa", "gen9vgc2023regulationb",
    "gen9vgc2023regulationc", "gen9vgc2023regulationd",
    "gen9vgc2024regg", "gen9vgc2024regh",
    "gen9vgc2024reggregf", "gen9vgc2025regg",
    # Draft League (1 format — yields 0 replays; private battles not on public ladder)
    "draftleague",
]

PRIORITY_FORMATS = [
    "gen9ou",
    "gen9vgc2023regulationa", "gen9vgc2023regulationb",
    "gen9vgc2023regulationc", "gen9vgc2023regulationd",
    "gen9vgc2024regg", "gen9vgc2024regh",
    "gen9vgc2024reggregf", "gen9vgc2025regg",
]

SPARSE_WARN_THRESHOLD = 200  # Named constant — not a magic number

# ---------------------------------------------------------------------------
# Summary table format constants
# ---------------------------------------------------------------------------
_HEADER = (
    f"{'format':<30} | {'scraped':>7} | {'parsed':>7} | "
    f"{'X_team':>14} | {'X_state':>14}"
)
_SEP = "-" * len(_HEADER)


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def get_system_python() -> str:
    """Return the system Python executable path (not .venv).

    System Python is needed for replay_scraper.py which requires aiohttp.
    aiohttp is intentionally NOT installed in .venv (ML isolation).
    """
    candidates = [
        r"C:\Program Files\Python314\python.exe",  # Windows default (Phase 8 confirmed)
        r"C:\Python314\python.exe",
        "/usr/bin/python3",
        "/usr/local/bin/python3",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    found = shutil.which("python3") or shutil.which("python")
    if found:
        return found
    raise RuntimeError(
        "Cannot locate system Python with aiohttp. "
        "Expected at C:\\Program Files\\Python314\\python.exe or via shutil.which."
    )


def should_skip_format(fmt: str, ml_dir: Path, replays_dir: Path) -> bool:
    """Return True if format already has fresh .npy files matching current replay count.

    Skipping avoids redundant parse+extract when the replay set has not changed.
    Returns False (do not skip) when:
    - manifest.json does not exist
    - format has no manifest entry
    - any of the 4 .npy files is missing
    - replay count on disk differs from manifest entry
    """
    manifest_path = ml_dir / "manifest.json"
    if not manifest_path.exists():
        return False

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest.get(fmt)
    if not entry:
        return False

    fmt_ml_dir = ml_dir / fmt
    npy_files = ["X_team.npy", "y_team.npy", "X_state.npy", "y_state.npy"]
    if not all((fmt_ml_dir / f).exists() for f in npy_files):
        return False

    # Compare replay count on disk vs manifest
    replay_count = len(list((replays_dir / fmt).glob("*.json")))
    return replay_count == entry.get("replay_count", -1)


def scrape_format(fmt: str, pages: int, min_rating: int) -> int:
    """Run replay_scraper.py via system Python. Returns exit code.

    Uses subprocess so replay_scraper.py runs in system Python (which has aiohttp),
    not the .venv (which has numpy/sklearn but not aiohttp).
    """
    system_python = get_system_python()
    result = subprocess.run(
        [
            system_python, "-m", "src.ml.replay_scraper",
            "--format", fmt,
            "--pages", str(pages),
            "--min-rating", str(min_rating),
        ],
        cwd=PROJECT_ROOT,
    )
    return result.returncode


def update_manifest(
    manifest_path: Path,
    fmt: str,
    replay_count: int,
    records_parsed: int,
    x_team_shape: tuple,
    x_state_shape: tuple,
    min_rating: int,
) -> None:
    """Read/update/write manifest.json for the given format entry.

    Creates the manifest file if it does not exist.
    Preserves existing entries for other formats.
    """
    manifest: dict = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    manifest[fmt] = {
        "format": fmt,
        "replay_count": replay_count,
        "records_parsed": records_parsed,
        "x_team_shape": list(x_team_shape),
        "x_state_shape": list(x_state_shape),
        "min_rating": min_rating,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _format_result_row(
    fmt: str,
    scraped: int,
    parsed: int,
    x_team_shape: tuple,
    x_state_shape: tuple,
    sparse: bool,
) -> str:
    """Format one row of the summary table. Appends WARN suffix for sparse formats."""
    flag = " WARN" if sparse else ""
    return (
        f"{fmt:<30} | {scraped:>7} | {parsed:>7} | "
        f"{str(x_team_shape):>14} | {str(x_state_shape):>14}{flag}"
    )


def run_pipeline(formats: list[str], pages: int, min_rating: int) -> None:
    """Run the full replay pipeline for all specified formats.

    Execution order: PRIORITY_FORMATS first, then remaining formats.
    For each format:
      1. Check should_skip_format — skip if already up to date
      2. Scrape via system Python subprocess
      3. Warn if scraped count < SPARSE_WARN_THRESHOLD
      4. Parse + extract features using shared vocabulary (VOCAB_DIR)
      5. Save 4 .npy files per format
      6. Update manifest.json

    Prints a summary table at the end.
    """
    # Lazy imports — only needed when running the full pipeline.
    # Placed here (not at module level) so tests can import the constants/helpers
    # without triggering src.ml imports unnecessarily.
    import numpy as np
    from src.ml.replay_parser import parse_replay_dir
    from src.ml.feature_extractor import FeatureExtractor

    # Determine processing order: PRIORITY_FORMATS first, then the rest
    priority_set = set(PRIORITY_FORMATS)
    ordered = [f for f in PRIORITY_FORMATS if f in formats]
    ordered += [f for f in formats if f not in priority_set]

    # ── Pass 1: Build shared vocabulary from all formats ──────────────────
    log.info("Pass 1: Building shared vocabulary across %d formats ...", len(ordered))
    VOCAB_DIR.mkdir(parents=True, exist_ok=True)
    extractor = FeatureExtractor.load_or_create(VOCAB_DIR)

    for fmt in ordered:
        replay_dir = REPLAYS_DIR / fmt
        if not replay_dir.exists():
            continue
        records = parse_replay_dir(replay_dir)
        if records:
            extractor.build_vocab_from_records(records)

    extractor.save(VOCAB_DIR)
    log.info("Shared vocabulary built and saved to %s", VOCAB_DIR)

    # ── Pass 2: Per-format scrape + extract ───────────────────────────────
    extractor.freeze()
    log.info("Pass 2: Scraping and extracting features per format ...")

    manifest_path = ML_DIR / "manifest.json"
    rows: list[str] = []

    for fmt in ordered:
        log.info("--- Processing format: %s ---", fmt)

        # Incremental skip check
        if should_skip_format(fmt, ML_DIR, REPLAYS_DIR):
            log.info("Skipping %s (up to date)", fmt)
            continue

        # Step 1: Scrape
        log.info("Scraping %s (pages=%d, min_rating=%d) ...", fmt, pages, min_rating)
        scrape_format(fmt, pages, min_rating)

        # Count scraped files
        replay_dir = REPLAYS_DIR / fmt
        replay_dir.mkdir(parents=True, exist_ok=True)
        scraped = len(list(replay_dir.glob("*.json")))

        # Sparse format warning
        if scraped < SPARSE_WARN_THRESHOLD:
            if fmt == "draftleague":
                log.info(
                    "draftleague yielded 0 replays — private battles, "
                    "not on the Showdown public ladder"
                )
            else:
                log.warning(
                    "Format %s yielded only %d replays (< %d threshold) — sparse",
                    fmt,
                    scraped,
                    SPARSE_WARN_THRESHOLD,
                )

        # Step 2: Parse
        records = parse_replay_dir(replay_dir)
        records = [r for r in records if r.rating >= min_rating]
        parsed = len(records)
        log.info("%s: scraped=%d, parsed=%d (after min_rating=%d)", fmt, scraped, parsed, min_rating)

        # Step 3: Extract features
        if records:
            X_team, y_team = extractor.team_features(records)
            X_state, y_state = extractor.state_features(records)
        else:
            X_team = np.empty((0, 12), dtype=np.float32)
            y_team = np.empty((0,), dtype=np.float32)
            X_state = np.empty((0, 19), dtype=np.float32)
            y_state = np.empty((0,), dtype=np.float32)

        # Step 4: Save .npy files
        fmt_ml_dir = ML_DIR / fmt
        fmt_ml_dir.mkdir(parents=True, exist_ok=True)
        np.save(fmt_ml_dir / "X_team.npy", X_team)
        np.save(fmt_ml_dir / "y_team.npy", y_team)
        np.save(fmt_ml_dir / "X_state.npy", X_state)
        np.save(fmt_ml_dir / "y_state.npy", y_state)

        # Step 5: Update manifest
        update_manifest(
            manifest_path=manifest_path,
            fmt=fmt,
            replay_count=scraped,
            records_parsed=parsed,
            x_team_shape=X_team.shape,
            x_state_shape=X_state.shape,
            min_rating=min_rating,
        )

        sparse = scraped < SPARSE_WARN_THRESHOLD
        rows.append(_format_result_row(fmt, scraped, parsed, X_team.shape, X_state.shape, sparse))
        log.info("Saved .npy files to %s", fmt_ml_dir)

    # Print summary table
    print("\n" + _HEADER)
    print(_SEP)
    for row in rows:
        print(row)
    print(_SEP)
    log.info("Pipeline complete.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="data_pipeline",
        description="Scrape, parse, and extract ML features from Pokemon Showdown replays.",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["all"],
        metavar="FORMAT",
        help=(
            "Format IDs to process (e.g. gen9ou gen9vgc2024regh). "
            "Use 'all' to expand to all 18 formats. Default: all"
        ),
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=20,
        help="Number of replay pages to scrape per format (approx 50 replays/page). Default: 20",
    )
    parser.add_argument(
        "--min-rating",
        type=int,
        default=1500,
        dest="min_rating",
        help="Minimum rating filter. Default: 1500",
    )
    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    # Expand 'all' to full format list
    if "all" in args.formats:
        formats = ALL_FORMATS
    else:
        formats = args.formats

    run_pipeline(formats, args.pages, args.min_rating)
