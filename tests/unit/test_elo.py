"""
Unit tests for EloService — rating calculations, matchmaking, standings.

Where ratings are held (cache / Local store / League sheet) is tested in
test_elo_store.py; here the store's collaborators are stubbed.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.config import settings
from src.data.elo_store import elo_store
from src.data.models import PlayerElo
from src.services.elo_service import EloService, expected_score, new_rating


# ── Pure ELO math ─────────────────────────────────────────────


def test_equal_ratings_expect_50_percent():
    assert expected_score(1000, 1000) == pytest.approx(0.5)


def test_higher_rating_expects_win():
    assert expected_score(1200, 1000) > 0.5


def test_lower_rating_expects_loss():
    assert expected_score(800, 1000) < 0.5


def test_new_rating_win_increases_rating():
    old = 1000
    exp = expected_score(1000, 1000)
    result = new_rating(old, exp, 1.0, 32)
    assert result > old


def test_new_rating_loss_decreases_rating():
    old = 1000
    exp = expected_score(1000, 1000)
    result = new_rating(old, exp, 0.0, 32)
    assert result < old


def test_upset_win_gives_large_gain():
    """Beating a much higher-rated player gives more ELO."""
    underdog_gain = new_rating(800, expected_score(800, 1200), 1.0, 32) - 800
    expected_gain = new_rating(1000, expected_score(1000, 1000), 1.0, 32) - 1000
    assert underdog_gain > expected_gain


def test_k_factor_scales_change():
    old = 1000
    exp = 0.5
    gain_k32 = new_rating(old, exp, 1.0, 32) - old
    gain_k16 = new_rating(old, exp, 1.0, 16) - old
    assert gain_k32 == gain_k16 * 2


# ── EloService ────────────────────────────────────────────────


@pytest.fixture
def stores():
    """Empty cache; League sheet and Local store stubbed. Yields (sheet, db_save)."""
    elo_store.cache.clear()
    with (
        patch("src.data.elo_store.league_sheet", autospec=True) as sheet,
        patch("src.data.elo_store._db_save_elo", new_callable=AsyncMock) as db_save,
    ):
        sheet.find_standing.return_value = None
        sheet.get_standings.return_value = []
        yield sheet, db_save
    elo_store.cache.clear()


@pytest.mark.asyncio
async def test_record_match_updates_both_players(stores):
    result = await EloService().record_match("guild1", "winner1", "loser1")

    assert result.winner_new_elo > result.winner_old_elo
    assert result.loser_new_elo < result.loser_old_elo


@pytest.mark.asyncio
async def test_record_match_sum_elo_conserved(stores):
    """ELO gained by winner ≈ ELO lost by loser (near conservation)."""
    result = await EloService().record_match("guild2", "w", "l")

    winner_gain = result.winner_new_elo - result.winner_old_elo
    loser_loss = result.loser_old_elo - result.loser_new_elo
    # Within 1 due to rounding
    assert abs(winner_gain - loser_loss) <= 1


@pytest.mark.asyncio
async def test_record_match_rejects_self_match(stores):
    with pytest.raises(ValueError):
        await EloService().record_match("g", "same", "same")


@pytest.mark.asyncio
async def test_standings_sorted_by_elo(stores):
    elo_store.cache["guild3"] = {
        "p1": PlayerElo(player_id="p1", guild_id="guild3", elo=1100, wins=5, losses=2),
        "p2": PlayerElo(player_id="p2", guild_id="guild3", elo=900, wins=2, losses=5),
        "p3": PlayerElo(player_id="p3", guild_id="guild3", elo=1000, wins=3, losses=3),
    }

    standings = await EloService().get_standings("guild3")
    elos = [p.elo for p in standings]
    assert elos == sorted(elos, reverse=True)
    assert standings[0].elo == 1100


@pytest.mark.asyncio
async def test_record_match_sets_display_names(stores):
    """winner_name and loser_name are applied to player records."""
    await EloService().record_match(
        "guild_dn", "w1", "l1", winner_name="Alice", loser_name="Bob"
    )

    assert elo_store.cache["guild_dn"]["w1"].display_name == "Alice"
    assert elo_store.cache["guild_dn"]["l1"].display_name == "Bob"


# ── NCLP-006: SQLite ELO write-through ───────────────────────────────────────


@pytest.mark.asyncio
async def test_record_match_writes_to_sqlite(stores):
    """record_match should persist both players to SQLite (NCLP-006)."""
    _, db_save = stores
    await EloService().record_match("guild_db", "w", "l")

    assert db_save.await_count == 2
    assert {c.kwargs["player_id"] for c in db_save.await_args_list} == {"w", "l"}


@pytest.mark.asyncio
async def test_record_match_writes_to_league_sheet(stores):
    sheet, _ = stores
    await EloService().record_match("guild_ls", "w", "l")

    written = {c.args[0]["player_id"] for c in sheet.save_standing.await_args_list}
    assert written == {"w", "l"}


@pytest.mark.asyncio
async def test_default_elo_is_configured_value(stores):
    player = await elo_store.get("guild4", "new_player")

    assert player.elo == settings.elo_default_rating


@pytest.mark.asyncio
async def test_restore_ratings_from_db_populates_cache(stores):
    """restore_ratings_from_db should fill the cache from SQLite rows (NCLP-006)."""
    rows = [
        {
            "guild_id": "g1",
            "player_id": "pA",
            "elo": 1150,
            "wins": 6,
            "losses": 2,
            "streak": 3,
            "display_name": "Alice",
        },
    ]
    with patch("src.data.elo_store.load_all_elo", return_value=rows):
        await EloService().restore_ratings_from_db()

    assert elo_store.cache["g1"]["pA"].elo == 1150
    assert elo_store.cache["g1"]["pA"].wins == 6
