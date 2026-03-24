"""Tests for TeamImportConfirmView and build_confirm_embed."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.views.team_import_view import TeamImportConfirmView, build_confirm_embed
from src.bot.constants import SUPPORTED_FORMATS


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_interaction():
    """Build a minimal mock discord.Interaction for view button tests."""
    interaction = MagicMock()
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _make_import_result(success: bool, pokemon=None, error=None):
    """Build a mock import result object."""
    result = MagicMock()
    result.success = success
    result.pokemon = pokemon or []
    result.error = error or ""
    return result


# ── TeamImportConfirmView.__init__ ─────────────────────────────────────────────

def test_init_stores_all_attributes():
    """Constructor stores all five arguments as instance attributes."""
    team_service = MagicMock()
    view = TeamImportConfirmView(
        team_service=team_service,
        guild_id="guild-1",
        player_id="player-1",
        showdown_text="Garchomp @ Choice Scarf\n...",
        format_key="gen9ou",
    )

    assert view.team_service is team_service
    assert view.guild_id == "guild-1"
    assert view.player_id == "player-1"
    assert view.showdown_text == "Garchomp @ Choice Scarf\n..."
    assert view.format_key == "gen9ou"


def test_init_sets_timeout():
    """View timeout is set to 120 seconds."""
    view = TeamImportConfirmView(
        team_service=MagicMock(),
        guild_id="g",
        player_id="p",
        showdown_text="",
        format_key="gen9ou",
    )
    assert view.timeout == 120


# ── TeamImportConfirmView.confirm — success ────────────────────────────────────

async def test_confirm_success_sends_pokemon_count():
    """Successful import reports the number of Pokemon loaded."""
    pokemon_list = [MagicMock(), MagicMock(), MagicMock()]
    result = _make_import_result(success=True, pokemon=pokemon_list)

    team_service = MagicMock()
    team_service.import_showdown = AsyncMock(return_value=result)

    view = TeamImportConfirmView(
        team_service=team_service,
        guild_id="guild-1",
        player_id="player-1",
        showdown_text="Garchomp @ Choice Scarf\n...",
        format_key="gen9ou",
    )
    interaction = _make_interaction()
    button = MagicMock()

    # @discord.ui.button creates a descriptor; call via class to get the raw function
    await TeamImportConfirmView.confirm(view, interaction, button)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    team_service.import_showdown.assert_awaited_once_with(
        guild_id="guild-1",
        player_id="player-1",
        showdown_text="Garchomp @ Choice Scarf\n...",
        format_key="gen9ou",
    )
    sent_text = interaction.followup.send.call_args[0][0]
    assert "3" in sent_text
    assert "Pokemon" in sent_text


async def test_confirm_success_uses_format_display_name():
    """Successful import message uses the human-readable format name."""
    result = _make_import_result(success=True, pokemon=[MagicMock()])
    team_service = MagicMock()
    team_service.import_showdown = AsyncMock(return_value=result)

    view = TeamImportConfirmView(
        team_service=team_service,
        guild_id="g",
        player_id="p",
        showdown_text="...",
        format_key="gen9ou",
    )
    interaction = _make_interaction()
    button = MagicMock()

    # @discord.ui.button creates a descriptor; call via class to get the raw function
    await TeamImportConfirmView.confirm(view, interaction, button)

    sent_text = interaction.followup.send.call_args[0][0]
    # "gen9ou" should be shown as "Gen 9 OU"
    assert "Gen 9 OU" in sent_text


async def test_confirm_success_unknown_format_falls_back_to_key():
    """Unknown format_key falls back to the raw key in the success message."""
    result = _make_import_result(success=True, pokemon=[MagicMock()])
    team_service = MagicMock()
    team_service.import_showdown = AsyncMock(return_value=result)

    view = TeamImportConfirmView(
        team_service=team_service,
        guild_id="g",
        player_id="p",
        showdown_text="...",
        format_key="gen99customfmt",
    )
    interaction = _make_interaction()
    button = MagicMock()

    # @discord.ui.button creates a descriptor; call via class to get the raw function
    await TeamImportConfirmView.confirm(view, interaction, button)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "gen99customfmt" in sent_text


# ── TeamImportConfirmView.confirm — failure ────────────────────────────────────

async def test_confirm_failure_sends_error_message():
    """Failed import sends the error string from the result."""
    result = _make_import_result(success=False, error="Pokemon not on your draft list.")
    team_service = MagicMock()
    team_service.import_showdown = AsyncMock(return_value=result)

    view = TeamImportConfirmView(
        team_service=team_service,
        guild_id="g",
        player_id="p",
        showdown_text="...",
        format_key="gen9ou",
    )
    interaction = _make_interaction()
    button = MagicMock()

    # @discord.ui.button creates a descriptor; call via class to get the raw function
    await TeamImportConfirmView.confirm(view, interaction, button)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "Pokemon not on your draft list." in sent_text
    assert "failed" in sent_text.lower() or "Import failed" in sent_text


async def test_confirm_failure_does_not_mention_pokemon_count():
    """Failed import message does not include the Pokemon count."""
    result = _make_import_result(success=False, error="Bad format.")
    team_service = MagicMock()
    team_service.import_showdown = AsyncMock(return_value=result)

    view = TeamImportConfirmView(
        team_service=team_service,
        guild_id="g",
        player_id="p",
        showdown_text="...",
        format_key="gen9ou",
    )
    interaction = _make_interaction()
    button = MagicMock()

    # @discord.ui.button creates a descriptor; call via class to get the raw function
    await TeamImportConfirmView.confirm(view, interaction, button)

    sent_text = interaction.followup.send.call_args[0][0]
    # Should mention the error, not "N Pokemon loaded"
    assert "Pokemon loaded" not in sent_text


async def test_confirm_stops_view_on_success():
    """View is stopped (timeout cleared) after a successful confirm."""
    result = _make_import_result(success=True, pokemon=[MagicMock()])
    team_service = MagicMock()
    team_service.import_showdown = AsyncMock(return_value=result)

    view = TeamImportConfirmView(
        team_service=team_service,
        guild_id="g",
        player_id="p",
        showdown_text="...",
        format_key="gen9ou",
    )

    original_stop = view.stop
    stop_called = []
    view.stop = lambda: stop_called.append(True) or original_stop()

    interaction = _make_interaction()
    button = MagicMock()
    # @discord.ui.button creates a descriptor; call via class to get the raw function
    await TeamImportConfirmView.confirm(view, interaction, button)

    assert stop_called, "view.stop() was not called after confirm"


async def test_confirm_stops_view_on_failure():
    """View is stopped even after a failed confirm."""
    result = _make_import_result(success=False, error="oops")
    team_service = MagicMock()
    team_service.import_showdown = AsyncMock(return_value=result)

    view = TeamImportConfirmView(
        team_service=team_service,
        guild_id="g",
        player_id="p",
        showdown_text="...",
        format_key="gen9ou",
    )

    original_stop = view.stop
    stop_called = []
    view.stop = lambda: stop_called.append(True) or original_stop()

    interaction = _make_interaction()
    button = MagicMock()
    # @discord.ui.button creates a descriptor; call via class to get the raw function
    await TeamImportConfirmView.confirm(view, interaction, button)

    assert stop_called, "view.stop() was not called after failed confirm"


# ── TeamImportConfirmView.cancel ───────────────────────────────────────────────

async def test_cancel_sends_cancelled_message():
    """Pressing Cancel sends 'Team import cancelled.' without calling import."""
    team_service = MagicMock()
    team_service.import_showdown = AsyncMock()

    view = TeamImportConfirmView(
        team_service=team_service,
        guild_id="g",
        player_id="p",
        showdown_text="...",
        format_key="gen9ou",
    )
    interaction = _make_interaction()
    button = MagicMock()

    # @discord.ui.button creates a descriptor; call via class to get the raw function
    await TeamImportConfirmView.cancel(view, interaction, button)

    team_service.import_showdown.assert_not_awaited()
    sent_text = interaction.response.send_message.call_args[0][0]
    assert "cancel" in sent_text.lower()


async def test_cancel_is_ephemeral():
    """Cancel message is sent as ephemeral."""
    team_service = MagicMock()
    view = TeamImportConfirmView(
        team_service=team_service,
        guild_id="g",
        player_id="p",
        showdown_text="...",
        format_key="gen9ou",
    )
    interaction = _make_interaction()
    button = MagicMock()

    # @discord.ui.button creates a descriptor; call via class to get the raw function
    await TeamImportConfirmView.cancel(view, interaction, button)

    kwargs = interaction.response.send_message.call_args[1]
    assert kwargs.get("ephemeral") is True


async def test_cancel_stops_view():
    """View is stopped after cancel."""
    team_service = MagicMock()
    view = TeamImportConfirmView(
        team_service=team_service,
        guild_id="g",
        player_id="p",
        showdown_text="...",
        format_key="gen9ou",
    )

    original_stop = view.stop
    stop_called = []
    view.stop = lambda: stop_called.append(True) or original_stop()

    interaction = _make_interaction()
    button = MagicMock()
    # @discord.ui.button creates a descriptor; call via class to get the raw function
    await TeamImportConfirmView.cancel(view, interaction, button)

    assert stop_called, "view.stop() was not called after cancel"
