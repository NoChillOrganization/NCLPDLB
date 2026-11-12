"""Validate all teams in a format pool against the local Showdown validator.

Usage:
    TRAIN_TEAM_FORMAT=gen9zu python scripts/validate_teams.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ml.teams import FORMAT_TEAMS


def main() -> None:
    team_format = os.environ.get("TRAIN_TEAM_FORMAT", "")
    if not team_format:
        print("TRAIN_TEAM_FORMAT not set — skipping validation")
        return

    teams = FORMAT_TEAMS.get(team_format)
    if not teams:
        print(f"No team pool mapped for {team_format} — skipping validation")
        return

    ps_dir = os.path.expanduser("~/pokemon-showdown")
    errors = 0

    for i, team in enumerate(teams, 1):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(team.strip() + "\n")
            fname = f.name
        try:
            result = subprocess.run(
                ["node", "pokemon-showdown", "validate-team", team_format],
                stdin=open(fname, encoding="utf-8"),
                capture_output=True,
                text=True,
                cwd=ps_dir,
                timeout=15,
            )
            violations = (result.stdout.strip() + result.stderr.strip()).strip()
        finally:
            os.unlink(fname)

        if violations:
            print(f"INVALID team {i}/{len(teams)}: {violations}")
            errors += 1
        else:
            print(f"OK     team {i}/{len(teams)}")

    if errors:
        print(
            f"\n{errors} invalid team(s) for {team_format} — fix data/teams/{team_format}.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"All {len(teams)} team(s) valid for {team_format}")


if __name__ == "__main__":
    main()
