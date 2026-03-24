"""Tests for src/data/sheets.py — SheetsClient methods (gspread mocked)."""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import gspread
from src.data.sheets import SheetsClient, Tab, sheets, _col_letter, _col_num, LearningSheets


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

    with patch("src.data.sheets.settings") as ms, \
         patch("src.data.sheets.Credentials.from_service_account_file") as mock_creds, \
         patch("src.data.sheets.gspread.authorize") as mock_auth:
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
    with patch.object(fresh, "connect", side_effect=lambda: setattr(fresh, "_spreadsheet", mock_sp)):
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
    import gspread
    fresh = SheetsClient.__new__(SheetsClient)
    mock_sp = MagicMock()
    new_ws = MagicMock()
    mock_sp.worksheet.side_effect = gspread.WorksheetNotFound
    mock_sp.add_worksheet.return_value = new_ws
    fresh._spreadsheet = mock_sp
    result = fresh.get_tab(Tab.SETUP)
    assert result is new_ws
    new_ws.append_row.assert_called_once()


# ── read_all / append_row / update_row ───────────────────────────────────────

def test_read_all(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = [{"key": "val"}]
    result = sheets.read_all(Tab.SETUP)
    assert result == [{"key": "val"}]


def test_append_row(patched_get_tab):
    mock_ws, _ = patched_get_tab
    sheets.append_row(Tab.DRAFT, ["a", "b", "c"])
    mock_ws.append_row.assert_called_once_with(["a", "b", "c"], value_input_option="USER_ENTERED")


def test_update_row(patched_get_tab):
    mock_ws, _ = patched_get_tab
    sheets.update_row(Tab.STANDINGS, 3, ["x", "y"])
    mock_ws.update.assert_called_once_with("A3", [["x", "y"]])


# ── find_row / find_rows ──────────────────────────────────────────────────────

def test_find_row_found(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = [
        {"player_id": "p1", "name": "Alice"},
        {"player_id": "p2", "name": "Bob"},
    ]
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
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["player_id", "name"]
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
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["server_id"]
    sheets.save_league_setup({
        "league_id": "L1", "server_id": "S1", "league_name": "Test League",
        "commissioner_id": "C1", "commissioner_name": "Admin",
    })
    mock_ws.append_row.assert_called()


def test_save_pick(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = []
    sheets.save_pick({"pick_id": "pk1", "draft_id": "d1", "pokemon_name": "Garchomp"})
    mock_ws.append_row.assert_called()


def test_get_draft_picks(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = [
        {"draft_id": "d1", "pokemon": "Garchomp"},
        {"draft_id": "d2", "pokemon": "Other"},
    ]
    result = sheets.get_draft_picks("d1")
    assert len(result) == 1


def test_update_pool_roster_pool_a(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["player_id"]
    sheets.update_pool_roster("A", {"player_id": "p1", "player_name": "Alice", "team_name": "Team A"}, ["Garchomp"])
    mock_ws.append_row.assert_called()


def test_update_pool_roster_pool_b(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["player_id"]
    sheets.update_pool_roster("B", {"player_id": "p2", "player_name": "Bob", "team_name": "Team B"}, [])
    mock_ws.append_row.assert_called()


def test_save_schedule_match(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["match_id"]
    sheets.save_schedule_match({"match_id": "m1", "week": 1, "player1_id": "p1", "player2_id": "p2"})
    mock_ws.append_row.assert_called()


def test_save_match_stats(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["match_id"]
    sheets.save_match_stats({
        "match_id": "m1", "league_id": "L1",
        "p1_team": ["Garchomp"], "p2_team": ["Corviknight"],
    })
    mock_ws.append_row.assert_called()


def test_upsert_standing(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["player_id"]
    sheets.upsert_standing({"player_id": "p1", "elo": 1050, "wins": 3, "losses": 1})
    mock_ws.append_row.assert_called()


def test_get_league_setup_found(patched_get_tab):
    """get_league_setup returns the matching row for a server_id."""
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = [
        {"server_id": "S1", "league_name": "Test League"},
        {"server_id": "S2", "league_name": "Other"},
    ]
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


def test_update_pokemon_stat(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["stat_id"]
    sheets.update_pokemon_stat({"stat_id": "s1", "pokemon": "Garchomp", "wins": 5})
    mock_ws.append_row.assert_called()


def test_refresh_mvp_race(patched_get_tab):
    mock_ws, _ = patched_get_tab
    entries = [{"rank": 1, "player_id": "p1", "mvp_pokemon": "Garchomp", "mvp_count": 3}]
    sheets.refresh_mvp_race(entries)
    mock_ws.resize.assert_called()
    mock_ws.append_row.assert_called()


def test_save_transaction(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["transaction_id"]
    sheets.save_transaction({"transaction_id": "t1", "type": "trade", "status": "pending"})
    mock_ws.append_row.assert_called()


def test_save_playoff_match(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["bracket_id"]
    sheets.save_playoff_match({"bracket_id": "b1", "round": "QF", "match_number": 1})
    mock_ws.append_row.assert_called()


def test_bulk_write_pokedex(patched_get_tab):
    mock_ws, _ = patched_get_tab
    pokemon_list = [
        {
            "national_dex": 1, "name": "Bulbasaur",
            "types": ["grass", "poison"],
            "base_stats": {"hp": 45, "atk": 49, "def": 49, "spa": 65, "spd": 65, "spe": 45},
            "showdown_tier": "NU", "generation": 1,
            "is_legendary": False, "is_mythical": False,
            "vgc_legal": True, "console_legal": {"sv": True, "swsh": False},
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
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["player_id"]
    sheets.upsert_team_page({
        "player_id": "p1", "player_name": "Alice", "team_name": "Team A",
        "slots": [("Garchomp", "Dragon"), ("Corviknight", "Flying")],
    })
    mock_ws.append_row.assert_called()


def test_upsert_team_page_no_slots(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["player_id"]
    sheets.upsert_team_page({"player_id": "p1", "player_name": "Alice", "team_name": "T"})
    mock_ws.append_row.assert_called()


def test_set_data(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["key"]
    sheets.set_data("season", "3", "string", "Current season")
    mock_ws.append_row.assert_called()


def test_get_data_found(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = [{"key": "season", "value": "3"}]
    result = sheets.get_data("season")
    assert result == "3"


def test_get_data_not_found(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    assert sheets.get_data("missing_key") is None


def test_save_replay_no_existing_match(patched_get_tab):
    """save_replay does nothing when match is not found."""
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    # Should not raise
    sheets.save_replay({"match_id": "m999", "url": "https://replay.ps.com/r1", "p1_team": [], "p2_team": [], "turns": 10})


def test_save_replay_updates_existing(patched_get_tab):
    """save_replay updates match row when match_id found."""
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = [
        {"match_id": "m1", "league_id": "L1", "week": 1, "pool": "A",
         "player1_id": "p1", "player1_name": "Alice",
         "player2_id": "p2", "player2_name": "Bob",
         "winner_id": "p1", "winner_name": "Alice",
         "game_format": "showdown", "replay_url": "", "video_url": ""},
    ]
    mock_ws.row_values.return_value = ["match_id"]
    sheets.save_replay({
        "match_id": "m1", "url": "https://replay.ps.com/r1",
        "p1_team": ["Garchomp"], "p2_team": ["Corviknight"], "turns": 25,
    })
    mock_ws.update.assert_called()


def test_save_video(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.get_all_records.return_value = []
    mock_ws.row_values.return_value = ["match_id"]
    sheets.save_video({
        "match_id": "m1", "league_id": "L1",
        "uploader_id": "p1", "opponent_id": "p2",
        "storage_url": "https://r2.example.com/video.mp4",
    })
    mock_ws.append_row.assert_called()


# ── _col_letter / _col_num ────────────────────────────────────────────────────

def test_col_letter_single_digits():
    assert _col_letter(1) == "A"
    assert _col_letter(26) == "Z"


def test_col_letter_double_digits():
    assert _col_letter(27) == "AA"
    assert _col_letter(52) == "AZ"
    assert _col_letter(702) == "ZZ"


def test_col_num_single():
    assert _col_num("A") == 1
    assert _col_num("Z") == 26


def test_col_num_double():
    assert _col_num("AA") == 27


def test_col_num_roundtrip():
    for n in [1, 13, 26, 27, 702]:
        assert _col_num(_col_letter(n)) == n


# ── _get_cell ─────────────────────────────────────────────────────────────────

def test_get_cell_returns_value():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    mock_sp = MagicMock()
    mock_sp.values_get.return_value = {"values": [["MyValue"]]}
    fresh._spreadsheet = mock_sp
    assert fresh._get_cell("Sheet1", "A1") == "MyValue"


def test_get_cell_empty_response():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    mock_sp = MagicMock()
    mock_sp.values_get.return_value = {"values": []}
    fresh._spreadsheet = mock_sp
    assert fresh._get_cell("Sheet1", "A1") == ""


# ── _get_range ────────────────────────────────────────────────────────────────

def test_get_range_returns_data():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    mock_sp = MagicMock()
    mock_sp.values_get.return_value = {"values": [["a", "b"], ["c", "d"]]}
    fresh._spreadsheet = mock_sp
    result = fresh._get_range("Sheet1", "A1:B2")
    assert result == [["a", "b"], ["c", "d"]]


# ── _set_cell ─────────────────────────────────────────────────────────────────

def test_set_cell():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    mock_ws = MagicMock()
    with patch.object(fresh, "get_tab", return_value=mock_ws):
        fresh._set_cell("Sheet1", "A1", "NewValue")
    mock_ws.update.assert_called_once_with([["NewValue"]], "A1", value_input_option="USER_ENTERED")


# ── _append_to_range ──────────────────────────────────────────────────────────

def test_append_to_range():
    fresh = SheetsClient.__new__(SheetsClient)
    mock_ws = MagicMock()
    fresh._append_to_range(mock_ws, "A1:Z100", ["x", "y", "z"])
    mock_ws.append_row.assert_called_once_with(
        ["x", "y", "z"], value_input_option="USER_ENTERED", table_range="A1:Z100"
    )


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


# ── get_schedule ──────────────────────────────────────────────────────────────

def test_get_schedule_parses_match():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    week_row = ["Week #1"] + [""] * 12
    match_row = ["", "", "", "", "", "", "TrainerA", "W", "2-0", "vs.", "0-2", "L", "TrainerB"]
    with patch.object(fresh, "_get_range", return_value=[week_row, match_row]):
        result = fresh.get_schedule()
    assert len(result) == 1
    assert result[0]["coach1"] == "TrainerA"
    assert result[0]["week"] == "Week #1"


def test_get_schedule_skips_non_vs_rows():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    week_row = ["Week #2"] + [""] * 12
    match_row = ["", "", "", "", "", "", "TrainerA", "W", "", "bye", "", "", ""]
    with patch.object(fresh, "_get_range", return_value=[week_row, match_row]):
        result = fresh.get_schedule()
    assert len(result) == 0


def test_get_schedule_skips_empty_rows():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    with patch.object(fresh, "_get_range", return_value=[[]]):
        result = fresh.get_schedule()
    assert len(result) == 0


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


# ── get_transactions ──────────────────────────────────────────────────────────

def test_get_transactions_parses_rows():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    raw = [
        ["1", "2", "Trade", "Alice", "Garchomp", "X", "Tyranitar", "Y", "Bob", "Notes"],
        ["", "", "", "", "", "", "", "", "", ""],
    ]
    with patch.object(fresh, "_get_range", return_value=raw):
        result = fresh.get_transactions()
    assert len(result) == 1
    assert result[0]["number"] == "1"
    assert result[0]["coach1"] == "Alice"
    assert result[0]["coach2"] == "Bob"


def test_get_transactions_short_row():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    with patch.object(fresh, "_get_range", return_value=[["1", "3", "FA"]]):
        result = fresh.get_transactions()
    assert len(result) == 1
    assert result[0]["pokemon2"] == ""
    assert result[0]["coach2"] == ""


# ── get_rules / append_rule ───────────────────────────────────────────────────

def test_get_rules_returns_non_empty():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    raw = [["No mega evolution"], [""], ["Terastallize allowed"]]
    with patch.object(fresh, "_get_range", return_value=raw):
        result = fresh.get_rules()
    assert result == ["No mega evolution", "Terastallize allowed"]


def test_append_rule_with_category():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    mock_ws = MagicMock()
    mock_ws.col_values.return_value = ["Header", "Rule 1", "Rule 2"]
    with patch.object(fresh, "get_tab", return_value=mock_ws):
        fresh.append_rule("Battle", "No timeout", "Do not let the timer run out")
    mock_ws.update.assert_called_once()
    args = mock_ws.update.call_args[0]
    assert "[Battle]" in args[1][0][1]


def test_append_rule_without_category():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    mock_ws = MagicMock()
    mock_ws.col_values.return_value = []
    with patch.object(fresh, "get_tab", return_value=mock_ws):
        fresh.append_rule("", "Simple Rule", "Description")
    args = mock_ws.update.call_args[0]
    assert "[" not in args[1][0][1]


# ── get_mvp_race ──────────────────────────────────────────────────────────────

def test_get_mvp_race_finds_record():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    row = ["TrainerAlice"] + [""] * 8 + ["3+2 in LC"]  # 10 elements; value has "+" and "in"
    with patch.object(fresh, "_get_range", return_value=[row]):
        result = fresh.get_mvp_race()
    assert len(result) == 1
    assert result[0]["coach"] == "TrainerAlice"


def test_get_mvp_race_row_too_short():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    with patch.object(fresh, "_get_range", return_value=[["Alice"] * 5]):  # < 10
        result = fresh.get_mvp_race()
    assert result == []


def test_get_mvp_race_no_matching_value():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    row = ["Alice"] + ["NoMatch"] * 9  # has 10 cols but no "+" and "in" together
    with patch.object(fresh, "_get_range", return_value=[row]):
        result = fresh.get_mvp_race()
    assert result == []


# ── get_coach_tab ─────────────────────────────────────────────────────────────

def test_get_coach_tab_found():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    mock_sp = MagicMock()
    mock_ws = MagicMock()
    mock_sp.worksheet.return_value = mock_ws
    mock_ws.get_all_values.return_value = [["a", "b"]] * 5
    fresh._spreadsheet = mock_sp
    result = fresh.get_coach_tab("Alice")
    assert result is not None
    assert result["coach"] == "Alice"
    assert len(result["rows"]) == 5


def test_get_coach_tab_not_found():
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    mock_sp = MagicMock()
    mock_sp.worksheet.side_effect = gspread.WorksheetNotFound
    fresh._spreadsheet = mock_sp
    result = fresh.get_coach_tab("NoCoach")
    assert result is None


# ── LearningSheets ────────────────────────────────────────────────────────────

def test_learning_sheets_enabled_true():
    fresh = LearningSheets.__new__(LearningSheets)
    with patch("src.data.sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = "some-id"
        assert fresh.enabled is True


def test_learning_sheets_enabled_false():
    fresh = LearningSheets.__new__(LearningSheets)
    with patch("src.data.sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = ""
        assert fresh.enabled is False


def test_learning_sheets_connect_success(tmp_path):
    creds_file = tmp_path / "creds.json"
    creds_file.write_text('{"type":"service_account"}')
    fresh = LearningSheets.__new__(LearningSheets)
    fresh._spreadsheet = None
    fresh._client = None
    with patch("src.data.sheets.settings") as ms, \
         patch("src.data.sheets.Credentials.from_service_account_file"), \
         patch("src.data.sheets.gspread.authorize") as mock_auth:
        ms.google_sheets_credentials_file = creds_file
        ms.ml_learning_spreadsheet_id = "sheetid"
        mock_sp = MagicMock()
        mock_sp.title = "Learning"
        mock_auth.return_value.open_by_key.return_value = mock_sp
        fresh._connect()
    assert fresh._spreadsheet is mock_sp


def test_learning_sheets_connect_missing_creds(tmp_path):
    fresh = LearningSheets.__new__(LearningSheets)
    fresh._spreadsheet = None
    fresh._client = None
    with patch("src.data.sheets.settings") as ms:
        ms.google_sheets_credentials_file = tmp_path / "missing.json"
        with pytest.raises(FileNotFoundError):
            fresh._connect()


def test_learning_sheets_spreadsheet_property_calls_connect():
    fresh = LearningSheets.__new__(LearningSheets)
    fresh._spreadsheet = None
    fresh._client = None
    mock_sp = MagicMock()
    with patch.object(fresh, "_connect", side_effect=lambda: setattr(fresh, "_spreadsheet", mock_sp)):
        sp = fresh.spreadsheet
    assert sp is mock_sp


def test_learning_sheets_get_replays_sheet_existing():
    fresh = LearningSheets.__new__(LearningSheets)
    mock_sp = MagicMock()
    mock_ws = MagicMock()
    mock_sp.worksheet.return_value = mock_ws
    fresh._spreadsheet = mock_sp
    result = fresh._get_replays_sheet()
    assert result is mock_ws


def test_learning_sheets_get_replays_sheet_creates_new():
    fresh = LearningSheets.__new__(LearningSheets)
    mock_sp = MagicMock()
    new_ws = MagicMock()
    mock_sp.worksheet.side_effect = gspread.WorksheetNotFound
    mock_sp.add_worksheet.return_value = new_ws
    fresh._spreadsheet = mock_sp
    result = fresh._get_replays_sheet()
    assert result is new_ws
    new_ws.append_row.assert_called_once()


def test_learning_sheets_save_replay_url_disabled():
    fresh = LearningSheets.__new__(LearningSheets)
    with patch("src.data.sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = ""
        fresh.save_replay_url({"format": "gen9ou"})  # should not raise


def test_learning_sheets_save_replay_url_enabled():
    fresh = LearningSheets.__new__(LearningSheets)
    mock_ws = MagicMock()
    with patch("src.data.sheets.settings") as ms, \
         patch.object(fresh, "_get_replays_sheet", return_value=mock_ws):
        ms.ml_learning_spreadsheet_id = "sheetid"
        fresh.save_replay_url({"format": "gen9ou", "replay_url": "http://example.com"})
    mock_ws.append_row.assert_called_once()


def test_learning_sheets_save_replay_url_exception_suppressed():
    fresh = LearningSheets.__new__(LearningSheets)
    with patch("src.data.sheets.settings") as ms, \
         patch.object(fresh, "_get_replays_sheet", side_effect=Exception("network error")):
        ms.ml_learning_spreadsheet_id = "sheetid"
        fresh.save_replay_url({"format": "gen9ou"})  # exception caught internally
