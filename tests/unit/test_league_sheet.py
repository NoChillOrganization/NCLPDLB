"""League sheet write path, through its async interface over a fake gspread sheet.

Pins the rows written (cell layout), the retry policy, the executor policy and
the player_id key of ELO rows.  See tests/fake_gspread.py for the fake.
"""

import asyncio
import json
import threading
from unittest.mock import patch

import pytest

from src.data.sheets import LeagueSheet, Tab
from tests.fake_gspread import FakeSpreadsheet, api_error


def make(**tabs) -> tuple[LeagueSheet, FakeSpreadsheet]:
    """A LeagueSheet already 'connected' to a fake spreadsheet."""
    ss = FakeSpreadsheet(**tabs)
    sheet = LeagueSheet()
    sheet._conn._spreadsheet = ss
    return sheet, ss


@pytest.fixture(autouse=True)
def no_backoff_sleep():
    with patch("src.data.sheet_plumbing._time.sleep") as sleep:
        yield sleep


# ── Rows written ──────────────────────────────────────────────────────────────


async def test_save_pick_row():
    sheet, ss = make(Draft=[["pick_id"]])
    await sheet.save_pick(
        {
            "pick_id": "k1",
            "draft_id": "d1",
            "player_id": "p1",
            "pokemon_name": "Garchomp",
            "round": 2,
            "pick_number": 3,
        }
    )
    row = ss.tabs[Tab.DRAFT].rows[1]
    assert row[:6] == ["k1", "d1", "p1", "Garchomp", 2, 3]
    assert len(row) == 7  # + timestamp


async def test_save_pick_twice_updates_same_row():
    sheet, ss = make(Draft=[["pick_id"]])
    await sheet.save_pick({"pick_id": "k1", "pokemon_name": "A"})
    await sheet.save_pick({"pick_id": "k1", "pokemon_name": "B"})
    rows = ss.tabs[Tab.DRAFT].rows
    assert len(rows) == 2
    assert rows[1][3] == "B"


async def test_save_league_setup_row_and_lookup():
    sheet, ss = make(Setup=[["server_id"]])
    await sheet.save_league_setup(
        {
            "league_id": "g1",
            "server_id": "g1",
            "league_name": "NCL",
            "commissioner_id": "u1",
            "commissioner_name": "Boss",
        }
    )
    assert ss.tabs[Tab.SETUP].rows[1][:5] == ["g1", "g1", "NCL", "u1", "Boss"]


async def test_get_league_setup_by_server_id():
    sheet, _ = make(Setup=[["league_id", "server_id"], ["a", "s1"], ["b", "s2"]])
    assert (await sheet.get_league_setup("s2"))["league_id"] == "b"
    assert await sheet.get_league_setup("nope") is None


async def test_get_league_setup_without_server_returns_first_or_empty():
    sheet, _ = make(Setup=[["league_id"], ["a"], ["b"]])
    assert (await sheet.get_league_setup())["league_id"] == "a"
    empty, _ = make(Setup=[])
    assert await empty.get_league_setup() == {}


async def test_save_transaction_row_with_legacy_key_fallbacks():
    sheet, ss = make(Transactions=[["transaction_id"]])
    await sheet.save_transaction(
        {
            "transaction_id": "t1",
            "week": 4,
            "type": "trade",
            "coach1": "A",
            "pokemon1": "Pika",
            "pokemon2": "Raichu",
            "coach2": "B",
            "status": "pending",
        }
    )
    row = ss.tabs[Tab.TRANSACTIONS].rows[1]
    assert row[:8] == ["t1", 4, "trade", "A", "Pika", "Raichu", "B", "pending"]


async def test_find_transaction():
    sheet, _ = make(Transactions=[["transaction_id", "status"], ["t1", "pending"]])
    assert (await sheet.find_transaction("t1"))["status"] == "pending"
    assert await sheet.find_transaction("t2") is None


async def test_save_replay_and_video_rows():
    sheet, ss = make(Match_Records=[["replay_id"]])
    await sheet.save_replay(
        {
            "replay_id": "r1",
            "match_id": "m1",
            "url": "http://r",
            "winner": "A",
            "p1_team": ["x"],
            "p2_team": ["y"],
            "turns": 12,
            "timestamp": "T",
        }
    )
    await sheet.save_video({"video_id": "v1", "match_id": "m1", "timestamp": "T"})
    rows = ss.tabs[Tab.MATCH_RECORDS].rows
    assert rows[1] == ["r1", "m1", "http://r", "A", "['x']", "['y']", "12", "T"]
    # video_id is not a header of this fake tab, so the row is appended
    assert rows[2][:2] == ["v1", "m1"]
    assert rows[2][-1] == "T"


async def test_save_match_stats_schedule_and_playoff_rows():
    sheet, ss = make()
    await sheet.save_match_stats({"match_id": "m1", "league_id": "L"})
    await sheet.save_schedule_match(
        {"match_id": "m1", "week": 1, "player1_id": "a", "player2_name": "B"}
    )
    await sheet.save_playoff_match({"bracket_id": "b1", "round": "SF"})
    assert ss.tabs[Tab.MATCH_RECORDS].rows[-1][:4] == ["m1", "L", "[]", "[]"]
    assert ss.tabs[Tab.SCHEDULE].rows[-1][:6] == ["m1", 1, "a", "", "", "B"]
    assert ss.tabs[Tab.PLAYOFFS].rows[-1][:2] == ["b1", "SF"]


async def test_read_schedule():
    sheet, _ = make(Schedule=[["week", "pool"], [1, "A"]])
    assert await sheet.read_schedule() == [{"week": 1, "pool": "A"}]


async def test_append_rule():
    sheet, ss = make(Rules=[["x"]])
    await sheet.append_rule(["id", "cat", "title", "desc", "now"])
    assert ss.tabs[Tab.RULES].rows[-1] == ["id", "cat", "title", "desc", "now"]


async def test_save_team_page_partial_update_preserves_other_columns():
    sheet, ss = make(
        Team_Page_Template=[
            ["player_id", "guild_id", "team_name", "pokemon_list", "updated_at"],
            ["p1", "g1", "Old Name", "[]", "T0"],
        ]
    )
    await sheet.save_team_page(
        {"player_id": "p1", "guild_id": "g1", "slots": [("Garchomp", None)]}
    )
    row = ss.tabs[Tab.TEAM_TEMPLATE].rows[1]
    assert row[2] == "Old Name"  # untouched: team_name not supplied
    assert json.loads(row[3]) == ["Garchomp"]
    assert (await sheet.find_team_page("p1"))["guild_id"] == "g1"
    assert await sheet.find_team_page("zz") is None


async def test_write_pokedex_replaces_tab():
    sheet, ss = make(Pokédex=[["old"], ["row"]])
    await sheet.write_pokedex(
        [
            {
                "national_dex": 445,
                "name": "Garchomp",
                "types": ["Dragon", "Ground"],
                "base_stats": {"hp": 108, "atk": 130},
            }
        ]
    )
    rows = ss.tabs[Tab.POKEDEX].rows
    assert len(rows) == 1
    assert rows[0][:7] == [445, "Garchomp", "Dragon", "Ground", 108, 130, 0]


async def test_write_pokedex_empty_just_clears():
    sheet, ss = make(Pokédex=[["old"]])
    await sheet.write_pokedex([])
    assert ss.tabs[Tab.POKEDEX].rows == []


# ── ELO rows: keyed by player_id only ─────────────────────────────────────────


async def test_save_standing_row_layout():
    sheet, ss = make(ELO_Data=[["player_id"]])
    await sheet.save_standing(
        {
            "player_id": "p1",
            "player_name": "Alice",
            "elo": 1016,
            "wins": 1,
            "losses": 0,
            "streak": 1,
        }
    )
    assert ss.tabs[Tab.ELO_DATA].rows[1][:6] == ["p1", "Alice", 1016, 1, 0, 1]


async def test_standing_is_keyed_by_player_id_alone():
    """One spreadsheet per League: the same player_id is one row, whatever the guild."""
    sheet, ss = make(ELO_Data=[["player_id"]])
    await sheet.save_standing({"player_id": "p1", "elo": 1000, "guild_id": "g1"})
    await sheet.save_standing({"player_id": "p1", "elo": 1100, "guild_id": "g2"})
    rows = ss.tabs[Tab.ELO_DATA].rows
    assert len(rows) == 2
    assert rows[1][2] == 1100
    assert (await sheet.find_standing("p1"))["player_id"] == "p1"


async def test_get_standings_reads_elo_tab():
    sheet, _ = make(ELO_Data=[["player_id", "elo"], ["p1", 1000]])
    assert await sheet.get_standings() == [{"player_id": "p1", "elo": 1000}]


# ── Retry policy ──────────────────────────────────────────────────────────────


async def test_transient_api_error_is_retried(no_backoff_sleep):
    sheet, ss = make(Draft=[["pick_id"]])
    ss.tabs[Tab.DRAFT].fail_next = [api_error(429), api_error(503)]
    await sheet.save_pick({"pick_id": "k1"})
    assert ss.tabs[Tab.DRAFT].rows[1][0] == "k1"
    assert no_backoff_sleep.call_count == 2


async def test_non_transient_api_error_propagates_immediately(no_backoff_sleep):
    sheet, ss = make(Draft=[["pick_id"]])
    ss.tabs[Tab.DRAFT].fail_next = [api_error(400)]
    with pytest.raises(Exception, match="boom"):
        await sheet.save_pick({"pick_id": "k1"})
    assert no_backoff_sleep.call_count == 0


async def test_retry_gives_up_after_max_tries(no_backoff_sleep):
    sheet, ss = make(Draft=[["pick_id"]])
    ss.tabs[Tab.DRAFT].fail_next = [api_error(429)] * 5
    with pytest.raises(Exception, match="boom"):
        await sheet.save_pick({"pick_id": "k1"})
    assert no_backoff_sleep.call_count == 4


# ── Executor policy ───────────────────────────────────────────────────────────


async def test_sheet_calls_never_run_on_the_event_loop_thread():
    sheet, ss = make(
        Draft=[["pick_id"]],
        ELO_Data=[["player_id"], ["p1"]],
        Setup=[["server_id"]],
    )
    await sheet.save_pick({"pick_id": "k1"})
    await sheet.find_standing("p1")
    await sheet.get_standings()
    await sheet.get_league_setup("s1")
    loop_thread = threading.get_ident()
    used = set().union(*(ws.threads for ws in ss.tabs.values()))
    assert used
    assert loop_thread not in used


async def test_event_loop_stays_responsive_during_a_slow_sheet_call():
    sheet, ss = make(Draft=[["pick_id"]])
    ws = ss.tabs[Tab.DRAFT]
    real_append = ws.append_row
    release = threading.Event()

    def slow_append(row, value_input_option=None):
        release.wait(2)
        real_append(row, value_input_option)

    ws.append_row = slow_append
    task = asyncio.create_task(sheet.save_pick({"pick_id": "k1"}))
    await asyncio.sleep(0.05)  # the loop runs while the sheet call is blocked
    assert not task.done()
    release.set()
    await task
