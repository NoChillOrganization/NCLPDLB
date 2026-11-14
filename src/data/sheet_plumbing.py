"""
Low-level gspread plumbing shared by the League sheet and the Learning sheet.

``SheetConnection`` owns auth, connection, retry and the generic find / upsert /
append operations.  It is synchronous and knows nothing about Tabs, layouts or
which spreadsheet it is — the adapter that composes it supplies the spreadsheet
id and decides how to run it off the event loop.  Adapters hold a connection;
they never inherit from it, so a Learning sheet cannot grow League-only methods.
"""

from __future__ import annotations

import logging
import random as _random
import time as _time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import gspread
import requests.exceptions
from google.oauth2.service_account import Credentials

from src.config import settings

log = logging.getLogger(__name__)

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def UTC_NOW() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _with_retry(fn, *args, max_tries: int = 5, **kwargs):
    """Call fn(*args, **kwargs) with exponential-backoff retry on HTTP 429/503 and transport errors.

    All other errors propagate immediately.
    """
    for attempt in range(max_tries):
        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as exc:
            status = None
            try:
                status = exc.response.status_code
            except AttributeError:
                pass
            if status not in (429, 503) or attempt == max_tries - 1:
                raise
            delay = (2**attempt) + _random.uniform(0, 1)
            log.warning(
                "Sheets API rate-limit (HTTP %s) — retrying in %.1fs (attempt %d/%d)",
                status,
                delay,
                attempt + 1,
                max_tries,
            )
            _time.sleep(delay)
        except requests.exceptions.RequestException as exc:
            if attempt == max_tries - 1:
                raise
            delay = (2**attempt) + _random.uniform(0, 1)
            log.warning(
                "Sheets transport error (%s) — retrying in %.1fs (attempt %d/%d)",
                exc,
                delay,
                attempt + 1,
                max_tries,
            )
            _time.sleep(delay)


def _col_letter(n: int) -> str:
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


class SheetConnection:
    """One lazily-connected spreadsheet plus the generic row operations on it.

    All methods block; callers run them via ``asyncio.to_thread`` (the League
    sheet does so in one place) or from an already-synchronous context.
    """

    def __init__(self, spreadsheet_id: Callable[[], str]) -> None:
        # A callable, not a value, so settings are read at connect time.
        self._spreadsheet_id = spreadsheet_id
        self._client: gspread.Client | None = None
        self._spreadsheet: gspread.Spreadsheet | None = None

    def connect(self) -> None:
        creds_path = settings.google_sheets_credentials_file
        if not creds_path.exists():
            raise FileNotFoundError(
                f"Google credentials not found: {creds_path}\n"
                "Download a service account JSON from Google Cloud Console."
            )
        creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
        self._client = gspread.authorize(creds)
        self._client.set_timeout(30)  # (s) so a stalled Sheets call can't hang forever
        self._spreadsheet = self._client.open_by_key(self._spreadsheet_id())
        log.info(f"Connected to Google Sheets: '{self._spreadsheet.title}'")

    @property
    def spreadsheet(self) -> gspread.Spreadsheet:
        if self._spreadsheet is None:
            self.connect()
        return self._spreadsheet

    def get_tab(
        self, tab_name: str, create: bool = False, headers: list[str] | None = None
    ) -> gspread.Worksheet:
        """Return a worksheet by name.

        Args:
            tab_name: Exact worksheet title.
            create:   If True, create the worksheet when it doesn't exist.
                      Read-only callers must leave this False (default) so a
                      missing tab raises WorksheetNotFound rather than silently
                      creating an empty sheet (H4).
            headers:  When creating, write this header row (sized to fit)
                      instead of the default single-cell title row.
        """
        try:
            return self.spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            if not create:
                raise
            log.warning(f"Tab '{tab_name}' not found — creating it.")
            if headers:
                ws = self.spreadsheet.add_worksheet(
                    title=tab_name, rows=10000, cols=len(headers)
                )
                ws.append_row(headers, value_input_option="USER_ENTERED")
            else:
                ws = self.spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=26)
                ws.append_row([tab_name], value_input_option="USER_ENTERED")
            return ws

    def append_row(self, tab_name: str, row: list[Any]) -> None:
        """Append a row to any tab."""
        ws = self.get_tab(tab_name, create=True)
        _with_retry(ws.append_row, row, value_input_option="USER_ENTERED")

    def replace_rows(self, tab_name: str, rows: list[list[Any]]) -> None:
        """Clear a tab and write *rows* (no retry — a bulk one-off sync)."""
        ws = self.get_tab(tab_name, create=True)
        ws.clear()
        if rows:
            ws.append_rows(rows, value_input_option="USER_ENTERED")

    def upsert_row(
        self, tab_name: str, key_col: str, key_val: str, row_data: list
    ) -> None:
        """Insert or update a row matched by key_col == key_val (positional write).

        Uses ws.find() to locate the row (H10) instead of get_all_records().
        All gspread calls are wrapped with _with_retry for 429/503 backoff (H9).
        """
        ws = self.get_tab(tab_name, create=True)
        headers = _with_retry(ws.row_values, 1)
        if key_col not in headers:
            _with_retry(ws.append_row, row_data, value_input_option="USER_ENTERED")
            return
        key_col_idx = headers.index(key_col) + 1  # 1-based
        cell = _with_retry(ws.find, str(key_val), in_column=key_col_idx)
        if cell is None:
            _with_retry(ws.append_row, row_data, value_input_option="USER_ENTERED")
        else:
            _with_retry(ws.update, f"A{cell.row}", [row_data])

    def upsert_record(
        self,
        tab_name: str,
        key_col: str,
        key_val: str,
        record: dict,
        create: bool = True,
    ) -> None:
        """Header-aware partial-update upsert (H3).

        Reads the header row once, locates the existing row via ws.find (H10),
        merges *only* the keys present in record into the existing row values
        (partial update — other columns are preserved), then writes the merged
        row back.  On insert appends a row built from headers → record mapping.
        """
        ws = self.get_tab(tab_name, create=create)
        headers = _with_retry(ws.row_values, 1)
        if not headers:
            # Bootstrap header row from record keys
            headers = list(record.keys())
            _with_retry(ws.append_row, headers, value_input_option="USER_ENTERED")

        if key_col not in headers:
            row_data = [record.get(h, "") for h in headers]
            _with_retry(ws.append_row, row_data, value_input_option="USER_ENTERED")
            return

        key_col_idx = headers.index(key_col) + 1
        last_col = _col_letter(len(headers))
        cell = _with_retry(ws.find, str(key_val), in_column=key_col_idx)
        if cell is None:
            row_data = [record.get(h, "") for h in headers]
            _with_retry(ws.append_row, row_data, value_input_option="USER_ENTERED")
        else:
            row_num = cell.row
            # Read current row, merge updates, write back (preserves unset columns)
            current = _with_retry(ws.row_values, row_num)
            current = (current + [""] * len(headers))[: len(headers)]
            for i, hdr in enumerate(headers):
                if hdr in record:
                    current[i] = record[hdr]
            _with_retry(ws.update, f"A{row_num}:{last_col}{row_num}", [current])

    def read_all(self, tab_name: str) -> list[dict]:
        """Generic read — returns all records from a tab via gspread get_all_records() (H9)."""
        ws = self.get_tab(tab_name)
        vals = _with_retry(ws.get_all_values)
        if not vals:
            return []
        seen: set[str] = set()
        hdrs: list[str] = []
        for h in vals[0]:
            if h and h not in seen:
                hdrs.append(h)
                seen.add(h)
        return _with_retry(ws.get_all_records, expected_headers=hdrs)

    def find_row(self, tab_name: str, col: str, value: str) -> dict | None:
        """Return the first row where col == value using ws.find() (H10 — avoids full read)."""
        ws = self.get_tab(tab_name)
        headers = _with_retry(ws.row_values, 1)
        if col not in headers:
            return None
        col_idx = headers.index(col) + 1
        cell = _with_retry(ws.find, str(value), in_column=col_idx)
        if cell is None:
            return None
        row_vals = (_with_retry(ws.row_values, cell.row) + [""] * len(headers))[
            : len(headers)
        ]
        return dict(zip(headers, row_vals))
