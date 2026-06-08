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
            delay = (2 ** attempt) + _random.uniform(0, 1)
            log.warning(
                "Sheets API rate-limit (HTTP %s) — retrying in %.1fs (attempt %d/%d)",
                status, delay, attempt + 1, max_tries,
            )
            _time.sleep(delay)
        except requests.exceptions.RequestException as exc:
            if attempt == max_tries - 1:
                raise
            delay = (2 ** attempt) + _random.uniform(0, 1)
            log.warning(
                "Sheets transport error (%s) — retrying in %.1fs (attempt %d/%d)",
                exc, delay, attempt + 1, max_tries,
            )
            _time.sleep(delay)


# ── Tab names (exact Unicode match to spreadsheet) ─────────────────────────────

class Tab:
    SETUP         = "Setup"
    RULES         = "Rules"
    COVER         = "Cover"
    DRAFT         = "Draft"
    DRAFT_BOARD   = "Draft Board"
    POOL_A        = "Pool A Board"
    POOL_B        = "Pool B Board"
    SCHEDULE      = "Schedule"
    MATCH_STATS   = "Match Stats"    # visual template — read-only via get_match_results()
    MATCH_RECORDS = "Match Records"  # flat tab: match/replay/video rows written by the bot
    STANDINGS     = "Standings"      # visual template — read-only via get_standings_visual()
    ELO_DATA      = "ELO Data"       # flat tab: ELO records written/read by EloService
    POKEMON_STATS = "Pokémon Stats"
    MVP_RACE      = "MVP Race"
    TRANSACTIONS  = "Transactions"
    PLAYOFFS      = "Playoffs"
    POKEDEX       = "Pokédex"
    TEAM_TEMPLATE = "Team Page Template"
    DATA          = "Data"


# ── Helper: column letter ↔ number ─────────────────────────────────────────────

def _col_letter(n: int) -> str:
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def _col_num(s: str) -> int:
    result = 0
    for ch in s.upper():
        result = result * 26 + (ord(ch) - 64)
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
        self._spreadsheet = self._client.open_by_key(settings.google_sheets_spreadsheet_id)
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

    def _get_cell(self, tab_name: str, cell: str) -> str:
        """Read a single cell's formatted value."""
        result = self.spreadsheet.values_get(
            f"'{tab_name}'!{cell}",
            params={"valueRenderOption": "FORMATTED_VALUE"},
        )
        vals = result.get("values", [[]])
        return vals[0][0] if vals and vals[0] else ""

    def _get_range(self, tab_name: str, range_: str) -> list[list[str]]:
        """Read a range returning a 2D list (empty strings for empty cells)."""
        result = self.spreadsheet.values_get(
            f"'{tab_name}'!{range_}",
            params={"valueRenderOption": "FORMATTED_VALUE"},
        )
        return result.get("values", [])

    def _set_cell(self, tab_name: str, cell: str, value: Any) -> None:
        """Write a single cell."""
        ws = self.get_tab(tab_name)
        _with_retry(ws.update, [[value]], cell, value_input_option="USER_ENTERED")

    def _append_to_range(self, ws: gspread.Worksheet, range_: str, row: list[Any]) -> None:
        """Append a row using USER_ENTERED so formulas are evaluated."""
        ws.append_row(row, value_input_option="USER_ENTERED", table_range=range_)

    # ── Generic helpers ───────────────────────────────────────────────────────

    def append_row(self, tab_name: str, row: list[Any]) -> None:
        """Append a row to any tab."""
        ws = self.get_tab(tab_name, create=True)
        _with_retry(ws.append_row, row, value_input_option="USER_ENTERED")

    def update_row(self, tab_name: str, row_num: int, row_data: list) -> None:
        """Overwrite a specific row (1-indexed) starting from column A."""
        ws = self.get_tab(tab_name, create=True)
        _with_retry(ws.update, f"A{row_num}", [row_data])

    def upsert_row(self, tab_name: str, key_col: str, key_val: str, row_data: list) -> None:
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
        row_vals = (_with_retry(ws.row_values, cell.row) + [""] * len(headers))[: len(headers)]
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
            data.get("league_id", ""), data.get("server_id", ""),
            data.get("league_name", ""), data.get("commissioner_id", ""),
            data.get("commissioner_name", ""), UTC_NOW(),
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
            standing.get("player_id", ""), standing.get("player_name", ""),
            standing.get("elo", ""), standing.get("wins", ""),
            standing.get("losses", ""), standing.get("streak", ""), UTC_NOW(),
        ]
        self.upsert_row(Tab.ELO_DATA, "player_id", standing.get("player_id", ""), row_data)

    # ── Schedule tab ──────────────────────────────────────────────────────────
    #
    # Layout (cols J=Coach1, K=result, L=score, M=vs, N=score, O=result, P=Coach2):
    #   Row 5: "Week #1" label in col D
    #   Rows 6-13: match rows for week 1

    def get_schedule(self) -> list[dict]:
        """Read all scheduled matches from the visual Schedule template."""
        raw = self._get_range(Tab.SCHEDULE, "D5:P260")
        matches = []
        current_week = ""
        for row in raw:
            if not row:
                continue
            d_val = row[0].strip() if len(row) > 0 else ""
            if d_val.startswith("Week"):
                current_week = d_val
                continue
            if len(row) < 13:
                row = row + [""] * (13 - len(row))
            coach1  = row[6].strip()
            result1 = row[7].strip()
            score1  = row[8].strip()
            vs_     = row[9].strip()
            score2  = row[10].strip()
            result2 = row[11].strip()
            coach2  = row[12].strip()
            if coach1 and vs_ == "vs.":
                matches.append({
                    "week":    current_week,
                    "coach1":  coach1,
                    "result1": result1,
                    "score1":  score1,
                    "score2":  score2,
                    "result2": result2,
                    "coach2":  coach2,
                })
        return matches

    def save_schedule_match(self, match: dict) -> None:
        """Write a scheduled match row."""
        row_data = [
            match.get("match_id", ""), match.get("week", ""),
            match.get("player1_id", ""), match.get("player1_name", ""),
            match.get("player2_id", ""), match.get("player2_name", ""), UTC_NOW(),
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
            match_raw = self._get_range(Tab.MATCH_STATS, f"E{match_start}:K{match_start + 80}")
            i = 0
            while i < len(match_raw):
                row = match_raw[i]
                coach1  = row[0].strip() if len(row) > 0 else ""
                result1 = row[2].strip() if len(row) > 2 else ""
                result2 = row[6].strip() if len(row) > 6 else ""
                coach2  = row[7].strip() if len(row) > 7 else ""
                if coach1 and result1 in {"W", "L", "DF", ""}:
                    winner = coach1 if result1 == "W" else (coach2 if result2 == "W" else "")
                    results.append({
                        "week":    wlabel,
                        "coach1":  coach1,
                        "coach2":  coach2,
                        "winner":  winner,
                        "result1": result1,
                        "result2": result2,
                    })
                    i += 9
                else:
                    i += 1
        return results

    def save_match_stats(self, match: dict) -> None:
        """Write match stats row to the flat Match Records tab."""
        row_data = [
            match.get("match_id", ""), match.get("league_id", ""),
            str(match.get("p1_team", [])), str(match.get("p2_team", [])), UTC_NOW(),
        ]
        self.upsert_row(Tab.MATCH_RECORDS, "match_id", match.get("match_id", ""), row_data)

    def save_replay(self, replay: dict) -> None:
        """Append a replay row to the flat Match Records tab, keyed by replay_id."""
        row_data = [
            replay.get("replay_id", ""), replay.get("match_id", ""),
            replay.get("url", ""), replay.get("winner", ""),
            str(replay.get("p1_team", [])), str(replay.get("p2_team", [])),
            str(replay.get("turns", "")), replay.get("timestamp", UTC_NOW()),
        ]
        self.upsert_row(Tab.MATCH_RECORDS, "replay_id", replay.get("replay_id", ""), row_data)

    def save_video(self, video: dict) -> None:
        """Append a video entry to the flat Match Records tab, keyed by video_id."""
        row_data = [
            video.get("video_id", ""), video.get("match_id", ""),
            video.get("uploader_id", ""), video.get("opponent_id", ""),
            video.get("storage_url", ""), video.get("thumbnail_url", ""),
            video.get("notes", ""), video.get("timestamp", UTC_NOW()),
        ]
        self.upsert_row(Tab.MATCH_RECORDS, "video_id", video.get("video_id", ""), row_data)

    # ── Transactions tab ──────────────────────────────────────────────────────
    #
    # Layout:
    #   Row 3: headers (D=#, E=W., F=Event, G=Coach#1, H=Pokémon#1, J=Pokémon#2, L=Coach#2, M=Notes)
    #   Rows 4-5: empty template rows
    #   Row 6+: data rows

    def get_transactions(self) -> list[dict]:
        """Read all logged transactions."""
        raw = self._get_range(Tab.TRANSACTIONS, "D6:M200")
        transactions = []
        for row in raw:
            if not row or not row[0].strip():
                continue
            transactions.append({
                "number":   row[0].strip() if len(row) > 0 else "",
                "week":     row[1].strip() if len(row) > 1 else "",
                "event":    row[2].strip() if len(row) > 2 else "",
                "coach1":   row[3].strip() if len(row) > 3 else "",
                "pokemon1": row[4].strip() if len(row) > 4 else "",
                "pokemon2": row[6].strip() if len(row) > 6 else "",
                "coach2":   row[8].strip() if len(row) > 8 else "",
                "notes":    row[9].strip() if len(row) > 9 else "",
            })
        return transactions

    def save_transaction(self, txn: dict) -> None:
        """Append a transaction row."""
        row_data = [
            txn.get("transaction_id", ""), txn.get("week", ""),
            txn.get("type", ""), txn.get("from_player_name", txn.get("coach1", "")),
            txn.get("pokemon_given", txn.get("pokemon1", "")),
            txn.get("pokemon_received", txn.get("pokemon2", "")),
            txn.get("to_player_name", txn.get("coach2", "")),
            txn.get("status", ""), UTC_NOW(),
        ]
        self.upsert_row(Tab.TRANSACTIONS, "transaction_id", txn.get("transaction_id", ""), row_data)

    # ── Draft tab ─────────────────────────────────────────────────────────────

    def save_pick(self, pick: dict) -> None:
        """Append a draft pick row."""
        row_data = [
            pick.get("pick_id", ""), pick.get("draft_id", ""), pick.get("player_id", ""),
            pick.get("pokemon_name", ""), pick.get("round", ""), pick.get("pick_number", ""),
            UTC_NOW(),
        ]
        self.upsert_row(Tab.DRAFT, "pick_id", pick.get("pick_id", ""), row_data)

    def get_draft_picks(self, draft_id: str) -> list[dict]:
        """Return all picks for a given draft_id."""
        return self.find_rows(Tab.DRAFT, "draft_id", draft_id)

    # ── Pool rosters ──────────────────────────────────────────────────────────

    def update_pool_roster(self, pool: str, player: dict, pokemon: list[str]) -> None:
        """Insert or update a player's roster in the pool board tab."""
        tab = Tab.POOL_A if pool == "A" else Tab.POOL_B
        row_data = [
            player.get("player_id", ""), player.get("player_name", ""),
            player.get("team_name", ""), ",".join(pokemon), UTC_NOW(),
        ]
        self.upsert_row(tab, "player_id", player.get("player_id", ""), row_data)

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
            rows.append([
                p.get("national_dex", ""), p.get("name", ""),
                types[0] if len(types) > 0 else "", types[1] if len(types) > 1 else "",
                stats.get("hp", 0), stats.get("atk", 0), stats.get("def", 0),
                stats.get("spa", 0), stats.get("spd", 0), stats.get("spe", 0),
                p.get("showdown_tier", ""), p.get("generation", ""),
                p.get("is_legendary", False), p.get("is_mythical", False),
                p.get("vgc_legal", False), p.get("sprite_url", ""),
            ])

        ws.append_rows(rows, value_input_option="USER_ENTERED")
        log.info(f"Pokédex tab populated with {len(rows)} Pokémon")

    # ── Rules tab ─────────────────────────────────────────────────────────────
    #
    # Layout: visual template; rules in col E starting row 4; col D has ✵ bullet.

    def get_rules(self) -> list[str]:
        """Return all rule text strings from column E (rows 4+)."""
        raw = self._get_range(Tab.RULES, "E4:E100")
        return [row[0].strip() for row in raw if row and row[0].strip()]

    def append_rule(self, category: str, title: str, description: str) -> None:
        """Append a new rule to the Rules tab (col D=✵, col E=text)."""
        ws = self.get_tab(Tab.RULES, create=True)
        e_col = ws.col_values(5)  # column E
        next_row = len(e_col) + 1
        text = f"[{category}] {title}: {description}" if category else f"{title}: {description}"
        ws.update([["✵", text]], f"D{next_row}:E{next_row}", value_input_option="USER_ENTERED")
        log.info(f"Rule appended at row {next_row}")

    # ── MVP Race tab ──────────────────────────────────────────────────────────

    def get_mvp_race(self) -> list[dict]:
        """Read the MVP Race tab."""
        raw = self._get_range(Tab.MVP_RACE, "A1:Z50")
        results = []
        for row in raw:
            if len(row) >= 10:
                for v in row:
                    if v and "+" in v and "in" in v:
                        results.append({
                            "coach": row[0].strip() if row else "",
                            "record": v.strip(),
                        })
                        break
        return results

    def refresh_mvp_race(self, mvp_entries: list[dict]) -> None:
        """Clear and re-write the MVP Race tab with updated entries."""
        ws = self.get_tab(Tab.MVP_RACE, create=True)
        ws.resize(rows=max(1, len(mvp_entries) + 1))
        for entry in mvp_entries:
            ws.append_row([
                entry.get("rank", ""), entry.get("player_id", ""),
                entry.get("mvp_pokemon", ""), entry.get("mvp_count", ""),
            ], value_input_option="USER_ENTERED")

    # ── Pokémon Stats tab ─────────────────────────────────────────────────────

    def update_pokemon_stat(self, stat: dict) -> None:
        """Insert or update a Pokémon stat row."""
        row_data = [
            stat.get("stat_id", ""), stat.get("pokemon", ""),
            stat.get("wins", ""), stat.get("losses", ""),
            stat.get("kills", ""), stat.get("deaths", ""), UTC_NOW(),
        ]
        self.upsert_row(Tab.POKEMON_STATS, "stat_id", stat.get("stat_id", ""), row_data)

    # ── Playoffs tab ──────────────────────────────────────────────────────────

    def save_playoff_match(self, match: dict) -> None:
        """Write a playoff match row."""
        row_data = [
            match.get("bracket_id", ""), match.get("round", ""),
            match.get("match_number", ""), match.get("player1_id", ""),
            match.get("player2_id", ""), UTC_NOW(),
        ]
        self.upsert_row(Tab.PLAYOFFS, "bracket_id", match.get("bracket_id", ""), row_data)

    # ── Team page (individual coach tabs) ─────────────────────────────────────

    def get_coach_tab(self, coach_name: str) -> dict | None:
        """Read a coach's individual team tab (e.g. 'Hannah4Ever')."""
        try:
            ws = self.spreadsheet.worksheet(coach_name)
        except gspread.WorksheetNotFound:
            log.warning(f"No tab found for coach '{coach_name}'")
            return None
        raw = ws.get_all_values()
        return {"coach": coach_name, "rows": raw[:10]}

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
            "player_id":     team.get("player_id", ""),
            "guild_id":      team.get("guild_id", ""),
            "pokemon_list":  _json.dumps(pokemon_names),
            "updated_at":    UTC_NOW(),
        }
        # Only include optional display fields when provided by the caller
        for field in ("player_name", "team_name", "team_logo_url", "pool"):
            if field in team:
                record[field] = team[field]
        self._upsert_record(
            Tab.TEAM_TEMPLATE, "player_id", team.get("player_id", ""), record
        )

    # ── Data tab ──────────────────────────────────────────────────────────────

    def set_data(self, key: str, value: str, type_: str = "string", description: str = "") -> None:
        """Upsert a key-value pair in the Data tab."""
        self.upsert_row(Tab.DATA, "key", key, [key, value, type_, description, UTC_NOW()])

    def get_data_value(self, label: str) -> str | None:
        """Read a labelled value from the Data tab."""
        row = self.find_row(Tab.DATA, "key", label)
        return row.get("value") if row else None

    def get_data(self, key: str) -> str | None:
        """Return the value for a key in the Data tab."""
        return self.get_data_value(key)


# Global singleton
sheets = SheetsClient()


# ── Master learning spreadsheet ────────────────────────────────────────────────

REPLAY_HEADERS = [
    "Timestamp", "Format", "Battle ID", "Bot", "Opponent",
    "Opponent Type", "Winner", "Turns", "KO Count", "Team",
    "Checkpoint", "Training Step", "Replay URL",
]

TRAINING_RUN_HEADERS = [
    "Timestamp", "Format", "Phase", "Checkpoint", "Training Step",
    "Win Rate", "Episodes", "Mean Reward", "Notes",
]

_WINNER_COL = REPLAY_HEADERS.index("Winner")
_FORMAT_COL  = REPLAY_HEADERS.index("Format")


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
        self._spreadsheet = self._client.open_by_key(settings.ml_learning_spreadsheet_id)
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
            ws = self.spreadsheet.add_worksheet(title="Replays", rows=10000, cols=len(REPLAY_HEADERS))
            ws.append_row(REPLAY_HEADERS, value_input_option="USER_ENTERED")
            log.info("Created 'Replays' tab in learning spreadsheet")
            return ws

    def _get_format_sheet(self, fmt: str) -> gspread.Worksheet:
        tab = fmt[:100]
        try:
            return self.spreadsheet.worksheet(tab)
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(title=tab, rows=10000, cols=len(REPLAY_HEADERS))
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
            ws.append_row([
                UTC_NOW(),
                data.get("format", ""),
                data.get("phase", ""),
                data.get("checkpoint", ""),
                data.get("training_step", ""),
                data.get("win_rate", ""),
                data.get("episodes", ""),
                data.get("mean_reward", ""),
                data.get("notes", ""),
            ], value_input_option="USER_ENTERED")
            log.info(
                "[LearningSheets] Saved training run: fmt=%s step=%s win_rate=%s",
                data.get("format", ""), data.get("training_step", ""), data.get("win_rate", ""),
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
            wins = sum(1 for r in recent if len(r) > _WINNER_COL and r[_WINNER_COL] == "bot")
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
            wins = sum(1 for r in recent if len(r) > _WINNER_COL and r[_WINNER_COL] == "bot")
            win_rate = wins / len(recent) if recent else 0.0
            tr = training_by_fmt.get(fmt, {})
            stats.append({
                "format":          fmt,
                "battles":         len(rows),
                "win_rate":        win_rate,
                "last_checkpoint": tr.get("Checkpoint", "—"),
                "last_step":       tr.get("Training Step", "—"),
                "last_trained":    tr.get("Timestamp", "—"),
            })
        return stats


# Global singleton
learning_sheets = LearningSheets()
