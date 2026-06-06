"""Tests for src/data/sheets.py — SheetsClient methods (gspread mocked)."""
import pytest
from unittest.mock import MagicMock, patch

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
         patch("src.data.sheets.Credentials.from_service_account_file"), \
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
    result = fresh.get_tab(Tab.SETUP, create=True)
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
    mock_ws.row_values.return_value = ["player_id"]
    mock_ws.find.return_value = None
    sheets.update_pool_roster("A", {"player_id": "p1", "player_name": "Alice", "team_name": "Team A"}, ["Garchomp"])
    mock_ws.append_row.assert_called()


def test_update_pool_roster_pool_b(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["player_id"]
    mock_ws.find.return_value = None
    sheets.update_pool_roster("B", {"player_id": "p2", "player_name": "Bob", "team_name": "Team B"}, [])
    mock_ws.append_row.assert_called()


def test_save_schedule_match(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["match_id"]
    mock_ws.find.return_value = None
    sheets.save_schedule_match({"match_id": "m1", "week": 1, "player1_id": "p1", "player2_id": "p2"})
    mock_ws.append_row.assert_called()


def test_save_match_stats(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["match_id"]
    mock_ws.find.return_value = None
    sheets.save_match_stats({
        "match_id": "m1", "league_id": "L1",
        "p1_team": ["Garchomp"], "p2_team": ["Corviknight"],
    })
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
    mock_ws.row_values.return_value = ["stat_id"]
    mock_ws.find.return_value = None
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
    mock_ws.row_values.return_value = ["transaction_id"]
    mock_ws.find.return_value = None
    sheets.save_transaction({"transaction_id": "t1", "type": "trade", "status": "pending"})
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
    mock_ws.row_values.return_value = ["player_id"]
    mock_ws.find.return_value = None
    sheets.upsert_team_page({
        "player_id": "p1", "player_name": "Alice", "team_name": "Team A",
        "slots": [("Garchomp", "Dragon"), ("Corviknight", "Flying")],
    })
    mock_ws.append_row.assert_called()


def test_upsert_team_page_no_slots(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["player_id"]
    mock_ws.find.return_value = None
    sheets.upsert_team_page({"player_id": "p1", "player_name": "Alice", "team_name": "T"})
    mock_ws.append_row.assert_called()


def test_set_data(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["key"]
    mock_ws.find.return_value = None
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
    """save_replay updates an existing replay row when replay_id found."""
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["replay_id"]
    # find() returns a cell → update path (not None → not append)
    sheets.save_replay({
        "replay_id": "r1", "match_id": "m1", "url": "https://replay.ps.com/r1",
        "p1_team": ["Garchomp"], "p2_team": ["Corviknight"], "turns": 25,
    })
    mock_ws.update.assert_called()


def test_save_video(patched_get_tab):
    mock_ws, _ = patched_get_tab
    mock_ws.row_values.return_value = ["match_id"]
    mock_ws.find.return_value = None
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


def test_get_schedule_pads_short_rows():
    """Rows with fewer than 13 elements are padded with empty strings."""
    fresh = SheetsClient.__new__(SheetsClient)
    fresh._client = None
    fresh._spreadsheet = MagicMock()
    week_row = ["Week #1"] + [""] * 12
    # Only 10 columns — triggers the row padding branch (line 250)
    short_row = ["", "", "", "", "", "", "TrainerA", "W", "2-0", "vs."]
    with patch.object(fresh, "_get_range", return_value=[week_row, short_row]):
        result = fresh.get_schedule()
    # coach1="TrainerA", vs_="vs." → match is appended
    assert len(result) == 1
    assert result[0]["coach1"] == "TrainerA"


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
            ["Name", "Score", "Name"],   # "Name" appears twice — deduplicated
            ["Alice", "10", "Alice"],
        ]
        mock_ws.get_all_records.return_value = [{"Name": "Alice", "Score": "10"}]
        result = sheets.read_all("SomeTab")
        call_kwargs = mock_ws.get_all_records.call_args[1]
        assert call_kwargs["expected_headers"] == ["Name", "Score"]
        assert result == [{"Name": "Alice", "Score": "10"}]


# ── LearningSheets — new methods ───────────────────────────────────────────────

def _fresh_ls():
    """Return an unconnected LearningSheets instance (bypasses __new__ singleton)."""
    inst = LearningSheets.__new__(LearningSheets)
    inst._spreadsheet = None
    inst._client = None
    return inst


def test_learning_sheets_build_replay_row():
    fresh = _fresh_ls()
    data = {
        "format": "gen9ou", "battle_id": "b1", "bot": "bot", "opponent": "opp",
        "opponent_type": "human", "winner": "bot", "turns": 20, "ko_count": 3,
        "team": "Pikachu", "checkpoint": "model.zip", "training_step": "1000",
        "replay_url": "http://example.com",
    }
    row = fresh._build_replay_row(data)
    assert len(row) == 13
    assert row[1] == "gen9ou"
    assert row[6] == "bot"      # Winner
    assert row[12] == "http://example.com"  # Replay URL


def test_learning_sheets_get_format_sheet_existing():
    fresh = _fresh_ls()
    mock_sp = MagicMock()
    mock_ws = MagicMock()
    mock_sp.worksheet.return_value = mock_ws
    fresh._spreadsheet = mock_sp
    result = fresh._get_format_sheet("gen9ou")
    assert result is mock_ws
    mock_sp.add_worksheet.assert_not_called()


def test_learning_sheets_get_format_sheet_creates_new():
    fresh = _fresh_ls()
    mock_sp = MagicMock()
    new_ws = MagicMock()
    mock_sp.worksheet.side_effect = gspread.WorksheetNotFound
    mock_sp.add_worksheet.return_value = new_ws
    fresh._spreadsheet = mock_sp
    result = fresh._get_format_sheet("gen9ou")
    assert result is new_ws
    new_ws.append_row.assert_called_once()


def test_learning_sheets_get_training_runs_sheet_existing():
    fresh = _fresh_ls()
    mock_sp = MagicMock()
    mock_ws = MagicMock()
    mock_sp.worksheet.return_value = mock_ws
    fresh._spreadsheet = mock_sp
    result = fresh._get_training_runs_sheet()
    assert result is mock_ws


def test_learning_sheets_get_training_runs_sheet_creates_new():
    fresh = _fresh_ls()
    mock_sp = MagicMock()
    new_ws = MagicMock()
    mock_sp.worksheet.side_effect = gspread.WorksheetNotFound
    mock_sp.add_worksheet.return_value = new_ws
    fresh._spreadsheet = mock_sp
    result = fresh._get_training_runs_sheet()
    assert result is new_ws
    new_ws.append_row.assert_called_once()


def test_learning_sheets_save_training_run_disabled():
    fresh = _fresh_ls()
    with patch("src.data.sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = ""
        fresh.save_training_run({"format": "gen9ou"})  # should not raise


def test_learning_sheets_save_training_run_enabled():
    fresh = _fresh_ls()
    mock_ws = MagicMock()
    with patch("src.data.sheets.settings") as ms, \
         patch.object(fresh, "_get_training_runs_sheet", return_value=mock_ws):
        ms.ml_learning_spreadsheet_id = "sheetid"
        fresh.save_training_run({
            "format": "gen9ou", "phase": "selfplay", "checkpoint": "model.zip",
            "training_step": 500, "win_rate": 0.6, "episodes": 100,
            "mean_reward": 1.2, "notes": "swap #1",
        })
    mock_ws.append_row.assert_called_once()
    row = mock_ws.append_row.call_args[0][0]
    assert row[1] == "gen9ou"
    assert row[2] == "selfplay"
    assert row[5] == 0.6


def test_learning_sheets_save_training_run_exception_suppressed():
    fresh = _fresh_ls()
    with patch("src.data.sheets.settings") as ms, \
         patch.object(fresh, "_get_training_runs_sheet", side_effect=Exception("err")):
        ms.ml_learning_spreadsheet_id = "sheetid"
        fresh.save_training_run({"format": "gen9ou"})  # exception caught internally


def test_learning_sheets_get_win_rate_disabled():
    fresh = _fresh_ls()
    with patch("src.data.sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = ""
        assert fresh.get_win_rate("gen9ou") is None


def test_learning_sheets_get_win_rate_no_data():
    fresh = _fresh_ls()
    mock_ws = MagicMock()
    mock_ws.get_all_values.return_value = [["Timestamp", "Format", "Winner"]]  # header only
    with patch("src.data.sheets.settings") as ms, \
         patch.object(fresh, "_get_format_sheet", return_value=mock_ws):
        ms.ml_learning_spreadsheet_id = "sheetid"
        assert fresh.get_win_rate("gen9ou") is None


def test_learning_sheets_get_win_rate_with_data():
    from src.data.sheets import REPLAY_HEADERS, _WINNER_COL
    fresh = _fresh_ls()
    mock_ws = MagicMock()
    # Build rows: 3 bot wins, 2 losses (5 total)
    winner_idx = _WINNER_COL
    def make_row(winner):
        row = [""] * len(REPLAY_HEADERS)
        row[winner_idx] = winner
        return row
    rows = [REPLAY_HEADERS] + [make_row("bot")] * 3 + [make_row("opponent")] * 2
    mock_ws.get_all_values.return_value = rows
    with patch("src.data.sheets.settings") as ms, \
         patch.object(fresh, "_get_format_sheet", return_value=mock_ws):
        ms.ml_learning_spreadsheet_id = "sheetid"
        result = fresh.get_win_rate("gen9ou")
    assert result == pytest.approx(0.6)


def test_learning_sheets_get_latest_checkpoint_disabled():
    fresh = _fresh_ls()
    with patch("src.data.sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = ""
        assert fresh.get_latest_checkpoint("gen9ou") is None


def test_learning_sheets_get_latest_checkpoint_no_rows():
    fresh = _fresh_ls()
    mock_ws = MagicMock()
    mock_ws.get_all_values.return_value = []
    with patch("src.data.sheets.settings") as ms, \
         patch.object(fresh, "_get_training_runs_sheet", return_value=mock_ws):
        ms.ml_learning_spreadsheet_id = "sheetid"
        assert fresh.get_latest_checkpoint("gen9ou") is None


def test_learning_sheets_get_latest_checkpoint_found():
    from src.data.sheets import TRAINING_RUN_HEADERS
    fresh = _fresh_ls()
    mock_ws = MagicMock()
    row = ["2026-01-01", "gen9ou", "final", "model.zip", "2000", "0.7", "200", "1.5", ""]
    mock_ws.get_all_values.return_value = [TRAINING_RUN_HEADERS, row]
    with patch("src.data.sheets.settings") as ms, \
         patch.object(fresh, "_get_training_runs_sheet", return_value=mock_ws):
        ms.ml_learning_spreadsheet_id = "sheetid"
        result = fresh.get_latest_checkpoint("gen9ou")
    assert result is not None
    assert result["Format"] == "gen9ou"
    assert result["Phase"] == "final"


def test_learning_sheets_get_latest_checkpoint_format_not_found():
    from src.data.sheets import TRAINING_RUN_HEADERS
    fresh = _fresh_ls()
    mock_ws = MagicMock()
    row = ["2026-01-01", "gen9uu", "final", "model.zip", "2000", "0.7", "200", "1.5", ""]
    mock_ws.get_all_values.return_value = [TRAINING_RUN_HEADERS, row]
    with patch("src.data.sheets.settings") as ms, \
         patch.object(fresh, "_get_training_runs_sheet", return_value=mock_ws):
        ms.ml_learning_spreadsheet_id = "sheetid"
        assert fresh.get_latest_checkpoint("gen9ou") is None


def test_learning_sheets_get_stats_table_disabled():
    fresh = _fresh_ls()
    with patch("src.data.sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = ""
        assert fresh.get_stats_table() == []


def test_learning_sheets_get_stats_table_with_data():
    from src.data.sheets import REPLAY_HEADERS, TRAINING_RUN_HEADERS, _FORMAT_COL, _WINNER_COL
    fresh = _fresh_ls()
    replays_ws = MagicMock()
    training_ws = MagicMock()

    def make_replay(fmt, winner):
        row = [""] * len(REPLAY_HEADERS)
        row[_FORMAT_COL] = fmt
        row[_WINNER_COL] = winner
        return row

    replays_ws.get_all_values.return_value = [
        REPLAY_HEADERS,
        make_replay("gen9ou", "bot"),
        make_replay("gen9ou", "bot"),
        make_replay("gen9ou", "opponent"),
        make_replay("gen9uu", "bot"),
    ]
    tr_row = ["2026-01-01", "gen9ou", "final", "ckpt.zip", "3000", "0.67", "300", "1.8", ""]
    training_ws.get_all_values.return_value = [TRAINING_RUN_HEADERS, tr_row]

    with patch("src.data.sheets.settings") as ms, \
         patch.object(fresh, "_get_replays_sheet", return_value=replays_ws), \
         patch.object(fresh, "_get_training_runs_sheet", return_value=training_ws):
        ms.ml_learning_spreadsheet_id = "sheetid"
        stats = fresh.get_stats_table()

    assert len(stats) == 2
    ou = next(s for s in stats if s["format"] == "gen9ou")
    assert ou["battles"] == 3
    assert ou["win_rate"] == pytest.approx(2 / 3)
    assert ou["last_checkpoint"] == "ckpt.zip"
    uu = next(s for s in stats if s["format"] == "gen9uu")
    assert uu["battles"] == 1
    assert uu["last_checkpoint"] == "—"
