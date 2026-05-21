"""
Unit tests for EloService — rating calculations, matchmaking, standings.
"""
import pytest
from unittest.mock import patch

from src.services.elo_service import EloService, expected_score, new_rating
from src.config import settings


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

@pytest.mark.asyncio
async def test_record_match_updates_both_players():
    svc = EloService()
    with patch.object(svc, "_save_player"), \
         patch.object(svc, "_save_player_to_db"), \
         patch("src.services.elo_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = None

        result = await svc.record_match("guild1", "winner1", "loser1")

    assert result.winner_new_elo > result.winner_old_elo
    assert result.loser_new_elo < result.loser_old_elo


@pytest.mark.asyncio
async def test_record_match_sum_elo_conserved():
    """ELO gained by winner ≈ ELO lost by loser (near conservation)."""
    svc = EloService()
    with patch.object(svc, "_save_player"), \
         patch.object(svc, "_save_player_to_db"), \
         patch("src.services.elo_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = None

        result = await svc.record_match("guild2", "w", "l")

    winner_gain = result.winner_new_elo - result.winner_old_elo
    loser_loss = result.loser_old_elo - result.loser_new_elo
    # Within 1 due to rounding
    assert abs(winner_gain - loser_loss) <= 1


@pytest.mark.asyncio
async def test_standings_sorted_by_elo():
    from src.data.models import PlayerElo
    import src.services.elo_service as elo_mod

    svc = EloService()
    elo_mod._elo_cache["guild3"] = {
        "p1": PlayerElo(player_id="p1", guild_id="guild3", elo=1100, wins=5, losses=2),
        "p2": PlayerElo(player_id="p2", guild_id="guild3", elo=900, wins=2, losses=5),
        "p3": PlayerElo(player_id="p3", guild_id="guild3", elo=1000, wins=3, losses=3),
    }

    standings = await svc.get_standings("guild3")
    elos = [p.elo for p in standings]
    assert elos == sorted(elos, reverse=True)
    assert standings[0].elo == 1100


@pytest.mark.asyncio
async def test_default_elo_is_configured_value():
    import src.services.elo_service as elo_mod
    elo_mod._elo_cache.clear()

    svc = EloService()
    with patch("src.services.elo_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = None
        player = svc._get_player("guild4", "new_player")

    assert player.elo == settings.elo_default_rating


# ── _get_player loads from sheets when record exists ──────────

def test_get_player_loads_from_sheets():
    import src.services.elo_service as elo_mod
    elo_mod._elo_cache.clear()

    svc = EloService()
    with patch("src.services.elo_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = {
            "player_id": "pS", "player_name": "Sheets Guy",
            "elo": 1200, "wins": 5, "losses": 2,
        }
        player = svc._get_player("guild5", "pS")

    assert player.elo == 1200
    assert player.wins == 5
    assert player.losses == 2


# ── get_standings loads from sheets when cache empty ──────────

@pytest.mark.asyncio
async def test_get_standings_loads_from_sheets():
    import src.services.elo_service as elo_mod
    elo_mod._elo_cache.clear()

    svc = EloService()
    with patch("src.services.elo_service.sheets") as mock_sheets:
        mock_sheets.get_standings.return_value = [
            {"player_id": "pA", "player_name": "Alice", "elo": 1100, "wins": 3, "losses": 1, "streak": 2},
            {"player_id": "pB", "player_name": "Bob",   "elo": 900,  "wins": 1, "losses": 3, "streak": 0},
        ]
        result = await svc.get_standings("guild6")

    assert len(result) == 2
    assert result[0].elo >= result[1].elo


# ── _save_player calls sheets.upsert_standing ─────────────────

def test_save_player_calls_upsert():
    from src.data.models import PlayerElo
    svc = EloService()
    player = PlayerElo(player_id="pX", guild_id="g1", display_name="Xavier", elo=1050, wins=4, losses=1)

    with patch("src.services.elo_service.sheets") as mock_sheets:
        svc._save_player(player)

    mock_sheets.upsert_standing.assert_called_once()
    call_args = mock_sheets.upsert_standing.call_args[0][0]
    assert call_args["player_id"] == "pX"
    assert call_args["elo"] == 1050


# ── record_match updates display names when provided ──────────

@pytest.mark.asyncio
async def test_record_match_sets_display_names():
    """winner_name and loser_name are applied to player records (lines 75, 77)."""
    svc = EloService()
    with patch.object(svc, "_save_player"), \
         patch.object(svc, "_save_player_to_db"), \
         patch("src.services.elo_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = None
        _ = await svc.record_match(
            "guild_dn", "w1", "l1",
            winner_name="Alice", loser_name="Bob",
        )

    import src.services.elo_service as elo_mod
    assert elo_mod._elo_cache["guild_dn"]["w1"].display_name == "Alice"
    assert elo_mod._elo_cache["guild_dn"]["l1"].display_name == "Bob"


# ── NCLP-006: SQLite ELO write-through ───────────────────────────────────────

@pytest.mark.asyncio
async def test_record_match_writes_to_sqlite():
    """record_match should persist both players to SQLite (NCLP-006)."""
    svc = EloService()
    with patch.object(svc, "_save_player"), \
         patch.object(svc, "_save_player_to_db") as mock_db, \
         patch("src.services.elo_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = None
        mock_db.return_value = None
        await svc.record_match("guild_db", "w", "l")

    assert mock_db.call_count == 2
    called_ids = {mock_db.call_args_list[i][0][0].player_id for i in range(2)}
    assert called_ids == {"w", "l"}


@pytest.mark.asyncio
async def test_restore_ratings_from_db_populates_cache():
    """restore_ratings_from_db should fill _elo_cache from SQLite rows (NCLP-006)."""
    import src.services.elo_service as elo_mod
    elo_mod._elo_cache.clear()

    rows = [
        {"guild_id": "g1", "player_id": "pA", "elo": 1150, "wins": 6,
         "losses": 2, "streak": 3, "display_name": "Alice"},
    ]
    svc = EloService()
    with patch("src.services.elo_service.load_all_elo", return_value=rows):
        await svc.restore_ratings_from_db()

    assert "g1" in elo_mod._elo_cache
    assert elo_mod._elo_cache["g1"]["pA"].elo == 1150
    assert elo_mod._elo_cache["g1"]["pA"].wins == 6
