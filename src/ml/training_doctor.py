"""
Training Doctor — preflight checks, error diagnosis, and auto-fix for the ML training pipeline.

Used by the Discord /admin-train and /admin-train-all commands to:
  1. Run preflight checks before starting a training subprocess.
  2. Parse subprocess output to identify known failure modes.
  3. Apply automatic fixes where possible (corrupt checkpoints, missing deps).
  4. Return a structured result so the bot can report status and retry.

Error types
───────────
  SHOWDOWN_OFFLINE    — local Showdown server unreachable (cannot auto-fix)
  CORRUPT_CHECKPOINT  — .zip model file is corrupt → delete and retry fresh
  MISSING_DEP         — pip-installable package missing → pip install
  WRONG_PYTHON        — system Python used instead of venv (no module named 'src')
  NO_TEAMS            — no teams found for format (soft warning only)
  UNKNOWN             — unrecognised failure

Usage
─────
  from src.ml.training_doctor import preflight_check, diagnose_output, apply_fix

  issues = preflight_check("gen9ou", save_dir=Path("data/ml/policy"))
  errors = diagnose_output(proc_output)
  for err in errors:
      if err["fixable"]:
          ok, msg = apply_fix(err, fmt="gen9ou", save_dir=Path("data/ml/policy"))
"""
from __future__ import annotations

import logging
import re
import socket
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

SHOWDOWN_HOST = "127.0.0.1"
SHOWDOWN_PORT = 8000

# ── Error pattern registry ────────────────────────────────────────────────────

# Each entry: (error_type, regex_pattern, description, fixable)
_PATTERNS: list[tuple[str, str, str, bool]] = [
    (
        "SHOWDOWN_OFFLINE",
        r"Cannot reach local Showdown server",
        "Local Showdown server is not running on ws://localhost:8000",
        False,
    ),
    (
        "SHOWDOWN_OFFLINE",
        r"Connection refused.*8000|8000.*Connection refused|OSError.*8000",
        "Local Showdown server connection refused on port 8000",
        False,
    ),
    (
        "CORRUPT_CHECKPOINT",
        r"(BadZipFile|zipfile\.BadZipFile|zipfile error|Bad magic number for file header"
        r"|Not a zip file|File is not a zip file)",
        "Checkpoint .zip file is corrupt — will delete and retry from scratch",
        True,
    ),
    (
        "CORRUPT_CHECKPOINT",
        r"(KeyError.*model\.zip|Error loading model|truncated zip|zipfile\.BadZipFile)",
        "Model .zip could not be loaded — will delete and retry from scratch",
        True,
    ),
    (
        "MISSING_DEP",
        r"No module named '?(numpy|torch|stable_baselines3|poke_env|gymnasium|tensorboard"
        r"|shimmy|cloudpickle)'?",
        "Missing Python dependency",
        True,
    ),
    (
        "MISSING_DEP",
        r"ImportError: cannot import name .* from '?(numpy|torch|stable_baselines3|poke_env)'?",
        "Package version too old — needs upgrade",
        True,
    ),
    (
        "WRONG_PYTHON",
        r"No module named 'src'",
        "Wrong Python interpreter — bot is not using the project venv",
        False,
    ),
    (
        "NO_TEAMS",
        r"No teams found for .* training without custom teams",
        "No pre-built teams for this format (soft warning — training continues without them)",
        False,
    ),
    (
        "OOM",
        r"CUDA out of memory|RuntimeError: CUDA|OutOfMemoryError",
        "GPU out of memory — training ran out of VRAM",
        False,
    ),
    (
        "SHAPE_MISMATCH",
        r"mat1 and mat2 shapes cannot be multiplied|Expected input with shape|size mismatch",
        "Tensor shape mismatch — model architecture may have changed; delete checkpoint and retry",
        True,
    ),
]

# Package name → pip install target
_DEP_TO_PACKAGE: dict[str, str] = {
    "numpy":             "numpy",
    "torch":             "torch",
    "stable_baselines3": "stable-baselines3>=2.2.0",
    "poke_env":          "poke-env>=0.8.1",
    "gymnasium":         "gymnasium",
    "tensorboard":       "tensorboard>=2.16.0",
    "shimmy":            "shimmy",
    "cloudpickle":       "cloudpickle",
}


# ── Preflight checks ──────────────────────────────────────────────────────────

def preflight_check(
    fmt: str,
    save_dir: Path,
    python_exe: str | None = None,
    server_mode: str = "localhost",
) -> list[dict]:
    """
    Run pre-training checks and return a list of issue dicts.

    Each dict has keys:
      type        : str  (error type constant)
      description : str
      fixable     : bool

    Returns an empty list if everything looks good.
    """
    issues: list[dict] = []
    exe = python_exe or sys.executable

    # 1. Showdown server reachable? (localhost mode only)
    if server_mode == "localhost":
        try:
            with socket.create_connection((SHOWDOWN_HOST, SHOWDOWN_PORT), timeout=3):
                pass
        except OSError:
            issues.append({
                "type":        "SHOWDOWN_OFFLINE",
                "description": (
                    f"Local Showdown server not reachable at {SHOWDOWN_HOST}:{SHOWDOWN_PORT}.\n"
                    "Start it with:\n"
                    "  cd pokemon-showdown && node pokemon-showdown start --no-security"
                ),
                "fixable": False,
            })

    # 2. Corrupt checkpoints?
    fmt_dir = save_dir / fmt
    if fmt_dir.exists():
        for zip_path in fmt_dir.glob("*.zip"):
            if _is_corrupt_zip(zip_path):
                issues.append({
                    "type":        "CORRUPT_CHECKPOINT",
                    "description": f"Corrupt checkpoint detected: {zip_path.name}",
                    "fixable":     True,
                    "path":        str(zip_path),
                })

    # 3. Core ML deps importable?
    for mod, pkg in [("numpy", "numpy"), ("stable_baselines3", "stable-baselines3>=2.2.0")]:
        ok = _can_import(exe, mod)
        if not ok:
            issues.append({
                "type":        "MISSING_DEP",
                "description": f"Missing dependency: {mod} (install: pip install {pkg})",
                "fixable":     True,
                "module":      mod,
                "package":     pkg,
            })

    # 4. Save directory writable?
    try:
        fmt_dir.mkdir(parents=True, exist_ok=True)
        test_file = fmt_dir / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
    except Exception as exc:
        issues.append({
            "type":        "WRITE_ERROR",
            "description": f"Cannot write to save directory {fmt_dir}: {exc}",
            "fixable":     False,
        })

    return issues


# ── Output diagnosis ──────────────────────────────────────────────────────────

def diagnose_output(output: str) -> list[dict]:
    """
    Scan subprocess output for known error patterns.

    Returns a list of matching error dicts (same shape as preflight_check).
    Deduplicates by error type (first match wins per type).
    """
    found: dict[str, dict] = {}  # keyed by type to deduplicate

    for err_type, pattern, description, fixable in _PATTERNS:
        if err_type in found:
            continue  # already matched this type
        m = re.search(pattern, output, re.IGNORECASE)
        if m:
            entry: dict = {
                "type":        err_type,
                "description": description,
                "fixable":     fixable,
            }
            # Extract module name for MISSING_DEP
            if err_type == "MISSING_DEP":
                mod_match = re.search(
                    r"No module named '?([a-zA-Z0-9_]+)'?", output, re.IGNORECASE
                )
                if mod_match:
                    mod = mod_match.group(1)
                    entry["module"]  = mod
                    entry["package"] = _DEP_TO_PACKAGE.get(mod, mod)
                    entry["description"] = f"Missing Python dependency: {mod}"
            found[err_type] = entry

    return list(found.values())


# ── Auto-fix ──────────────────────────────────────────────────────────────────

def apply_fix(
    error: dict,
    fmt: str,
    save_dir: Path,
    python_exe: str | None = None,
) -> tuple[bool, str]:
    """
    Attempt to auto-fix the given error.

    Returns (success: bool, message: str).
    """
    exe = python_exe or sys.executable
    err_type = error.get("type", "UNKNOWN")

    if err_type == "CORRUPT_CHECKPOINT":
        return _fix_corrupt_checkpoints(fmt, save_dir)

    if err_type == "SHAPE_MISMATCH":
        # Same fix as corrupt checkpoint — wipe and start fresh
        return _fix_corrupt_checkpoints(fmt, save_dir)

    if err_type == "MISSING_DEP":
        pkg = error.get("package")
        mod = error.get("module", "unknown")
        if not pkg:
            return False, f"Cannot auto-fix: unknown package for module '{mod}'"
        return _fix_install_dep(exe, pkg)

    return False, f"Error type '{err_type}' cannot be auto-fixed."


def apply_all_fixes(
    errors: list[dict],
    fmt: str,
    save_dir: Path,
    python_exe: str | None = None,
) -> list[tuple[dict, bool, str]]:
    """
    Attempt to fix all fixable errors.

    Returns list of (error, success, message).
    """
    results = []
    for err in errors:
        if not err.get("fixable", False):
            results.append((err, False, "Not auto-fixable"))
            continue
        ok, msg = apply_fix(err, fmt, save_dir, python_exe)
        results.append((err, ok, msg))
    return results


# ── Progress parsing ──────────────────────────────────────────────────────────

def parse_timestep_progress(line: str) -> int | None:
    """
    Extract total_timesteps from a stable-baselines3 PPO progress line.

    SB3 verbose output looks like:
      |    total_timesteps      | 4096         |
    Returns the int if found, else None.
    """
    m = re.search(r"total_timesteps\s*\|\s*(\d+)", line)
    if m:
        return int(m.group(1))
    return None


def make_progress_bar(current: int, total: int, width: int = 20) -> str:
    """
    Build a Unicode text progress bar.

    Example: [████████░░░░░░░░░░░░] 40%
    """
    pct = min(current / total, 1.0) if total > 0 else 0.0
    filled = round(pct * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct*100:.1f}%"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _is_corrupt_zip(path: Path) -> bool:
    """Return True if the zip file is empty, truncated, or otherwise corrupt."""
    import zipfile
    if path.stat().st_size == 0:
        return True
    try:
        with zipfile.ZipFile(path, "r") as zf:
            bad = zf.testzip()
            return bad is not None
    except Exception:
        return True


def _can_import(python_exe: str, module: str) -> bool:
    """Return True if `python_exe -c 'import <module>'` succeeds."""
    try:
        result = subprocess.run(
            [python_exe, "-c", f"import {module}"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _fix_corrupt_checkpoints(fmt: str, save_dir: Path) -> tuple[bool, str]:
    """Delete all .zip checkpoints for the format so training restarts fresh."""
    fmt_dir = save_dir / fmt
    deleted: list[str] = []
    if fmt_dir.exists():
        for zip_path in fmt_dir.glob("*.zip"):
            try:
                zip_path.unlink()
                deleted.append(zip_path.name)
            except Exception as exc:
                log.warning(f"[doctor] Could not delete {zip_path}: {exc}")
    if deleted:
        return True, f"Deleted {len(deleted)} corrupt checkpoint(s): {', '.join(deleted)}"
    return True, "No checkpoints found to delete — will train from scratch"


def _fix_install_dep(python_exe: str, package: str) -> tuple[bool, str]:
    """Run pip install <package> using the given Python executable."""
    log.info(f"[doctor] Installing: {package}")
    try:
        result = subprocess.run(
            [python_exe, "-m", "pip", "install", package],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return True, f"Installed `{package}` successfully"
        err_snippet = (result.stderr or "")[-300:]
        return False, f"pip install `{package}` failed:\n{err_snippet}"
    except subprocess.TimeoutExpired:
        return False, f"pip install `{package}` timed out (>120s)"
    except Exception as exc:
        return False, f"pip install `{package}` raised: {exc}"
