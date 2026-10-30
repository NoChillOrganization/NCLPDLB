"""
/result must not change anyone's ELO until the named opponent confirms.
"""

from unittest.mock import AsyncMock, MagicMock

import discord

from src.bot.cogs.league import LeagueCog, ResultConfirmView
from src.bot.permissions import ROLE_COACH, ROLE_MOD, member_has_role


def make_member(user_id: int, roles: tuple[str, ...] = (ROLE_COACH,), bot=False):
    member = MagicMock()
    member.id = user_id
    member.bot = bot
    member.display_name = f"user{user_id}"
    member.mention = f"<@{user_id}>"
    member.guild_permissions.manage_guild = False
    member.roles = []
    for name in roles:
        role = MagicMock()
        role.name = name
        member.roles.append(role)
    return member


def make_interaction(user):
    interaction = MagicMock()
    interaction.guild_id = "9999"
    interaction.user = user
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.original_response = AsyncMock(return_value=MagicMock())
    interaction.message = MagicMock()
    interaction.message.edit = AsyncMock()
    return interaction


def make_cog():
    cog = LeagueCog(MagicMock())
    cog.elo = MagicMock()
    cog.elo.record_match = AsyncMock()
    return cog


# ── member_has_role ───────────────────────────────────────────


def test_member_has_role_accepts_higher_tier():
    assert member_has_role(make_member(1, (ROLE_MOD,)), ROLE_COACH)


def test_member_has_role_rejects_member_without_roles():
    assert not member_has_role(make_member(1, ()), ROLE_COACH)


# ── the command ───────────────────────────────────────────────


async def test_result_against_yourself_is_refused():
    me = make_member(1)
    interaction = make_interaction(me)
    cog = make_cog()

    await cog.result.callback(cog, interaction, me, True)

    cog.elo.record_match.assert_not_called()
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True
    assert "view" not in interaction.response.send_message.await_args.kwargs


async def test_result_against_a_bot_or_non_coach_is_refused():
    cog = make_cog()
    for opponent in (make_member(2, bot=True), make_member(3, roles=())):
        interaction = make_interaction(make_member(1))
        await cog.result.callback(cog, interaction, opponent, True)
        cog.elo.record_match.assert_not_called()
        assert "view" not in interaction.response.send_message.await_args.kwargs


async def test_result_asks_the_opponent_and_records_nothing_yet():
    cog = make_cog()
    interaction = make_interaction(make_member(1))

    await cog.result.callback(cog, interaction, make_member(2), True)

    cog.elo.record_match.assert_not_called()
    sent = interaction.response.send_message.await_args.kwargs
    assert isinstance(sent["view"], ResultConfirmView)


# ── the confirmation view ─────────────────────────────────────


async def test_only_the_opponent_may_answer():
    opponent = make_member(2)
    view = ResultConfirmView(opponent=opponent, on_confirm=AsyncMock())

    stranger = make_interaction(make_member(3))
    assert await view.interaction_check(stranger) is False
    stranger.response.send_message.assert_awaited_once()

    assert await view.interaction_check(make_interaction(opponent)) is True


async def test_confirm_records_exactly_once():
    on_confirm = AsyncMock()
    opponent = make_member(2)
    view = ResultConfirmView(opponent=opponent, on_confirm=on_confirm)
    click = make_interaction(opponent)

    await view.confirm.callback(click)
    await view.confirm.callback(click)

    on_confirm.assert_awaited_once_with(click)


async def test_decline_records_nothing_and_blocks_a_later_confirm():
    on_confirm = AsyncMock()
    opponent = make_member(2)
    view = ResultConfirmView(opponent=opponent, on_confirm=on_confirm)
    click = make_interaction(opponent)

    await view.decline.callback(click)
    await view.confirm.callback(click)

    on_confirm.assert_not_called()


async def test_timeout_edits_the_message_and_records_nothing():
    on_confirm = AsyncMock()
    view = ResultConfirmView(opponent=make_member(2), on_confirm=on_confirm)
    view.message = MagicMock(spec=discord.Message)
    view.message.edit = AsyncMock()

    await view.on_timeout()

    view.message.edit.assert_awaited_once()
    on_confirm.assert_not_called()
