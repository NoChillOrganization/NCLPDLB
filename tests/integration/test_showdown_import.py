"""
Integration tests for Showdown import/export, replay parsing, and console legality checking.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.services.team_service import TeamService
from src.services.battle_sim import BattleSimService

SAMPLE_TEAM = """
Garchomp @ Choice Scarf
Ability: Rough Skin
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Scale Shot
- Earthquake

Corviknight @ Leftovers
Ability: Pressure
- Body Press
- Roost

Toxapex @ Black Sludge
Ability: Regenerator
- Scald
- Toxic
"""

NICKNAME_TEAM = """
Speedy (Garchomp) @ Choice Scarf
- Earthquake

BigBird (Corviknight) @ Leftovers
- Body Press
"""


def _mock_db(known: list[str]):
    def find(name):
        for k in known:
            if k.lower() in name.lower() or name.lower() in k.lower():
                m = MagicMock()
                m.name = k
                m.types = ["normal"]
                return m
        return None
    return find


@pytest.mark.asyncio
async def test_import_standard_format():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as db, \
         patch("src.services.team_service.sheets"):
        db.find = _mock_db(["Garchomp", "Corviknight", "Toxapex"])
        result = await svc.import_showdown("g1", "p1", SAMPLE_TEAM)
    assert result.success
    names = [p.name for p in result.pokemon]
    assert "Garchomp" in names and "Corviknight" in names and "Toxapex" in names


@pytest.mark.asyncio
async def test_import_nickname_format():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as db, \
         patch("src.services.team_service.sheets"):
        db.find = _mock_db(["Garchomp", "Corviknight"])
        result = await svc.import_showdown("g2", "p2", NICKNAME_TEAM)
    assert result.success
    names = [p.name for p in result.pokemon]
    assert "Garchomp" in names and "Corviknight" in names


@pytest.mark.asyncio
async def test_import_empty_fails():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as db, \
         patch("src.services.team_service.sheets"):
        db.find = MagicMock(return_value=None)
        result = await svc.import_showdown("g3", "p3", "")
    assert not result.success


@pytest.mark.asyncio
async def test_legality_vgc_legal():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as db:
        mon = MagicMock()
        mon.name = "Garchomp"
        mon.vgc_legal = True
        mon.vgc_season = "Regulation H"
        db.find = MagicMock(return_value=mon)
        result = await svc.check_legality("Garchomp", "vgc")
    assert result.legal


@pytest.mark.asyncio
async def test_legality_sv_available():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as db:
        mon = MagicMock()
        mon.name = "Pikachu"
        mon.console_legal = {"sv": True, "swsh": True, "bdsp": False, "legends": False}
        db.find = MagicMock(return_value=mon)
        result = await svc.check_legality("Pikachu", "sv")
    assert result.legal
    assert "Scarlet/Violet" in result.reason


@pytest.mark.asyncio
async def test_legality_not_in_sv():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as db:
        mon = MagicMock()
        mon.name = "Mewtwo"
        mon.console_legal = {"sv": False, "swsh": False, "bdsp": True, "legends": False}
        db.find = MagicMock(return_value=mon)
        result = await svc.check_legality("Mewtwo", "sv")
    assert not result.legal
    assert "NOT available" in result.reason


@pytest.mark.asyncio
async def test_legality_unknown_pokemon():
    svc = TeamService()
    with patch("src.services.team_service.pokemon_db") as db:
        db.find = MagicMock(return_value=None)
        result = await svc.check_legality("NotReal", "sv")
    assert not result.legal
    assert "not found" in result.reason


# ── Replay Parsing Tests ─────────────────────────────────────────────────────

MOCK_REPLAY_JSON = {
    "p1": "Alice",
    "p2": "Bob",
    "log": """
|player|p1|Alice|1|
|player|p2|Bob|2|
|teamsize|p1|6
|teamsize|p2|6
|gametype|singles
|gen|9
|tier|Gen 9 OU
|poke|p1|Garchomp, L50
|poke|p1|Corviknight, L50
|poke|p1|Toxapex, L50
|poke|p2|Dragapult, L50
|poke|p2|Ferrothorn, L50
|poke|p2|Heatran, L50
|start
|turn|1
|switch|p1a: Garchomp|Garchomp, L50, M|100/100
|switch|p2a: Dragapult|Dragapult, L50, M|100/100
|turn|2
|move|p1a: Garchomp|Earthquake|p2a: Dragapult
|-damage|p2a: Dragapult|45/100
|turn|3
|move|p2a: Dragapult|Dragon Darts|p1a: Garchomp
|-damage|p1a: Garchomp|0 fnt
|faint|p1a: Garchomp
|win|Bob
""".strip()
}


@pytest.mark.asyncio
async def test_replay_parse_success():
    """Test parsing a valid Showdown replay JSON."""
    svc = BattleSimService()
    result = svc._parse_replay_data(MOCK_REPLAY_JSON)

    assert result.success
    assert result.p1_name == "Alice"
    assert result.p2_name == "Bob"
    assert "Garchomp" in result.p1_team
    assert "Corviknight" in result.p1_team
    assert "Toxapex" in result.p1_team
    assert "Dragapult" in result.p2_team
    assert "Ferrothorn" in result.p2_team
    assert "Heatran" in result.p2_team
    assert result.winner_name == "Bob"
    assert result.turns == 3


@pytest.mark.asyncio
async def test_replay_parse_empty_log():
    """Test replay parsing with empty log."""
    svc = BattleSimService()
    result = svc._parse_replay_data({"log": "", "p1": "P1", "p2": "P2"})

    assert result.success
    assert result.p1_name == "P1"
    assert result.p2_name == "P2"
    assert len(result.p1_team) == 0
    assert len(result.p2_team) == 0
    assert result.turns == 0


@pytest.mark.asyncio
async def test_replay_parse_duplicate_pokemon():
    """Test that duplicate Pokemon in log are deduplicated."""
    svc = BattleSimService()
    replay_data = {
        "p1": "Alice",
        "p2": "Bob",
        "log": """
|poke|p1|Garchomp, L50
|poke|p1|Garchomp, L50
|poke|p1|Corviknight, L50
|poke|p2|Dragapult, L50
""".strip()
    }
    result = svc._parse_replay_data(replay_data)

    assert result.success
    assert result.p1_team.count("Garchomp") == 1
    assert result.p1_team.count("Corviknight") == 1


# ── Showdown Export Tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_round_trip():
    """Test import → export round-trip preserves core team data."""
    from src.data.models import Pokemon, PokemonStats, TeamRoster
    svc = TeamService()

    def make_mon(name: str) -> Pokemon:
        return Pokemon(
            national_dex=1,
            name=name.title(),
            types=["normal"],
            base_stats=PokemonStats(hp=80, atk=80, def_=80, spa=80, spd=80, spe=80),
            generation=8,
        )

    with patch("src.services.team_service.pokemon_db") as db, \
         patch("src.services.team_service.sheets"):
        db.find = lambda name: make_mon(name)

        # Import team
        import_result = await svc.import_showdown("g1", "p1", SAMPLE_TEAM)
        assert import_result.success

        # Build a TeamRoster from the imported pokemon (export_showdown expects TeamRoster)
        roster = TeamRoster(player_id="p1", guild_id="g1", pokemon=import_result.pokemon)

        # Export team — returns a plain str
        with patch.object(svc, "get_team", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = roster
            export_result = await svc.export_showdown("g1", "p1")

        assert isinstance(export_result, str)
        assert "Garchomp" in export_result
        assert "Corviknight" in export_result
        assert "Toxapex" in export_result


@pytest.mark.asyncio
async def test_import_with_tera_type():
    """Test importing team with Gen 9 Tera Type."""
    tera_team = """
Garchomp @ Choice Scarf
Ability: Rough Skin
Tera Type: Fire
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Earthquake
- Fire Fang
"""
    svc = TeamService()

    with patch("src.services.team_service.pokemon_db") as db, \
         patch("src.services.team_service.sheets"):
        mon = MagicMock()
        mon.name = "Garchomp"
        mon.types = ["dragon", "ground"]
        db.find = MagicMock(return_value=mon)

        result = await svc.import_showdown("g1", "p1", tera_team)

    assert result.success
    assert "Garchomp" in [p.name for p in result.pokemon]


@pytest.mark.asyncio
async def test_import_malformed_team():
    """Test import with malformed Showdown format fails gracefully."""
    malformed = "This is not a valid team format at all!!!"
    svc = TeamService()

    with patch("src.services.team_service.pokemon_db") as db, \
         patch("src.services.team_service.sheets"):
        db.find = MagicMock(return_value=None)
        result = await svc.import_showdown("g1", "p1", malformed)

    assert not result.success
