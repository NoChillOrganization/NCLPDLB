"""Validate all teams in a format pool against the local Showdown validator.

Usage:
    TRAIN_TEAM_FORMAT=gen9zu python scripts/validate_teams.py
"""
import ast
import os
import re
import subprocess
import sys
import tempfile


def main() -> None:
    team_format = os.environ.get("TRAIN_TEAM_FORMAT", "")
    if not team_format:
        print("TRAIN_TEAM_FORMAT not set — skipping validation")
        return

    src = open("src/ml/teams.py", encoding="utf-8").read()

    map_match = re.search(r"FORMAT_TEAMS\b\s*(?::[^=\n]+)?=\s*\{(.*?)\}", src, re.DOTALL)
    if not map_match:
        print("ERROR: FORMAT_TEAMS not found in teams.py", file=sys.stderr)
        sys.exit(1)

    var_match = re.search(
        r"""['"]""" + re.escape(team_format) + r"""['"]\s*:\s*(\w+)""",
        map_match.group(1),
    )
    if not var_match:
        print(f"No team pool mapped for {team_format} — skipping validation")
        return

    var_name = var_match.group(1)
    lst_match = re.search(
        rf"^{var_name}\s*=\s*(\[.*?\n\])", src, re.MULTILINE | re.DOTALL
    )
    if not lst_match:
        print(f"Variable {var_name} not found in teams.py", file=sys.stderr)
        sys.exit(1)

    teams = ast.literal_eval(lst_match.group(1))
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
            f"\n{errors} invalid team(s) for {team_format} — fix src/ml/teams.py",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"All {len(teams)} team(s) valid for {team_format}")


if __name__ == "__main__":
    main()
