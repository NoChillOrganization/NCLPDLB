"""Tests for src/bot/main.py — pure helper functions."""
from unittest.mock import MagicMock

from src.bot.main import _command_fingerprint, drift_check_commands


# ── _command_fingerprint ──────────────────────────────────────────────────────

def test_command_fingerprint_stable_order_independent():
    """Same commands in different order produce the same hash."""
    cmd1 = MagicMock()
    cmd1.name = "draft"
    cmd1.description = "Pick a Pokemon"
    cmd1.parameters = []

    cmd2 = MagicMock()
    cmd2.name = "team"
    cmd2.description = "View your team"
    cmd2.parameters = []

    fp1 = _command_fingerprint([cmd1, cmd2])
    fp2 = _command_fingerprint([cmd2, cmd1])
    assert fp1 == fp2
    assert len(fp1) == 16


def test_command_fingerprint_with_parameters():
    cmd = MagicMock()
    cmd.name = "draft"
    cmd.description = "Pick a Pokemon"
    p1, p2 = MagicMock(), MagicMock()
    p1.name = "pokemon"
    p2.name = "tier"
    cmd.parameters = [p1, p2]
    fp = _command_fingerprint([cmd])
    assert isinstance(fp, str)
    assert len(fp) == 16


def test_command_fingerprint_changes_on_name_change():
    cmd_a = MagicMock()
    cmd_a.name = "draft"
    cmd_a.description = "Pick"
    cmd_a.parameters = []

    cmd_b = MagicMock()
    cmd_b.name = "draft-pick"
    cmd_b.description = "Pick"
    cmd_b.parameters = []

    assert _command_fingerprint([cmd_a]) != _command_fingerprint([cmd_b])


def test_command_fingerprint_changes_on_description_change():
    cmd_a = MagicMock()
    cmd_a.name = "draft"
    cmd_a.description = "Old description"
    cmd_a.parameters = []

    cmd_b = MagicMock()
    cmd_b.name = "draft"
    cmd_b.description = "New description"
    cmd_b.parameters = []

    assert _command_fingerprint([cmd_a]) != _command_fingerprint([cmd_b])


def test_command_fingerprint_empty_list():
    fp = _command_fingerprint([])
    assert isinstance(fp, str)
    assert len(fp) == 16


# ── drift_check_commands ──────────────────────────────────────────────────────

def test_drift_check_no_drift():
    assert drift_check_commands({"draft", "team"}, {"draft", "team"}) == set()


def test_drift_check_extra_in_registered():
    result = drift_check_commands({"draft"}, {"draft", "secret-command"})
    assert result == {"secret-command"}


def test_drift_check_missing_from_registered_not_drift():
    # Commands in CSV but absent from bot tree are NOT drift (drift = reg - csv)
    result = drift_check_commands({"draft", "old-command"}, {"draft"})
    assert result == set()


def test_drift_check_both_empty():
    assert drift_check_commands(set(), set()) == set()


def test_drift_check_all_drift():
    result = drift_check_commands(set(), {"cmd1", "cmd2"})
    assert result == {"cmd1", "cmd2"}
