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

This module is the League sheet's only door.  Callers ``await`` a method by intent
(``save_pick``, ``save_standing`` …); nobody wraps a sheet call in
``asyncio.to_thread``.  The executor policy (one place: ``LeagueSheet._run``), the
retry policy (``sheet_plumbing._with_retry``) and the cell layout all live here.  The
gspread plumbing is the shared synchronous ``SheetConnection``; the Learning sheet is
a separate adapter over the same plumbing (src/data/learning_sheets.py).

Invariant: ELO rows on the ELO Data tab are keyed by ``player_id`` alone.  There is
one spreadsheet per League (guild), so no guild key is written to the sheet; the
guild is implied by which spreadsheet is configured.  Reconciling those rows with
the in-memory cache and the Local store (SQLite) is src/data/elo_store.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import gspread

from src.config import settings
from src.data.sheet_plumbing import UTC_NOW, SheetConnection

log = logging.getLogger(__name__)


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
    MATCH_STATS = "Match Stats"  # visual template — not read by the bot
    MATCH_RECORDS = (
        "Match Records"  # flat tab: match/replay/video rows written by the bot
    )
    STANDINGS = "Standings"  # visual template — not read by the bot
    ELO_DATA = "ELO Data"  # flat tab: ELO records written/read via the ELO store
    POKEMON_STATS = "Pokémon Stats"
    MVP_RACE = "MVP Race"
    TRANSACTIONS = "Transactions"
    PLAYOFFS = "Playoffs"
    POKEDEX = "Pokédex"
    TEAM_TEMPLATE = "Team Page Template"
    DATA = "Data"


# ── League sheet ───────────────────────────────────────────────────────────────


class LeagueSheet:
    """The League's Google spreadsheet, as async operations by intent."""

    def __init__(self) -> None:
        self._conn = SheetConnection(lambda: settings.google_sheets_spreadsheet_id)

    def open_spreadsheet(self) -> gspread.Spreadsheet:
        """The raw spreadsheet — for the preflight script only (blocking).

        A method, not a property, so autospec'd test doubles never connect.
        """
        return self._conn.spreadsheet

    @staticmethod
    async def _run(fn, *args):
        """The one executor policy: blocking gspread work never runs on the loop."""
        return await asyncio.to_thread(fn, *args)

    async def _upsert(self, tab: str, key_col: str, key_val: str, row: list) -> None:
        await self._run(self._conn.upsert_row, tab, key_col, key_val, row)

    # ── Setup tab ─────────────────────────────────────────────────────────────

    async def get_league_setup(self, server_id: str | None = None) -> dict | None:
        """Return league setup dict, optionally filtered by server_id."""
        if server_id:
            return await self._run(
                self._conn.find_row, Tab.SETUP, "server_id", server_id
            )
        rows = await self._run(self._conn.read_all, Tab.SETUP)
        return rows[0] if rows else {}

    async def save_league_setup(self, data: dict) -> None:
        """Write editable Setup values."""
        row_data = [
            data.get("league_id", ""),
            data.get("server_id", ""),
            data.get("league_name", ""),
            data.get("commissioner_id", ""),
            data.get("commissioner_name", ""),
            UTC_NOW(),
        ]
        await self._upsert(Tab.SETUP, "server_id", data.get("server_id", ""), row_data)

    # ── ELO Data tab (flat; keyed by player_id only — see module docstring) ───

    async def get_standings(self) -> list[dict]:
        """Return ELO standings rows from the flat ELO Data tab."""
        return await self._run(self._conn.read_all, Tab.ELO_DATA)

    async def find_standing(self, player_id: str) -> dict | None:
        """Return one player's ELO row (matched on player_id alone), or None."""
        return await self._run(
            self._conn.find_row, Tab.ELO_DATA, "player_id", player_id
        )

    async def save_standing(self, standing: dict) -> None:
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
        await self._upsert(
            Tab.ELO_DATA, "player_id", standing.get("player_id", ""), row_data
        )

    # ── Schedule tab ──────────────────────────────────────────────────────────
    #
    # Layout (cols J=Coach1, K=result, L=score, M=vs, N=score, O=result, P=Coach2):
    #   Row 5: "Week #1" label in col D
    #   Rows 6-13: match rows for week 1

    async def read_schedule(self) -> list[dict]:
        """Return the Schedule tab as records."""
        return await self._run(self._conn.read_all, Tab.SCHEDULE)

    async def save_schedule_match(self, match: dict) -> None:
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
        await self._upsert(
            Tab.SCHEDULE, "match_id", match.get("match_id", ""), row_data
        )

    # ── Match Records tab ─────────────────────────────────────────────────────

    async def save_match_stats(self, match: dict) -> None:
        """Write match stats row to the flat Match Records tab."""
        row_data = [
            match.get("match_id", ""),
            match.get("league_id", ""),
            str(match.get("p1_team", [])),
            str(match.get("p2_team", [])),
            UTC_NOW(),
        ]
        await self._upsert(
            Tab.MATCH_RECORDS, "match_id", match.get("match_id", ""), row_data
        )

    async def save_replay(self, replay: dict) -> None:
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
        await self._upsert(
            Tab.MATCH_RECORDS, "replay_id", replay.get("replay_id", ""), row_data
        )

    async def save_video(self, video: dict) -> None:
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
        await self._upsert(
            Tab.MATCH_RECORDS, "video_id", video.get("video_id", ""), row_data
        )

    # ── Transactions tab ──────────────────────────────────────────────────────
    #
    # Layout:
    #   Row 3: headers (D=#, E=W., F=Event, G=Coach#1, H=Pokémon#1, J=Pokémon#2, L=Coach#2, M=Notes)
    #   Rows 4-5: empty template rows
    #   Row 6+: data rows

    async def save_transaction(self, txn: dict) -> None:
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
        await self._upsert(
            Tab.TRANSACTIONS, "transaction_id", txn.get("transaction_id", ""), row_data
        )

    async def find_transaction(self, transaction_id: str) -> dict | None:
        """Return the Transactions row for *transaction_id*, or None."""
        return await self._run(
            self._conn.find_row, Tab.TRANSACTIONS, "transaction_id", transaction_id
        )

    # ── Draft tab ─────────────────────────────────────────────────────────────

    async def save_pick(self, pick: dict) -> None:
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
        await self._upsert(Tab.DRAFT, "pick_id", pick.get("pick_id", ""), row_data)

    # ── Rules tab ─────────────────────────────────────────────────────────────

    async def append_rule(self, row: list[Any]) -> None:
        """Append a rule row to the Rules tab."""
        await self._run(self._conn.append_row, Tab.RULES, row)

    # ── Pokédex tab ───────────────────────────────────────────────────────────
    #
    # Layout (row 1 = headers, row 2 = dashes/template, row 3+ = data):
    #   B=GitHub Name, C=Smogon Name, D=PMD Reference, F=Pts, I=Pokémon, J=Type1, K=Type2
    #   L=HP, M=Atk, N=Def, O=SpA, P=SpD, Q=Spe

    async def write_pokedex(self, pokemon_list: list[dict]) -> None:
        """Write all Pokémon to the Pokédex tab."""
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
        await self._run(self._conn.replace_rows, Tab.POKEDEX, rows)
        if rows:
            log.info(f"Pokédex tab populated with {len(rows)} Pokémon")

    # ── Playoffs tab ──────────────────────────────────────────────────────────

    async def save_playoff_match(self, match: dict) -> None:
        """Write a playoff match row."""
        row_data = [
            match.get("bracket_id", ""),
            match.get("round", ""),
            match.get("match_number", ""),
            match.get("player1_id", ""),
            match.get("player2_id", ""),
            UTC_NOW(),
        ]
        await self._upsert(
            Tab.PLAYOFFS, "bracket_id", match.get("bracket_id", ""), row_data
        )

    # ── Team page (individual coach tabs) ─────────────────────────────────────

    async def find_team_page(self, player_id: str) -> dict | None:
        """Return the Team Page Template row for *player_id*, or None."""
        return await self._run(
            self._conn.find_row, Tab.TEAM_TEMPLATE, "player_id", player_id
        )

    async def save_team_page(self, team: dict) -> None:
        """Insert or update a team row in the Team Page Template tab.

        Writes pokemon_list as a JSON array of names (H2) and guild_id (H5)
        so the team can be read back.  Uses header-aware upsert_record
        for a partial update — fields absent from team dict are preserved.
        """
        slots = team.get("slots", [])
        pokemon_names = [name for name, _tera in slots] if slots else []
        record: dict[str, Any] = {
            "player_id": team.get("player_id", ""),
            "guild_id": team.get("guild_id", ""),
            "pokemon_list": json.dumps(pokemon_names),
            "updated_at": UTC_NOW(),
        }
        # Only include optional display fields when provided by the caller
        for field in ("player_name", "team_name", "team_logo_url", "pool"):
            if field in team:
                record[field] = team[field]
        await self._run(
            self._conn.upsert_record,
            Tab.TEAM_TEMPLATE,
            "player_id",
            team.get("player_id", ""),
            record,
        )


# Global singleton
league_sheet = LeagueSheet()
