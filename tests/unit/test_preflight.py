"""Pure-logic tests for scripts/preflight.py (no network, no real credentials)."""

import importlib.util
import json
from pathlib import Path

from pydantic import BaseModel

_spec = importlib.util.spec_from_file_location(
    "preflight", Path(__file__).parents[2] / "scripts" / "preflight.py"
)
preflight = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(preflight)


def test_credentials_prints_email_only(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps({"client_email": "bot@x.iam", "private_key": "TOPSECRET"}),
        encoding="utf-8",
    )
    ok, msg = preflight.check_credentials(p)
    assert ok and "bot@x.iam" in msg and "TOPSECRET" not in msg


def test_credentials_bad_inputs(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json TOPSECRET", encoding="utf-8")
    noemail = tmp_path / "n.json"
    noemail.write_text('{"private_key": "TOPSECRET"}', encoding="utf-8")
    for p in (bad, noemail, tmp_path / "missing.json"):
        ok, msg = preflight.check_credentials(p)
        assert not ok and "TOPSECRET" not in msg


def test_missing_settings_lists_names_only():
    class M(BaseModel):
        discord_token: str
        discord_client_id: str

    def loader():
        M(discord_token="hunter2-secret")  # client_id missing

    ok, msg = preflight.check_settings(loader)
    assert not ok and "discord_client_id" in msg
    assert "hunter2-secret" not in msg


def test_paths_reports_missing(tmp_path):
    ok, msg = preflight.check_paths(tmp_path / ".env", tmp_path / "c.json")
    assert not ok and "MISSING" in msg


def test_run_checks_exit_code_and_isolation(capsys):
    def boom():
        raise RuntimeError("secret-ish")

    code = preflight.run_checks(
        [("a", lambda: (True, "fine")), ("b", boom), ("c", lambda: (True, "fine"))]
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL b" in out and "PASS c" in out and "secret-ish" not in out
    assert preflight.run_checks([("a", lambda: (True, "ok"))]) == 0


def test_tab_name_accent_insensitive():
    assert preflight._norm("Pokémon Stats") == preflight._norm("Pokemon Stats")
