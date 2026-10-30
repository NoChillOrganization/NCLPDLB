"""
Trade integrity: accept_trade must not duplicate or drop Pokémon when rosters
changed after the offer, and two answers to one trade must not both succeed.
"""

import asyncio
from unittest.mock import patch

import pytest

import src.services.team_service as ts_mod
from src.data.models import Pokemon, PokemonStats, TeamRoster
from src.services.team_service import TeamService


def make_pokemon(name: str) -> Pokemon:
    return Pokemon(
        national_dex=1,
        name=name,
        types=["normal"],
        base_stats=PokemonStats(hp=80, atk=80, def_=80, spa=80, spd=80, spe=80),
        generation=4,
        showdown_tier="OU",
        vgc_legal=True,
        console_legal={"sv": True, "swsh": True, "bdsp": False, "legends": False},
    )


def make_record(**overrides) -> dict:
    record = {
        "transaction_id": "t1",
        "league_id": "g1",
        "from_player_id": "alice",
        "to_player_id": "bob",
        "pokemon_given": "Garchomp",
        "pokemon_received": "Gholdengo",
        "status": "pending",
    }
    record.update(overrides)
    return record


@pytest.fixture(autouse=True)
def clean_state():
    ts_mod._roster_cache.clear()
    ts_mod._trade_locks.clear()
    yield
    ts_mod._roster_cache.clear()
    ts_mod._trade_locks.clear()


def seed(player: str, names: list[str]) -> TeamRoster:
    roster = TeamRoster(
        player_id=player, guild_id="g1", pokemon=[make_pokemon(n) for n in names]
    )
    ts_mod._roster_cache[f"g1:{player}"] = roster
    return roster


def names(roster: TeamRoster) -> list[str]:
    return sorted(p.name for p in roster.pokemon)


async def test_accept_swaps_the_two_pokemon():
    alice = seed("alice", ["Garchomp", "Corviknight"])
    bob = seed("bob", ["Gholdengo", "Kingambit"])
    record = make_record()
    with patch("src.services.team_service.sheets") as sheets:
        sheets.find_row.return_value = record
        result = await TeamService().accept_trade("bob", "t1")

    assert result.success
    assert names(alice) == ["Corviknight", "Gholdengo"]
    assert names(bob) == ["Garchomp", "Kingambit"]
    assert record["status"] == "accepted"


async def test_accept_fails_when_sender_gave_the_pokemon_away():
    # Alice offered Garchomp, then lost it before Bob answered.
    alice = seed("alice", ["Corviknight"])
    bob = seed("bob", ["Gholdengo", "Kingambit"])
    record = make_record()
    with patch("src.services.team_service.sheets") as sheets:
        sheets.find_row.return_value = record
        result = await TeamService().accept_trade("bob", "t1")

    assert not result.success
    assert "Garchomp" in result.error
    assert names(alice) == ["Corviknight"]
    assert names(bob) == ["Gholdengo", "Kingambit"]
    assert record["status"] == "pending"
    sheets.upsert_team_page.assert_not_called()


async def test_accept_fails_when_receiver_no_longer_has_the_requested_pokemon():
    alice = seed("alice", ["Garchomp"])
    bob = seed("bob", ["Kingambit"])
    record = make_record()
    with patch("src.services.team_service.sheets") as sheets:
        sheets.find_row.return_value = record
        result = await TeamService().accept_trade("bob", "t1")

    assert not result.success
    assert "Gholdengo" in result.error
    assert names(alice) == ["Garchomp"]
    assert names(bob) == ["Kingambit"]
    sheets.upsert_team_page.assert_not_called()


async def test_failed_sheets_write_leaves_cached_rosters_untouched():
    alice = seed("alice", ["Garchomp"])
    bob = seed("bob", ["Gholdengo"])
    with patch("src.services.team_service.sheets") as sheets:
        sheets.find_row.return_value = make_record()
        sheets.upsert_team_page.side_effect = RuntimeError("sheets down")
        with pytest.raises(RuntimeError):
            await TeamService().accept_trade("bob", "t1")

    assert names(alice) == ["Garchomp"]
    assert names(bob) == ["Gholdengo"]


async def test_two_simultaneous_accepts_only_one_wins():
    seed("alice", ["Garchomp"])
    seed("bob", ["Gholdengo"])
    record = make_record()
    with patch("src.services.team_service.sheets") as sheets:
        sheets.find_row.return_value = record
        svc = TeamService()
        first, second = await asyncio.gather(
            svc.accept_trade("bob", "t1"), svc.accept_trade("bob", "t1")
        )

    assert sorted([first.success, second.success]) == [False, True]


async def test_accept_and_decline_cannot_both_succeed():
    seed("alice", ["Garchomp"])
    seed("bob", ["Gholdengo"])
    record = make_record()
    with patch("src.services.team_service.sheets") as sheets:
        sheets.find_row.return_value = record
        svc = TeamService()
        accepted, declined = await asyncio.gather(
            svc.accept_trade("bob", "t1"), svc.decline_trade("bob", "t1")
        )

    assert sorted([accepted.success, declined.success]) == [False, True]
