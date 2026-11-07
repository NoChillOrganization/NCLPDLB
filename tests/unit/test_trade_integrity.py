"""
Trade integrity: accept_trade must not duplicate or drop Pokémon when rosters
changed after the offer, and two answers to one trade must not both succeed.
"""

import asyncio
from unittest.mock import patch

import pytest

import src.services.team_service as ts_mod
from src.data.models import Pokemon, PokemonStats, TeamRoster


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
        result = await ts_mod.TeamService().accept_trade("bob", "t1")

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
        result = await ts_mod.TeamService().accept_trade("bob", "t1")

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
        result = await ts_mod.TeamService().accept_trade("bob", "t1")

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
            await ts_mod.TeamService().accept_trade("bob", "t1")

    assert names(alice) == ["Garchomp"]
    assert names(bob) == ["Gholdengo"]


async def test_two_simultaneous_accepts_only_one_wins():
    seed("alice", ["Garchomp"])
    seed("bob", ["Gholdengo"])
    record = make_record()
    with patch("src.services.team_service.sheets") as sheets:
        sheets.find_row.return_value = record
        svc = ts_mod.TeamService()
        first, second = await asyncio.gather(
            svc.accept_trade("bob", "t1"), svc.accept_trade("bob", "t1")
        )

    assert sorted([first.success, second.success]) == [False, True]


async def test_same_pokemon_in_two_trades_is_only_traded_once():
    # Alice offered Garchomp to both Bob and Carol; both accept at the same moment.
    alice = seed("alice", ["Garchomp"])
    bob = seed("bob", ["Gholdengo"])
    carol = seed("carol", ["Kingambit"])
    records = {
        "t1": make_record(),
        "t2": make_record(
            transaction_id="t2", to_player_id="carol", pokemon_received="Kingambit"
        ),
    }
    with patch("src.services.team_service.sheets") as sheets:
        sheets.find_row.side_effect = lambda tab, col, value: records[value]
        svc = ts_mod.TeamService()
        first, second = await asyncio.gather(
            svc.accept_trade("bob", "t1"), svc.accept_trade("carol", "t2")
        )

    assert sorted([first.success, second.success]) == [False, True]
    everyone = names(alice) + names(bob) + names(carol)
    assert everyone.count("Garchomp") == 1
    assert len(everyone) == 3


async def test_second_roster_write_failure_restores_the_first():
    alice = seed("alice", ["Garchomp"])
    bob = seed("bob", ["Gholdengo"])
    with patch("src.services.team_service.sheets") as sheets:
        sheets.find_row.return_value = make_record()
        sheets.upsert_team_page.side_effect = [None, RuntimeError("quota"), None, None]
        with pytest.raises(RuntimeError):
            await ts_mod.TeamService().accept_trade("bob", "t1")

    written = [c.args[0] for c in sheets.upsert_team_page.call_args_list]
    assert [w["player_id"] for w in written] == [
        "alice",
        "bob",
        "alice",
        "bob",
    ]
    assert written[2]["slots"] == [("Garchomp", "")]  # alice put back as it was
    assert written[3]["slots"] == [("Gholdengo", "")]  # bob too (write may have landed)
    assert names(alice) == ["Garchomp"]
    assert names(bob) == ["Gholdengo"]


async def test_accept_and_decline_cannot_both_succeed():
    seed("alice", ["Garchomp"])
    seed("bob", ["Gholdengo"])
    record = make_record()
    with patch("src.services.team_service.sheets") as sheets:
        sheets.find_row.return_value = record
        svc = ts_mod.TeamService()
        accepted, declined = await asyncio.gather(
            svc.accept_trade("bob", "t1"), svc.decline_trade("bob", "t1")
        )

    assert sorted([accepted.success, declined.success]) == [False, True]


async def test_failed_final_save_restores_both_rosters_and_keeps_trade_pending():
    alice = seed("alice", ["Garchomp"])
    bob = seed("bob", ["Gholdengo"])
    record = make_record()
    with patch("src.services.team_service.sheets") as sheets:
        sheets.find_row.return_value = record
        sheets.save_transaction.side_effect = RuntimeError("sheets down")
        with pytest.raises(RuntimeError):
            await ts_mod.TeamService().accept_trade("bob", "t1")

    assert names(alice) == ["Garchomp"]
    assert names(bob) == ["Gholdengo"]
    assert record["status"] == "pending"
    # Last write per player must be the original roster.
    last = {}
    for call in sheets.upsert_team_page.call_args_list:
        page = call.args[0]
        last[page["player_id"]] = [n for n, _ in page["slots"]]
    assert last == {"alice": ["Garchomp"], "bob": ["Gholdengo"]}


async def test_trade_with_yourself_is_rejected():
    alice = seed("alice", ["Garchomp", "Gholdengo"])
    record = make_record(to_player_id="alice")
    with patch("src.services.team_service.sheets") as sheets:
        sheets.find_row.return_value = record
        result = await ts_mod.TeamService().accept_trade("alice", "t1")

    assert not result.success
    assert names(alice) == ["Garchomp", "Gholdengo"]
    sheets.upsert_team_page.assert_not_called()


async def test_register_team_waits_for_an_in_flight_trade():
    lock = ts_mod._trade_locks.setdefault("g1", asyncio.Lock())
    with patch("src.services.team_service.sheets") as sheets:
        async with lock:
            task = asyncio.create_task(
                ts_mod.TeamService().register_team("g1", "alice", "Alice", "Team")
            )
            await asyncio.sleep(0.05)
            sheets.upsert_team_page.assert_not_called()
        await task
        sheets.upsert_team_page.assert_called_once()
