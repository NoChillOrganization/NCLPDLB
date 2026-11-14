"""Tests for src/data/learning_sheets.py — LearningSheets methods (gspread mocked).

Extracted from test_sheets.py alongside the LearningSheets -> learning_sheets.py
module split (sheets.py had grown past the project's 800-line guideline).
"""

import pytest
from unittest.mock import MagicMock, patch

import gspread
from src.data.learning_sheets import LearningSheets


# ── LearningSheets ────────────────────────────────────────────────────────────


def test_learning_sheets_enabled_true():
    fresh = LearningSheets()
    with patch("src.data.learning_sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = "some-id"
        assert fresh.enabled is True


def test_learning_sheets_enabled_false():
    fresh = LearningSheets()
    with patch("src.data.learning_sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = ""
        assert fresh.enabled is False


def test_learning_sheet_opens_the_learning_spreadsheet_id(tmp_path):
    """The shared plumbing is given the ML id, not the League id."""
    creds_file = tmp_path / "creds.json"
    creds_file.write_text('{"type":"service_account"}')
    with (
        patch("src.data.sheet_plumbing.settings") as plumbing_settings,
        patch("src.data.learning_sheets.settings") as ms,
        patch("src.data.sheet_plumbing.Credentials.from_service_account_file"),
        patch("src.data.sheet_plumbing.gspread.authorize") as mock_auth,
    ):
        plumbing_settings.google_sheets_credentials_file = creds_file
        ms.ml_learning_spreadsheet_id = "ml-id"
        mock_auth.return_value.open_by_key.return_value.title = "Learning"
        LearningSheets()._conn.connect()
    mock_auth.return_value.open_by_key.assert_called_once_with("ml-id")


def test_learning_sheet_does_not_expose_league_methods():
    """Composition, not inheritance: no save_pick / save_transaction on a Learning sheet."""
    ls = LearningSheets()
    for name in ("save_pick", "save_transaction", "save_standing", "find_standing"):
        assert not hasattr(ls, name)


def test_learning_sheets_get_replays_sheet_existing():
    fresh = LearningSheets()
    mock_sp = MagicMock()
    mock_ws = MagicMock()
    mock_sp.worksheet.return_value = mock_ws
    fresh._conn._spreadsheet = mock_sp
    result = fresh._get_replays_sheet()
    assert result is mock_ws


def test_learning_sheets_get_replays_sheet_creates_new():
    fresh = LearningSheets()
    mock_sp = MagicMock()
    new_ws = MagicMock()
    mock_sp.worksheet.side_effect = gspread.WorksheetNotFound
    mock_sp.add_worksheet.return_value = new_ws
    fresh._conn._spreadsheet = mock_sp
    result = fresh._get_replays_sheet()
    assert result is new_ws
    new_ws.append_row.assert_called_once()


def test_learning_sheets_save_replay_url_disabled():
    fresh = LearningSheets()
    with patch("src.data.learning_sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = ""
        fresh.save_replay_url({"format": "gen9ou"})  # should not raise


def test_learning_sheets_save_replay_url_enabled():
    fresh = LearningSheets()
    mock_ws = MagicMock()
    with (
        patch("src.data.learning_sheets.settings") as ms,
        patch.object(fresh, "_get_replays_sheet", return_value=mock_ws),
    ):
        ms.ml_learning_spreadsheet_id = "sheetid"
        fresh.save_replay_url({"format": "gen9ou", "replay_url": "http://example.com"})
    mock_ws.append_row.assert_called_once()


def test_learning_sheets_save_replay_url_exception_suppressed():
    fresh = LearningSheets()
    with (
        patch("src.data.learning_sheets.settings") as ms,
        patch.object(
            fresh, "_get_replays_sheet", side_effect=Exception("network error")
        ),
    ):
        ms.ml_learning_spreadsheet_id = "sheetid"
        fresh.save_replay_url({"format": "gen9ou"})  # exception caught internally


# ── LearningSheets — new methods ───────────────────────────────────────────────


def _fresh_ls():
    """Return an unconnected LearningSheets instance (no Google connection yet)."""
    inst = LearningSheets()
    inst._conn._spreadsheet = None
    inst._conn._client = None
    return inst


def test_learning_sheets_build_replay_row():
    fresh = _fresh_ls()
    data = {
        "format": "gen9ou",
        "battle_id": "b1",
        "bot": "bot",
        "opponent": "opp",
        "opponent_type": "human",
        "winner": "bot",
        "turns": 20,
        "ko_count": 3,
        "team": "Pikachu",
        "checkpoint": "model.zip",
        "training_step": "1000",
        "replay_url": "http://example.com",
    }
    row = fresh._build_replay_row(data)
    assert len(row) == 13
    assert row[1] == "gen9ou"
    assert row[6] == "bot"  # Winner
    assert row[12] == "http://example.com"  # Replay URL


def test_learning_sheets_get_format_sheet_existing():
    fresh = _fresh_ls()
    mock_sp = MagicMock()
    mock_ws = MagicMock()
    mock_sp.worksheet.return_value = mock_ws
    fresh._conn._spreadsheet = mock_sp
    result = fresh._get_format_sheet("gen9ou")
    assert result is mock_ws
    mock_sp.add_worksheet.assert_not_called()


def test_learning_sheets_get_format_sheet_creates_new():
    fresh = _fresh_ls()
    mock_sp = MagicMock()
    new_ws = MagicMock()
    mock_sp.worksheet.side_effect = gspread.WorksheetNotFound
    mock_sp.add_worksheet.return_value = new_ws
    fresh._conn._spreadsheet = mock_sp
    result = fresh._get_format_sheet("gen9ou")
    assert result is new_ws
    new_ws.append_row.assert_called_once()


def test_learning_sheets_get_training_runs_sheet_existing():
    fresh = _fresh_ls()
    mock_sp = MagicMock()
    mock_ws = MagicMock()
    mock_sp.worksheet.return_value = mock_ws
    fresh._conn._spreadsheet = mock_sp
    result = fresh._get_training_runs_sheet()
    assert result is mock_ws


def test_learning_sheets_get_training_runs_sheet_creates_new():
    fresh = _fresh_ls()
    mock_sp = MagicMock()
    new_ws = MagicMock()
    mock_sp.worksheet.side_effect = gspread.WorksheetNotFound
    mock_sp.add_worksheet.return_value = new_ws
    fresh._conn._spreadsheet = mock_sp
    result = fresh._get_training_runs_sheet()
    assert result is new_ws
    new_ws.append_row.assert_called_once()


def test_learning_sheets_save_training_run_disabled():
    fresh = _fresh_ls()
    with patch("src.data.learning_sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = ""
        fresh.save_training_run({"format": "gen9ou"})  # should not raise


def test_learning_sheets_save_training_run_enabled():
    fresh = _fresh_ls()
    mock_ws = MagicMock()
    with (
        patch("src.data.learning_sheets.settings") as ms,
        patch.object(fresh, "_get_training_runs_sheet", return_value=mock_ws),
    ):
        ms.ml_learning_spreadsheet_id = "sheetid"
        fresh.save_training_run(
            {
                "format": "gen9ou",
                "phase": "selfplay",
                "checkpoint": "model.zip",
                "training_step": 500,
                "win_rate": 0.6,
                "episodes": 100,
                "mean_reward": 1.2,
                "notes": "swap #1",
            }
        )
    mock_ws.append_row.assert_called_once()
    row = mock_ws.append_row.call_args[0][0]
    assert row[1] == "gen9ou"
    assert row[2] == "selfplay"
    assert row[5] == 0.6


def test_learning_sheets_save_training_run_exception_suppressed():
    fresh = _fresh_ls()
    with (
        patch("src.data.learning_sheets.settings") as ms,
        patch.object(fresh, "_get_training_runs_sheet", side_effect=Exception("err")),
    ):
        ms.ml_learning_spreadsheet_id = "sheetid"
        fresh.save_training_run({"format": "gen9ou"})  # exception caught internally


def test_learning_sheets_get_stats_table_disabled():
    fresh = _fresh_ls()
    with patch("src.data.learning_sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = ""
        assert fresh.get_stats_table() == []


def test_learning_sheets_get_stats_table_with_data():
    from src.data.learning_sheets import (
        REPLAY_HEADERS,
        TRAINING_RUN_HEADERS,
        _FORMAT_COL,
        _WINNER_COL,
    )

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
    tr_row = [
        "2026-01-01",
        "gen9ou",
        "final",
        "ckpt.zip",
        "3000",
        "0.67",
        "300",
        "1.8",
        "",
    ]
    training_ws.get_all_values.return_value = [TRAINING_RUN_HEADERS, tr_row]

    with (
        patch("src.data.learning_sheets.settings") as ms,
        patch.object(fresh, "_get_replays_sheet", return_value=replays_ws),
        patch.object(fresh, "_get_training_runs_sheet", return_value=training_ws),
    ):
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
