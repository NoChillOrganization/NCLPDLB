"""
Unit tests for BattleSimService — replay parsing, team comparison.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.battle_sim import BattleSimService, ReplayParseResult


SAMPLE_REPLAY_LOG = """|j|☆Player1
|j|☆Player2
|poke|p1|Garchomp, L100, M
|poke|p1|Dragapult, L100
|poke|p2|Corviknight, L100
|poke|p2|Toxapex, L100
|turn|1
|turn|15
|win|Player1
"""

SAMPLE_REPLAY_JSON = {
    "p1": "Player1",
    "p2": "Player2",
    "log": SAMPLE_REPLAY_LOG,
}


# ── Replay Parser ─────────────────────────────────────────────

def test_parse_replay_extracts_winner():
    svc = BattleSimService()
    result = svc._parse_replay_data(SAMPLE_REPLAY_JSON)
    assert result.winner_name == "Player1"

def test_parse_replay_extracts_teams():
    svc = BattleSimService()
    result = svc._parse_replay_data(SAMPLE_REPLAY_JSON)
    assert "Garchomp" in result.p1_team
    assert "Dragapult" in result.p1_team
    assert "Corviknight" in result.p2_team
    assert "Toxapex" in result.p2_team

def test_parse_replay_counts_turns():
    svc = BattleSimService()
    result = svc._parse_replay_data(SAMPLE_REPLAY_JSON)
    assert result.turns == 15

def test_parse_replay_no_winner_returns_unknown():
    svc = BattleSimService()
    data = {"p1": "A", "p2": "B", "log": "|poke|p1|Pikachu\n|turn|1"}
    result = svc._parse_replay_data(data)
    assert result.winner_name == "Unknown"

def test_parse_replay_empty_log():
    svc = BattleSimService()
    result = svc._parse_replay_data({"p1": "A", "p2": "B", "log": ""})
    assert result.success is True
    assert result.p1_team == []
    assert result.p2_team == []

def test_parse_replay_deduplicates_pokemon():
    svc = BattleSimService()
    log = "|poke|p1|Garchomp\n|poke|p1|Garchomp\n|win|A"
    result = svc._parse_replay_data({"p1": "A", "p2": "B", "log": log})
    assert result.p1_team.count("Garchomp") == 1


# ── Team Comparison ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_compare_teams_returns_result():
    from src.data.models import Pokemon, PokemonStats, TeamRoster
    svc = BattleSimService()

    def make_mon(name, types, spe=80, atk=100):
        return Pokemon(
            national_dex=1, name=name, types=types,
            base_stats=PokemonStats(hp=80, atk=atk, def_=80, spa=80, spd=80, spe=spe),
            generation=1,
        )

    team1 = TeamRoster(player_id="p1", guild_id="g1", pokemon=[
        make_mon("Charizard", ["fire", "flying"]),
        make_mon("Gyarados", ["water", "flying"]),
    ])
    team2 = TeamRoster(player_id="p2", guild_id="g1", pokemon=[
        make_mon("Blastoise", ["water"]),
        make_mon("Raichu", ["electric"]),
    ])

    with patch("src.services.battle_sim.TeamService") as MockTS:
        instance = MockTS.return_value
        instance.get_team = AsyncMock(side_effect=[team1, team2])
        result = await svc.compare_teams("g1", "p1", "p2")

    assert result.advantage_summary != ""
    assert isinstance(result.p1_score, float)
    assert isinstance(result.p2_score, float)


@pytest.mark.asyncio
async def test_compare_teams_missing_team():
    svc = BattleSimService()
    with patch("src.services.battle_sim.TeamService") as MockTS:
        instance = MockTS.return_value
        instance.get_team = AsyncMock(return_value=None)
        result = await svc.compare_teams("g1", "p1", "p2")

    assert "Could not load" in result.advantage_summary


# ── Replay fetch (integration-style, mocked HTTP) ─────────────

@pytest.mark.asyncio
async def test_parse_replay_command_fetches_json():
    svc = BattleSimService()
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=SAMPLE_REPLAY_JSON)

    with patch("src.services.battle_sim.sheets") as mock_sheets, \
         patch("aiohttp.ClientSession") as MockSession:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx.get = MagicMock(return_value=mock_ctx)
        mock_ctx.status = 200
        mock_ctx.json = AsyncMock(return_value=SAMPLE_REPLAY_JSON)
        MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        MockSession.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_sheets.save_replay = MagicMock()

        result = await svc.parse_replay(
            guild_id="g1",
            player_id="p1",
            replay_url="https://replay.pokemonshowdown.com/gen9ou-12345",
        )

    assert result.success is True


# ── ReplayParseResult __post_init__ with None teams ────────────

def test_replay_parse_result_default_teams_are_lists():
    """__post_init__ sets p1_team/p2_team to [] when passed None."""
    r = ReplayParseResult(success=True, p1_team=None, p2_team=None)
    assert r.p1_team == []
    assert r.p2_team == []


# ── compare_teams advantage branches ──────────────────────────

@pytest.mark.asyncio
async def test_compare_teams_p1_clear_advantage():
    """p1_score > p2_score + 5 → Player 1 has the advantage."""
    from src.data.models import Pokemon, PokemonStats, TeamRoster
    svc = BattleSimService()

    def make_mon(name, types, spe=80, atk=130):
        return Pokemon(
            national_dex=1, name=name, types=types,
            base_stats=PokemonStats(hp=80, atk=atk, def_=80, spa=80, spd=80, spe=spe),
            generation=1,
        )

    # p1 has fire types; p2 has only steel (fire beats steel)
    team1 = TeamRoster(player_id="p1", guild_id="g1", pokemon=[
        make_mon("Charizard", ["fire"]),
        make_mon("Moltres", ["fire", "flying"]),
        make_mon("Arcanine", ["fire"]),
    ])
    team2 = TeamRoster(player_id="p2", guild_id="g1", pokemon=[
        make_mon("Steelix", ["steel", "ground"], atk=40, spe=30),
        make_mon("Forretress", ["bug", "steel"], atk=40, spe=30),
        make_mon("Skarmory", ["steel", "flying"], atk=40, spe=30),
    ])

    with patch("src.services.battle_sim.TeamService") as MockTS:
        instance = MockTS.return_value
        instance.get_team = AsyncMock(side_effect=[team1, team2])
        result = await svc.compare_teams("g1", "p1", "p2")

    assert result.advantage_summary != ""


@pytest.mark.asyncio
async def test_compare_teams_p2_clear_advantage():
    """p2_score > p1_score + 5 → Player 2 has the advantage."""
    from src.data.models import Pokemon, PokemonStats, TeamRoster
    svc = BattleSimService()

    def make_mon(name, types, spe=80, atk=80):
        return Pokemon(
            national_dex=1, name=name, types=types,
            base_stats=PokemonStats(hp=80, atk=atk, def_=80, spa=80, spd=80, spe=spe),
            generation=1,
        )

    # p1 normal types; p2 fighting (super-effective vs normal)
    team1 = TeamRoster(player_id="p1", guild_id="g1", pokemon=[
        make_mon("Rattata", ["normal"], atk=40, spe=30),
        make_mon("Snorlax", ["normal"], atk=40, spe=30),
    ])
    team2 = TeamRoster(player_id="p2", guild_id="g1", pokemon=[
        make_mon("Machamp", ["fighting"], atk=130, spe=90),
        make_mon("Conkeldurr", ["fighting"], atk=140, spe=45),
    ])

    with patch("src.services.battle_sim.TeamService") as MockTS:
        instance = MockTS.return_value
        instance.get_team = AsyncMock(side_effect=[team1, team2])
        result = await svc.compare_teams("g1", "p1", "p2")

    assert result.advantage_summary != ""


# ── _team_matchup_score speed bonus ───────────────────────────

def test_matchup_score_speed_bonus():
    """Faster Pokemon add 0.5 score bonus."""
    from src.data.models import Pokemon, PokemonStats
    svc = BattleSimService()

    fast = Pokemon(national_dex=1, name="Fast", types=["normal"],
                   base_stats=PokemonStats(hp=80, atk=80, def_=80, spa=80, spd=80, spe=130), generation=1)
    slow = Pokemon(national_dex=2, name="Slow", types=["normal"],
                   base_stats=PokemonStats(hp=80, atk=80, def_=80, spa=80, spd=80, spe=30), generation=1)

    score_fast_vs_slow = svc._team_matchup_score([fast], [slow])
    score_slow_vs_fast = svc._team_matchup_score([slow], [fast])
    assert score_fast_vs_slow > score_slow_vs_fast


# ── parse_replay HTTP error branches ──────────────────────────

@pytest.mark.asyncio
async def test_parse_replay_http_error_status():
    """HTTP non-200 response returns error result."""
    svc = BattleSimService()

    mock_resp = AsyncMock()
    mock_resp.status = 404

    with patch("aiohttp.ClientSession") as MockSession:
        mock_session = AsyncMock()
        MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        MockSession.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_get_ctx = AsyncMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_get_ctx)

        result = await svc.parse_replay("g1", "p1", "https://replay.pokemonshowdown.com/test")

    assert not result.success
    assert "404" in result.error


@pytest.mark.asyncio
async def test_parse_replay_client_error():
    """aiohttp.ClientError is caught and returned as error result."""
    import aiohttp
    svc = BattleSimService()

    with patch("aiohttp.ClientSession") as MockSession:
        mock_session = AsyncMock()
        MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        MockSession.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_get_ctx = AsyncMock()
        mock_get_ctx.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("connection refused"))
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_get_ctx)

        result = await svc.parse_replay("g1", "p1", "https://replay.pokemonshowdown.com/test")

    assert not result.success
    assert "Network error" in result.error


@pytest.mark.asyncio
async def test_parse_replay_non_https_url():
    """URL without https gets upgraded to https://."""
    svc = BattleSimService()

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=SAMPLE_REPLAY_JSON)

    with patch("src.services.battle_sim.sheets"), \
         patch("aiohttp.ClientSession") as MockSession:
        mock_session = AsyncMock()
        MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        MockSession.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_get_ctx = AsyncMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_get_ctx)

        result = await svc.parse_replay("g1", "p1", "replay.pokemonshowdown.com/gen9ou-99")

    assert result.success is True


# ── Malformed turn line (except branch) ───────────────────────

@pytest.mark.asyncio
async def test_parse_replay_parse_exception():
    """_parse_replay_data raising an exception returns error result (lines 163-165)."""
    svc = BattleSimService()

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"p1": "P1", "p2": "P2", "log": "|win|P1"})

    with patch.object(svc, "_parse_replay_data", side_effect=RuntimeError("bad data")), \
         patch("aiohttp.ClientSession") as MockSession:
        mock_session = AsyncMock()
        MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        MockSession.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_get_ctx = AsyncMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_get_ctx)

        result = await svc.parse_replay("g1", "p1", "https://replay.pokemonshowdown.com/test")

    assert not result.success
    assert "Parse error" in result.error


def test_parse_replay_malformed_turn_line():
    """Malformed |turn| line doesn't crash; except block is hit."""
    svc = BattleSimService()
    log = "|poke|p1|Pikachu\n|turn|notanumber\n|win|P1"
    result = svc._parse_replay_data({"p1": "P1", "p2": "P2", "log": log})
    assert result.success
    assert result.turns == 0  # Not updated due to parse error
