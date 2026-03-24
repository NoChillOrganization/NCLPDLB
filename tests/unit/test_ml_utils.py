"""
ML Utils — 100% coverage tests for:
  - src/ml/showdown_modes.py
  - src/ml/teambuilder.py
  - src/ml/replay_scraper.py

Run:
    .venv/Scripts/python -m pytest tests/unit/test_ml_utils.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── showdown_modes ─────────────────────────────────────────────────────────────

class TestShowdownModeConstants:
    """Verify the module-level constants are present and correct."""

    def test_mode_constants_exist(self):
        from src.ml.showdown_modes import MODE_LOCALHOST, MODE_SHOWDOWN, MODE_BROWSER
        assert MODE_LOCALHOST == "localhost"
        assert MODE_SHOWDOWN == "showdown"
        assert MODE_BROWSER == "browser"

    def test_valid_modes_contains_all_three(self):
        from src.ml.showdown_modes import VALID_MODES, MODE_LOCALHOST, MODE_SHOWDOWN, MODE_BROWSER
        assert MODE_LOCALHOST in VALID_MODES
        assert MODE_SHOWDOWN in VALID_MODES
        assert MODE_BROWSER in VALID_MODES
        assert len(VALID_MODES) == 3


class TestServerConfigForMode:
    """server_config_for_mode() returns the correct poke-env config object."""

    def test_showdown_mode_returns_showdown_config(self):
        pytest.importorskip("poke_env")
        from src.ml.showdown_modes import server_config_for_mode
        from poke_env.ps_client.server_configuration import ShowdownServerConfiguration

        result = server_config_for_mode("showdown")
        assert result is ShowdownServerConfiguration

    def test_localhost_mode_returns_localhost_config(self):
        pytest.importorskip("poke_env")
        from src.ml.showdown_modes import server_config_for_mode
        from poke_env.ps_client.server_configuration import LocalhostServerConfiguration

        result = server_config_for_mode("localhost")
        assert result is LocalhostServerConfiguration

    def test_browser_mode_returns_localhost_config(self):
        pytest.importorskip("poke_env")
        from src.ml.showdown_modes import server_config_for_mode
        from poke_env.ps_client.server_configuration import LocalhostServerConfiguration

        # browser mode also routes through local server initially
        result = server_config_for_mode("browser")
        assert result is LocalhostServerConfiguration


class TestAccountConfigsForMode:
    """account_configs_for_mode() returns (None, None) for local modes and
    AccountConfiguration pairs for showdown mode."""

    def test_localhost_returns_none_pair(self):
        from src.ml.showdown_modes import account_configs_for_mode
        acc1, acc2 = account_configs_for_mode("localhost")
        assert acc1 is None
        assert acc2 is None

    def test_browser_returns_none_pair(self):
        from src.ml.showdown_modes import account_configs_for_mode
        acc1, acc2 = account_configs_for_mode("browser")
        assert acc1 is None
        assert acc2 is None

    def test_showdown_mode_with_all_env_vars_returns_account_configs(self):
        pytest.importorskip("poke_env")
        from src.ml.showdown_modes import account_configs_for_mode
        from poke_env.ps_client.account_configuration import AccountConfiguration

        env_vars = {
            "SHOWDOWN_TRAIN_USER1": "user1",
            "SHOWDOWN_TRAIN_PASS1": "pass1",
            "SHOWDOWN_TRAIN_USER2": "user2",
            "SHOWDOWN_TRAIN_PASS2": "pass2",
        }
        with patch.dict(os.environ, env_vars):
            acc1, acc2 = account_configs_for_mode("showdown")

        assert isinstance(acc1, AccountConfiguration)
        assert isinstance(acc2, AccountConfiguration)
        assert acc1.username == "user1"
        assert acc2.username == "user2"

    def test_showdown_mode_missing_env_vars_raises_value_error(self):
        from src.ml.showdown_modes import account_configs_for_mode

        # Remove all 4 env vars if present
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ("SHOWDOWN_TRAIN_USER1", "SHOWDOWN_TRAIN_PASS1",
                                  "SHOWDOWN_TRAIN_USER2", "SHOWDOWN_TRAIN_PASS2")}
        with patch.dict(os.environ, clean_env, clear=True):
            with pytest.raises(ValueError, match="SHOWDOWN_TRAIN_USER1"):
                account_configs_for_mode("showdown")

    def test_showdown_mode_partial_env_vars_raises_value_error(self):
        from src.ml.showdown_modes import account_configs_for_mode

        # Only 2 of the 4 required vars are set
        partial_env = {
            "SHOWDOWN_TRAIN_USER1": "user1",
            "SHOWDOWN_TRAIN_PASS1": "pass1",
        }
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ("SHOWDOWN_TRAIN_USER1", "SHOWDOWN_TRAIN_PASS1",
                                  "SHOWDOWN_TRAIN_USER2", "SHOWDOWN_TRAIN_PASS2")}
        clean_env.update(partial_env)
        with patch.dict(os.environ, clean_env, clear=True):
            with pytest.raises(ValueError):
                account_configs_for_mode("showdown")


# ── teambuilder ────────────────────────────────────────────────────────────────

class TestRotatingTeambuilder:
    """RotatingTeambuilder cycles through teams round-robin."""

    # Minimal valid Showdown export-format team strings (one Pokemon each).
    TEAM_A = (
        "Garchomp @ Rocky Helmet\n"
        "Ability: Rough Skin\n"
        "EVs: 252 HP / 4 Atk / 252 Spe\n"
        "Jolly Nature\n"
        "- Earthquake\n"
        "- Dragon Claw\n"
        "- Swords Dance\n"
        "- Stealth Rock\n"
    )
    TEAM_B = (
        "Corviknight @ Leftovers\n"
        "Ability: Pressure\n"
        "EVs: 252 HP / 4 Def / 252 SpD\n"
        "Careful Nature\n"
        "- Body Press\n"
        "- Iron Defense\n"
        "- Roost\n"
        "- Defog\n"
    )

    def test_empty_team_list_raises_value_error(self):
        pytest.importorskip("poke_env")
        from src.ml.teambuilder import RotatingTeambuilder

        with pytest.raises(ValueError, match="at least one team"):
            RotatingTeambuilder([])

    def test_single_team_len_is_one(self):
        pytest.importorskip("poke_env")
        from src.ml.teambuilder import RotatingTeambuilder

        tb = RotatingTeambuilder([self.TEAM_A])
        assert len(tb) == 1

    def test_two_teams_len_is_two(self):
        pytest.importorskip("poke_env")
        from src.ml.teambuilder import RotatingTeambuilder

        tb = RotatingTeambuilder([self.TEAM_A, self.TEAM_B])
        assert len(tb) == 2

    def test_yield_team_returns_string(self):
        pytest.importorskip("poke_env")
        from src.ml.teambuilder import RotatingTeambuilder

        tb = RotatingTeambuilder([self.TEAM_A])
        result = tb.yield_team()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_yield_team_cycles_round_robin(self):
        pytest.importorskip("poke_env")
        from src.ml.teambuilder import RotatingTeambuilder

        tb = RotatingTeambuilder([self.TEAM_A, self.TEAM_B])
        first = tb.yield_team()   # index 0
        second = tb.yield_team()  # index 1
        third = tb.yield_team()   # index 0 again (wraps)

        assert first == third, "Round-robin should wrap back to first team"
        assert first != second, "Two different teams should produce different packed strings"

    def test_yield_team_increments_index(self):
        pytest.importorskip("poke_env")
        from src.ml.teambuilder import RotatingTeambuilder

        tb = RotatingTeambuilder([self.TEAM_A, self.TEAM_B])
        assert tb._idx == 0
        tb.yield_team()
        assert tb._idx == 1
        tb.yield_team()
        assert tb._idx == 2

    def test_uses_gen9ou_teams_from_format_teams(self):
        pytest.importorskip("poke_env")
        from src.ml.teambuilder import RotatingTeambuilder
        from src.ml.teams import FORMAT_TEAMS

        teams = FORMAT_TEAMS.get("gen9ou", [])
        assert len(teams) > 0
        tb = RotatingTeambuilder(teams)
        assert len(tb) == len(teams)
        # Cycle through all teams once
        results = [tb.yield_team() for _ in range(len(teams))]
        assert len(set(results)) == len(teams), "Each team should produce a unique packed string"


# ── replay_scraper ─────────────────────────────────────────────────────────────

class TestReplayMeta:
    """ReplayMeta dataclass stores fields from API dict."""

    def test_init_with_full_data(self):
        pytest.importorskip("aiohttp")
        from src.ml.replay_scraper import ReplayMeta

        data = {
            "id": "gen9ou-12345",
            "format": "gen9ou",
            "p1": "Alice",
            "p2": "Bob",
            "rating": 1750,
            "uploadtime": 1700000000,
        }
        meta = ReplayMeta(data)
        assert meta.id == "gen9ou-12345"
        assert meta.format == "gen9ou"
        assert meta.p1 == "Alice"
        assert meta.p2 == "Bob"
        assert meta.rating == 1750
        assert meta.uploadtime == 1700000000

    def test_init_with_missing_optional_fields_uses_defaults(self):
        pytest.importorskip("aiohttp")
        from src.ml.replay_scraper import ReplayMeta

        meta = ReplayMeta({"id": "test-001"})
        assert meta.id == "test-001"
        assert meta.format == "unknown"
        assert meta.p1 == ""
        assert meta.p2 == ""
        assert meta.rating == 0
        assert meta.uploadtime == 0

    def test_init_with_none_rating_defaults_to_zero(self):
        pytest.importorskip("aiohttp")
        from src.ml.replay_scraper import ReplayMeta

        # rating=None is treated as 0 via `or 0`
        meta = ReplayMeta({"id": "test-002", "rating": None})
        assert meta.rating == 0

    def test_repr_contains_id_and_players(self):
        pytest.importorskip("aiohttp")
        from src.ml.replay_scraper import ReplayMeta

        meta = ReplayMeta({"id": "gen9ou-99", "p1": "Ash", "p2": "Gary", "rating": 1600})
        r = repr(meta)
        assert "gen9ou-99" in r
        assert "Ash" in r
        assert "Gary" in r
        assert "1600" in r


class TestReplayScraperInit:
    """ReplayScraper.__init__ creates output directory and loads seen IDs."""

    def test_init_creates_output_dir(self, tmp_path):
        pytest.importorskip("aiohttp")
        from src.ml.replay_scraper import ReplayScraper

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)
        assert (tmp_path / "gen9ou").is_dir()

    def test_init_format_stored(self, tmp_path):
        pytest.importorskip("aiohttp")
        from src.ml.replay_scraper import ReplayScraper

        scraper = ReplayScraper(format="gen9vgc2024regh", output_dir=tmp_path)
        assert scraper.format == "gen9vgc2024regh"

    def test_init_min_rating_stored(self, tmp_path):
        pytest.importorskip("aiohttp")
        from src.ml.replay_scraper import ReplayScraper

        scraper = ReplayScraper(format="gen9ou", min_rating=1600, output_dir=tmp_path)
        assert scraper.min_rating == 1600

    def test_init_loads_existing_seen_ids(self, tmp_path):
        pytest.importorskip("aiohttp")
        from src.ml.replay_scraper import ReplayScraper

        # Pre-create some replay JSON files in the expected subdirectory
        fmt_dir = tmp_path / "gen9ou"
        fmt_dir.mkdir()
        (fmt_dir / "gen9ou-111.json").write_text("{}", encoding="utf-8")
        (fmt_dir / "gen9ou-222.json").write_text("{}", encoding="utf-8")

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)
        assert "gen9ou-111" in scraper._seen
        assert "gen9ou-222" in scraper._seen

    def test_replay_path_returns_correct_path(self, tmp_path):
        pytest.importorskip("aiohttp")
        from src.ml.replay_scraper import ReplayScraper

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)
        path = scraper._replay_path("gen9ou-999")
        assert path == tmp_path / "gen9ou" / "gen9ou-999.json"


class TestFetchSearchPage:
    """_fetch_search_page() handles HTTP responses and filtering."""

    def test_returns_list_of_replay_metas_on_success(self, tmp_path):
        pytest.importorskip("aiohttp")
        from aioresponses import aioresponses
        from src.ml.replay_scraper import ReplayScraper, SEARCH_URL

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)
        page_data = [
            {"id": "gen9ou-1", "format": "gen9ou", "p1": "Alice", "p2": "Bob",
             "rating": 1700, "uploadtime": 1700000001},
            {"id": "gen9ou-2", "format": "gen9ou", "p1": "Carol", "p2": "Dan",
             "rating": 1650, "uploadtime": 1700000002},
        ]

        async def run():
            import aiohttp
            with aioresponses() as mock:
                mock.get(re.compile(re.escape(SEARCH_URL) + '.*'), payload=page_data)
                async with aiohttp.ClientSession() as session:
                    return await scraper._fetch_search_page(session, page=1)

        result = asyncio.get_event_loop().run_until_complete(run())
        assert len(result) == 2
        assert result[0].id == "gen9ou-1"
        assert result[1].id == "gen9ou-2"

    def test_returns_empty_list_on_non_200_status(self, tmp_path):
        pytest.importorskip("aiohttp")
        from aioresponses import aioresponses
        from src.ml.replay_scraper import ReplayScraper, SEARCH_URL

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)

        async def run():
            import aiohttp
            with aioresponses() as mock:
                mock.get(re.compile(re.escape(SEARCH_URL) + ".*"), status=503)
                async with aiohttp.ClientSession() as session:
                    return await scraper._fetch_search_page(session, page=1)

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result == []

    def test_returns_empty_list_on_exception(self, tmp_path):
        pytest.importorskip("aiohttp")
        from aioresponses import aioresponses
        from src.ml.replay_scraper import ReplayScraper, SEARCH_URL

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)

        async def run():
            import aiohttp
            with aioresponses() as mock:
                mock.get(re.compile(re.escape(SEARCH_URL) + ".*"), exception=aiohttp.ClientError("network error"))
                async with aiohttp.ClientSession() as session:
                    return await scraper._fetch_search_page(session, page=1)

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result == []

    def test_returns_empty_list_when_response_is_not_list(self, tmp_path):
        pytest.importorskip("aiohttp")
        from aioresponses import aioresponses
        from src.ml.replay_scraper import ReplayScraper, SEARCH_URL

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)

        async def run():
            import aiohttp
            with aioresponses() as mock:
                # API returns a dict instead of a list
                mock.get(re.compile(re.escape(SEARCH_URL) + ".*"), payload={"error": "not found"})
                async with aiohttp.ClientSession() as session:
                    return await scraper._fetch_search_page(session, page=1)

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result == []

    def test_filters_by_min_rating(self, tmp_path):
        pytest.importorskip("aiohttp")
        from aioresponses import aioresponses
        from src.ml.replay_scraper import ReplayScraper, SEARCH_URL

        scraper = ReplayScraper(format="gen9ou", min_rating=1700, output_dir=tmp_path)
        page_data = [
            {"id": "gen9ou-hi", "rating": 1800},
            {"id": "gen9ou-lo", "rating": 1500},
        ]

        async def run():
            import aiohttp
            with aioresponses() as mock:
                mock.get(re.compile(re.escape(SEARCH_URL) + ".*"), payload=page_data)
                async with aiohttp.ClientSession() as session:
                    return await scraper._fetch_search_page(session, page=1)

        result = asyncio.get_event_loop().run_until_complete(run())
        assert len(result) == 1
        assert result[0].id == "gen9ou-hi"


class TestFetchReplay:
    """_fetch_replay() downloads individual replays and writes them to disk."""

    def test_skips_already_seen_replay(self, tmp_path):
        pytest.importorskip("aiohttp")
        from src.ml.replay_scraper import ReplayScraper, ReplayMeta

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)
        scraper._seen.add("gen9ou-already")
        meta = ReplayMeta({"id": "gen9ou-already", "rating": 1600})

        async def run():
            import aiohttp
            semaphore = asyncio.Semaphore(5)
            async with aiohttp.ClientSession() as session:
                return await scraper._fetch_replay(session, meta, semaphore)

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result is False

    def test_returns_false_on_non_200_status(self, tmp_path):
        pytest.importorskip("aiohttp")
        from aioresponses import aioresponses
        from src.ml.replay_scraper import ReplayScraper, ReplayMeta, REPLAY_URL

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)
        meta = ReplayMeta({"id": "gen9ou-404", "rating": 1600})
        url = REPLAY_URL.format(id=meta.id)

        async def run():
            import aiohttp
            with aioresponses() as mock:
                mock.get(url, status=404)
                semaphore = asyncio.Semaphore(5)
                async with aiohttp.ClientSession() as session:
                    return await scraper._fetch_replay(session, meta, semaphore)

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result is False

    def test_returns_false_on_exception(self, tmp_path):
        pytest.importorskip("aiohttp")
        from aioresponses import aioresponses
        from src.ml.replay_scraper import ReplayScraper, ReplayMeta, REPLAY_URL

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)
        meta = ReplayMeta({"id": "gen9ou-err", "rating": 1600})
        url = REPLAY_URL.format(id=meta.id)

        async def run():
            import aiohttp
            with aioresponses() as mock:
                mock.get(url, exception=aiohttp.ClientError("fail"))
                semaphore = asyncio.Semaphore(5)
                async with aiohttp.ClientSession() as session:
                    return await scraper._fetch_replay(session, meta, semaphore)

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result is False

    def test_success_writes_json_file_and_returns_true(self, tmp_path):
        pytest.importorskip("aiohttp")
        from aioresponses import aioresponses
        from src.ml.replay_scraper import ReplayScraper, ReplayMeta, REPLAY_URL

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)
        meta = ReplayMeta({"id": "gen9ou-new", "rating": 1700, "format": "gen9ou"})
        url = REPLAY_URL.format(id=meta.id)
        replay_json = {"id": "gen9ou-new", "log": "|start\n|turn|1\n|win|Alice"}

        async def run():
            import aiohttp
            with aioresponses() as mock:
                mock.get(url, payload=replay_json)
                semaphore = asyncio.Semaphore(5)
                async with aiohttp.ClientSession() as session:
                    return await scraper._fetch_replay(session, meta, semaphore)

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result is True

        # File should exist on disk
        saved_path = tmp_path / "gen9ou" / "gen9ou-new.json"
        assert saved_path.exists()
        saved_data = json.loads(saved_path.read_text(encoding="utf-8"))
        assert saved_data["id"] == "gen9ou-new"
        assert saved_data["format"] == "gen9ou"
        assert saved_data["rating"] == 1700

    def test_success_adds_id_to_seen_set(self, tmp_path):
        pytest.importorskip("aiohttp")
        from aioresponses import aioresponses
        from src.ml.replay_scraper import ReplayScraper, ReplayMeta, REPLAY_URL

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)
        meta = ReplayMeta({"id": "gen9ou-track", "rating": 1700})
        url = REPLAY_URL.format(id=meta.id)

        async def run():
            import aiohttp
            with aioresponses() as mock:
                mock.get(url, payload={"id": "gen9ou-track", "log": ""})
                semaphore = asyncio.Semaphore(5)
                async with aiohttp.ClientSession() as session:
                    return await scraper._fetch_replay(session, meta, semaphore)

        asyncio.get_event_loop().run_until_complete(run())
        assert "gen9ou-track" in scraper._seen

    def test_success_sets_default_format_and_rating(self, tmp_path):
        """setdefault calls on data dict are covered — format/rating filled in if absent."""
        pytest.importorskip("aiohttp")
        from aioresponses import aioresponses
        from src.ml.replay_scraper import ReplayScraper, ReplayMeta, REPLAY_URL

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)
        meta = ReplayMeta({"id": "gen9ou-noformat", "rating": 1800})
        url = REPLAY_URL.format(id=meta.id)
        # Response JSON intentionally lacks "format" and "rating"
        replay_json = {"id": "gen9ou-noformat", "log": ""}

        async def run():
            import aiohttp
            with aioresponses() as mock:
                mock.get(url, payload=replay_json)
                semaphore = asyncio.Semaphore(5)
                async with aiohttp.ClientSession() as session:
                    return await scraper._fetch_replay(session, meta, semaphore)

        asyncio.get_event_loop().run_until_complete(run())
        saved = json.loads(
            (tmp_path / "gen9ou" / "gen9ou-noformat.json").read_text(encoding="utf-8")
        )
        assert saved["format"] == "gen9ou"
        assert saved["rating"] == 1800


class TestScrape:
    """scrape() orchestrates multi-page fetching and returns download count."""

    def test_scrape_downloads_new_replays_and_returns_count(self, tmp_path):
        pytest.importorskip("aiohttp")
        from aioresponses import aioresponses
        from src.ml.replay_scraper import ReplayScraper, SEARCH_URL, REPLAY_URL

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)
        search_page = [{"id": "gen9ou-s1", "rating": 1600, "format": "gen9ou"}]
        replay_data = {"id": "gen9ou-s1", "log": ""}
        replay_url = REPLAY_URL.format(id="gen9ou-s1")

        async def run():
            import aiohttp
            with aioresponses() as mock:
                # Page 1 returns one result; page 2 returns empty (stops early)
                mock.get(re.compile(re.escape(SEARCH_URL) + ".*"), payload=search_page)
                mock.get(re.compile(re.escape(SEARCH_URL) + ".*"), payload=[])
                mock.get(replay_url, payload=replay_data)
                return await scraper.scrape(pages=5)

        count = asyncio.get_event_loop().run_until_complete(run())
        assert count == 1

    def test_scrape_skips_page_of_already_seen_metas(self, tmp_path):
        pytest.importorskip("aiohttp")
        from aioresponses import aioresponses
        from src.ml.replay_scraper import ReplayScraper, SEARCH_URL

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)
        # Pre-mark the replay as seen
        scraper._seen.add("gen9ou-seen")
        search_page = [{"id": "gen9ou-seen", "rating": 1600}]

        async def run():
            import aiohttp
            with aioresponses() as mock:
                mock.get(re.compile(re.escape(SEARCH_URL) + ".*"), payload=search_page)
                mock.get(re.compile(re.escape(SEARCH_URL) + ".*"), payload=[])  # second page — stops early
                return await scraper.scrape(pages=5)

        count = asyncio.get_event_loop().run_until_complete(run())
        assert count == 0

    def test_scrape_stops_early_on_empty_page(self, tmp_path):
        pytest.importorskip("aiohttp")
        from aioresponses import aioresponses
        from src.ml.replay_scraper import ReplayScraper, SEARCH_URL

        scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)

        async def run():
            import aiohttp
            with aioresponses() as mock:
                # First page empty — should stop immediately
                mock.get(re.compile(re.escape(SEARCH_URL) + ".*"), payload=[])
                return await scraper.scrape(pages=10)

        count = asyncio.get_event_loop().run_until_complete(run())
        assert count == 0


class TestReplayStats:
    """replay_stats() returns per-format replay counts."""

    def test_returns_empty_dict_when_replays_dir_absent(self, tmp_path):
        pytest.importorskip("aiohttp")
        from src.ml.replay_scraper import replay_stats, REPLAYS_DIR
        import src.ml.replay_scraper as scraper_mod

        nonexistent = tmp_path / "does_not_exist"
        original = scraper_mod.REPLAYS_DIR
        scraper_mod.REPLAYS_DIR = nonexistent
        try:
            result = replay_stats()
        finally:
            scraper_mod.REPLAYS_DIR = original

        assert result == {}

    def test_returns_counts_for_all_formats_when_no_filter(self, tmp_path):
        pytest.importorskip("aiohttp")
        from src.ml.replay_scraper import replay_stats
        import src.ml.replay_scraper as scraper_mod

        # Build a fake replays directory structure
        (tmp_path / "gen9ou").mkdir()
        (tmp_path / "gen9ou" / "r1.json").write_text("{}")
        (tmp_path / "gen9ou" / "r2.json").write_text("{}")
        (tmp_path / "gen9uu").mkdir()
        (tmp_path / "gen9uu" / "r3.json").write_text("{}")

        original = scraper_mod.REPLAYS_DIR
        scraper_mod.REPLAYS_DIR = tmp_path
        try:
            result = replay_stats()
        finally:
            scraper_mod.REPLAYS_DIR = original

        assert result["gen9ou"] == 2
        assert result["gen9uu"] == 1

    def test_returns_count_for_specific_format(self, tmp_path):
        pytest.importorskip("aiohttp")
        from src.ml.replay_scraper import replay_stats
        import src.ml.replay_scraper as scraper_mod

        (tmp_path / "gen9ou").mkdir()
        (tmp_path / "gen9ou" / "r1.json").write_text("{}")
        (tmp_path / "gen9uu").mkdir()
        (tmp_path / "gen9uu" / "r2.json").write_text("{}")

        original = scraper_mod.REPLAYS_DIR
        scraper_mod.REPLAYS_DIR = tmp_path
        try:
            result = replay_stats(format="gen9ou")
        finally:
            scraper_mod.REPLAYS_DIR = original

        assert result == {"gen9ou": 1}
