"""
Pre-built teams for each training format.

5 teams per format in Showdown export format, stored as text files under
``data/teams/<format>.txt`` (teams separated by a ``\n---\n`` line). Used by
RotatingTeambuilder to cycle through diverse teams during RL training.

ponytail: data lives in data/teams/*.txt, not inline. Edit the .txt files to
add/change teams — no code change needed. Add a format by dropping a new
<format>.txt and appending its key to TEAM_POOL_KEYS in src/ml/formats.py.
"""

from pathlib import Path

from src.ml.formats import TEAM_POOL_KEYS

_DATA = Path(__file__).resolve().parents[2] / "data" / "teams"

FORMAT_KEYS = TEAM_POOL_KEYS  # the key list lives in src.ml.formats


def _load(fmt: str) -> list[str]:
    raw = (_DATA / f"{fmt}.txt").read_text(encoding="utf-8")
    return [t.strip() for t in raw.split("\n---\n") if t.strip()]


FORMAT_TEAMS: dict[str, list[str]] = {k: _load(k) for k in FORMAT_KEYS}


def main() -> None:
    assert len(FORMAT_TEAMS) == len(FORMAT_KEYS) == 23
    for _fmt, _teams in FORMAT_TEAMS.items():
        assert _teams, f"{_fmt} has no teams"
        assert any("@" in t for t in _teams), f"{_fmt} missing item notation"
    assert len(FORMAT_TEAMS["gen9ou"]) == 5
    print("teams.py OK:", sum(len(v) for v in FORMAT_TEAMS.values()), "teams")


if __name__ == "__main__":
    main()
