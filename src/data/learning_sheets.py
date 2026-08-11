"""
Master learning spreadsheet — ML training data logging.

Extracted from sheets.py (which had grown past the project's 800-line
guideline). This is a separate spreadsheet from the league sheet
(SheetsClient in sheets.py): set ML_LEARNING_SPREADSHEET_ID in .env.
"""

from __future__ import annotations

import logging

import gspread
from google.oauth2.service_account import Credentials

from src.config import settings
from src.data.sheets import SCOPES, UTC_NOW

log = logging.getLogger(__name__)


# ── Master learning spreadsheet ────────────────────────────────────────────────

REPLAY_HEADERS = [
    "Timestamp",
    "Format",
    "Battle ID",
    "Bot",
    "Opponent",
    "Opponent Type",
    "Winner",
    "Turns",
    "KO Count",
    "Team",
    "Checkpoint",
    "Training Step",
    "Replay URL",
]

TRAINING_RUN_HEADERS = [
    "Timestamp",
    "Format",
    "Phase",
    "Checkpoint",
    "Training Step",
    "Win Rate",
    "Episodes",
    "Mean Reward",
    "Notes",
]

_WINNER_COL = REPLAY_HEADERS.index("Winner")
_FORMAT_COL = REPLAY_HEADERS.index("Format")


class LearningSheets:
    """
    Writes/reads ML training data in the master learning spreadsheet.

    Tabs:
      Replays        — all battles (every format, full history)
      <format>       — per-format battle rows (same schema as Replays)
      Training Runs  — PPO checkpoint metrics logged during training

    Set ML_LEARNING_SPREADSHEET_ID in .env (or leave blank to disable).
    All writes are fire-and-forget: exceptions are caught and logged so a
    bad sheet config never crashes the bot or a training run.
    """

    _instance: "LearningSheets | None" = None
    _client: gspread.Client | None = None
    _spreadsheet: gspread.Spreadsheet | None = None

    def __new__(cls) -> "LearningSheets":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def enabled(self) -> bool:
        return bool(settings.ml_learning_spreadsheet_id)

    def _connect(self) -> None:
        creds_path = settings.google_sheets_credentials_file
        if not creds_path.exists():
            raise FileNotFoundError(f"Google credentials not found: {creds_path}")
        creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
        self._client = gspread.authorize(creds)
        self._spreadsheet = self._client.open_by_key(
            settings.ml_learning_spreadsheet_id
        )
        log.info(f"Connected to learning spreadsheet: '{self._spreadsheet.title}'")

    @property
    def spreadsheet(self) -> gspread.Spreadsheet:
        if self._spreadsheet is None:
            self._connect()
        return self._spreadsheet

    # ── Tab helpers ────────────────────────────────────────────────────

    def _get_replays_sheet(self) -> gspread.Worksheet:
        try:
            return self.spreadsheet.worksheet("Replays")
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(
                title="Replays", rows=10000, cols=len(REPLAY_HEADERS)
            )
            ws.append_row(REPLAY_HEADERS, value_input_option="USER_ENTERED")
            log.info("Created 'Replays' tab in learning spreadsheet")
            return ws

    def _get_format_sheet(self, fmt: str) -> gspread.Worksheet:
        tab = fmt[:100]
        try:
            return self.spreadsheet.worksheet(tab)
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(
                title=tab, rows=10000, cols=len(REPLAY_HEADERS)
            )
            ws.append_row(REPLAY_HEADERS, value_input_option="USER_ENTERED")
            log.info(f"Created '{tab}' tab in learning spreadsheet")
            return ws

    def _get_training_runs_sheet(self) -> gspread.Worksheet:
        try:
            return self.spreadsheet.worksheet("Training Runs")
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(
                title="Training Runs", rows=10000, cols=len(TRAINING_RUN_HEADERS)
            )
            ws.append_row(TRAINING_RUN_HEADERS, value_input_option="USER_ENTERED")
            log.info("Created 'Training Runs' tab in learning spreadsheet")
            return ws

    # ── Write helpers ──────────────────────────────────────────────────

    def _build_replay_row(self, data: dict) -> list:
        return [
            UTC_NOW(),
            data.get("format", ""),
            data.get("battle_id", ""),
            data.get("bot", ""),
            data.get("opponent", ""),
            data.get("opponent_type", ""),
            data.get("winner", ""),
            data.get("turns", ""),
            data.get("ko_count", ""),
            data.get("team", ""),
            data.get("checkpoint", ""),
            data.get("training_step", ""),
            data.get("replay_url", ""),
        ]

    def save_replay_url(self, data: dict) -> None:
        """
        Append a battle row to the Replays tab and the per-format tab.

        Expected keys: format, battle_id, bot, opponent, opponent_type,
                       winner, turns, ko_count, team, checkpoint,
                       training_step, replay_url
        """
        if not self.enabled:
            log.debug("Learning spreadsheet not configured — skipping replay save")
            return
        row = self._build_replay_row(data)
        try:
            ws = self._get_replays_sheet()
            ws.append_row(row, value_input_option="USER_ENTERED")
            log.info(f"Saved replay to Replays tab: {data.get('replay_url', '')}")
        except Exception as exc:
            log.warning(f"Failed to write to Replays tab: {exc}")
        fmt = data.get("format", "")
        if fmt:
            try:
                ws = self._get_format_sheet(fmt)
                ws.append_row(row, value_input_option="USER_ENTERED")
            except Exception as exc:
                log.warning(f"Failed to write to '{fmt}' tab: {exc}")

    def save_training_run(self, data: dict) -> None:
        """
        Append a training checkpoint row to the Training Runs tab.

        Expected keys: format, phase, checkpoint, training_step,
                       win_rate, episodes, mean_reward, notes
        """
        if not self.enabled:
            return
        try:
            ws = self._get_training_runs_sheet()
            ws.append_row(
                [
                    UTC_NOW(),
                    data.get("format", ""),
                    data.get("phase", ""),
                    data.get("checkpoint", ""),
                    data.get("training_step", ""),
                    data.get("win_rate", ""),
                    data.get("episodes", ""),
                    data.get("mean_reward", ""),
                    data.get("notes", ""),
                ],
                value_input_option="USER_ENTERED",
            )
            log.info(
                "[LearningSheets] Saved training run: fmt=%s step=%s win_rate=%s",
                data.get("format", ""),
                data.get("training_step", ""),
                data.get("win_rate", ""),
            )
        except Exception as exc:
            log.warning(f"Failed to save training run: {exc}")

    # ── Read helpers ───────────────────────────────────────────────────

    def get_win_rate(self, fmt: str, last_n: int = 100) -> float | None:
        """Return win rate over the last `last_n` battles for `fmt`, or None if no data."""
        if not self.enabled:
            return None
        try:
            ws = self._get_format_sheet(fmt)
            rows = ws.get_all_values()
            data_rows = rows[1:]  # skip header
            if not data_rows:
                return None
            recent = data_rows[-last_n:]
            wins = sum(
                1 for r in recent if len(r) > _WINNER_COL and r[_WINNER_COL] == "bot"
            )
            return wins / len(recent)
        except Exception as exc:
            log.warning(f"Failed to read win rate for {fmt}: {exc}")
            return None

    def get_latest_checkpoint(self, fmt: str) -> dict | None:
        """Return the most recent Training Runs row for `fmt`, or None."""
        if not self.enabled:
            return None
        try:
            ws = self._get_training_runs_sheet()
            rows = ws.get_all_values()
            if len(rows) < 2:
                return None
            header = rows[0]
            for row in reversed(rows[1:]):
                if len(row) > 1 and row[1] == fmt:
                    return dict(zip(header, row))
            return None
        except Exception as exc:
            log.warning(f"Failed to read latest checkpoint for {fmt}: {exc}")
            return None

    def get_stats_table(self) -> list[dict]:
        """
        Return per-format stats rows for /ml-stats.

        Each entry: format, battles, win_rate, last_checkpoint, last_step, last_trained
        Only formats with at least one battle row are included.
        """
        if not self.enabled:
            return []
        stats: list[dict] = []
        try:
            # Scan Replays tab to discover which formats have data
            replays_ws = self._get_replays_sheet()
            all_rows = replays_ws.get_all_values()
            data_rows = all_rows[1:]
            formats_seen: dict[str, list] = {}
            for r in data_rows:
                fmt = r[_FORMAT_COL] if len(r) > _FORMAT_COL else ""
                if fmt:
                    formats_seen.setdefault(fmt, []).append(r)
        except Exception as exc:
            log.warning(f"Failed to scan Replays tab for stats: {exc}")
            return []

        # Read Training Runs once
        training_by_fmt: dict[str, dict] = {}
        try:
            tr_ws = self._get_training_runs_sheet()
            tr_rows = tr_ws.get_all_values()
            if len(tr_rows) >= 2:
                tr_header = tr_rows[0]
                for row in tr_rows[1:]:
                    if len(row) > 1 and row[1]:
                        training_by_fmt[row[1]] = dict(zip(tr_header, row))
        except Exception as exc:
            log.warning(f"Failed to read Training Runs for stats: {exc}")

        for fmt, rows in sorted(formats_seen.items()):
            recent = rows[-100:]
            wins = sum(
                1 for r in recent if len(r) > _WINNER_COL and r[_WINNER_COL] == "bot"
            )
            win_rate = wins / len(recent) if recent else 0.0
            tr = training_by_fmt.get(fmt, {})
            stats.append(
                {
                    "format": fmt,
                    "battles": len(rows),
                    "win_rate": win_rate,
                    "last_checkpoint": tr.get("Checkpoint", "—"),
                    "last_step": tr.get("Training Step", "—"),
                    "last_trained": tr.get("Timestamp", "—"),
                }
            )
        return stats


# Global singleton
learning_sheets = LearningSheets()
