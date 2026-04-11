"""
Sequential training runner for all SPAR_FORMATS.

Trains a PPO policy for each configured format, one at a time.
Skips any format that already has a final_model.zip.
Formats that require custom teams use RotatingTeambuilder via --team-format.
Doubles formats use BattleDoubleEnv automatically (detected in train_policy.py).

Format → Training format mapping
──────────────────────────────────
  gen9randombattle        → gen9randombattle        (direct, no teams)
  gen9monorandom          → gen9monorandom          (direct, no teams)
  gen9randomdoublesbattle → gen9randomdoublesbattle (direct, no teams, doubles)
  gen7randombattle        → gen7randombattle        (direct, no teams)
  gen6randombattle        → gen6randombattle        (direct, no teams)
  gen9ou                  → gen9ou                  (direct, RotatingTeambuilder)
  gen9ubers               → gen9ubers               (direct, RotatingTeambuilder)
  gen9uu                  → gen9uu                  (direct, RotatingTeambuilder)
  gen9ru                  → gen9ru                  (direct, RotatingTeambuilder)
  gen9nu                  → gen9nu                  (direct, RotatingTeambuilder)
  gen9pu                  → gen9pu                  (direct, RotatingTeambuilder)
  gen9zu                  → gen9zu                  (direct, RotatingTeambuilder)
  gen9lc                  → gen9lc                  (direct, RotatingTeambuilder)
  gen9monotype            → gen9monotype            (direct, RotatingTeambuilder)
  gen9nationaldex         → gen9nationaldex         (direct, RotatingTeambuilder)
  gen9anythinggoes        → gen9anythinggoes        (direct, RotatingTeambuilder)
  gen9doublesou           → gen9doublesou           (direct, RotatingTeambuilder, doubles)
  gen9doublesubers        → gen9doublesubers        (direct, RotatingTeambuilder, doubles)
  gen9doublesuu           → gen9doublesuu           (direct, RotatingTeambuilder, doubles)
  gen9doublesnu           → gen9doublesnu           (direct, RotatingTeambuilder, doubles)
  gen9vgc2025regg         → gen9vgc2025regg         (direct, RotatingTeambuilder, doubles)
  gen9vgc2025regh         → gen9vgc2025regh         (direct, RotatingTeambuilder, doubles)
  gen9vgc2025regi         → gen9vgc2025regi         (direct, RotatingTeambuilder, doubles)
  gen9vgc2025reggbo3      → gen9vgc2025reggbo3      (direct, RotatingTeambuilder, doubles)
  gen9vgc2025reghbo3      → gen9vgc2025reghbo3      (direct, RotatingTeambuilder, doubles)
  gen9vgc2025regibo3      → gen9vgc2025regibo3      (direct, RotatingTeambuilder, doubles)
  gen9vgc2026regf         → gen9vgc2026regf         (direct, RotatingTeambuilder, doubles)
  gen9vgc2026regi         → gen9vgc2026regi         (direct, RotatingTeambuilder, doubles)
  gen9vgc2026regfbo3      → gen9vgc2026regfbo3      (direct, RotatingTeambuilder, doubles)
  gen9vgc2026regibo3      → gen9vgc2026regibo3      (direct, RotatingTeambuilder, doubles)

Usage
─────
  python -m src.ml.train_all
  python -m src.ml.train_all --timesteps 1000000 --swap-every 100000
  python -m src.ml.train_all --formats gen9randombattle gen9monotype
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from src.ml.showdown_modes import VALID_MODES, MODE_LOCALHOST

log = logging.getLogger(__name__)

# ── Format → (training format, team_format) mapping ──────────────────────────
# Maps each SPAR_FORMAT to:
#   train_fmt  : actual Showdown format string passed to train_policy.py
#   team_fmt   : key into FORMAT_TEAMS for RotatingTeambuilder (None = no teams)
#
# None for train_fmt means SKIP entirely.
TRAINING_MAP: dict[str, tuple[str | None, str | None]] = {
    # Random Battle (no teams needed)
    "gen9randombattle"       : ("gen9randombattle",       None),
    "gen9monorandom"         : ("gen9monorandom",         None),
    "gen9randomdoublesbattle": ("gen9randomdoublesbattle", None),
    "gen7randombattle"       : ("gen7randombattle",       None),
    "gen6randombattle"       : ("gen6randombattle",       None),
    # Smogon Singles
    "gen9ou"                 : ("gen9ou",                 "gen9ou"),
    "gen9ubers"              : ("gen9ubers",              "gen9ubers"),
    "gen9uu"                 : ("gen9uu",                 "gen9uu"),
    "gen9ru"                 : ("gen9ru",                 "gen9ru"),
    "gen9nu"                 : ("gen9nu",                 "gen9nu"),
    "gen9pu"                 : ("gen9pu",                 "gen9pu"),
    "gen9zu"                 : ("gen9zu",                 "gen9zu"),
    "gen9lc"                 : ("gen9lc",                 "gen9lc"),
    "gen9monotype"           : ("gen9monotype",           "gen9monotype"),
    "gen9nationaldex"        : ("gen9nationaldex",        "gen9nationaldex"),
    "gen9anythinggoes"       : ("gen9anythinggoes",       "gen9anythinggoes"),
    # Smogon Doubles
    "gen9doublesou"          : ("gen9doublesou",          "gen9doublesou"),
    "gen9doublesubers"       : ("gen9doublesubers",       "gen9doublesubers"),
    "gen9doublesuu"          : ("gen9doublesuu",          "gen9doublesuu"),
    "gen9doublesnu"          : ("gen9doublesnu",          "gen9doublesnu"),
    # VGC 2025
    "gen9vgc2025regg"        : ("gen9vgc2025regg",        "gen9vgc2025regg"),
    "gen9vgc2025regh"        : ("gen9vgc2025regh",        "gen9vgc2025regh"),
    "gen9vgc2025regi"        : ("gen9vgc2025regi",        "gen9vgc2025regi"),
    "gen9vgc2025reggbo3"     : ("gen9vgc2025reggbo3",     "gen9vgc2025regg"),
    "gen9vgc2025reghbo3"     : ("gen9vgc2025reghbo3",     "gen9vgc2025regh"),
    "gen9vgc2025regibo3"     : ("gen9vgc2025regibo3",     "gen9vgc2025regi"),
    # VGC 2026
    "gen9vgc2026regf"        : ("gen9vgc2026regf",        "gen9vgc2026regf"),
    "gen9vgc2026regi"        : ("gen9vgc2026regi",        "gen9vgc2026regi"),
    "gen9vgc2026regfbo3"     : ("gen9vgc2026regfbo3",     "gen9vgc2026regf"),
    "gen9vgc2026regibo3"     : ("gen9vgc2026regibo3",     "gen9vgc2026regi"),
}

DEFAULT_TIMESTEPS   = 500_000
DEFAULT_SWAP_EVERY  = 50_000
DEFAULT_SAVE_DIR    = "data/ml/policy"
DEFAULT_RESULTS_DIR = "src/ml/models/results"


def _model_done(spar_fmt: str, results_dir: Path) -> bool:
    """Return True if a dated final model exists for this format in results_dir."""
    return any(results_dir.glob(f"{spar_fmt}_*.zip"))


def _resume_checkpoint(spar_fmt: str, save_dir: Path) -> Path | None:
    """Return latest.zip path if an in-progress checkpoint exists, else None."""
    p = save_dir / spar_fmt / "latest.zip"
    return p if p.exists() else None


def train_format(  # pragma: no cover
    spar_fmt: str,
    train_fmt: str,
    team_fmt: str | None,
    total_timesteps: int,
    swap_every: int,
    save_dir: Path,
    results_dir: Path | None = None,
    server: str = MODE_LOCALHOST,
) -> bool:
    """
    Train a policy for `spar_fmt` using `train_fmt` as the actual battle format.

    Each format is trained in a fresh subprocess so torch/poke-env state from one
    run doesn't bleed into the next (avoids torch._dynamo circular import errors).

    If `team_fmt` is provided, passes --team-format to train_policy.py so it uses
    a RotatingTeambuilder with the appropriate pre-built teams.

    Auto-resumes from latest.zip if an in-progress checkpoint exists.

    Returns True on success, False on failure.
    """
    import subprocess

    resume_path = _resume_checkpoint(spar_fmt, save_dir)
    log.info(f"[train_all] {spar_fmt}: training directly on {train_fmt}"
             + (f" with teams from {team_fmt}" if team_fmt else "")
             + (f" [RESUMING from {resume_path.name}]" if resume_path else ""))

    # ── Spawn fresh subprocess for each training run ────────────────
    project_root = Path(__file__).parents[2]
    _results_dir = results_dir if results_dir is not None else Path(DEFAULT_RESULTS_DIR)
    cmd = [
        sys.executable, "-m", "src.ml.train_policy",
        "--format",      train_fmt,
        "--timesteps",   str(total_timesteps),
        "--swap-every",  str(swap_every),
        "--save-dir",    str(save_dir),
        "--results-dir", str(_results_dir),
    ]
    if team_fmt:
        cmd += ["--team-format", team_fmt]
    if resume_path:
        cmd += ["--resume", str(resume_path)]
    if server != MODE_LOCALHOST:
        cmd += ["--server", server]

    log.info(f"[train_all] running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    ok = result.returncode == 0

    if result.stdout:
        for line in result.stdout.splitlines():
            log.info(f"[{spar_fmt}] {line}")
    if result.stderr:
        for line in result.stderr.splitlines():
            (log.info if ok else log.error)(f"[{spar_fmt}] {line}")

    if not ok:
        log.error(
            f"[train_all] {spar_fmt}: subprocess exited with code {result.returncode}. "
            f"Check output above for the root cause."
        )

    return ok


def run(  # pragma: no cover
    formats: list[str],
    total_timesteps: int,
    swap_every: int,
    save_dir: Path,
    results_dir: Path | None = None,
    force: bool = False,
    server: str = MODE_LOCALHOST,
) -> None:
    _results_dir = results_dir if results_dir is not None else Path(DEFAULT_RESULTS_DIR)
    _results_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}

    for spar_fmt in formats:
        entry = TRAINING_MAP.get(spar_fmt)

        # ── Skip cases ─────────────────────────────────────────────
        if entry is None:
            log.warning(f"[train_all] {spar_fmt}: SKIPPED (not in TRAINING_MAP)")
            results[spar_fmt] = "skipped"
            continue

        train_fmt, team_fmt = entry

        if train_fmt is None:
            log.warning(f"[train_all] {spar_fmt}: SKIPPED (no training format defined)")
            results[spar_fmt] = "skipped"
            continue

        if not force and _model_done(spar_fmt, _results_dir):
            log.info(f"[train_all] {spar_fmt}: already trained, skipping")
            results[spar_fmt] = "already_done"
            continue

        # ── Train ──────────────────────────────────────────────────
        log.info("############################################################")
        log.info(f"  Training: {spar_fmt}")
        if team_fmt:
            log.info(f"  (teams: {team_fmt})")
        log.info("############################################################")

        t0 = time.time()
        ok = train_format(
            spar_fmt=spar_fmt,
            train_fmt=train_fmt,
            team_fmt=team_fmt,
            total_timesteps=total_timesteps,
            swap_every=swap_every,
            save_dir=save_dir,
            results_dir=_results_dir,
            server=server,
        )
        elapsed = time.time() - t0
        results[spar_fmt] = "done" if ok else "failed"
        log.info(f"\n[train_all] {spar_fmt}: {'OK' if ok else 'FAILED'} ({elapsed/60:.1f} min)")

    # ── Summary ────────────────────────────────────────────────────
    log.info("============================================================")
    log.info("  Training Summary")
    log.info("============================================================")
    for fmt, status in results.items():
        icon = {"done": "OK", "already_done": "--", "skipped": "~~", "failed": "XX"}.get(status, "??")
        log.info(f"  {icon}  {fmt:<25} {status}")
    log.info("")


def _parse_args() -> argparse.Namespace:  # pragma: no cover
    ap = argparse.ArgumentParser(
        description="Train PPO policies for all SPAR_FORMATS sequentially"
    )
    ap.add_argument(
        "--formats", "-f",
        nargs="+",
        default=[fmt for fmt, entry in TRAINING_MAP.items() if entry[0] is not None],
        help="Formats to train (default: all non-skipped)",
    )
    ap.add_argument(
        "--timesteps", "-t",
        type=int,
        default=DEFAULT_TIMESTEPS,
        help=f"Timesteps per format (default: {DEFAULT_TIMESTEPS:,})",
    )
    ap.add_argument(
        "--swap-every",
        type=int,
        default=DEFAULT_SWAP_EVERY,
        help=f"Self-play swap interval (default: {DEFAULT_SWAP_EVERY:,})",
    )
    ap.add_argument(
        "--save-dir",
        default=DEFAULT_SAVE_DIR,
        help=f"Root checkpoint directory (default: {DEFAULT_SAVE_DIR})",
    )
    ap.add_argument(
        "--results-dir",
        default=DEFAULT_RESULTS_DIR,
        help=f"Directory for final dated models (default: {DEFAULT_RESULTS_DIR})",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Re-train even if a dated model already exists in results-dir",
    )
    ap.add_argument(
        "--server",
        default=MODE_SHOWDOWN,
        choices=[MODE_SHOWDOWN],
        help="Showdown connection mode: showdown (wss://sim3.psim.us — requires 2 accounts)",
    )
    return ap.parse_args()


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    args = _parse_args()
    run(
        formats=args.formats,
        total_timesteps=args.timesteps,
        swap_every=args.swap_every,
        save_dir=Path(args.save_dir),
        results_dir=Path(args.results_dir),
        force=args.force,
        server=args.server,
    )
