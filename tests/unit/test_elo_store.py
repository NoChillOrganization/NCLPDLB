"""ELO reconciliation across cache, Local store (SQLite) and League sheet.

The League sheet is a real LeagueSheet over a fake spreadsheet; SQLite writes
are captured.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.config import settings
from src.data.elo_store import EloStore
from src.data.models import PlayerElo
from src.data.sheets import LeagueSheet, Tab
from tests.fake_gspread import FakeSpreadsheet

HEADERS = ["player_id", "player_name", "elo", "wins", "losses", "streak"]


@pytest.fixture
def world():
    """(store, ss, db_save): a fresh EloStore over a fake League sheet."""
    ss = FakeSpreadsheet(ELO_Data=[HEADERS])
    sheet = LeagueSheet()
    sheet._conn._spreadsheet = ss
    with (
        patch("src.data.elo_store.league_sheet", sheet),
        patch("src.data.elo_store._db_save_elo", new_callable=AsyncMock) as db_save,
    ):
        yield EloStore(), ss, db_save


async def test_cache_hit_does_not_touch_the_sheet(world):
    store, ss, _ = world
    store.cache["g"] = {"p1": PlayerElo(player_id="p1", guild_id="g", elo=1234)}
    assert (await store.get("g", "p1")).elo == 1234
    assert not ss.tabs[Tab.ELO_DATA].threads


async def test_miss_reads_the_league_sheet_by_player_id(world):
    store, ss, _ = world
    ss.tabs[Tab.ELO_DATA].rows.append(["p1", "Alice", "1200 ", "5", "2", "-1"])
    player = await store.get("g", "p1")
    assert (player.display_name, player.elo, player.wins, player.losses) == (
        "Alice",
        1200,
        5,
        2,
    )
    assert player.streak == -1
    assert player.guild_id == "g"  # the guild comes from the cache key, not the sheet
    assert store.cache["g"]["p1"] is player


async def test_miss_on_sheet_gives_default_rating(world):
    store, _, _ = world
    assert (await store.get("g", "new")).elo == settings.elo_default_rating


async def test_sheet_row_is_not_guild_scoped(world):
    """One spreadsheet per League: a player_id found on the sheet serves any guild."""
    store, ss, _ = world
    ss.tabs[Tab.ELO_DATA].rows.append(["p1", "Alice", "1200", "5", "2", "0"])
    assert (await store.get("g1", "p1")).elo == 1200
    assert (await store.get("g2", "p1")).elo == 1200


async def test_blank_cells_fall_back_to_defaults(world):
    store, ss, _ = world
    ss.tabs[Tab.ELO_DATA].rows.append(["p1", "Alice", "", "", "x", ""])
    player = await store.get("g", "p1")
    assert (player.elo, player.wins, player.losses, player.streak) == (
        settings.elo_default_rating,
        0,
        0,
        0,
    )


async def test_save_writes_sheet_then_local_store(world):
    store, ss, db_save = world
    a = PlayerElo(player_id="a", guild_id="g", display_name="A", elo=1016, wins=1)
    b = PlayerElo(player_id="b", guild_id="g", display_name="B", elo=984, losses=1)
    seen_in_sheet_at_db_time: list[int] = []
    db_save.side_effect = lambda **kw: seen_in_sheet_at_db_time.append(
        len(ss.tabs[Tab.ELO_DATA].rows)
    )

    await store.save(a, b)

    rows = ss.tabs[Tab.ELO_DATA].rows
    assert rows[1][:5] == ["a", "A", 1016, 1, 0]
    assert rows[2][:5] == ["b", "B", 984, 0, 1]
    assert seen_in_sheet_at_db_time == [
        3,
        3,
    ]  # both sheet rows exist before any db write
    assert [c.kwargs["player_id"] for c in db_save.await_args_list] == ["a", "b"]
    assert db_save.await_args_list[0].kwargs["elo"] == 1016


async def test_local_store_failure_is_raised(world):
    store, _, db_save = world
    db_save.side_effect = RuntimeError("disk full")
    with pytest.raises(RuntimeError, match="disk full"):
        await store.save(PlayerElo(player_id="a", guild_id="g"))


async def test_sheet_failure_stops_before_the_local_store(world):
    store, ss, db_save = world
    ss.tabs[Tab.ELO_DATA].fail_next = [ValueError("sheet down")]
    with pytest.raises(ValueError):
        await store.save(PlayerElo(player_id="a", guild_id="g"))
    db_save.assert_not_awaited()


async def test_standings_seeds_cache_from_sheet_sorted(world):
    store, ss, _ = world
    ss.tabs[Tab.ELO_DATA].rows += [
        ["p1", "Low", "900", "1", "3", "0"],
        ["p2", "High", "1100", "3", "1", "2"],
        ["", "NoId", "5", "0", "0", "0"],
    ]
    result = await store.standings("g")
    assert [p.player_id for p in result] == ["p2", "p1"]
    assert set(store.cache["g"]) == {"p1", "p2"}


async def test_restore_loads_local_store_into_cache(world):
    store, _, _ = world
    rows = [
        {
            "guild_id": "g1",
            "player_id": "pA",
            "elo": 1150,
            "wins": 6,
            "losses": 2,
            "streak": 3,
            "display_name": "Alice",
        }
    ]
    with patch("src.data.elo_store.load_all_elo", return_value=rows):
        await store.restore()
    assert store.cache["g1"]["pA"].elo == 1150
