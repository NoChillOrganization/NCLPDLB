"""Tests for src/data/sheets.py — SheetsClient methods (gspread mocked)."""

import pytest
from unittest.mock import MagicMock, patch

import gspread
from src.data.sheets import (
    SheetsClient,
    Tab,
    sheets,
    _col_letter,
)


# ── Fixture: worksheet mock ──────────────────────────────────────────────────


@pytest.fixture
def mock_ws():
    ws = MagicMock()
    ws.get_all_records.return_value = []
    ws.row_values.return_value = []
    return ws


@pytest.fixture
def patched_get_tab(mock_ws):
    """Patches sheets.get_tab to return mock_ws without touching Google."""
    with patch.object(sheets, "get_tab", return_value=mock_ws) as p:
        yield mock_ws, p


# ── connect() ────────────────────────────────────────────────────────────────


def test_connect_file_not_found(tmp_path):
    """connect() raises FileNotFoundError when credentials file is missing."""
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._spreadsheet = None
    fresh._client = None
    with patch("src.data.sheets.settings") as ms:
        ms.google_sheets_credentials_file = tmp_path / "missing.json"
        ms.google_sheets_spreadsheet_id = "x"
        with pytest.raises(FileNotFoundError):
            fresh.connect()


def test_connect_success(tmp_path):
    """connect() sets _spreadsheet on success."""
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text('{"type":"service_account"}')

    fresh = SheetsClient.__new__(SheetsClient)
    fresh._spreadsheet = None
    fresh._client = None

    with (
        patch("src.data.sheets.settings") as ms,
        patch("src.data.sheets.Credentials.from_service_account_file"),
        patch("src.data.sheets.gspread.authorize") as mock_auth,
    ):
        ms.google_sheets_credentials_file = creds_file
        ms.google_sheets_spreadsheet_id = "test-id"
        mock_sp = MagicMock()
        mock_sp.title = "Test Sheet"
        mock_auth.return_value.open_by_key.return_value = mock_sp
        fresh.connect()
    assert fresh._spreadsheet is mock_sp


# ── spreadsheet property ──────────────────────────────────────────────────────


def test_spreadsheet_property_calls_connect_when_none():
    """spreadsheet property triggers connect() if _spreadsheet is None."""
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._spreadsheet = None
    fresh._client = None
    mock_sp = MagicMock()
    mock_sp.title = "T"
    with patch.object(
        fresh, "connect", side_effect=lambda: setattr(fresh, "_spreadsheet", mock_sp)
    ):
        sp = fresh.spreadsheet
    assert sp is mock_sp


# ── get_tab() ─────────────────────────────────────────────────────────────────


def test_get_tab_found():
    """get_tab returns worksheet when it exists."""
    fresh = SheetsClient.__new__(SheetsClient)
    mock_sp = MagicMock()
    mock_ws = MagicMock()
    mock_sp.worksheet.return_value = mock_ws
    fresh._spreadsheet = mock_sp
    result = fresh.get_tab(Tab.SETUP)
    assert result is mock_ws


def test_get_tab_creates_when_not_found():
    """get_tab creates the tab when WorksheetNotFound is raised."""

    fresh = SheetsClient.__new__(SheetsClient)
    mock_sp = MagicMock()
    new_ws = MagicMock()
    mock_sp.worksheet.side_effect = gspread.WorksheetNotFound
    mock_sp.add_worksheet.return_value = new_ws
    fresh._spreadsheet = mock_sp
    result = fresh.get_tab(Tab.SETUP, create=True)
    assert result is new_ws
    new_ws.append_row.assert_called_once()


# ── read_all / append_row ───────────────────────────────────────


def test_read_all(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = [{"key": "val"}]
    result = sheets.read_all(Tab.SETUP)
    assert result == [{"key": "val"}]


def test_append_row(patched_get_tab):
    mock_ws, _ = patched_get_tab
    sheets.append_row(Tab.DRAFT, ["a", "b", "c"])
    mock_ws.append_row.assert_called_once_with(
        ["a", "b", "c"], value_input_option="USER_ENTERED"
    )


# ── find_row / find_rows ──────────────────────────────────────────────────────


def test_find_row_found(patched_get_tab):
    mock_ws, _ = patched_get_tab
    cell = MagicMock()
    cell.row = 2
    mock_ws.row_values.side_effect = lambda row: (
        ["player_id", "name"] if row == 1 else ["p1", "Alice"]
    )
    mock_ws.find.return_value = cell
    result = sheets.find_row(Tab.STANDINGS, "player_id", "p1")
    assert result["name"] == "Alice"


def test_find_row_not_found(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    assert sheets.find_row(Tab.STANDINGS, "player_id", "missing") is None


def test_find_rows(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = [
        {"draft_id": "d1", "pick": "Garchomp"},
        {"draft_id": "d1", "pick": "Corviknight"},
        {"draft_id": "d2", "pick": "Toxapex"},
    ]
    result = sheets.find_rows(Tab.DRAFT, "draft_id", "d1")
    assert len(result) == 2


# ── upsert_row ────────────────────────────────────────────────────────────────


def test_upsert_row_appends_when_not_found(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["player_id", "name"]
    mock_ws.find.return_value = None
    sheets.upsert_row(Tab.STANDINGS, "player_id", "p99", ["p99", "New Guy"])
    mock_ws.append_row.assert_called()


def test_upsert_row_updates_when_found(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = [{"player_id": "p1", "name": "Alice"}]
    mock_ws.row_values.return_value = ["player_id", "name"]
    sheets.upsert_row(Tab.STANDINGS, "player_id", "p1", ["p1", "Alice Updated"])
    mock_ws.update.assert_called()


def test_upsert_row_appends_when_col_not_in_headers(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["other_col"]
    sheets.upsert_row(Tab.STANDINGS, "player_id", "p1", ["p1", "Alice"])
    mock_ws.append_row.assert_called()


# ── Domain methods ────────────────────────────────────────────────────────────


def test_save_league_setup(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["server_id"]
    mock_ws.find.return_value = None
    sheets.save_league_setup(
        {
            "league_id": "L1",
            "server_id": "S1",
            "league_name": "Test League",
            "commissioner_id": "C1",
            "commissioner_name": "Admin",
        }
    )
    mock_ws.append_row.assert_called()


def test_save_pick(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = []
    sheets.save_pick({"pick_id": "pk1", "draft_id": "d1", "pokemon_name": "Garchomp"})
    mock_ws.append_row.assert_called()


def test_save_schedule_match(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["match_id"]
    mock_ws.find.return_value = None
    sheets.save_schedule_match(
        {"match_id": "m1", "week": 1, "player1_id": "p1", "player2_id": "p2"}
    )
    mock_ws.append_row.assert_called()


def test_save_match_stats(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["match_id"]
    mock_ws.find.return_value = None
    sheets.save_match_stats(
        {
            "match_id": "m1",
            "league_id": "L1",
            "p1_team": ["Garchomp"],
            "p2_team": ["Corviknight"],
        }
    )
    mock_ws.append_row.assert_called()


def test_upsert_standing(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["player_id"]
    mock_ws.find.return_value = None
    sheets.upsert_standing({"player_id": "p1", "elo": 1050, "wins": 3, "losses": 1})
    mock_ws.append_row.assert_called()


def test_get_league_setup_found(patched_get_tab):
    """get_league_setup returns the matching row for a server_id."""
    mock_ws, _ = patched_get_tab
    cell = MagicMock()
    cell.row = 2
    mock_ws.row_values.side_effect = lambda row: (
        ["server_id", "league_name"] if row == 1 else ["S1", "Test League"]
    )
    mock_ws.find.return_value = cell
    result = sheets.get_league_setup("S1")
    assert result is not None
    assert result["league_name"] == "Test League"


def test_get_standings_all(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = [
        {"rank": 1, "pool": "A", "player_id": "p1"},
        {"rank": 2, "pool": "B", "player_id": "p2"},
    ]
    result = sheets.get_standings()
    assert len(result) == 2


def test_get_standings_filtered_by_pool(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = [
        {"rank": 1, "pool": "A", "player_id": "p1"},
        {"rank": 2, "pool": "B", "player_id": "p2"},
    ]
    result = sheets.get_standings(pool="A")
    assert len(result) == 1
    assert result[0]["player_id"] == "p1"


def test_save_transaction(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["transaction_id"]
    mock_ws.find.return_value = None
    sheets.save_transaction(
        {"transaction_id": "t1", "type": "trade", "status": "pending"}
    )
    mock_ws.append_row.assert_called()


def test_save_playoff_match(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["bracket_id"]
    mock_ws.find.return_value = None
    sheets.save_playoff_match({"bracket_id": "b1", "round": "QF", "match_number": 1})
    mock_ws.append_row.assert_called()


def test_bulk_write_pokedex(patched_get_tab):
    mock_ws, _ = patched_get_tab
    pokemon_list = [
        {
            "national_dex": 1,
            "name": "Bulbasaur",
            "types": ["grass", "poison"],
            "base_stats": {
                "hp": 45,
                "atk": 49,
                "def": 49,
                "spa": 65,
                "spd": 65,
                "spe": 45,
            },
            "showdown_tier": "NU",
            "generation": 1,
            "is_legendary": False,
            "is_mythical": False,
            "vgc_legal": True,
            "console_legal": {"sv": True, "swsh": False},
            "sprite_url": "",
        }
    ]
    sheets.bulk_write_pokedex(pokemon_list)
    mock_ws.clear.assert_called_once()
    mock_ws.append_rows.assert_called_once()


def test_bulk_write_pokedex_empty(patched_get_tab):
    mock_ws, _ = patched_get_tab
    sheets.bulk_write_pokedex([])
    mock_ws.clear.assert_called_once()
    mock_ws.append_rows.assert_not_called()


def test_upsert_team_page(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["player_id"]
    mock_ws.find.return_value = None
    sheets.upsert_team_page(
        {
            "player_id": "p1",
            "player_name": "Alice",
            "team_name": "Team A",
            "slots": [("Garchomp", "Dragon"), ("Corviknight", "Flying")],
        }
    )
    mock_ws.append_row.assert_called()


def test_upsert_team_page_no_slots(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["player_id"]
    mock_ws.find.return_value = None
    sheets.upsert_team_page(
        {"player_id": "p1", "player_name": "Alice", "team_name": "T"}
    )
    mock_ws.append_row.assert_called()


def test_save_replay_no_existing_match(patched_get_tab):
    """save_replay does nothing when match is not found."""
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    # Should not raise
    sheets.save_replay(
        {
            "match_id": "m999",
            "url": "https://replay.ps.com/r1",
            "p1_team": [],
            "p2_team": [],
            "turns": 10,
        }
    )


def test_save_replay_updates_existing(patched_get_tab):
    """save_replay updates an existing replay row when replay_id found."""
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["replay_id"]
    # find() returns a cell → update path (not None → not append)
    sheets.save_replay(
        {
            "replay_id": "r1",
            "match_id": "m1",
            "url": "https://replay.ps.com/r1",
            "p1_team": ["Garchomp"],
            "p2_team": ["Corviknight"],
            "turns": 25,
        }
    )
    mock_ws.update.assert_called()


def test_save_video(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["match_id"]
    mock_ws.find.return_value = None
    sheets.save_video(
        {
            "match_id": "m1",
            "league_id": "L1",
            "uploader_id": "p1",
            "opponent_id": "p2",
            "storage_url": "https://r2.example.com/video.mp4",
        }
    )
    mock_ws.append_row.assert_called()


# ── _col_letter ────────────────────────────────────────────────────


def test_col_letter_single_digits():
    assert _col_letter(1) == "A"
    assert _col_letter(26) == "Z"


def test_col_letter_double_digits():
    assert _col_letter(27) == "AA"
    assert _col_letter(52) == "AZ"
    assert _col_letter(702) == "ZZ"


# ── _get_range ────────────────────────────────────────────────────────────────


def test_get_range_returns_data():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    mock_sp = MagicMock()
    mock_sp.values_get.return_value = {"values": [["a", "b"], ["c", "d"]]}
    fresh._spreadsheet = mock_sp
    result = fresh._get_range("Sheet1", "A1:B2")
    assert result == [["a", "b"], ["c", "d"]]


# ── get_league_setup (no server_id) ──────────────────────────────────────────


def test_get_league_setup_no_server_id_returns_first(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = [{"server_id": "S1", "league_name": "NCL"}]
    result = sheets.get_league_setup()
    assert result == {"server_id": "S1", "league_name": "NCL"}


def test_get_league_setup_no_server_id_empty(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    result = sheets.get_league_setup()
    assert result == {}


# ── get_match_results ─────────────────────────────────────────────────────────


def test_get_match_results_parses_match():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    d_col = [["Week #1"]]
    match_raw = [["TrainerA", "x", "W", "x", "x", "x", "L", "TrainerB"]]

    def mock_get_range(tab, rng):
        return d_col if "D3" in rng else match_raw

    with patch.object(fresh, "_get_range", side_effect=mock_get_range):
        result = fresh.get_match_results()
    assert len(result) == 1
    assert result[0]["coach1"] == "TrainerA"
    assert result[0]["winner"] == "TrainerA"
    assert result[0]["week"] == "Week #1"


def test_get_match_results_week_filter():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    d_col = [["Week #1"], ["Week #2"]]
    match_raw = [["TrainerA", "x", "W", "x", "x", "x", "L", "TrainerB"]]

    def mock_get_range(tab, rng):
        return d_col if "D3" in rng else match_raw

    with patch.object(fresh, "_get_range", side_effect=mock_get_range):
        result = fresh.get_match_results(week=2)
    assert len(result) == 1
    assert result[0]["week"] == "Week #2"


def test_get_match_results_non_match_rows_skipped():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    d_col = [["Week #1"]]
    match_raw = [["", "", "X", "", "", "", "", ""]]  # empty coach1 → skip

    def mock_get_range(tab, rng):
        return d_col if "D3" in rng else match_raw

    with patch.object(fresh, "_get_range", side_effect=mock_get_range):
        result = fresh.get_match_results()
    assert result == []


# ── read_all ──────────────────────────────────────────────────────────────────


class TestReadAll:
    """Cover SheetsClient.read_all() — empty-vals early return and header dedup."""

    def test_empty_vals_returns_empty_list(self, patched_get_tab):
        mock_ws, _ = patched_get_tab
        mock_ws.get_all_values.return_value = []
        result = sheets.read_all("SomeTab")
        assert result == []

    def test_valid_headers_deduped_and_forwarded(self, patched_get_tab):
        mock_ws, _ = patched_get_tab
        mock_ws.get_all_values.return_value = [
            ["Name", "Score", "Name"],  # "Name" appears twice — deduplicated
            ["Alice", "10", "Alice"],
        ]
        mock_ws.get_all_records.return_value = [{"Name": "Alice", "Score": "10"}]
        result = sheets.read_all("SomeTab")
        call_kwargs = mock_ws.get_all_records.call_args[1]
        assert call_kwargs["expected_headers"] == ["Name", "Score"]
        assert result == [{"Name": "Alice", "Score": "10"}]
