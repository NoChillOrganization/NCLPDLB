"""Production readiness check. Run after placing .env and credentials.json.

Usage:
    python scripts/preflight.py [--skip-network]

Prints one PASS/FAIL line per check and exits 1 if any check fails.
Never prints secret values: only paths, setting names, client_email, bot name.
"""

import argparse
import json
import sys
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pydantic import ValidationError

from src.config import PROJECT_ROOT, Settings

Result = tuple[bool, str]


def expected_tabs() -> list[str]:
    """The 17 template tabs in README.md ("Google Sheets Structure"), from Tab.

    Excludes the two flat tabs the bot creates itself (Match Records, ELO Data).
    """
    from src.data.sheets import Tab

    flat = {Tab.MATCH_RECORDS, Tab.ELO_DATA}
    return [v for k, v in vars(Tab).items() if k.isupper() and v not in flat]


DISCORD_ME_URL = "https://discord.com/api/v10/users/@me"


def _norm(name: str) -> str:
    """Casefold and strip accents so 'Pokémon Stats' matches 'Pokemon Stats'."""
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold()


def check_paths(env_path: Path, creds_path: Path) -> Result:
    parts = [
        f"{label}={p.resolve()} ({'exists' if p.exists() else 'MISSING'})"
        for label, p in (("env", env_path), ("credentials", creds_path))
    ]
    return env_path.exists() and creds_path.exists(), "; ".join(parts)


def check_settings(loader: Callable[[], object] = Settings) -> Result:
    try:
        loader()
    except ValidationError as exc:
        names = sorted({str(e["loc"][0]) for e in exc.errors() if e["loc"]})
        return False, "missing/invalid settings: " + ", ".join(names)
    return True, "all required settings present"


def check_credentials(path: Path) -> Result:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False, "credentials file not found"
    except (OSError, ValueError) as exc:
        return False, f"credentials file unreadable: {type(exc).__name__}"
    email = data.get("client_email") if isinstance(data, dict) else None
    if not isinstance(email, str) or not email:
        return False, "credentials JSON has no client_email"
    return True, f"client_email={email}"


def check_discord(token: str, timeout: float = 10) -> Result:
    req = urllib.request.Request(
        DISCORD_ME_URL,
        headers={
            "Authorization": f"Bot {token}",
            # Discord's edge rejects the default Python-urllib agent.
            "User-Agent": "DiscordBot (nclpdlb-preflight, 1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.load(resp)
            return True, f"HTTP {resp.status}, bot={body.get('username')}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} (token rejected or blocked)"
    except (OSError, ValueError) as exc:
        return False, f"request failed: {type(exc).__name__}"


def check_sheets() -> Result:
    from src.data.sheets import SheetsClient

    ss = SheetsClient().spreadsheet
    titles = [ws.title for ws in ss.worksheets()]
    have = {_norm(t) for t in titles}
    missing = [t for t in expected_tabs() if _norm(t) not in have]
    msg = f"title={ss.title!r}, tabs={len(titles)}"
    if missing:
        return False, f"{msg}, missing tabs: {', '.join(missing)}"
    return True, msg


def run_checks(checks: list[tuple[str, Callable[[], Result]]]) -> int:
    """Run every check, print one line each, return process exit code."""
    failed = 0
    for name, fn in checks:
        try:
            ok, msg = fn()
        except Exception as exc:  # one broken check must not hide the others
            ok, msg = False, f"unexpected {type(exc).__name__}"
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'} {name}: {msg}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--skip-network", action="store_true", help="skip Discord and Sheets checks"
    )
    args = ap.parse_args(argv)

    try:
        s = Settings()
    except ValidationError:
        s = None
    creds = s.google_sheets_credentials_file if s else PROJECT_ROOT / "credentials.json"

    def need_settings(fn: Callable[[], Result]) -> Callable[[], Result]:
        return fn if s else lambda: (False, "skipped: settings invalid")

    checks: list[tuple[str, Callable[[], Result]]] = [
        ("paths", lambda: check_paths(PROJECT_ROOT / ".env", creds)),
        ("settings", check_settings),
        ("credentials", lambda: check_credentials(creds)),
    ]
    if not args.skip_network:
        checks += [
            (
                "discord",
                need_settings(
                    lambda: check_discord(s.discord_token.get_secret_value())
                ),
            ),
            ("sheets", need_settings(check_sheets)),
        ]
    # /spar model check skipped: best_model_for_format imports battle_env (numpy/gymnasium/poke_env).
    return run_checks(checks)


if __name__ == "__main__":
    sys.exit(main())
