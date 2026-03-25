"""
Shared pytest fixtures for the Pokemon Draft League Bot test suite.

Fixtures here are available to all tests in tests/ without importing.
The pytest.ini at project root sets asyncio_mode=auto, so async test
functions and async fixtures work without @pytest.mark.asyncio.
"""
import pytest
import tracemalloc
from unittest.mock import MagicMock, AsyncMock

tracemalloc.start()

from src.data.models import (
    Pokemon, PokemonStats,
    Draft, DraftFormat, DraftStatus,
    TeamRoster, PlayerElo,
)


# ── Pokemon helpers ───────────────────────────────────────────────────────────

@pytest.fixture
def make_pokemon():
    """Factory fixture: returns a callable to build Pokemon test objects."""
    def _make(
        name: str = "Garchomp",
        types: list[str] | None = None,
        hp: int = 80, atk: int = 100, def_: int = 80,
        spa: int = 80, spd: int = 80, spe: int = 100,
        generation: int = 4,
        national_dex: int = 445,
        is_legendary: bool = False,
        is_mythical: bool = False,
    ) -> Pokemon:
        return Pokemon(
            national_dex=national_dex,
            name=name,
            types=types or ["dragon", "ground"],
            base_stats=PokemonStats(
                hp=hp, atk=atk, def_=def_, spa=spa, spd=spd, spe=spe
            ),
            generation=generation,
            is_legendary=is_legendary,
            is_mythical=is_mythical,
        )
    return _make


@pytest.fixture
def mock_pokemon(make_pokemon) -> Pokemon:
    """A single ready-to-use Garchomp Pokemon object."""
    return make_pokemon()


# ── Sheets mock ───────────────────────────────────────────────────────────────

@pytest.fixture
def mock_sheets():
    """
    A MagicMock that satisfies all SheetsClient method calls.
    Use with: patch("src.services.<module>.sheets", mock_sheets)
    """
    m = MagicMock()
    m.save_league_setup = MagicMock()
    m.save_pick = MagicMock()
    m.save_transaction = MagicMock()
    m.save_replay = MagicMock()
    m.upsert_standing = MagicMock()
    m.get_standings = MagicMock(return_value=[])
    m.find_row = MagicMock(return_value=None)
    m.read_all = MagicMock(return_value=[])
    m.bulk_write_pokedex = MagicMock()
    return m


# ── Pokemon DB mock ───────────────────────────────────────────────────────────

@pytest.fixture
def mock_pokemon_db(mock_pokemon):
    """
    A MagicMock that satisfies PokemonDatabase method calls.
    find() returns mock_pokemon by default; search() returns a one-item list.
    Use with: patch("src.services.<module>.pokemon_db", mock_pokemon_db)
    """
    m = MagicMock()
    m.find = MagicMock(return_value=mock_pokemon)
    m.search = MagicMock(return_value=[mock_pokemon])
    m.all_pokemon = [mock_pokemon]
    return m


# ── Draft helpers ─────────────────────────────────────────────────────────────

@pytest.fixture
def active_draft(make_pokemon) -> Draft:
    """
    A pre-built 2-player snake draft in ACTIVE state with no picks yet.
    Players: "p1" (commissioner), "p2".
    """
    return Draft(
        draft_id="test-draft",
        guild_id="test-guild",
        commissioner_id="p1",
        format=DraftFormat.SNAKE,
        status=DraftStatus.ACTIVE,
        total_rounds=3,
        player_order=["p1", "p2"],
    )


# ── ELO helpers ───────────────────────────────────────────────────────────────

@pytest.fixture
def make_elo():
    """Factory fixture: returns a callable to build PlayerElo test objects."""
    def _make(
        player_id: str = "p1",
        guild_id: str = "guild1",
        elo: int = 1000,
        wins: int = 0,
        losses: int = 0,
        streak: int = 0,
        display_name: str = "",
    ) -> PlayerElo:
        return PlayerElo(
            player_id=player_id,
            guild_id=guild_id,
            elo=elo,
            wins=wins,
            losses=losses,
            streak=streak,
            display_name=display_name or player_id,
        )
    return _make


# ── TeamRoster helpers ────────────────────────────────────────────────────────

@pytest.fixture
def make_team(make_pokemon):
    """Factory fixture: returns a callable to build TeamRoster test objects."""
    def _make(
        player_id: str = "p1",
        guild_id: str = "guild1",
        pokemon_names: list[str] | None = None,
    ) -> TeamRoster:
        if pokemon_names is None:
            pokemon_names = ["Garchomp", "Corviknight", "Toxapex"]
        mons = [make_pokemon(name=n, types=["normal"], national_dex=i + 1)
                for i, n in enumerate(pokemon_names)]
        return TeamRoster(player_id=player_id, guild_id=guild_id, pokemon=mons)
    return _make


# ── Async discord.Interaction mock ────────────────────────────────────────────

@pytest.fixture
def mock_interaction():
    """
    A minimal AsyncMock of a discord.Interaction for testing cog commands.
    Sets interaction.response.send_message, interaction.user.id, etc.
    """
    interaction = MagicMock()
    interaction.guild_id = 123456789
    interaction.user = MagicMock()
    interaction.user.id = 111111111
    interaction.user.display_name = "TestUser"
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction
