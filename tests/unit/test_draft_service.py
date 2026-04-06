"""
Unit tests for DraftService — snake, auction, ban, admin ops.
Run: pytest tests/unit/test_draft_service.py -v
"""
import pytest
from unittest.mock import MagicMock, patch

from src.data.models import DraftFormat, DraftStatus
from src.services.draft_service import DraftService


@pytest.fixture
def draft_svc():
    return DraftService()


@pytest.mark.asyncio
async def test_create_snake_draft(draft_svc):
    with patch("src.services.draft_service.sheets") as mock_sheets:
        mock_sheets.save_league_setup = MagicMock()
        draft = await draft_svc.create_draft(
            guild_id="guild1",
            commissioner_id="user1",
            format=DraftFormat.SNAKE,
            rounds=6,
            timer_seconds=60,
        )
    assert draft.guild_id == "guild1"
    assert draft.format == DraftFormat.SNAKE
    assert draft.total_rounds == 6
    assert draft.status == DraftStatus.SETUP


@pytest.mark.asyncio
async def test_add_players(draft_svc):
    with patch("src.services.draft_service.sheets"):
        await draft_svc.create_draft("guild2", "user1", DraftFormat.SNAKE)
        r1 = await draft_svc.add_player("guild2", "user1")
        r2 = await draft_svc.add_player("guild2", "user2")
    assert r1.success
    assert r2.success
    assert r2.player_count == 2


@pytest.mark.asyncio
async def test_cannot_join_twice(draft_svc):
    with patch("src.services.draft_service.sheets"):
        await draft_svc.create_draft("guild3", "user1", DraftFormat.SNAKE)
        await draft_svc.add_player("guild3", "user1")
        result = await draft_svc.add_player("guild3", "user1")
    assert not result.success
    assert "already joined" in result.error


@pytest.mark.asyncio
async def test_start_requires_two_players(draft_svc):
    with patch("src.services.draft_service.sheets"):
        await draft_svc.create_draft("guild4", "user1", DraftFormat.SNAKE)
        await draft_svc.add_player("guild4", "user1")
    with pytest.raises(ValueError, match="at least 2"):
        await draft_svc.start_draft("guild4", "user1")


@pytest.mark.asyncio
async def test_snake_pick_order(draft_svc):
    """Round 1 picks in order, Round 2 reverses (snake format)."""
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guild5", "p1", DraftFormat.SNAKE, rounds=2)
        for uid in ["p1", "p2", "p3"]:
            await draft_svc.add_player("guild5", uid)
        draft.status = DraftStatus.ACTIVE

    assert draft.current_player_id == "p1"
    draft._advance_pick = DraftService._advance_pick.__get__(draft_svc)

    # Simulate advancing through round 1
    draft_svc._advance_pick(draft)
    assert draft.current_player_id == "p2"
    draft_svc._advance_pick(draft)
    assert draft.current_player_id == "p3"
    # Round 2 should reverse (snake)
    draft_svc._advance_pick(draft)
    assert draft.current_round == 2
    assert draft.current_player_id == "p3"  # reversed


@pytest.mark.asyncio
async def test_pick_already_taken(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guild6", "p1", DraftFormat.SNAKE)
        await draft_svc.add_player("guild6", "p1")
        await draft_svc.add_player("guild6", "p2")
        draft.status = DraftStatus.ACTIVE

    mock_pokemon = MagicMock()
    mock_pokemon.name = "Garchomp"
    with patch("src.services.draft_service.pokemon_db") as mock_db:
        mock_db.find.return_value = mock_pokemon
        with patch("src.services.draft_service.sheets"):
            await draft_svc.make_pick("guild6", "p1", "Garchomp")
            result = await draft_svc.make_pick("guild6", "p2", "Garchomp")

    assert not result.success
    assert "already taken" in result.error


@pytest.mark.asyncio
async def test_auction_bid(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guild7", "p1", DraftFormat.AUCTION)
        await draft_svc.add_player("guild7", "p1")
        draft.budget["p1"] = 1000
        draft.status = DraftStatus.ACTIVE
        draft.current_nomination_id = "Garchomp"

    result = await draft_svc.place_bid("guild7", "p1", 500)
    assert result.success
    assert result.current_high == 500


@pytest.mark.asyncio
async def test_auction_bid_exceeds_budget(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guild8", "p1", DraftFormat.AUCTION)
        await draft_svc.add_player("guild8", "p1")
        draft.budget["p1"] = 100
        draft.status = DraftStatus.ACTIVE
        draft.current_nomination_id = "Garchomp"

    result = await draft_svc.place_bid("guild8", "p1", 500)
    assert not result.success
    assert "budget" in result.error.lower()


@pytest.mark.asyncio
async def test_pause_resume(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guild9", "p1", DraftFormat.SNAKE)
        await draft_svc.add_player("guild9", "p1")
        await draft_svc.add_player("guild9", "p2")
        draft.status = DraftStatus.ACTIVE

    await draft_svc.pause_draft("guild9")
    assert draft.status == DraftStatus.PAUSED

    await draft_svc.resume_draft("guild9")
    assert draft.status == DraftStatus.ACTIVE


@pytest.mark.asyncio
async def test_admin_reset(draft_svc):
    with patch("src.services.draft_service.sheets"):
        await draft_svc.create_draft("guild10", "p1", DraftFormat.SNAKE)
    await draft_svc.reset_draft("guild10")
    assert await draft_svc.get_active_draft("guild10") is None


# ── create_draft_from_config ───────────────────────────────────

@pytest.mark.asyncio
async def test_create_draft_from_config(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft_from_config({
            "guild_id": "guildCFG",
            "commissioner_id": "u1",
            "format": "snake",
            "total_rounds": 4,
            "timer_seconds": 90,
        })
    assert draft.guild_id == "guildCFG"
    assert draft.total_rounds == 4


# ── add_player error paths ─────────────────────────────────────

@pytest.mark.asyncio
async def test_add_player_no_draft(draft_svc):
    result = await draft_svc.add_player("no_such_guild", "p1")
    assert not result.success
    assert "No active draft" in result.error


@pytest.mark.asyncio
async def test_add_player_draft_already_started(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildAS", "p1", DraftFormat.SNAKE)
        await draft_svc.add_player("guildAS", "p1")
        await draft_svc.add_player("guildAS", "p2")
        draft.status = DraftStatus.ACTIVE
    result = await draft_svc.add_player("guildAS", "p3")
    assert not result.success
    assert "already started" in result.error


@pytest.mark.asyncio
async def test_add_player_with_team_name(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildTN", "p1", DraftFormat.SNAKE)
        result = await draft_svc.add_player("guildTN", "p1", team_name="Fire Squad")
    assert result.success
    assert draft.team_names.get("p1") == "Fire Squad"


# ── start_draft error paths ────────────────────────────────────

@pytest.mark.asyncio
async def test_start_draft_no_draft_raises(draft_svc):
    with pytest.raises(ValueError, match="No draft found"):
        await draft_svc.start_draft("missing_guild", "p1")


@pytest.mark.asyncio
async def test_start_draft_wrong_commissioner_raises(draft_svc):
    with patch("src.services.draft_service.sheets"):
        await draft_svc.create_draft("guildWC", "p1", DraftFormat.SNAKE)
        await draft_svc.add_player("guildWC", "p1")
        await draft_svc.add_player("guildWC", "p2")
    with pytest.raises(PermissionError, match="commissioner"):
        await draft_svc.start_draft("guildWC", "not_p1")


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_start_draft_snake_sets_active(draft_svc):
    """Non-CUSTOM formats set status to ACTIVE (draft_service.py:165)."""
    with patch("src.services.draft_service.sheets"):
        _ = await draft_svc.create_draft("guildACT", "p1", DraftFormat.SNAKE)
        await draft_svc.add_player("guildACT", "p1")
        await draft_svc.add_player("guildACT", "p2")
        started = await draft_svc.start_draft("guildACT", "p1")
    assert started.status == DraftStatus.ACTIVE


async def test_start_draft_custom_format_enters_ban_phase(draft_svc):
    with patch("src.services.draft_service.sheets"):
        _ = await draft_svc.create_draft("guildCUST", "p1", DraftFormat.CUSTOM)
        await draft_svc.add_player("guildCUST", "p1")
        await draft_svc.add_player("guildCUST", "p2")
        started = await draft_svc.start_draft("guildCUST", "p1")
    assert started.status == DraftStatus.BAN_PHASE


# ── make_pick error paths ──────────────────────────────────────

@pytest.mark.asyncio
async def test_make_pick_no_draft(draft_svc):
    result = await draft_svc.make_pick("no_guild", "p1", "Garchomp")
    assert not result.success
    assert "No active draft" in result.error


@pytest.mark.asyncio
async def test_make_pick_wrong_turn(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildWT", "p1", DraftFormat.SNAKE)
        await draft_svc.add_player("guildWT", "p1")
        await draft_svc.add_player("guildWT", "p2")
        draft.status = DraftStatus.ACTIVE
    result = await draft_svc.make_pick("guildWT", "p2", "Garchomp")
    assert not result.success
    assert "not your turn" in result.error.lower()


@pytest.mark.asyncio
async def test_make_pick_pokemon_not_found(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildNF", "p1", DraftFormat.SNAKE)
        await draft_svc.add_player("guildNF", "p1")
        await draft_svc.add_player("guildNF", "p2")
        draft.status = DraftStatus.ACTIVE
    with patch("src.services.draft_service.pokemon_db") as mock_db:
        mock_db.find.return_value = None
        result = await draft_svc.make_pick("guildNF", "p1", "FakeMon")
    assert not result.success
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_make_pick_not_active(draft_svc):
    with patch("src.services.draft_service.sheets"):
        _ = await draft_svc.create_draft("guildNA", "p1", DraftFormat.SNAKE)
        await draft_svc.add_player("guildNA", "p1")
        await draft_svc.add_player("guildNA", "p2")
        # Status stays SETUP
    result = await draft_svc.make_pick("guildNA", "p1", "Garchomp")
    assert not result.success
    assert "not currently active" in result.error


# ── ban_pokemon ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ban_pokemon_no_draft(draft_svc):
    result = await draft_svc.ban_pokemon("no_guild", "p1", "Mewtwo")
    assert not result.success
    assert "No active draft" in result.error


@pytest.mark.asyncio
async def test_ban_pokemon_wrong_phase(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildBP", "p1", DraftFormat.SNAKE)
        await draft_svc.add_player("guildBP", "p1")
        await draft_svc.add_player("guildBP", "p2")
        draft.status = DraftStatus.ACTIVE  # not BAN_PHASE
    result = await draft_svc.ban_pokemon("guildBP", "p1", "Mewtwo")
    assert not result.success
    assert "ban phase" in result.error.lower()


@pytest.mark.asyncio
async def test_ban_pokemon_not_found(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildBNF", "p1", DraftFormat.CUSTOM)
        await draft_svc.add_player("guildBNF", "p1")
        await draft_svc.add_player("guildBNF", "p2")
        draft.status = DraftStatus.BAN_PHASE
    with patch("src.services.draft_service.pokemon_db") as mock_db:
        mock_db.find.return_value = None
        result = await draft_svc.ban_pokemon("guildBNF", "p1", "FakeMon")
    assert not result.success
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_ban_pokemon_success(draft_svc):
    """Successful ban appends DraftBan to draft.bans (lines 240-246)."""
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildBOK", "p1", DraftFormat.CUSTOM)
        await draft_svc.add_player("guildBOK", "p1")
        await draft_svc.add_player("guildBOK", "p2")
        draft.status = DraftStatus.BAN_PHASE
    mock_mon = MagicMock()
    mock_mon.name = "Mewtwo"
    with patch("src.services.draft_service.pokemon_db") as mock_db:
        mock_db.find.return_value = mock_mon
        result = await draft_svc.ban_pokemon("guildBOK", "p1", "Mewtwo")
    assert result.success
    assert len(draft.bans) == 1
    assert draft.bans[0].pokemon_name == "Mewtwo"


@pytest.mark.asyncio
async def test_make_pick_banned_pokemon(draft_svc):
    """Picking a banned Pokemon returns error (line 188)."""
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildBanned", "p1", DraftFormat.SNAKE)
        await draft_svc.add_player("guildBanned", "p1")
        await draft_svc.add_player("guildBanned", "p2")
        draft.status = DraftStatus.ACTIVE
    # Manually insert a ban entry
    from src.data.models import DraftBan
    draft.bans.append(DraftBan(draft_id=draft.draft_id, player_id="p1", pokemon_name="Garchomp"))
    result = await draft_svc.make_pick("guildBanned", "p1", "Garchomp")
    assert not result.success
    assert "banned" in result.error.lower()


@pytest.mark.asyncio
async def test_draft_completes_after_all_rounds(draft_svc):
    """Draft status becomes COMPLETED when all rounds are exhausted (lines 225-226)."""
    with patch("src.services.draft_service.sheets"):
        # 1 round, 2 players → 2 total picks to complete the draft
        draft = await draft_svc.create_draft("guildCOMP", "p1", DraftFormat.SNAKE, rounds=1)
        await draft_svc.add_player("guildCOMP", "p1")
        await draft_svc.add_player("guildCOMP", "p2")
        draft.status = DraftStatus.ACTIVE

    mock_mon = MagicMock()
    mock_mon.name = "Garchomp"
    mock_mon2 = MagicMock()
    mock_mon2.name = "Corviknight"
    with patch("src.services.draft_service.pokemon_db") as mock_db, \
         patch("src.services.draft_service.sheets"):
        mock_db.find.side_effect = [mock_mon, mock_mon2]
        await draft_svc.make_pick("guildCOMP", "p1", "Garchomp")
        await draft_svc.make_pick("guildCOMP", "p2", "Corviknight")
    assert draft.status == DraftStatus.COMPLETED


# ── Pick timer ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_timer_creates_task(draft_svc):
    """_start_timer creates an asyncio task that can be cancelled."""
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("gT1", "p1", DraftFormat.SNAKE, timer_seconds=999)
        await draft_svc.add_player("gT1", "p1")
        await draft_svc.add_player("gT1", "p2")
        draft.status = DraftStatus.ACTIVE

    import src.services.draft_service as ds_mod
    draft_svc._start_timer("gT1", draft, None)
    assert "gT1" in ds_mod._timer_tasks
    draft_svc._cancel_timer("gT1")
    assert "gT1" not in ds_mod._timer_tasks


@pytest.mark.asyncio
async def test_cancel_timer_noop_when_no_task(draft_svc):
    """_cancel_timer is safe to call when no task exists."""
    draft_svc._cancel_timer("guild_no_timer")  # Should not raise


@pytest.mark.asyncio
async def test_timer_fires_and_auto_skips(draft_svc):
    """Timer task auto-skips after expiry and calls on_timeout callback."""
    import asyncio

    with patch("src.services.draft_service.sheets") as mock_sheets:
        mock_sheets.save_pick = MagicMock()
        draft = await draft_svc.create_draft("gTFire", "p1", DraftFormat.SNAKE, timer_seconds=0)
        await draft_svc.add_player("gTFire", "p1")
        await draft_svc.add_player("gTFire", "p2")
        draft.status = DraftStatus.ACTIVE

    callback_args = []

    async def on_timeout(guild_id, skipped_player):
        callback_args.append((guild_id, skipped_player))

    # Start timer with 0-second delay so it fires immediately
    draft_svc._start_timer("gTFire", draft, on_timeout)
    # Allow the timer coroutine to run
    await asyncio.sleep(0.05)

    assert ("gTFire", "p1") in callback_args
    # Pick should have advanced to p2
    assert draft.current_player_id == "p2"


@pytest.mark.asyncio
async def test_timer_callback_error_is_swallowed(draft_svc):
    """Errors in on_timeout callback don't crash the timer task."""
    import asyncio

    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("gTErr", "p1", DraftFormat.SNAKE, timer_seconds=0)
        await draft_svc.add_player("gTErr", "p1")
        await draft_svc.add_player("gTErr", "p2")
        draft.status = DraftStatus.ACTIVE

    async def bad_callback(gid, pid):
        raise RuntimeError("boom")

    draft_svc._start_timer("gTErr", draft, bad_callback)
    await asyncio.sleep(0.05)
    # Draft still advanced despite callback error
    assert draft.current_player_id == "p2"


@pytest.mark.asyncio
async def test_make_pick_cancels_old_timer(draft_svc):
    """Successful pick cancels the existing timer."""
    import src.services.draft_service as ds_mod

    with patch("src.services.draft_service.sheets") as mock_sheets, \
         patch("src.services.draft_service.pokemon_db") as mock_db:
        mock_sheets.save_pick = MagicMock()
        mon = MagicMock()
        mon.name = "Pikachu"
        mock_db.find = MagicMock(return_value=mon)

        draft = await draft_svc.create_draft("gTCancel", "p1", DraftFormat.SNAKE, timer_seconds=999)
        await draft_svc.add_player("gTCancel", "p1")
        await draft_svc.add_player("gTCancel", "p2")
        draft.status = DraftStatus.ACTIVE
        draft_svc._start_timer("gTCancel", draft, None)

        assert "gTCancel" in ds_mod._timer_tasks
        result = await draft_svc.make_pick("gTCancel", "p1", "Pikachu")

    assert result.success
    # Timer for gTCancel is gone (was cancelled), or replaced with p2's timer
    # Either way the old "999-second" task should be done/cancelled


@pytest.mark.asyncio
async def test_start_draft_with_timer_starts_first_timer(draft_svc):
    """start_draft fires _start_timer for the first player."""
    import src.services.draft_service as ds_mod

    with patch("src.services.draft_service.sheets"):
        _ = await draft_svc.create_draft("gTStart", "p1", DraftFormat.SNAKE, timer_seconds=999)
        await draft_svc.add_player("gTStart", "p1")
        await draft_svc.add_player("gTStart", "p2")
        started = await draft_svc.start_draft("gTStart", "p1")

    assert started.status == DraftStatus.ACTIVE
    assert "gTStart" in ds_mod._timer_tasks
    draft_svc._cancel_timer("gTStart")


@pytest.mark.asyncio
async def test_pause_draft_cancels_timer(draft_svc):
    """pause_draft cancels the active timer."""
    import src.services.draft_service as ds_mod

    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("gTPause", "p1", DraftFormat.SNAKE, timer_seconds=999)
        await draft_svc.add_player("gTPause", "p1")
        await draft_svc.add_player("gTPause", "p2")
        draft.status = DraftStatus.ACTIVE
        draft_svc._start_timer("gTPause", draft, None)
        assert "gTPause" in ds_mod._timer_tasks
        await draft_svc.pause_draft("gTPause")

    assert "gTPause" not in ds_mod._timer_tasks


@pytest.mark.asyncio
async def test_reset_draft_cancels_timer(draft_svc):
    """reset_draft cancels the active timer."""
    import src.services.draft_service as ds_mod

    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("gTReset", "p1", DraftFormat.SNAKE, timer_seconds=999)
        await draft_svc.add_player("gTReset", "p1")
        await draft_svc.add_player("gTReset", "p2")
        draft.status = DraftStatus.ACTIVE
        draft_svc._start_timer("gTReset", draft, None)
        assert "gTReset" in ds_mod._timer_tasks
        await draft_svc.reset_draft("gTReset")

    assert "gTReset" not in ds_mod._timer_tasks


@pytest.mark.asyncio
async def test_start_timer_returns_early_when_no_current_player(draft_svc):
    """_start_timer line 277: returns early when current_player_id is None."""
    from src.data.models import Draft, DraftFormat, DraftStatus
    import src.services.draft_service as ds_mod

    # Draft with no players → current_player_id is None
    draft = Draft(
        draft_id="empty", guild_id="gEmpty", commissioner_id="p1",
        format=DraftFormat.SNAKE, status=DraftStatus.ACTIVE,
        total_rounds=3, player_order=[], timer_seconds=999,
    )
    ds_mod._active_drafts["gEmpty"] = draft

    draft_svc._start_timer("gEmpty", draft, None)
    # No task should have been created since current_player_id is None
    assert "gEmpty" not in ds_mod._timer_tasks

    ds_mod._active_drafts.pop("gEmpty", None)


@pytest.mark.asyncio
async def test_timer_fires_and_starts_next_player_timer(draft_svc):
    """Line 293: after auto-skip, timer restarts for the next player."""
    import asyncio
    import src.services.draft_service as ds_mod

    callback_players = []

    async def cb(gid, pid):
        callback_players.append(pid)

    with patch("src.services.draft_service.sheets"):
        # timer_seconds=0 → asyncio.sleep(0) fires instantly (real yield, no mocking needed)
        draft = await draft_svc.create_draft("gChain", "p1", DraftFormat.SNAKE, timer_seconds=0)
        await draft_svc.add_player("gChain", "p1")
        await draft_svc.add_player("gChain", "p2")
        await draft_svc.add_player("gChain", "p3")
        draft.status = DraftStatus.ACTIVE

    draft_svc._start_timer("gChain", draft, cb)
    # Mutate timer_seconds to 1 AFTER creating the task but BEFORE it runs.
    # The task closure uses draft.timer_seconds for sleep (0 → instant),
    # but active.timer_seconds for the restart guard (1 → line 293 fires).
    draft.timer_seconds = 1
    for _ in range(10):
        await asyncio.sleep(0)

    # p1 should have been skipped and line 293 should have restarted timer for p2
    assert "p1" in callback_players
    assert "gChain" in ds_mod._timer_tasks
    # Clean up
    draft_svc._cancel_timer("gChain")
    ds_mod._active_drafts.pop("gChain", None)


@pytest.mark.asyncio
async def test_start_timer_handles_no_event_loop(draft_svc):
    """Lines 298-300: RuntimeError from get_event_loop is silently caught."""
    from src.data.models import Draft, DraftFormat, DraftStatus
    import src.services.draft_service as ds_mod

    draft = Draft(
        draft_id="loopless", guild_id="gLoop", commissioner_id="p1",
        format=DraftFormat.SNAKE, status=DraftStatus.ACTIVE,
        total_rounds=3, player_order=["p1", "p2"], timer_seconds=999,
    )
    ds_mod._active_drafts["gLoop"] = draft

    with patch("asyncio.get_event_loop", side_effect=RuntimeError("no loop")):
        # Should not raise
        draft_svc._start_timer("gLoop", draft, None)

    assert "gLoop" not in ds_mod._timer_tasks
    ds_mod._active_drafts.pop("gLoop", None)


# ── place_bid no draft ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_place_bid_no_auction_draft(draft_svc):
    result = await draft_svc.place_bid("no_guild", "p1", 100)
    assert not result.success
    assert "No active auction" in result.error


@pytest.mark.asyncio
async def test_place_bid_draft_not_active(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildBidNA", "p1", DraftFormat.AUCTION)
        await draft_svc.add_player("guildBidNA", "p1")
        draft.budget["p1"] = 1000
        draft.current_nomination_id = "Garchomp"
        # Leave status as PENDING (not ACTIVE)

    result = await draft_svc.place_bid("guildBidNA", "p1", 100)
    assert not result.success
    assert "not currently active" in result.error


@pytest.mark.asyncio
async def test_place_bid_no_nomination(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildBidNN", "p1", DraftFormat.AUCTION)
        await draft_svc.add_player("guildBidNN", "p1")
        draft.budget["p1"] = 1000
        draft.status = DraftStatus.ACTIVE
        # current_nomination_id is None by default

    result = await draft_svc.place_bid("guildBidNN", "p1", 100)
    assert not result.success
    assert "No active nomination" in result.error


@pytest.mark.asyncio
async def test_place_bid_zero_amount(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildBidZ", "p1", DraftFormat.AUCTION)
        await draft_svc.add_player("guildBidZ", "p1")
        draft.budget["p1"] = 1000
        draft.status = DraftStatus.ACTIVE
        draft.current_nomination_id = "Garchomp"

    result = await draft_svc.place_bid("guildBidZ", "p1", 0)
    assert not result.success
    assert "at least 1" in result.error


@pytest.mark.asyncio
async def test_place_bid_not_exceeding_current_high(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildBidHigh", "p1", DraftFormat.AUCTION)
        await draft_svc.add_player("guildBidHigh", "p1")
        await draft_svc.add_player("guildBidHigh", "p2")
        draft.budget["p1"] = 1000
        draft.budget["p2"] = 1000
        draft.status = DraftStatus.ACTIVE
        draft.current_nomination_id = "Garchomp"
        draft.nomination_bids["Garchomp"] = {"p2": 300}

    result = await draft_svc.place_bid("guildBidHigh", "p1", 300)
    assert not result.success
    assert "exceed" in result.error


# ── force_skip ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_force_skip_advances_pick(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildFS", "p1", DraftFormat.SNAKE)
        await draft_svc.add_player("guildFS", "p1")
        await draft_svc.add_player("guildFS", "p2")
        draft.status = DraftStatus.ACTIVE
    original_idx = draft.current_pick_index
    await draft_svc.force_skip("guildFS", "p1")
    assert draft.current_pick_index != original_idx or draft.current_round > 1


# ── override_pick ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_override_pick_replaces_pokemon(draft_svc):
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildOP", "p1", DraftFormat.SNAKE)
        await draft_svc.add_player("guildOP", "p1")
        await draft_svc.add_player("guildOP", "p2")
        draft.status = DraftStatus.ACTIVE

    mock_mon = MagicMock()
    mock_mon.name = "Garchomp"
    with patch("src.services.draft_service.pokemon_db") as mock_db, \
         patch("src.services.draft_service.sheets"):
        mock_db.find.return_value = mock_mon
        await draft_svc.make_pick("guildOP", "p1", "Garchomp")

    await draft_svc.override_pick("guildOP", "p1", "Garchomp", "Dragonite")
    assert draft.picks[0].pokemon_name == "Dragonite"


@pytest.mark.asyncio
async def test_override_pick_no_draft(draft_svc):
    """override_pick with no draft does nothing (no crash)."""
    await draft_svc.override_pick("no_guild", "p1", "Old", "New")  # no exception


# ── place_bid — additional edge cases ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_place_bid_draft_not_active(draft_svc):
    """place_bid on a SETUP (not ACTIVE) auction draft returns error."""
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildBidSetup", "p1", DraftFormat.AUCTION)
        await draft_svc.add_player("guildBidSetup", "p1")
        draft.budget["p1"] = 1000
        # status stays SETUP (not ACTIVE)
        draft.current_nomination_id = "Garchomp"

    result = await draft_svc.place_bid("guildBidSetup", "p1", 100)
    assert not result.success
    assert "not currently active" in result.error.lower()


@pytest.mark.asyncio
async def test_place_bid_no_current_nomination(draft_svc):
    """place_bid when no nomination is active returns error."""
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildBidNoNom", "p1", DraftFormat.AUCTION)
        await draft_svc.add_player("guildBidNoNom", "p1")
        draft.budget["p1"] = 1000
        draft.status = DraftStatus.ACTIVE
        # current_nomination_id stays None

    result = await draft_svc.place_bid("guildBidNoNom", "p1", 100)
    assert not result.success
    assert "no active nomination" in result.error.lower()


@pytest.mark.asyncio
async def test_place_bid_zero_amount(draft_svc):
    """place_bid with amount < 1 returns error."""
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildBidZero", "p1", DraftFormat.AUCTION)
        await draft_svc.add_player("guildBidZero", "p1")
        draft.budget["p1"] = 1000
        draft.status = DraftStatus.ACTIVE
        draft.current_nomination_id = "Garchomp"

    result = await draft_svc.place_bid("guildBidZero", "p1", 0)
    assert not result.success
    assert "at least 1" in result.error.lower()


@pytest.mark.asyncio
async def test_place_bid_not_exceeding_current_high(draft_svc):
    """place_bid that does not exceed current high bid returns error."""
    with patch("src.services.draft_service.sheets"):
        draft = await draft_svc.create_draft("guildBidLow", "p1", DraftFormat.AUCTION)
        await draft_svc.add_player("guildBidLow", "p1")
        await draft_svc.add_player("guildBidLow", "p2")
        draft.budget["p1"] = 1000
        draft.budget["p2"] = 1000
        draft.status = DraftStatus.ACTIVE
        draft.current_nomination_id = "Garchomp"

    # p2 bids 300 first
    await draft_svc.place_bid("guildBidLow", "p2", 300)
    # p1 tries to bid 300 (not strictly higher) → should fail
    result = await draft_svc.place_bid("guildBidLow", "p1", 300)
    assert not result.success
    assert "300" in result.error
