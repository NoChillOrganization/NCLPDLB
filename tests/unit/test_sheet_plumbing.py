"""Tests for src/data/sheet_plumbing.py — SheetConnection (gspread mocked / faked).

The League sheet's rows and policies are tested through its own interface in
test_league_sheet.py; this file covers the shared low-level operations.
"""

from unittest.mock import MagicMock, patch

import gspread
import pytest

from src.data.sheet_plumbing import SheetConnection, _col_letter
from tests.fake_gspread import FakeSpreadsheet, api_error


def make(**tabs) -> tuple[SheetConnection, FakeSpreadsheet]:
    ss = FakeSpreadsheet(**tabs)
    conn = SheetConnection(lambda: "id")
    conn._spreadsheet = ss
    return conn, ss


# ── connect() ────────────────────────────────────────────────────────────────


def test_connect_file_not_found(tmp_path):
    """connect() raises FileNotFoundError when credentials file is missing."""
    conn = SheetConnection(lambda: "x")
    with patch("src.data.sheet_plumbing.settings") as ms:
        ms.google_sheets_credentials_file = tmp_path / "missing.json"
        with pytest.raises(FileNotFoundError):
            conn.connect()


def test_connect_success(tmp_path):
    """connect() sets _spreadsheet on success, opening the id the adapter supplied."""
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text('{"type":"service_account"}')
    conn = SheetConnection(lambda: "test-id")

    with (
        patch("src.data.sheet_plumbing.settings") as ms,
        patch("src.data.sheet_plumbing.Credentials.from_service_account_file"),
        patch("src.data.sheet_plumbing.gspread.authorize") as mock_auth,
    ):
        ms.google_sheets_credentials_file = creds_file
        mock_sp = MagicMock()
        mock_sp.title = "Test Sheet"
        mock_auth.return_value.open_by_key.return_value = mock_sp
        conn.connect()
    assert conn._spreadsheet is mock_sp
    mock_auth.return_value.open_by_key.assert_called_once_with("test-id")


def test_spreadsheet_property_calls_connect_when_none():
    conn = SheetConnection(lambda: "x")
    mock_sp = MagicMock()
    with patch.object(
        conn, "connect", side_effect=lambda: setattr(conn, "_spreadsheet", mock_sp)
    ):
        assert conn.spreadsheet is mock_sp


# ── get_tab() ─────────────────────────────────────────────────────────────────


def test_get_tab_found():
    conn, ss = make(Setup=[])
    assert conn.get_tab("Setup") is ss.tabs["Setup"]


def test_get_tab_missing_raises_when_not_creating():
    conn, _ = make()
    with pytest.raises(gspread.WorksheetNotFound):
        conn.get_tab("Nope")


def test_get_tab_creates_with_title_row():
    conn, ss = make()
    ws = conn.get_tab("Setup", create=True)
    assert ws is ss.tabs["Setup"]
    assert ws.rows == [["Setup"]]


def test_get_tab_creates_with_headers():
    conn, _ = make()
    ws = conn.get_tab("Replays", create=True, headers=["a", "b"])
    assert ws.rows == [["a", "b"]]


# ── read_all / append_row / replace_rows ──────────────────────────────────────


def test_read_all():
    conn, _ = make(Setup=[["key"], ["val"]])
    assert conn.read_all("Setup") == [{"key": "val"}]


def test_read_all_empty_tab():
    conn, _ = make(Setup=[])
    assert conn.read_all("Setup") == []


def test_append_row():
    conn, ss = make(Draft=[["h"]])
    conn.append_row("Draft", ["a", "b"])
    assert ss.tabs["Draft"].rows[-1] == ["a", "b"]


def test_replace_rows():
    conn, ss = make(Pokédex=[["old"]])
    conn.replace_rows("Pokédex", [["a"], ["b"]])
    assert ss.tabs["Pokédex"].rows == [["a"], ["b"]]


# ── find_row ──────────────────────────────────────────────────────────────────


def test_find_row_found_pads_short_rows():
    conn, _ = make(Standings=[["player_id", "name", "extra"], ["p1", "Alice"]])
    assert conn.find_row("Standings", "player_id", "p1") == {
        "player_id": "p1",
        "name": "Alice",
        "extra": "",
    }


def test_find_row_not_found():
    conn, _ = make(Standings=[["player_id"], ["p1"]])
    assert conn.find_row("Standings", "player_id", "missing") is None


def test_find_row_column_not_in_headers():
    conn, _ = make(Standings=[["other"], ["p1"]])
    assert conn.find_row("Standings", "player_id", "p1") is None


# ── upsert_row ────────────────────────────────────────────────────────────────


def test_upsert_row_appends_when_not_found():
    conn, ss = make(Standings=[["player_id", "name"]])
    conn.upsert_row("Standings", "player_id", "p99", ["p99", "New Guy"])
    assert ss.tabs["Standings"].rows[-1] == ["p99", "New Guy"]


def test_upsert_row_updates_when_found():
    conn, ss = make(Standings=[["player_id", "name"], ["p1", "Alice"]])
    conn.upsert_row("Standings", "player_id", "p1", ["p1", "Alice Updated"])
    assert ss.tabs["Standings"].rows == [
        ["player_id", "name"],
        ["p1", "Alice Updated"],
    ]


def test_upsert_row_appends_when_col_not_in_headers():
    conn, ss = make(Standings=[["other_col"]])
    conn.upsert_row("Standings", "player_id", "p1", ["p1", "Alice"])
    assert ss.tabs["Standings"].rows[-1] == ["p1", "Alice"]


# ── upsert_record ─────────────────────────────────────────────────────────────


def test_upsert_record_bootstraps_headers_on_empty_tab():
    conn, ss = make(Teams=[])
    conn.upsert_record("Teams", "player_id", "p1", {"player_id": "p1", "n": "x"})
    assert ss.tabs["Teams"].rows == [["player_id", "n"], ["p1", "x"]]


def test_upsert_record_partial_update_keeps_other_columns():
    conn, ss = make(Teams=[["player_id", "n", "z"], ["p1", "old", "keep"]])
    conn.upsert_record("Teams", "player_id", "p1", {"player_id": "p1", "n": "new"})
    assert ss.tabs["Teams"].rows[1] == ["p1", "new", "keep"]


def test_upsert_record_insert_follows_header_order():
    conn, ss = make(Teams=[["n", "player_id"]])
    conn.upsert_record("Teams", "player_id", "p1", {"player_id": "p1", "n": "x"})
    assert ss.tabs["Teams"].rows[-1] == ["x", "p1"]


# ── retry ─────────────────────────────────────────────────────────────────────


def test_find_row_retries_transient_error():
    conn, ss = make(Standings=[["player_id"], ["p1"]])
    ss.tabs["Standings"].fail_next = [api_error(503)]
    with patch("src.data.sheet_plumbing._time.sleep"):
        assert conn.find_row("Standings", "player_id", "p1") == {"player_id": "p1"}


# ── _col_letter ────────────────────────────────────────────────────


def test_col_letter_single_digits():
    assert _col_letter(1) == "A"
    assert _col_letter(26) == "Z"


def test_col_letter_double_digits():
    assert _col_letter(27) == "AA"
    assert _col_letter(52) == "AZ"
    assert _col_letter(702) == "ZZ"
