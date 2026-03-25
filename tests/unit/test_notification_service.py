"""
Unit tests for NotificationService — DMs for pick turns, trades, match results.
All Discord API calls are mocked so no real bot is needed.
"""
from unittest.mock import AsyncMock, MagicMock

import discord

from src.services.notification_service import NotificationService


def make_service():
    """Create a NotificationService with a mocked bot."""
    bot = AsyncMock(spec=discord.Client)
    # get_user (sync cache lookup) returns None so tests fall through to fetch_user
    bot.get_user = MagicMock(return_value=None)
    svc = NotificationService(bot)
    return svc, bot


def make_user(dm_ok: bool = True):
    """Return a mock discord.User that either accepts or rejects DMs."""
    user = AsyncMock()
    if dm_ok:
        user.send = AsyncMock(return_value=None)
    else:
        user.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Cannot DM"))
    return user


# ── _dm success path ──────────────────────────────────────────

async def test_dm_success_returns_true():
    svc, bot = make_service()
    user = make_user(dm_ok=True)
    bot.fetch_user = AsyncMock(return_value=user)

    result = await svc._dm("123", "Hello!")

    assert result is True
    user.send.assert_called_once_with("Hello!")


# ── _dm failure paths ─────────────────────────────────────────

async def test_dm_forbidden_returns_false():
    """Users with DMs disabled return False without raising."""
    svc, bot = make_service()
    user = make_user(dm_ok=False)
    bot.fetch_user = AsyncMock(return_value=user)

    result = await svc._dm("123", "Hello!")

    assert result is False


async def test_dm_not_found_returns_false():
    svc, bot = make_service()
    bot.fetch_user = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Unknown User"))

    result = await svc._dm("999", "Hey")

    assert result is False


async def test_dm_generic_error_returns_false():
    svc, bot = make_service()
    bot.fetch_user = AsyncMock(side_effect=RuntimeError("network error"))

    result = await svc._dm("123", "Hey")

    assert result is False


# ── notify_pick_turn ──────────────────────────────────────────

async def test_notify_pick_turn_contains_timer():
    svc, bot = make_service()
    user = make_user()
    bot.fetch_user = AsyncMock(return_value=user)

    await svc.notify_pick_turn("42", time_remaining=90)

    sent = user.send.call_args[0][0]
    assert "90 seconds" in sent
    assert "/pick" in sent


async def test_notify_pick_turn_with_hint():
    svc, bot = make_service()
    user = make_user()
    bot.fetch_user = AsyncMock(return_value=user)

    await svc.notify_pick_turn("42", pokemon_hint="Garchomp", time_remaining=60)

    sent = user.send.call_args[0][0]
    assert "Garchomp" in sent


# ── notify_pick_warning ───────────────────────────────────────

async def test_notify_pick_warning_contains_seconds():
    svc, bot = make_service()
    user = make_user()
    bot.fetch_user = AsyncMock(return_value=user)

    await svc.notify_pick_warning("42", seconds_left=30)

    sent = user.send.call_args[0][0]
    assert "30 seconds" in sent


# ── notify_trade_offer ────────────────────────────────────────

async def test_notify_trade_offer_contains_details():
    svc, bot = make_service()
    user = make_user()
    bot.fetch_user = AsyncMock(return_value=user)

    await svc.notify_trade_offer("42", "Alice", "Garchomp", "Corviknight", "trade-xyz")

    sent = user.send.call_args[0][0]
    assert "Alice" in sent
    assert "Garchomp" in sent
    assert "Corviknight" in sent
    assert "trade-xyz" in sent


# ── notify_trade_accepted ─────────────────────────────────────

async def test_notify_trade_accepted_contains_pokemon():
    svc, bot = make_service()
    user = make_user()
    bot.fetch_user = AsyncMock(return_value=user)

    await svc.notify_trade_accepted("42", "Garchomp", "Corviknight")

    sent = user.send.call_args[0][0]
    assert "Garchomp" in sent
    assert "Corviknight" in sent


# ── notify_match_reminder ─────────────────────────────────────

async def test_notify_match_reminder_contains_opponent():
    svc, bot = make_service()
    user = make_user()
    bot.fetch_user = AsyncMock(return_value=user)

    await svc.notify_match_reminder("42", "Bob", minutes_until=30)

    sent = user.send.call_args[0][0]
    assert "Bob" in sent
    assert "30 minutes" in sent


# ── notify_draft_complete ─────────────────────────────────────

async def test_notify_draft_complete_contains_team():
    svc, bot = make_service()
    user = make_user()
    bot.fetch_user = AsyncMock(return_value=user)

    await svc.notify_draft_complete("42", "Garchomp, Corviknight, Toxapex")

    sent = user.send.call_args[0][0]
    assert "Garchomp" in sent
    assert "draft is complete" in sent.lower()


# ── notify_elo_update ─────────────────────────────────────────

async def test_notify_elo_update_win():
    svc, bot = make_service()
    user = make_user()
    bot.fetch_user = AsyncMock(return_value=user)

    await svc.notify_elo_update("42", won=True, old_elo=1000, new_elo=1016, opponent_name="Bob")

    sent = user.send.call_args[0][0]
    assert "won" in sent
    assert "Bob" in sent
    assert "1000" in sent
    assert "1016" in sent
    assert "+16" in sent


async def test_notify_elo_update_loss():
    svc, bot = make_service()
    user = make_user()
    bot.fetch_user = AsyncMock(return_value=user)

    await svc.notify_elo_update("42", won=False, old_elo=1000, new_elo=984, opponent_name="Alice")

    sent = user.send.call_args[0][0]
    assert "lost" in sent
    assert "Alice" in sent
    assert "-16" in sent
