"""
Google Sheets data layer — matched to the actual "No Chill League" spreadsheet visual template.

The spreadsheet uses visual templates (not flat database tables).  Each tab has its own
cell-specific layout.  Methods here read/write to the correct positions.

Key layout discoveries (from inspect_writable_tabs.py):
  Setup         — config values in column H (H5=League Name, H7=Budget, H8=FA limit,
                  H9=Mechanic, H16=Weeks, H18=Current Week); coach list in L5:N (col L=name, M=team, N=logo)
  Standings     — visual template; 2 rows/team starting row 6; col F=team+coach, col U=record
  Schedule      — visual template; col J=Coach1, K=result, L=score, M=vs, N=score, O=result, P=Coach2;
                  week labels in col D
  Match Stats   — 168-col visual template; week blocks side-by-side (Week 1 @col D, Week 2 @col O, …);
                  per-match: row 0=coaches, rows 1-6=Pokémon (col E=name, F=K, G=D, I=D, J=K, K=name)
  Transactions  — near-flat; headers row 3 (D=#, E=W., F=Event, G=Coach1, H=Poke1, J=Poke2, L=Coach2, M=Notes);
                  data starts row 6
  Pokédex       — headers row 1 (B=GH name, C=Smogon name, D=PMD ref, F=Pts, I=Pokémon, J=Type1, K=Type2,
                  L=HP, M=Atk, N=Def, O=SpA, P=SpD, Q=Spe, V=Sprite); data from row 3
  Rules         — visual template; rules in col E starting row 4 (col D has ✵ bullets)
  MVP Race      — formula-driven view of Data tab; read-only
  Pokémon Stats — formula-driven view of Data tab; read-only

Uses gspread synchronously (run in executor for async contexts).
"""

from __future__ import annotations

import logging
import random as _random
import time as _time
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


# ── Tab names (exact Unicode match to spreadsheet) ─────────────────────────────


class Tab:
    SETUP = "Setup"
    RULES = "Rules"
    COVER = "Cover"
    DRAFT = "Draft"
    DRAFT_BOARD = "Draft Board"
    POOL_A = "Pool A Board"
    POOL_B = "Pool B Board"
    SCHEDULE = "Schedule"
    MATCH_STATS = "Match Stats"  # visual template — read-only via get_match_results()
    MATCH_RECORDS = (
        "Match Records"  # flat tab: match/replay/video rows written by the bot
    )
    STANDINGS = "Standings"  # visual template — read-only via get_standings_visual()
    ELO_DATA = "ELO Data"  # flat tab: ELO records written/read by EloService
    POKEMON_STATS = "Pokémon Stats"
    MVP_RACE = "MVP Race"
    TRANSACTIONS = "Transactions"
    PLAYOFFS = "Playoffs"
    POKEDEX = "Pokédex"
    TEAM_TEMPLATE = "Team Page Template"
    DATA = "Data"


# ── Helper: column letter ↔ number ─────────────────────────────────────────────


def _col_letter(n: int) -> str:
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


# ── Client ─────────────────────────────────────────────────────────────────────


class SheetsClient:
    """Singleton Google Sheets client for the No Chill League spreadsheet."""

    _instance: SheetsClient | None = None
    _client: gspread.Client | None = None
    _spreadsheet: gspread.Spreadsheet | None = None

    def __new__(cls) -> SheetsClient:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

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
        self._spreadsheet = self._client.open_by_key(
            settings.google_sheets_spreadsheet_id
        )
        log.info(f"Connected to Google Sheets: '{self._spreadsheet.title}'")

    @property
    def spreadsheet(self) -> gspread.Spreadsheet:
        if self._spreadsheet is None:
            self.connect()
        return self._spreadsheet

    def get_tab(self, tab_name: str, create: bool = False) -> gspread.Worksheet:
        """Return a worksheet by name.

        Args:
            tab_name: Exact worksheet title.
            create:   If True, create the worksheet when it doesn't exist.
                      Read-only callers must leave this False (default) so a
                      missing tab raises WorksheetNotFound rather than silently
                      creating an empty sheet (H4).
        """
        try:
            return self.spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            if not create:
                raise
            log.warning(f"Tab '{tab_name}' not found — creating it.")
            ws = self.spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=26)
            ws.append_row([tab_name], value_input_option="USER_ENTERED")
            return ws

    def _get_range(self, tab_name: str, range_: str) -> list[list[str]]:
        """Read a range returning a 2D list (empty strings for empty cells)."""
        result = self.spreadsheet.values_get(
            f"'{tab_name}'!{range_}",
            params={"valueRenderOption": "FORMATTED_VALUE"},
        )
        return result.get("values", [])

    # ── Generic helpers ───────────────────────────────────────────────────────

    def append_row(self, tab_name: str, row: list[Any]) -> None:
        """Append a row to any tab."""
        ws = self.get_tab(tab_name, create=True)
        _with_retry(ws.append_row, row, value_input_option="USER_ENTERED")

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

    def _upsert_record(
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

    def find_rows(self, tab_name: str, col: str, value: str) -> list[dict]:
        """Return all rows where col == value."""
        return [r for r in self.read_all(tab_name) if str(r.get(col, "")) == str(value)]

    # ── Setup tab ─────────────────────────────────────────────────────────────

    def get_league_setup(self, server_id: str | None = None) -> dict | None:
        """Return league setup dict, optionally filtered by server_id."""
        if server_id:
            return self.find_row(Tab.SETUP, "server_id", server_id)
        rows = self.read_all(Tab.SETUP)
        return rows[0] if rows else {}

    def save_league_setup(self, data: dict) -> None:
        """Write editable Setup values."""
        row_data = [
            data.get("league_id", ""),
            data.get("server_id", ""),
            data.get("league_name", ""),
            data.get("commissioner_id", ""),
            data.get("commissioner_name", ""),
            UTC_NOW(),
        ]
        self.upsert_row(Tab.SETUP, "server_id", data.get("server_id", ""), row_data)

    # ── Standings tab ─────────────────────────────────────────────────────────

    def get_standings(self, pool: str | None = None) -> list[dict]:
        """Return ELO standings rows from the flat ELO Data tab."""
        rows = self.read_all(Tab.ELO_DATA)
        if pool:
            rows = [r for r in rows if str(r.get("pool", "")) == str(pool)]
        return rows

    def upsert_standing(self, standing: dict) -> None:
        """Insert or update an ELO standing row in the flat ELO Data tab."""
        row_data = [
            standing.get("player_id", ""),
            standing.get("player_name", ""),
            standing.get("elo", ""),
            standing.get("wins", ""),
            standing.get("losses", ""),
            standing.get("streak", ""),
            UTC_NOW(),
        ]
        self.upsert_row(
            Tab.ELO_DATA, "player_id", standing.get("player_id", ""), row_data
        )

    # ── Schedule tab ──────────────────────────────────────────────────────────
    #
    # Layout (cols J=Coach1, K=result, L=score, M=vs, N=score, O=result, P=Coach2):
    #   Row 5: "Week #1" label in col D
    #   Rows 6-13: match rows for week 1

    def save_schedule_match(self, match: dict) -> None:
        """Write a scheduled match row."""
        row_data = [
            match.get("match_id", ""),
            match.get("week", ""),
            match.get("player1_id", ""),
            match.get("player1_name", ""),
            match.get("player2_id", ""),
            match.get("player2_name", ""),
            UTC_NOW(),
        ]
        self.upsert_row(Tab.SCHEDULE, "match_id", match.get("match_id", ""), row_data)

    # ── Match Stats tab ───────────────────────────────────────────────────────

    def get_match_results(self, week: int | None = None) -> list[dict]:
        """Read match results from Match Stats visual template."""
        d_col = self._get_range(Tab.MATCH_STATS, "D3:D152")
        week_rows: list[tuple[int, str]] = []
        for i, row in enumerate(d_col, 3):
            v = row[0].strip() if row else ""
            if v.startswith("Week"):
                week_rows.append((i, v))

        results = []
        for _wi, (wrow, wlabel) in enumerate(week_rows):
            if week is not None and f"#{week}" not in wlabel:
                continue
            match_start = wrow + 1
            match_raw = self._get_range(
                Tab.MATCH_STATS, f"E{match_start}:K{match_start + 80}"
            )
            i = 0
            while i < len(match_raw):
                row = match_raw[i]
                coach1 = row[0].strip() if len(row) > 0 else ""
                result1 = row[2].strip() if len(row) > 2 else ""
                result2 = row[6].strip() if len(row) > 6 else ""
                coach2 = row[7].strip() if len(row) > 7 else ""
                if coach1 and result1 in {"W", "L", "DF", ""}:
                    winner = (
                        coach1 if result1 == "W" else (coach2 if result2 == "W" else "")
                    )
                    results.append(
                        {
                            "week": wlabel,
                            "coach1": coach1,
                            "coach2": coach2,
                            "winner": winner,
                            "result1": result1,
                            "result2": result2,
                        }
                    )
                    i += 9
                else:
                    i += 1
        return results

    def save_match_stats(self, match: dict) -> None:
        """Write match stats row to the flat Match Records tab."""
        row_data = [
            match.get("match_id", ""),
            match.get("league_id", ""),
            str(match.get("p1_team", [])),
            str(match.get("p2_team", [])),
            UTC_NOW(),
        ]
        self.upsert_row(
            Tab.MATCH_RECORDS, "match_id", match.get("match_id", ""), row_data
        )

    def save_replay(self, replay: dict) -> None:
        """Append a replay row to the flat Match Records tab, keyed by replay_id."""
        row_data = [
            replay.get("replay_id", ""),
            replay.get("match_id", ""),
            replay.get("url", ""),
            replay.get("winner", ""),
            str(replay.get("p1_team", [])),
            str(replay.get("p2_team", [])),
            str(replay.get("turns", "")),
            replay.get("timestamp", UTC_NOW()),
        ]
        self.upsert_row(
            Tab.MATCH_RECORDS, "replay_id", replay.get("replay_id", ""), row_data
        )

    def save_video(self, video: dict) -> None:
        """Append a video entry to the flat Match Records tab, keyed by video_id."""
        row_data = [
            video.get("video_id", ""),
            video.get("match_id", ""),
            video.get("uploader_id", ""),
            video.get("opponent_id", ""),
            video.get("storage_url", ""),
            video.get("thumbnail_url", ""),
            video.get("notes", ""),
            video.get("timestamp", UTC_NOW()),
        ]
        self.upsert_row(
            Tab.MATCH_RECORDS, "video_id", video.get("video_id", ""), row_data
        )

    # ── Transactions tab ──────────────────────────────────────────────────────
    #
    # Layout:
    #   Row 3: headers (D=#, E=W., F=Event, G=Coach#1, H=Pokémon#1, J=Pokémon#2, L=Coach#2, M=Notes)
    #   Rows 4-5: empty template rows
    #   Row 6+: data rows

    def save_transaction(self, txn: dict) -> None:
        """Append a transaction row."""
        row_data = [
            txn.get("transaction_id", ""),
            txn.get("week", ""),
            txn.get("type", ""),
            txn.get("from_player_name", txn.get("coach1", "")),
            txn.get("pokemon_given", txn.get("pokemon1", "")),
            txn.get("pokemon_received", txn.get("pokemon2", "")),
            txn.get("to_player_name", txn.get("coach2", "")),
            txn.get("status", ""),
            UTC_NOW(),
        ]
        self.upsert_row(
            Tab.TRANSACTIONS, "transaction_id", txn.get("transaction_id", ""), row_data
        )

    # ── Draft tab ─────────────────────────────────────────────────────────────

    def save_pick(self, pick: dict) -> None:
        """Append a draft pick row."""
        row_data = [
            pick.get("pick_id", ""),
            pick.get("draft_id", ""),
            pick.get("player_id", ""),
            pick.get("pokemon_name", ""),
            pick.get("round", ""),
            pick.get("pick_number", ""),
            UTC_NOW(),
        ]
        self.upsert_row(Tab.DRAFT, "pick_id", pick.get("pick_id", ""), row_data)

    # ── Pokédex tab ───────────────────────────────────────────────────────────
    #
    # Layout (row 1 = headers, row 2 = dashes/template, row 3+ = data):
    #   B=GitHub Name, C=Smogon Name, D=PMD Reference, F=Pts, I=Pokémon, J=Type1, K=Type2
    #   L=HP, M=Atk, N=Def, O=SpA, P=SpD, Q=Spe

    def bulk_write_pokedex(self, pokemon_list: list[dict]) -> None:
        """Write all Pokémon to the Pokédex tab."""
        ws = self.get_tab(Tab.POKEDEX, create=True)
        ws.clear()
        if not pokemon_list:
            return

        rows = []
        for p in pokemon_list:
            stats = p.get("base_stats", {})
            types = p.get("types", ["", ""])
            rows.append(
                [
                    p.get("national_dex", ""),
                    p.get("name", ""),
                    types[0] if len(types) > 0 else "",
                    types[1] if len(types) > 1 else "",
                    stats.get("hp", 0),
                    stats.get("atk", 0),
                    stats.get("def", 0),
                    stats.get("spa", 0),
                    stats.get("spd", 0),
                    stats.get("spe", 0),
                    p.get("showdown_tier", ""),
                    p.get("generation", ""),
                    p.get("is_legendary", False),
                    p.get("is_mythical", False),
                    p.get("vgc_legal", False),
                    p.get("sprite_url", ""),
                ]
            )

        ws.append_rows(rows, value_input_option="USER_ENTERED")
        log.info(f"Pokédex tab populated with {len(rows)} Pokémon")

    # ── Playoffs tab ──────────────────────────────────────────────────────────

    def save_playoff_match(self, match: dict) -> None:
        """Write a playoff match row."""
        row_data = [
            match.get("bracket_id", ""),
            match.get("round", ""),
            match.get("match_number", ""),
            match.get("player1_id", ""),
            match.get("player2_id", ""),
            UTC_NOW(),
        ]
        self.upsert_row(
            Tab.PLAYOFFS, "bracket_id", match.get("bracket_id", ""), row_data
        )

    # ── Team page (individual coach tabs) ─────────────────────────────────────

    def upsert_team_page(self, team: dict) -> None:
        """Insert or update a team row in the Team Page Template tab.

        Writes pokemon_list as a JSON array of names (H2) and guild_id (H5)
        so get_team() can read them back.  Uses header-aware _upsert_record
        for a partial update — fields absent from team dict are preserved.
        """
        import json as _json

        slots = team.get("slots", [])
        pokemon_names = [name for name, _tera in slots] if slots else []
        record: dict[str, Any] = {
            "player_id": team.get("player_id", ""),
            "guild_id": team.get("guild_id", ""),
            "pokemon_list": _json.dumps(pokemon_names),
            "updated_at": UTC_NOW(),
        }
        # Only include optional display fields when provided by the caller
        for field in ("player_name", "team_name", "team_logo_url", "pool"):
            if field in team:
                record[field] = team[field]
        self._upsert_record(
            Tab.TEAM_TEMPLATE, "player_id", team.get("player_id", ""), record
        )


# Global singleton
sheets = SheetsClient()
