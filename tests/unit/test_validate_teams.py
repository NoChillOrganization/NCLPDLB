"""scripts/validate_teams.py reads the live FORMAT_TEAMS (built from data/teams/*.txt)."""

import importlib.util
from pathlib import Path

from src.ml.teams import FORMAT_TEAMS

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate_teams.py"


def _load():
    spec = importlib.util.spec_from_file_location("validate_teams", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_uses_imported_format_teams():
    assert _load().FORMAT_TEAMS is FORMAT_TEAMS


def test_unmapped_format_skips(monkeypatch, capsys):
    monkeypatch.setenv("TRAIN_TEAM_FORMAT", "gen9notaformat")
    _load().main()
    assert "No team pool mapped" in capsys.readouterr().out
