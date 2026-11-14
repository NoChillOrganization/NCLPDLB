"""
Draft lifecycle tests, written through the DraftService interface only.

No private state is touched. Persistence is observed through an in-memory
adapter at the Draft-store seam (the three src.data.db functions the service
imports), and Pick timers run out when the test says so instead of after real
seconds.
Run: pytest tests/unit/test_draft_lifecycle.py -v
"""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

import src.services.draft_service as ds
from src.data.models import DraftFormat, DraftStatus

GUILD = "lifecycle-guild"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def store(monkeypatch):
    """In-memory Draft store ({guild_id: draft_json}) standing in for the Local store."""
    rows: dict[str, str] = {}

    async def save(guild_id, draft_json):
        rows[guild_id] = draft_json

    async def delete(guild_id):
        rows.pop(guild_id, None)

    async def load_all():
        return list(rows.items())

    monkeypatch.setattr(ds, "_db_save_draft", save)
    monkeypatch.setattr(ds, "_db_delete_draft", delete)
    monkeypatch.setattr(ds, "load_all_drafts", load_all)
    return rows


@pytest.fixture
def sheet(monkeypatch):
    """Stand-in League sheet."""
    sheet = AsyncMock()
    monkeypatch.setattr(ds, "league_sheet", sheet)
    return sheet


@pytest.fixture
def pokedex(monkeypatch):
    """Every name is a real Pokémon except 'Missingno'."""
    pokedex = MagicMock()
    pokedex.find.side_effect = lambda name: (
        None if name == "Missingno" else SimpleNamespace(name=name)
    )
    monkeypatch.setattr(ds, "pokemon_db", pokedex)


async def settle():
    """Let scheduled tasks run."""
    for _ in range(20):
        await asyncio.sleep(0)


@pytest.fixture
def expire_timer(monkeypatch):
    """Pick timers wait on the test, not on real seconds.

    `await expire_timer()` runs the current Pick timer out (one call, one timer)
    and lets the auto-skip finish.
    """
    expired = asyncio.Event()
    real_sleep = asyncio.sleep

    async def sleep(delay, *args, **kwargs):
        if delay < 1:  # the tests' own short waits
            await real_sleep(delay, *args, **kwargs)
        else:
            await expired.wait()
            expired.clear()

    monkeypatch.setattr(ds.asyncio, "sleep", sleep)

    async def expire():
        expired.set()
        await settle()
        expired.clear()

    return expire


@pytest_asyncio.fixture
async def svc(store, sheet, pokedex, expire_timer):
    service = ds.DraftService()
    yield service
    await service.reset_draft(GUILD)  # stops the Pick timer, drops the Draft


async def start(
    svc, *, on_timeout=None, coaches=("p1", "p2"), rounds=2, fmt=DraftFormat.SNAKE
):
    """Create, fill and start a Draft; returns the list of Coaches whose auto-skip was announced."""
    skipped: list[str] = []

    async def announce(guild_id, coach):
        skipped.append(coach)

    await svc.create_draft(GUILD, coaches[0], fmt, rounds=rounds, timer_seconds=30)
    for coach in coaches:
        await svc.add_player(GUILD, coach)
    await svc.start_draft(GUILD, coaches[0], on_timeout=on_timeout or announce)
    return skipped


async def complete(svc):
    """Play a one-round, two-Coach Draft to completion."""
    await start(svc, rounds=1)
    await svc.make_pick(GUILD, "p1", "Garchomp")
    last = await svc.make_pick(GUILD, "p2", "Dragonite")
    await settle()
    return last


def stored(store) -> dict:
    return json.loads(store[GUILD])


# ── Pick timer ────────────────────────────────────────────────────────────────


async def test_timer_expiry_skips_the_coach_and_announces_it(svc, expire_timer):
    skipped = await start(svc)

    await expire_timer()

    assert skipped == ["p1"]
    assert svc.get_draft(GUILD).current_player_id == "p2"


async def test_failing_announcement_does_not_stop_the_draft(svc, expire_timer):
    async def discord_is_down(guild_id, coach):
        raise RuntimeError("discord is down")

    await start(svc, on_timeout=discord_is_down, coaches=("p1", "p2", "p3"))

    await expire_timer()
    assert svc.get_draft(GUILD).current_player_id == "p2"
    await expire_timer()  # the next Coach still got a Pick timer
    assert svc.get_draft(GUILD).current_player_id == "p3"


async def test_rejected_pick_keeps_the_pick_timer_running(svc, expire_timer):
    """A pick that fails validation must not cost the Coach their auto-skip."""
    skipped = await start(svc)

    result = await svc.make_pick(GUILD, "p1", "Missingno")
    assert not result.success
    await expire_timer()

    assert skipped == ["p1"]


async def test_taken_pick_keeps_the_pick_timer_running(svc, expire_timer):
    await start(svc, coaches=("p1", "p2", "p3"))
    await svc.make_pick(GUILD, "p1", "Garchomp")

    result = await svc.make_pick(GUILD, "p2", "Garchomp")
    assert not result.success
    await expire_timer()

    assert svc.get_draft(GUILD).current_player_id == "p3"


async def test_auto_skip_is_announced_after_a_pick_that_passes_no_callback(
    svc, expire_timer
):
    """/pick calls make_pick without on_timeout; the Draft's callback must survive it."""
    skipped = await start(svc, coaches=("p1", "p2", "p3"))
    assert (await svc.make_pick(GUILD, "p1", "Garchomp")).success

    await expire_timer()

    assert skipped == ["p2"]


async def test_next_pick_does_not_cancel_an_announcement_in_flight(svc, expire_timer):
    """The skip announcement (a Discord send) finishes even if the next Coach picks meanwhile."""
    announced: list[str] = []
    sending = asyncio.Event()
    sent = asyncio.Event()

    async def slow_announce(guild_id, coach):
        sending.set()
        await sent.wait()
        announced.append(coach)

    await start(svc, on_timeout=slow_announce, coaches=("p1", "p2", "p3"))
    await expire_timer()
    await asyncio.wait_for(sending.wait(), timeout=1)  # p1 skipped, send in flight

    assert (await svc.make_pick(GUILD, "p2", "Garchomp")).success
    sent.set()
    await settle()

    assert announced == ["p1"]


# ── Force-skip ────────────────────────────────────────────────────────────────


async def test_force_skip_restarts_the_pick_timer_for_the_next_coach(svc, expire_timer):
    skipped = await start(svc, coaches=("p1", "p2", "p3"))

    result = await svc.force_skip(GUILD, "p1")
    assert result.success
    assert result.next_player == "<@p2>"
    await expire_timer()

    assert skipped == ["p2"]


async def test_force_skip_refuses_a_coach_whose_turn_it_is_not(svc):
    """If the named Coach already picked, the next Coach must not lose their turn."""
    await start(svc)

    result = await svc.force_skip(GUILD, "p2")

    assert not result.success
    assert svc.get_draft(GUILD).current_player_id == "p1"


async def test_force_skip_is_refused_once_the_draft_is_complete(svc, store):
    await complete(svc)

    result = await svc.force_skip(GUILD, "p1")
    await settle()

    assert not result.success
    assert GUILD not in store  # a finished Draft is not written back


# ── Completion ────────────────────────────────────────────────────────────────


async def test_completed_draft_leaves_the_local_store(svc, store):
    await start(svc, rounds=1)
    assert GUILD in store  # saved when it started
    await svc.make_pick(GUILD, "p1", "Garchomp")

    last = await svc.make_pick(GUILD, "p2", "Dragonite")

    assert last.next_player_name == "Draft complete!"
    assert svc.get_draft(GUILD).status == DraftStatus.COMPLETED
    assert GUILD not in store


async def test_completed_draft_leaves_the_real_local_store(
    monkeypatch, tmp_path, sheet, pokedex, expire_timer
):
    """Same check against aiosqlite: nothing is left for a restart to restore."""
    from src.data import db

    monkeypatch.setattr(db, "_db_path", lambda: tmp_path / "drafts.db")
    await db.init_db()
    svc = ds.DraftService()
    try:
        await start(svc, rounds=1)
        assert [guild for guild, _ in await db.load_all_drafts()] == [GUILD]
        await svc.make_pick(GUILD, "p1", "Garchomp")
        await svc.make_pick(GUILD, "p2", "Dragonite")

        assert await db.load_all_drafts() == []  # removed before the pick returns
    finally:
        await svc.reset_draft(GUILD)


# ── Pause / Resume ────────────────────────────────────────────────────────────


async def test_pause_and_resume_are_persisted(svc, store):
    await start(svc)

    await svc.pause_draft(GUILD)
    assert stored(store)["status"] == "paused"

    await svc.resume_draft(GUILD)
    assert stored(store)["status"] == "active"


async def test_resume_restarts_the_pick_timer(svc, expire_timer):
    skipped = await start(svc)

    await svc.pause_draft(GUILD)
    await expire_timer()
    assert skipped == []  # paused: nobody is auto-skipped

    await svc.resume_draft(GUILD)
    await expire_timer()
    assert skipped == ["p1"]


async def test_resume_ends_the_ban_phase_and_starts_the_pick_timer(svc, expire_timer):
    """Resume is how a Moderator ends the Ban phase of a custom Draft."""
    skipped = await start(svc, fmt=DraftFormat.CUSTOM)
    assert svc.get_draft(GUILD).status == DraftStatus.BAN_PHASE

    await svc.resume_draft(GUILD)
    assert svc.get_draft(GUILD).status == DraftStatus.ACTIVE
    await expire_timer()

    assert skipped == ["p1"]


async def test_completed_draft_cannot_be_paused_or_resumed(svc, store):
    await complete(svc)

    assert not await svc.pause_draft(GUILD)
    assert not await svc.resume_draft(GUILD)

    assert svc.get_draft(GUILD).status == DraftStatus.COMPLETED
    assert GUILD not in store


# ── Override pick ─────────────────────────────────────────────────────────────


async def test_override_pick_is_persisted(svc, store):
    await start(svc)
    await svc.make_pick(GUILD, "p1", "Garchomp")

    await svc.override_pick(GUILD, "p1", "Garchomp", "Dragonite")

    assert [pick["pokemon_name"] for pick in stored(store)["picks"]] == ["Dragonite"]


# ── League sheet writes ───────────────────────────────────────────────────────


async def test_failed_sheet_write_is_logged_and_the_pick_stands(svc, sheet, caplog):
    sheet.save_pick.side_effect = RuntimeError("quota exceeded")
    await start(svc)

    def logged() -> bool:
        return any(
            record.name == ds.log.name
            and record.levelno == logging.ERROR
            and "quota exceeded" in record.getMessage()
            for record in caplog.records
        )

    with caplog.at_level(logging.ERROR, logger=ds.log.name):
        result = await svc.make_pick(GUILD, "p1", "Garchomp")
        for _ in range(100):  # the write runs in a worker thread
            if logged():
                break
            await asyncio.sleep(0.01)

    assert result.success
    assert logged()
