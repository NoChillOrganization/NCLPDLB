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
    fresh = LearningSheets.__new__(LearningSheets)
    with patch("src.data.learning_sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = "some-id"
        assert fresh.enabled is True


def test_learning_sheets_enabled_false():
    fresh = LearningSheets.__new__(LearningSheets)
    with patch("src.data.learning_sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = ""
        assert fresh.enabled is False


def test_learning_sheets_connect_success(tmp_path):
    creds_file = tmp_path / "creds.json"
    creds_file.write_text('{"type":"service_account"}')
    fresh = LearningSheets.__new__(LearningSheets)
    fresh._spreadsheet = None
    fresh._client = None
    with (
        patch("src.data.learning_sheets.settings") as ms,
        patch("src.data.learning_sheets.Credentials.from_service_account_file"),
        patch("src.data.learning_sheets.gspread.authorize") as mock_auth,
    ):
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
    with patch("src.data.learning_sheets.settings") as ms:
        ms.google_sheets_credentials_file = tmp_path / "missing.json"
        with pytest.raises(FileNotFoundError):
            fresh._connect()


def test_learning_sheets_spreadsheet_property_calls_connect():
    fresh = LearningSheets.__new__(LearningSheets)
    fresh._spreadsheet = None
    fresh._client = None
    mock_sp = MagicMock()
    with patch.object(
        fresh, "_connect", side_effect=lambda: setattr(fresh, "_spreadsheet", mock_sp)
    ):
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
    with patch("src.data.learning_sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = ""
        fresh.save_replay_url({"format": "gen9ou"})  # should not raise


def test_learning_sheets_save_replay_url_enabled():
    fresh = LearningSheets.__new__(LearningSheets)
    mock_ws = MagicMock()
    with (
        patch("src.data.learning_sheets.settings") as ms,
        patch.object(fresh, "_get_replays_sheet", return_value=mock_ws),
    ):
        ms.ml_learning_spreadsheet_id = "sheetid"
        fresh.save_replay_url({"format": "gen9ou", "replay_url": "http://example.com"})
    mock_ws.append_row.assert_called_once()


def test_learning_sheets_save_replay_url_exception_suppressed():
    fresh = LearningSheets.__new__(LearningSheets)
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
    """Return an unconnected LearningSheets instance (bypasses __new__ singleton)."""
    inst = LearningSheets.__new__(LearningSheets)
    inst._spreadsheet = None
    inst._client = None
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


def test_learning_sheets_get_win_rate_disabled():
    fresh = _fresh_ls()
    with patch("src.data.learning_sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = ""
        assert fresh.get_win_rate("gen9ou") is None


def test_learning_sheets_get_win_rate_no_data():
    fresh = _fresh_ls()
    mock_ws = MagicMock()
    mock_ws.get_all_values.return_value = [
        ["Timestamp", "Format", "Winner"]
    ]  # header only
    with (
        patch("src.data.learning_sheets.settings") as ms,
        patch.object(fresh, "_get_format_sheet", return_value=mock_ws),
    ):
        ms.ml_learning_spreadsheet_id = "sheetid"
        assert fresh.get_win_rate("gen9ou") is None


def test_learning_sheets_get_win_rate_with_data():
    from src.data.learning_sheets import REPLAY_HEADERS, _WINNER_COL

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
    with (
        patch("src.data.learning_sheets.settings") as ms,
        patch.object(fresh, "_get_format_sheet", return_value=mock_ws),
    ):
        ms.ml_learning_spreadsheet_id = "sheetid"
        result = fresh.get_win_rate("gen9ou")
    assert result == pytest.approx(0.6)


def test_learning_sheets_get_latest_checkpoint_disabled():
    fresh = _fresh_ls()
    with patch("src.data.learning_sheets.settings") as ms:
        ms.ml_learning_spreadsheet_id = ""
        assert fresh.get_latest_checkpoint("gen9ou") is None


def test_learning_sheets_get_latest_checkpoint_no_rows():
    fresh = _fresh_ls()
    mock_ws = MagicMock()
    mock_ws.get_all_values.return_value = []
    with (
        patch("src.data.learning_sheets.settings") as ms,
        patch.object(fresh, "_get_training_runs_sheet", return_value=mock_ws),
    ):
        ms.ml_learning_spreadsheet_id = "sheetid"
        assert fresh.get_latest_checkpoint("gen9ou") is None


def test_learning_sheets_get_latest_checkpoint_found():
    from src.data.learning_sheets import TRAINING_RUN_HEADERS

    fresh = _fresh_ls()
    mock_ws = MagicMock()
    row = [
        "2026-01-01",
        "gen9ou",
        "final",
        "model.zip",
        "2000",
        "0.7",
        "200",
        "1.5",
        "",
    ]
    mock_ws.get_all_values.return_value = [TRAINING_RUN_HEADERS, row]
    with (
        patch("src.data.learning_sheets.settings") as ms,
        patch.object(fresh, "_get_training_runs_sheet", return_value=mock_ws),
    ):
        ms.ml_learning_spreadsheet_id = "sheetid"
        result = fresh.get_latest_checkpoint("gen9ou")
    assert result is not None
    assert result["Format"] == "gen9ou"
    assert result["Phase"] == "final"


def test_learning_sheets_get_latest_checkpoint_format_not_found():
    from src.data.learning_sheets import TRAINING_RUN_HEADERS

    fresh = _fresh_ls()
    mock_ws = MagicMock()
    row = [
        "2026-01-01",
        "gen9uu",
        "final",
        "model.zip",
        "2000",
        "0.7",
        "200",
        "1.5",
        "",
    ]
    mock_ws.get_all_values.return_value = [TRAINING_RUN_HEADERS, row]
    with (
        patch("src.data.learning_sheets.settings") as ms,
        patch.object(fresh, "_get_training_runs_sheet", return_value=mock_ws),
    ):
        ms.ml_learning_spreadsheet_id = "sheetid"
        assert fresh.get_latest_checkpoint("gen9ou") is None


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
