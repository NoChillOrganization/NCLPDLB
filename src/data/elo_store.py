"""
ELO ratings across the in-memory cache, the Local store (SQLite) and the League sheet.

One module owns how the three agree:
  read  — cache first; on a miss, the ELO Data tab on the League sheet; else a fresh
          default rating.  (The Local store is loaded into the cache at startup.)
  write — League sheet first, then the Local store (write-through).  A Local store
          failure is raised so the caller knows the update was not durably stored.

The cache is keyed guild -> player.  The League sheet is one spreadsheet per League
and its ELO rows are keyed by player_id alone (see src/data/sheets.py), so a sheet
read for a player is not guild-scoped; the guild comes from the cache key only.
"""

from __future__ import annotations

import logging

from src.config import settings
from src.data.db import load_all_elo, save_elo as _db_save_elo
from src.data.models import PlayerElo
from src.data.sheets import league_sheet

log = logging.getLogger(__name__)


def _safe_int(val: object, default: int) -> int:
    """Parse ELO/wins/losses from a Sheets cell; return default on blank or non-numeric."""
    try:
        return int(str(val).strip().split()[0]) if str(val).strip() else default
    except (ValueError, IndexError):
        return default


class EloStore:
    def __init__(self) -> None:
        # guild_id -> {player_id -> PlayerElo}
        self.cache: dict[str, dict[str, PlayerElo]] = {}

    async def restore(self) -> None:
        """Load all ELO rows from SQLite into the in-memory cache on startup."""
        rows = await load_all_elo()
        for row in rows:
            guild_id = row["guild_id"]
            player_id = row["player_id"]
            self.cache.setdefault(guild_id, {})[player_id] = PlayerElo(
                player_id=player_id,
                guild_id=guild_id,
                display_name=row.get("display_name", ""),
                elo=int(row["elo"]),
                wins=int(row["wins"]),
                losses=int(row["losses"]),
                streak=int(row.get("streak", 0)),
            )
        if rows:
            log.info("Restored %d ELO record(s) from SQLite", len(rows))

    async def get(self, guild_id: str, player_id: str) -> PlayerElo:
        guild_elo = self.cache.setdefault(guild_id, {})
        if player_id not in guild_elo:
            # Try loading from flat ELO Data tab
            record = await league_sheet.find_standing(player_id)
            if record:
                guild_elo[player_id] = PlayerElo(
                    player_id=player_id,
                    guild_id=guild_id,
                    display_name=str(record.get("player_name", "")),
                    elo=_safe_int(
                        record.get("elo", settings.elo_default_rating),
                        settings.elo_default_rating,
                    ),
                    wins=_safe_int(record.get("wins", 0), 0),
                    losses=_safe_int(record.get("losses", 0), 0),
                    streak=_safe_int(record.get("streak", 0), 0),
                )
            else:
                guild_elo[player_id] = PlayerElo(
                    player_id=player_id,
                    guild_id=guild_id,
                    elo=settings.elo_default_rating,
                )
        return guild_elo[player_id]

    async def standings(self, guild_id: str) -> list[PlayerElo]:
        """All of a guild's ratings, highest ELO first (sheet-seeded if the cache is empty)."""
        guild_elo = self.cache.get(guild_id, {})
        if not guild_elo:
            for r in await league_sheet.get_standings():
                pid = str(r.get("player_id", ""))
                if pid:
                    guild_elo[pid] = PlayerElo(
                        player_id=pid,
                        guild_id=guild_id,
                        display_name=str(r.get("player_name", "")),
                        elo=_safe_int(r.get("elo", 1000), 1000),
                        wins=_safe_int(r.get("wins", 0), 0),
                        losses=_safe_int(r.get("losses", 0), 0),
                        streak=_safe_int(r.get("streak", 0), 0),
                    )
            self.cache[guild_id] = guild_elo
        return sorted(guild_elo.values(), key=lambda p: p.elo, reverse=True)

    async def save(self, *players: PlayerElo) -> None:
        """Persist ratings: every League sheet row first, then every Local store row."""
        for player in players:
            await league_sheet.save_standing(
                {
                    "player_id": player.player_id,
                    "player_name": player.display_name,
                    "elo": player.elo,
                    "wins": player.wins,
                    "losses": player.losses,
                    "streak": player.streak,
                    "win_pct": round(player.win_rate, 2),
                }
            )
        for player in players:
            await _db_save_elo(
                guild_id=player.guild_id,
                player_id=player.player_id,
                elo=player.elo,
                wins=player.wins,
                losses=player.losses,
                streak=player.streak,
                display_name=player.display_name,
            )


# Global singleton
elo_store = EloStore()
