"""
ELO Rating Service — Standard ELO with K=32, per-league ratings.

The rating math and match recording live here; where ratings are held (cache,
Local store, League sheet) is src/data/elo_store.py.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from src.config import settings
from src.data.elo_store import elo_store
from src.data.models import PlayerElo

log = logging.getLogger(__name__)

# Per-guild locks to serialize concurrent record_match calls (M7)
_elo_locks: dict[str, asyncio.Lock] = {}


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
        await elo_store.restore()

    async def record_match(
        self,
        guild_id: str,
        winner_id: str,
        loser_id: str,
        winner_name: str = "",
        loser_name: str = "",
    ) -> EloMatchResult:
        # M9: reject self-matches before any mutation
        if winner_id == loser_id:
            raise ValueError("Winner and loser cannot be the same player.")

        # M7: serialize concurrent record_match calls per guild
        lock = _elo_locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            winner = await elo_store.get(guild_id, winner_id)
            loser = await elo_store.get(guild_id, loser_id)
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
            winner.streak = winner.streak + 1 if winner.streak >= 0 else 1
            loser.streak = loser.streak - 1 if loser.streak <= 0 else -1

            # League sheet then SQLite write-through — raises on failure so the
            # caller knows the update was not durably stored.
            await elo_store.save(winner, loser)

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
        return await elo_store.standings(guild_id)
