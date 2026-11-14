"""In-memory stand-in for the few gspread calls the Sheets plumbing uses.

Only what src/data/sheet_plumbing.py touches is modelled: worksheet lookup and
creation, row_values / find / append_row / append_rows / update / clear /
get_all_values / get_all_records.  Every worksheet call records the thread it
ran on, so tests can assert that sheet work never runs on the event loop.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import gspread


class FakeWorksheet:
    def __init__(self, title: str, rows: list[list] | None = None) -> None:
        self.title = title
        self.rows: list[list] = [list(r) for r in (rows or [])]
        self.threads: set[int] = set()
        self.fail_next: list[Exception] = []  # raised (one per call) before any op

    def _enter(self) -> None:
        self.threads.add(threading.get_ident())
        if self.fail_next:
            raise self.fail_next.pop(0)

    def row_values(self, n: int) -> list:
        self._enter()
        return list(self.rows[n - 1]) if n <= len(self.rows) else []

    def find(self, query: str, in_column: int | None = None):
        self._enter()
        for i, row in enumerate(self.rows, 1):
            col = in_column or 1
            if len(row) >= col and str(row[col - 1]) == str(query):
                return SimpleNamespace(row=i, col=col)
        return None

    def append_row(self, row: list, value_input_option: str | None = None) -> None:
        self._enter()
        self.rows.append(list(row))

    def append_rows(self, rows: list[list], value_input_option: str | None = None):
        self._enter()
        self.rows.extend(list(r) for r in rows)

    def update(self, range_: str, values: list[list]) -> None:
        """Handles the 'A{n}' and 'A{n}:{col}{n}' ranges the plumbing writes."""
        self._enter()
        row_num = int("".join(ch for ch in range_.split(":")[0] if ch.isdigit()))
        while len(self.rows) < row_num:
            self.rows.append([])
        self.rows[row_num - 1] = list(values[0])

    def clear(self) -> None:
        self._enter()
        self.rows = []

    def get_all_values(self) -> list[list]:
        self._enter()
        return [list(r) for r in self.rows]

    def get_all_records(self, expected_headers: list[str] | None = None) -> list[dict]:
        self._enter()
        if not self.rows:
            return []
        headers = self.rows[0]
        return [dict(zip(headers, row)) for row in self.rows[1:]]


class FakeSpreadsheet:
    title = "Fake League"

    def __init__(self, **tabs: list[list]) -> None:
        self.tabs: dict[str, FakeWorksheet] = {}
        for name, rows in tabs.items():
            self.add(name.replace("_", " "), rows)

    def add(self, title: str, rows: list[list] | None = None) -> FakeWorksheet:
        ws = FakeWorksheet(title, rows)
        self.tabs[title] = ws
        return ws

    def worksheet(self, title: str) -> FakeWorksheet:
        try:
            return self.tabs[title]
        except KeyError:
            raise gspread.WorksheetNotFound(title) from None

    def add_worksheet(self, title: str, rows: int, cols: int) -> FakeWorksheet:
        return self.add(title)


def api_error(status: int) -> gspread.exceptions.APIError:
    """An APIError carrying an HTTP status, as gspread raises on a bad response."""
    response = SimpleNamespace(
        status_code=status,
        text="boom",
        json=lambda: {"error": {"code": status, "message": "boom", "status": "X"}},
    )
    return gspread.exceptions.APIError(response)
