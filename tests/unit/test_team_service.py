"""
Unit tests for TeamService — roster management, trades, import/export, legality.
"""
import json
import pytest
from unittest.mock import MagicMock, patch

import src.services.team_service as ts_mod
from src.services.team_service import TeamService
from src.data.models import Pokemon, PokemonStats, TeamRoster


# ── Helpers ───────────────────────────────────────────────────

def make_pokemon(name: str, types=None, spe=80, tier="OU", vgc=True,
                 console=None, showdown_tier="OU") -> Pokemon:
    return Pokemon(
        national_dex=1, name=name,
        types=types or ["dragon", "ground"],
        base_stats=PokemonStats(hp=80, atk=100, def_=80, spa=80, spd=80, spe=spe),
        generation=4,
        showdown_tier=showdown_tier,
        vgc_legal=vgc,
        console_legal=console or {"sv": True, "swsh": True, "bdsp": False, "legends": False},
    )


@pytest.fixture(autouse=True)
def clear_roster_cache():
    ts_mod._roster_cache.clear()
    yield
    ts_mod._roster_cache.clear()


# ── get_team ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_team_returns_none_when_not_found():
    svc = TeamService()
    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = None
        result = await svc.get_team("g1", "p_missing")
    assert result is None


@pytest.mark.asyncio
async def test_get_team_from_cache():
    svc = TeamService()
    garchomp = make_pokemon("Garchomp")
    roster = TeamRoster(player_id="p1", guild_id="g1", pokemon=[garchomp])
    ts_mod._roster_cache["g1:p1"] = roster

    result = await svc.get_team("g1", "p1")
    assert result is roster


@pytest.mark.asyncio
async def test_get_team_loads_from_sheets():
    svc = TeamService()
    garchomp = make_pokemon("Garchomp")

    with patch("src.services.team_service.sheets") as mock_sheets, \
         patch("src.services.team_service.pokemon_db") as mock_db:
        mock_sheets.find_row.return_value = {
            "team_id": "T1", "player_id": "p1", "guild_id": "g1",
            "pokemon_list": json.dumps(["Garchomp"]),
        }
        mock_db.find.return_value = garchomp
        result = await svc.get_team("g1", "p1")

    assert result is not None
    assert len(result.pokemon) == 1
    assert result.pokemon[0].name == "Garchomp"


@pytest.mark.asyncio
async def test_get_team_wrong_guild():
    svc = TeamService()
    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = {
            "team_id": "T1", "player_id": "p1", "guild_id": "g2",
        }
        result = await svc.get_team("g1", "p1")
    assert result is None


@pytest.mark.asyncio
async def test_get_team_invalid_json_pokemon_list():
    """pokemon_list with invalid JSON triggers JSONDecodeError → defaults to empty list."""
    svc = TeamService()
    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = {
            "team_id": "T1", "player_id": "p1", "guild_id": "g1",
            "pokemon_list": "not valid json ][",
        }
        result = await svc.get_team("g1", "p1")
    assert result is not None
    assert result.pokemon == []


@pytest.mark.asyncio
async def test_get_team_non_list_json_pokemon_list():
    """pokemon_list containing a JSON string (not a list) triggers isinstance check → empty list."""
    svc = TeamService()
    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = {
            "team_id": "T1", "player_id": "p1", "guild_id": "g1",
            "pokemon_list": '"a string value"',
        }
        result = await svc.get_team("g1", "p1")
    assert result is not None
    assert result.pokemon == []


# ── register_team ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_team_creates_roster():
    svc = TeamService()
    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.upsert_team_page = MagicMock()
        roster = await svc.register_team("g1", "p1", "Alice", "Flame Squad", pool="A")

    assert roster.team_name == "Flame Squad"
    assert roster.pool == "A"
    mock_sheets.upsert_team_page.assert_called_once()


@pytest.mark.asyncio
async def test_register_team_updates_existing_in_cache():
    svc = TeamService()
    garchomp = make_pokemon("Garchomp")
    existing = TeamRoster(player_id="p1", guild_id="g1", pokemon=[garchomp])
    ts_mod._roster_cache["g1:p1"] = existing

    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.upsert_team_page = MagicMock()
        roster = await svc.register_team("g1", "p1", "Alice", "New Name", pool="B")

    assert roster.team_name == "New Name"
    assert len(roster.pokemon) == 1  # preserved existing pokemon


# ── propose_trade ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_propose_trade_success():
    svc = TeamService()
    garchomp = make_pokemon("Garchomp")
    corviknight = make_pokemon("Corviknight", types=["flying", "steel"])

    from_team = TeamRoster(player_id="p1", guild_id="g1", pokemon=[garchomp])
    to_team = TeamRoster(player_id="p2", guild_id="g1", pokemon=[corviknight])
    ts_mod._roster_cache["g1:p1"] = from_team
    ts_mod._roster_cache["g1:p2"] = to_team

    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.save_transaction = MagicMock()
        result = await svc.propose_trade("g1", "p1", "p2", "Garchomp", "Corviknight")

    assert result.success
    assert result.trade_id != ""
    mock_sheets.save_transaction.assert_called_once()


@pytest.mark.asyncio
async def test_propose_trade_no_from_team():
    svc = TeamService()
    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = None
        result = await svc.propose_trade("g1", "no_team", "p2", "Garchomp", "Corviknight")
    assert not result.success
    assert "don't have a team" in result.error


@pytest.mark.asyncio
async def test_propose_trade_no_to_team():
    svc = TeamService()
    from_team = TeamRoster(player_id="p1", guild_id="g1", pokemon=[make_pokemon("Garchomp")])
    ts_mod._roster_cache["g1:p1"] = from_team

    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = None
        result = await svc.propose_trade("g1", "p1", "no_team", "Garchomp", "Corviknight")
    assert not result.success
    assert "doesn't have a team" in result.error


@pytest.mark.asyncio
async def test_propose_trade_dont_have_offering():
    svc = TeamService()
    from_team = TeamRoster(player_id="p1", guild_id="g1", pokemon=[make_pokemon("Garchomp")])
    to_team = TeamRoster(player_id="p2", guild_id="g1", pokemon=[make_pokemon("Corviknight")])
    ts_mod._roster_cache["g1:p1"] = from_team
    ts_mod._roster_cache["g1:p2"] = to_team

    result = await svc.propose_trade("g1", "p1", "p2", "Mewtwo", "Corviknight")
    assert not result.success
    assert "don't have" in result.error


@pytest.mark.asyncio
async def test_propose_trade_opponent_doesnt_have():
    svc = TeamService()
    from_team = TeamRoster(player_id="p1", guild_id="g1", pokemon=[make_pokemon("Garchomp")])
    to_team = TeamRoster(player_id="p2", guild_id="g1", pokemon=[make_pokemon("Corviknight")])
    ts_mod._roster_cache["g1:p1"] = from_team
    ts_mod._roster_cache["g1:p2"] = to_team

    result = await svc.propose_trade("g1", "p1", "p2", "Garchomp", "Mewtwo")
    assert not result.success
    assert "Opponent doesn't have" in result.error


# ── accept_trade ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_accept_trade_success():
    svc = TeamService()
    garchomp = make_pokemon("Garchomp")
    corviknight = make_pokemon("Corviknight")
    from_team = TeamRoster(player_id="p1", guild_id="g1", pokemon=[garchomp])
    to_team = TeamRoster(player_id="p2", guild_id="g1", pokemon=[corviknight])
    ts_mod._roster_cache["g1:p1"] = from_team
    ts_mod._roster_cache["g1:p2"] = to_team

    with patch("src.services.team_service.sheets") as mock_sheets, \
         patch("src.services.team_service.pokemon_db") as mock_db:
        mock_sheets.find_row.return_value = {
            "transaction_id": "T1",
            "to_player_id": "p2",
            "from_player_id": "p1",
            "league_id": "g1",
            "pokemon_given": "Garchomp",
            "pokemon_received": "Corviknight",
            "status": "pending",
        }
        mock_sheets.save_transaction = MagicMock()
        mock_db.find.side_effect = lambda name: make_pokemon(name)
        result = await svc.accept_trade("p2", "T1")

    assert result.success
    assert "Garchomp" in result.summary
    assert "Corviknight" in result.summary


@pytest.mark.asyncio
async def test_accept_trade_not_found():
    svc = TeamService()
    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = None
        result = await svc.accept_trade("p1", "bad_id")
    assert not result.success
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_accept_trade_wrong_player():
    svc = TeamService()
    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = {
            "transaction_id": "T1", "to_player_id": "p2", "status": "pending",
        }
        result = await svc.accept_trade("wrong_player", "T1")
    assert not result.success
    assert "not for you" in result.error


@pytest.mark.asyncio
async def test_accept_trade_not_pending():
    svc = TeamService()
    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = {
            "transaction_id": "T1", "to_player_id": "p2", "status": "accepted",
        }
        result = await svc.accept_trade("p2", "T1")
    assert not result.success
    assert "no longer pending" in result.error


# ── decline_trade ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decline_trade_success():
    svc = TeamService()
    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = {
            "transaction_id": "T1", "to_player_id": "p2", "status": "pending",
        }
        mock_sheets.save_transaction = MagicMock()
        result = await svc.decline_trade("p2", "T1")
    assert result.success
    assert "declined" in result.summary.lower()


@pytest.mark.asyncio
async def test_decline_trade_not_found():
    svc = TeamService()
    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = None
        result = await svc.decline_trade("p1", "bad_id")
    assert not result.success


@pytest.mark.asyncio
async def test_decline_trade_wrong_player():
    svc = TeamService()
    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = {
            "transaction_id": "T1", "to_player_id": "p2", "status": "pending",
        }
        result = await svc.decline_trade("wrong", "T1")
    assert not result.success
    assert "not for you" in result.error


@pytest.mark.asyncio
async def test_decline_trade_not_pending():
    svc = TeamService()
    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = {
            "transaction_id": "T1", "to_player_id": "p2", "status": "declined",
        }
        result = await svc.decline_trade("p2", "T1")
    assert not result.success
    assert "no longer pending" in result.error


# ── import_showdown ───────────────────────────────────────────

SHOWDOWN_TEXT = """Garchomp @ Choice Scarf
Ability: Rough Skin
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Scale Shot
- Earthquake

Corviknight @ Rocky Helmet
Ability: Mirror Armor
"""


@pytest.mark.asyncio
async def test_import_showdown_success():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as mock_db:
        mock_db.find.side_effect = lambda name: make_pokemon(name)
        result = await svc.import_showdown("g1", "p1", SHOWDOWN_TEXT)
    assert result.success
    assert len(result.pokemon) == 2


@pytest.mark.asyncio
async def test_import_showdown_pokemon_not_in_db(capsys):
    """Lines with unknown Pokemon log a warning but continue."""
    svc = TeamService()
    text = "FakeMon123 @ Choice Scarf\nAbility: Test\n\nGarchomp @ Scarf\nAbility: Rough Skin"
    with patch("src.services.team_service.pokemon_db") as mock_db:
        mock_db.find.side_effect = lambda name: None if "FakeMon" in name else make_pokemon(name)
        result = await svc.import_showdown("g1", "p1", text)
    # Only Garchomp was found
    assert result.success
    assert len(result.pokemon) == 1


@pytest.mark.asyncio
async def test_import_showdown_no_valid_pokemon():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as mock_db:
        mock_db.find.return_value = None
        result = await svc.import_showdown("g1", "p1", "FakeMon @ Scarf\n")
    assert not result.success
    assert "No valid Pokemon" in result.error


# ── export_showdown ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_showdown_no_team():
    svc = TeamService()
    with patch("src.services.team_service.sheets") as mock_sheets:
        mock_sheets.find_row.return_value = None
        result = await svc.export_showdown("g1", "p1")
    assert "No team" in result


@pytest.mark.asyncio
async def test_export_showdown_with_team():
    svc = TeamService()
    garchomp = make_pokemon("Garchomp")
    garchomp.abilities = ["Rough Skin", "Sand Veil"]
    roster = TeamRoster(player_id="p1", guild_id="g1", pokemon=[garchomp])
    ts_mod._roster_cache["g1:p1"] = roster

    result = await svc.export_showdown("g1", "p1")
    assert "Garchomp" in result
    assert "Ability:" in result


# ── check_legality ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_legality_pokemon_not_found():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as mock_db:
        mock_db.find.return_value = None
        result = await svc.check_legality("FakeMon", "vgc")
    assert not result.legal
    assert "not found" in result.reason


@pytest.mark.asyncio
async def test_check_legality_vgc_legal():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as mock_db:
        mock_db.find.return_value = make_pokemon("Garchomp", vgc=True)
        result = await svc.check_legality("Garchomp", "vgc")
    assert result.legal
    assert "✅" in result.reason


@pytest.mark.asyncio
async def test_check_legality_vgc_illegal():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as mock_db:
        mock_db.find.return_value = make_pokemon("MewtwoVGC", vgc=False)
        result = await svc.check_legality("MewtwoVGC", "vgc")
    assert not result.legal
    assert "❌" in result.reason


@pytest.mark.asyncio
async def test_check_legality_showdown_tier():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as mock_db:
        mock_db.find.return_value = make_pokemon("Garchomp", showdown_tier="OU")
        result = await svc.check_legality("Garchomp", "showdown_OU")
    assert result.legal
    assert "OU" in result.reason


@pytest.mark.asyncio
async def test_check_legality_showdown_wrong_tier():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as mock_db:
        mock_db.find.return_value = make_pokemon("Rattata", showdown_tier="PU")
        result = await svc.check_legality("Rattata", "showdown_OU")
    assert not result.legal


@pytest.mark.asyncio
async def test_check_legality_console_sv():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as mock_db:
        mock_db.find.return_value = make_pokemon("Garchomp", console={"sv": True})
        result = await svc.check_legality("Garchomp", "sv")
    assert result.legal
    assert "Scarlet/Violet" in result.reason


@pytest.mark.asyncio
async def test_check_legality_console_swsh():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as mock_db:
        mock_db.find.return_value = make_pokemon("Old", console={"swsh": True})
        result = await svc.check_legality("Old", "swsh")
    assert result.legal
    assert "Sword/Shield" in result.reason


@pytest.mark.asyncio
async def test_check_legality_console_not_available():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as mock_db:
        mock_db.find.return_value = make_pokemon("Missingno", console={"sv": False})
        result = await svc.check_legality("Missingno", "sv")
    assert not result.legal
    assert "❌" in result.reason
