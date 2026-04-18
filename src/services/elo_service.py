"""
ELO Rating Service — Standard ELO with K=32, per-league ratings.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.config import settings
from src.data.db import load_all_elo, save_elo as _db_save_elo
from src.data.models import PlayerElo
from src.data.sheets import Tab, sheets

log = logging.getLogger(__name__)

# In-memory ELO cache
_elo_cache: dict[str, dict[str, PlayerElo]] = {}  # guild_id -> {player_id -> PlayerElo}


@dataclass
class EloMatchResult:
    winner_old_elo: int
    winner_new_elo: int
    loser_old_elo: int
    loser_new_elo: int
    winner_id: str
    loser_id: str


def expected_score(rating_a: int, rating_b: int) -> float:
    """Expected win probability for player A."""
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def new_rating(old_rating: int, expected: float, actual: float, k: int) -> int:
    """Calculate new ELO rating after a match."""
    return round(old_rating + k * (actual - expected))


class EloService:
    async def restore_ratings_from_db(self) -> None:
        """Load all ELO rows from SQLite into the in-memory cache on startup."""
        rows = await load_all_elo()
        for row in rows:
            guild_id  = row["guild_id"]
            player_id = row["player_id"]
            _elo_cache.setdefault(guild_id, {})[player_id] = PlayerElo(
                player_id    = player_id,
                guild_id     = guild_id,
                display_name = row.get("display_name", ""),
                elo          = int(row["elo"]),
                wins         = int(row["wins"]),
                losses       = int(row["losses"]),
                streak       = int(row.get("streak", 0)),
            )
        if rows:
            log.info("Restored %d ELO record(s) from SQLite", len(rows))

    async def _save_player_to_db(self, player: PlayerElo) -> None:
        await _db_save_elo(
            guild_id     = player.guild_id,
            player_id    = player.player_id,
            elo          = player.elo,
            wins         = player.wins,
            losses       = player.losses,
            streak       = player.streak,
            display_name = player.display_name,
        )

    def _get_player(self, guild_id: str, player_id: str) -> PlayerElo:
        guild_elo = _elo_cache.setdefault(guild_id, {})
        if player_id not in guild_elo:
            # Try loading from Standings tab
            record = sheets.find_row(Tab.STANDINGS, "player_id", player_id)
            if record:
                guild_elo[player_id] = PlayerElo(
                    player_id=player_id,
                    guild_id=guild_id,
                    display_name=str(record.get("player_name", "")),
                    elo=int(record.get("elo", settings.elo_default_rating)),
                    wins=int(record.get("wins", 0)),
                    losses=int(record.get("losses", 0)),
                )
            else:
                guild_elo[player_id] = PlayerElo(
                    player_id=player_id,
                    guild_id=guild_id,
                    elo=settings.elo_default_rating,
                )
        return guild_elo[player_id]

    async def record_match(
        self,
        guild_id: str,
        winner_id: str,
        loser_id: str,
        winner_name: str = "",
        loser_name: str = "",
    ) -> EloMatchResult:
        winner = self._get_player(guild_id, winner_id)
        loser = self._get_player(guild_id, loser_id)
        if winner_name:
            winner.display_name = winner_name
        if loser_name:
            loser.display_name = loser_name

        exp_winner = expected_score(winner.elo, loser.elo)
        exp_loser = expected_score(loser.elo, winner.elo)

        old_winner_elo = winner.elo
        old_loser_elo = loser.elo

        winner.elo = new_rating(winner.elo, exp_winner, 1.0, settings.elo_k_factor)
        loser.elo = new_rating(loser.elo, exp_loser, 0.0, settings.elo_k_factor)
        winner.wins += 1
        loser.losses += 1

        # Persist to Sheets (sync via gspread)
        self._save_player(winner)
        self._save_player(loser)

        # Persist to SQLite write-through cache — raise on failure so the
        # caller knows the update was not durably stored.
        await self._save_player_to_db(winner)
        await self._save_player_to_db(loser)

        log.info(
            f"Match recorded: {winner_id} ({old_winner_elo}→{winner.elo}) "
            f"beat {loser_id} ({old_loser_elo}→{loser.elo})"
        )

        return EloMatchResult(
            winner_id=winner_id,
            loser_id=loser_id,
            winner_old_elo=old_winner_elo,
            winner_new_elo=winner.elo,
            loser_old_elo=old_loser_elo,
            loser_new_elo=loser.elo,
        )

    async def get_standings(self, guild_id: str) -> list[PlayerElo]:
        guild_elo = _elo_cache.get(guild_id, {})
        if not guild_elo:
            records = sheets.get_standings()
            for r in records:
                pid = str(r.get("player_id", ""))
                if pid:
                    guild_elo[pid] = PlayerElo(
                        player_id=pid,
                        guild_id=guild_id,
                        display_name=str(r.get("player_name", "")),
                        elo=int(r.get("elo", 1000)),
                        wins=int(r.get("wins", 0)),
                        losses=int(r.get("losses", 0)),
                        streak=int(r.get("streak", 0)),
                    )
            _elo_cache[guild_id] = guild_elo
        return sorted(guild_elo.values(), key=lambda p: p.elo, reverse=True)

    def _save_player(self, player: PlayerElo) -> None:
        sheets.upsert_standing({
            "player_id": player.player_id,
            "player_name": player.display_name,
            "elo": player.elo,
            "wins": player.wins,
            "losses": player.losses,
            "streak": player.streak,
            "win_pct": round(player.win_rate, 2),
        })
