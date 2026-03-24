"""Tests for pure helper functions in bot cogs and views."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from src.bot.cogs.team import decode_attachment_bytes
from src.bot.views.team_import_view import build_confirm_embed
from src.bot.cogs.admin import (
    _model_exists,
    _build_progress_embed,
    _build_queue_embed,
    _try_edit,
    ConfirmResetView,
    AdminCog,
)
from src.bot.cogs.misc import build_help_embed, MiscCog


# ── Shared interaction helper ──────────────────────────────────────────────────

def make_interaction(guild_id="1234", user_id="5678"):
    """Build a minimal mock discord.Interaction for command tests."""
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.guild = MagicMock()
    interaction.guild.id = int(guild_id)
    interaction.user = MagicMock()
    interaction.user.id = user_id
    interaction.user.display_name = "TestUser"
    interaction.user.mention = "<@5678>"
    interaction.user.send = AsyncMock()
    interaction.user.guild_permissions = MagicMock()
    interaction.user.guild_permissions.manage_guild = True
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock(return_value=MagicMock())
    interaction.client = MagicMock()
    interaction.client.tree = MagicMock()
    interaction.client.tree.sync = AsyncMock(return_value=[MagicMock(), MagicMock()])
    interaction.client.tree.copy_global_to = MagicMock()
    interaction.client.tree.get_commands = MagicMock(return_value=[])
    interaction.client.reload_extension = AsyncMock()
    interaction.channel = MagicMock()
    interaction.channel.send = AsyncMock()
    return interaction


# ── decode_attachment_bytes ────────────────────────────────────────────────────

def test_decode_utf8_text():
    data = "Pokémon Showdown export".encode("utf-8")
    assert decode_attachment_bytes(data) == "Pokémon Showdown export"


def test_decode_ascii():
    data = b"Garchomp @ Choice Scarf"
    assert decode_attachment_bytes(data) == "Garchomp @ Choice Scarf"


def test_decode_invalid_bytes_uses_replacement():
    data = b"\xff\xfe" + b"Valid"
    result = decode_attachment_bytes(data)
    assert "Valid" in result  # replacement chars for invalid bytes, ASCII survives


def test_decode_empty_bytes():
    assert decode_attachment_bytes(b"") == ""


# ── build_confirm_embed (uncovered paths) ─────────────────────────────────────

def test_build_confirm_embed_unknown_format_key():
    """Unknown format key falls back to the key itself in the title."""
    embed = build_confirm_embed("gen9fakefmt", ["Pikachu"])
    assert "gen9fakefmt" in embed.title


def test_build_confirm_embed_empty_pokemon_list():
    embed = build_confirm_embed("gen9ou", [])
    pokemon_field = next(f for f in embed.fields if f.name == "Pokemon")
    assert pokemon_field.value == "No Pokemon found."


# ── _model_exists ─────────────────────────────────────────────────────────────

def test_model_exists_per_format_subdir(tmp_path):
    fmt_dir = tmp_path / "gen9ou"
    fmt_dir.mkdir()
    (fmt_dir / "gen9ou_2026-01-01.zip").touch()
    assert _model_exists(tmp_path, "gen9ou") is True


def test_model_exists_flat_root(tmp_path):
    (tmp_path / "gen9ou_2026-01-01.zip").touch()
    assert _model_exists(tmp_path, "gen9ou") is True


def test_model_exists_false(tmp_path):
    assert _model_exists(tmp_path, "gen9ou") is False


def test_model_exists_different_format_no_match(tmp_path):
    (tmp_path / "gen9uu_2026-01-01.zip").touch()
    assert _model_exists(tmp_path, "gen9ou") is False


# ── _build_progress_embed ─────────────────────────────────────────────────────

def test_build_progress_embed_initial():
    embed = _build_progress_embed("gen9ou", 0, 500_000, 1)
    assert "gen9ou" in embed.title
    assert "⚙️" in embed.title


def test_build_progress_embed_done():
    embed = _build_progress_embed("gen9ou", 500_000, 500_000, 1, done=True)
    assert "✅" in embed.title
    assert "gen9ou" in embed.title


def test_build_progress_embed_failed():
    embed = _build_progress_embed("gen9ou", 0, 500_000, 1, failed=True)
    assert "❌" in embed.title


def test_build_progress_embed_retry():
    embed = _build_progress_embed("gen9ou", 100_000, 500_000, 2)
    assert "🔄" in embed.title
    assert "attempt 2" in embed.title


def test_build_progress_embed_description_has_steps():
    embed = _build_progress_embed("gen9ou", 250_000, 500_000, 1)
    assert "250,000" in embed.description
    assert "500,000" in embed.description


def test_build_progress_embed_zero_total_no_crash():
    embed = _build_progress_embed("gen9ou", 0, 0, 1)
    assert embed is not None


# ── _build_queue_embed ────────────────────────────────────────────────────────

def test_build_queue_embed_initial_queued():
    embed = _build_queue_embed(5, 0, 500_000)
    assert "🚀" in embed.title
    assert "5 format(s)" in embed.title


def test_build_queue_embed_currently_training():
    embed = _build_queue_embed(5, 0, 500_000, current_fmt="gen9ou", current_steps=100_000, n_done=1)
    assert "⚙️" in embed.title
    assert "gen9ou" in embed.title


def test_build_queue_embed_done_all_success():
    embed = _build_queue_embed(5, 0, 500_000, n_done=5, done=True)
    assert "✅" in embed.title


def test_build_queue_embed_done_with_failures():
    embed = _build_queue_embed(5, 0, 500_000, n_done=4, n_failed=1, done=True)
    assert "⚠️" in embed.title


def test_build_queue_embed_with_skipped():
    embed = _build_queue_embed(5, 2, 500_000)
    assert "2 skipped" in embed.description


def test_build_queue_embed_description_has_queue_summary():
    embed = _build_queue_embed(10, 3, 500_000, n_done=2, n_failed=1)
    assert "done" in embed.description
    assert "failed" in embed.description
    assert "remaining" in embed.description


# ── build_help_embed ───────────────────────────────────────────────────────────

def test_build_help_embed_missing_csv(tmp_path):
    """When the CSV does not exist, embed has an unavailable description."""
    nonexistent = tmp_path / "nope.csv"
    embed = build_help_embed(csv_path=nonexistent)
    assert embed.title == "Bot Commands"
    assert "unavailable" in embed.description.lower()


def test_build_help_embed_with_real_csv(tmp_path):
    """Happy path: reads CSV and adds one field per category."""
    csv_file = tmp_path / "commands.csv"
    csv_file.write_text(
        "Category,Command\nDraft,/draft\nDraft,/pick\nTeam,/team\n",
        encoding="utf-8",
    )
    embed = build_help_embed(csv_path=csv_file)
    field_names = [f.name for f in embed.fields]
    assert "Draft" in field_names
    assert "Team" in field_names


def test_build_help_embed_skips_rows_with_no_command(tmp_path):
    """Rows where Command is blank are not added to any field."""
    csv_file = tmp_path / "commands.csv"
    csv_file.write_text(
        "Category,Command\nDraft,\nTeam,/team\n",
        encoding="utf-8",
    )
    embed = build_help_embed(csv_path=csv_file)
    # Only 'Team' field should appear since Draft row has no command
    field_names = [f.name for f in embed.fields]
    assert "Team" in field_names
    assert "Draft" not in field_names


def test_build_help_embed_groups_commands_in_field(tmp_path):
    """Multiple commands in the same category appear in one field value."""
    csv_file = tmp_path / "commands.csv"
    csv_file.write_text(
        "Category,Command\nDraft,/draft\nDraft,/pick\n",
        encoding="utf-8",
    )
    embed = build_help_embed(csv_path=csv_file)
    draft_field = next(f for f in embed.fields if f.name == "Draft")
    assert "/draft" in draft_field.value
    assert "/pick" in draft_field.value


# ── MiscCog.help_cmd ──────────────────────────────────────────────────────────

async def test_misc_cog_help_cmd_defers_and_sends():
    """help_cmd defers then sends a followup embed."""
    bot = MagicMock()
    cog = MiscCog(bot)
    interaction = make_interaction()

    with patch("src.bot.cogs.misc.build_help_embed") as mock_build:
        mock_embed = MagicMock()
        mock_build.return_value = mock_embed
        # @app_commands.command wraps the method — call the underlying callback
        await cog.help_cmd.callback(cog, interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    interaction.followup.send.assert_awaited_once_with(embed=mock_embed, ephemeral=True)


# ── MiscCog setup ─────────────────────────────────────────────────────────────

async def test_misc_cog_setup_adds_cog():
    """setup() registers MiscCog to the bot."""
    bot = MagicMock()
    bot.add_cog = AsyncMock()
    from src.bot.cogs.misc import setup
    await setup(bot)
    bot.add_cog.assert_awaited_once()
    cog_arg = bot.add_cog.call_args[0][0]
    assert isinstance(cog_arg, MiscCog)


# ── AdminCog setup ────────────────────────────────────────────────────────────

async def test_admin_cog_setup_adds_cog():
    """setup() registers AdminCog to the bot."""
    bot = MagicMock()
    bot.add_cog = AsyncMock()
    from src.bot.cogs.admin import setup
    await setup(bot)
    bot.add_cog.assert_awaited_once()
    cog_arg = bot.add_cog.call_args[0][0]
    assert isinstance(cog_arg, AdminCog)


# ── AdminCog command handlers ──────────────────────────────────────────────────

async def test_admin_skip_sends_followup():
    """admin_skip defers, calls force_skip, then sends a followup."""
    bot = MagicMock()
    cog = AdminCog(bot)
    cog.draft_service = MagicMock()
    skip_result = MagicMock()
    skip_result.next_player = "Player2"
    cog.draft_service.force_skip = AsyncMock(return_value=skip_result)

    interaction = make_interaction()
    user = MagicMock()
    user.id = "9999"
    user.display_name = "Player1"

    # @app_commands.command wraps the method — call the underlying callback
    await cog.admin_skip.callback(cog, interaction, user)

    interaction.response.defer.assert_awaited_once()
    cog.draft_service.force_skip.assert_awaited_once_with(
        guild_id="1234", player_id="9999"
    )
    sent_text = interaction.followup.send.call_args[0][0]
    assert "Player1" in sent_text
    assert "Player2" in sent_text


async def test_admin_pause_sends_paused_message():
    """admin_pause defers, calls pause_draft, confirms with 'paused'."""
    bot = MagicMock()
    cog = AdminCog(bot)
    cog.draft_service = MagicMock()
    cog.draft_service.pause_draft = AsyncMock()

    interaction = make_interaction()
    await cog.admin_pause.callback(cog, interaction)

    interaction.response.defer.assert_awaited_once()
    cog.draft_service.pause_draft.assert_awaited_once_with("1234")
    sent_text = interaction.followup.send.call_args[0][0]
    assert "paused" in sent_text.lower()


async def test_admin_resume_sends_resumed_message():
    """admin_resume defers, calls resume_draft, confirms with 'resumed'."""
    bot = MagicMock()
    cog = AdminCog(bot)
    cog.draft_service = MagicMock()
    cog.draft_service.resume_draft = AsyncMock()

    interaction = make_interaction()
    await cog.admin_resume.callback(cog, interaction)

    interaction.response.defer.assert_awaited_once()
    cog.draft_service.resume_draft.assert_awaited_once_with("1234")
    sent_text = interaction.followup.send.call_args[0][0]
    assert "resumed" in sent_text.lower()


async def test_admin_override_pick_sends_confirmation():
    """admin_override_pick calls override_pick and confirms both pokemon names."""
    bot = MagicMock()
    cog = AdminCog(bot)
    cog.draft_service = MagicMock()
    cog.draft_service.override_pick = AsyncMock()

    interaction = make_interaction()
    user = MagicMock()
    user.id = "9999"
    user.display_name = "Player1"

    await cog.admin_override_pick.callback(cog, interaction, user, "Garchomp", "Dragonite")

    cog.draft_service.override_pick.assert_awaited_once_with(
        guild_id="1234",
        player_id="9999",
        old_pokemon="Garchomp",
        new_pokemon="Dragonite",
    )
    sent_text = interaction.followup.send.call_args[0][0]
    assert "Garchomp" in sent_text
    assert "Dragonite" in sent_text


# ── admin_sync ────────────────────────────────────────────────────────────────

async def test_admin_sync_guild_scope_syncs_to_guild():
    """Guild scope: copy_global_to + sync(guild=...) called, count in response."""
    bot = MagicMock()
    cog = AdminCog(bot)

    interaction = make_interaction()
    # Two synced commands returned
    interaction.client.tree.sync = AsyncMock(return_value=[MagicMock(), MagicMock()])

    scope = MagicMock()
    scope.value = "guild"

    await cog.admin_sync.callback(cog, interaction, scope)

    interaction.client.tree.copy_global_to.assert_called_once_with(guild=interaction.guild)
    interaction.client.tree.sync.assert_awaited_once_with(guild=interaction.guild)
    # followup.send called with positional string + ephemeral kwarg
    sent_text = interaction.followup.send.call_args[0][0]
    assert "2" in sent_text
    assert "✅" in sent_text


async def test_admin_sync_global_scope_syncs_globally():
    """Global scope: sync() called without guild kwarg."""
    bot = MagicMock()
    cog = AdminCog(bot)

    interaction = make_interaction()
    interaction.client.tree.sync = AsyncMock(return_value=[MagicMock()])

    scope = MagicMock()
    scope.value = "global"

    await cog.admin_sync.callback(cog, interaction, scope)

    # sync called with no guild argument
    interaction.client.tree.sync.assert_awaited_once_with()
    sent_text = interaction.followup.send.call_args[0][0]
    assert "✅" in sent_text
    assert "1" in sent_text


async def test_admin_sync_none_scope_defaults_to_guild():
    """No scope provided defaults to guild sync."""
    bot = MagicMock()
    cog = AdminCog(bot)

    interaction = make_interaction()
    interaction.client.tree.sync = AsyncMock(return_value=[])

    await cog.admin_sync.callback(cog, interaction, None)

    interaction.client.tree.copy_global_to.assert_called_once()
    interaction.client.tree.sync.assert_awaited_once_with(guild=interaction.guild)


async def test_admin_sync_http_exception_reports_failure():
    """HTTPException during sync sends an error followup with status code."""
    bot = MagicMock()
    cog = AdminCog(bot)

    interaction = make_interaction()
    http_exc = discord.HTTPException(MagicMock(status=429), "Rate limited")
    http_exc.status = 429
    http_exc.text = "Rate limited"
    interaction.client.tree.sync = AsyncMock(side_effect=http_exc)

    scope = MagicMock()
    scope.value = "guild"

    await cog.admin_sync.callback(cog, interaction, scope)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "❌" in sent_text
    assert "429" in sent_text


# ── admin_reset ───────────────────────────────────────────────────────────────

async def test_admin_reset_sends_confirm_view():
    """admin_reset sends an ephemeral message containing the confirm view."""
    bot = MagicMock()
    cog = AdminCog(bot)
    cog.draft_service = MagicMock()

    interaction = make_interaction()
    await cog.admin_reset.callback(cog, interaction)

    interaction.response.send_message.assert_awaited_once()
    call_kwargs = interaction.response.send_message.call_args[1]
    assert call_kwargs.get("ephemeral") is True
    assert isinstance(call_kwargs.get("view"), ConfirmResetView)


# ── admin_train ───────────────────────────────────────────────────────────────

async def test_admin_train_unknown_format_sends_error():
    """Unknown format key sends ephemeral error without launching training."""
    bot = MagicMock()
    cog = AdminCog(bot)

    interaction = make_interaction()
    await cog.admin_train.callback(cog, interaction, format="gen99fakefmt")

    sent_text = interaction.followup.send.call_args[0][0]
    assert "Unknown format" in sent_text


async def test_admin_train_model_exists_no_force_sends_error(tmp_path):
    """When model exists and force=False, sends 'already exists' message."""
    bot = MagicMock()
    cog = AdminCog(bot)

    # Create a fake model zip so _model_exists returns True
    from src.ml.train_all import TRAINING_MAP
    fmt = next(iter(TRAINING_MAP))  # pick any valid format

    with patch("src.bot.cogs.admin._model_exists", return_value=True):
        interaction = make_interaction()
        await cog.admin_train.callback(cog, interaction, format=fmt, force=False)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "already exists" in sent_text


async def test_admin_train_valid_format_creates_task():
    """Valid format with no existing model starts a training task."""
    from src.ml.train_all import TRAINING_MAP
    fmt = next(iter(TRAINING_MAP))

    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()

    with patch("src.bot.cogs.admin._model_exists", return_value=False), \
         patch("src.bot.cogs.admin._run_training", new_callable=AsyncMock) as mock_run, \
         patch("asyncio.create_task") as mock_task:
        await cog.admin_train.callback(cog, interaction, format=fmt, timesteps=10_000)

    # followup.send called (status embed) and create_task called
    interaction.followup.send.assert_awaited_once()
    mock_task.assert_called_once()


# ── admin_train_format_autocomplete ───────────────────────────────────────────

async def test_admin_train_autocomplete_returns_matching_formats():
    """Autocomplete filters TRAINING_MAP keys by the current input."""
    from src.ml.train_all import TRAINING_MAP
    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()

    # Use a prefix that should match at least one format
    prefix = "gen9"
    # autocomplete handlers are regular async methods — call directly
    choices = await cog.admin_train_format_autocomplete(interaction, prefix)

    assert len(choices) > 0
    for choice in choices:
        assert prefix in choice.value.lower()


async def test_admin_train_autocomplete_empty_current_returns_all_or_25():
    """Empty current string returns up to 25 choices (all formats)."""
    from src.ml.train_all import TRAINING_MAP
    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()

    choices = await cog.admin_train_format_autocomplete(interaction, "")
    assert len(choices) == min(len(TRAINING_MAP), 25)


async def test_admin_train_autocomplete_no_match_returns_empty():
    """Completely non-matching input returns empty list."""
    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()

    choices = await cog.admin_train_format_autocomplete(interaction, "zzznomatch999")
    assert choices == []


# ── admin_train_all ───────────────────────────────────────────────────────────

async def test_admin_train_all_defers_and_creates_task():
    """admin_train_all defers, sends status embed, and spawns an asyncio task."""
    bot = MagicMock()
    cog = AdminCog(bot)

    interaction = make_interaction()

    with patch("src.bot.cogs.admin._model_exists", return_value=False), \
         patch("src.bot.cogs.admin._run_training_all", new_callable=AsyncMock), \
         patch("asyncio.create_task") as mock_task:
        await cog.admin_train_all.callback(
            cog, interaction, timesteps=10_000, skip_existing=False
        )

    interaction.response.defer.assert_awaited_once_with(thinking=True)
    interaction.followup.send.assert_awaited_once()
    mock_task.assert_called_once()


async def test_admin_train_all_skips_existing_when_flag_set():
    """With skip_existing=True, already-existing models are counted as skipped."""
    from src.ml.train_all import TRAINING_MAP
    bot = MagicMock()
    cog = AdminCog(bot)

    interaction = make_interaction()

    # All models "exist" so they should all be skipped
    with patch("src.bot.cogs.admin._model_exists", return_value=True), \
         patch("src.bot.cogs.admin._run_training_all", new_callable=AsyncMock), \
         patch("asyncio.create_task"):
        await cog.admin_train_all.callback(
            cog, interaction, timesteps=10_000, skip_existing=True
        )

    # followup.send was still called (even with 0 formats to train)
    interaction.followup.send.assert_awaited_once()


# ── admin_showdown_check ──────────────────────────────────────────────────────

async def test_admin_showdown_check_server_reachable():
    """When socket connects successfully, sends a '✅ reachable' followup."""
    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()

    mock_socket = MagicMock()
    mock_socket.__enter__ = MagicMock(return_value=mock_socket)
    mock_socket.__exit__ = MagicMock(return_value=False)

    with patch("socket.create_connection", return_value=mock_socket), \
         patch("webbrowser.open") as mock_browser:
        await cog.admin_showdown_check.callback(cog, interaction)

    mock_browser.assert_called_once()
    sent_text = interaction.followup.send.call_args[0][0]
    assert "✅" in sent_text
    assert "reachable" in sent_text.lower()


async def test_admin_showdown_check_server_unreachable():
    """When socket raises OSError, sends a '❌ NOT running' followup."""
    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()

    with patch("socket.create_connection", side_effect=OSError("refused")), \
         patch("webbrowser.open") as mock_browser:
        await cog.admin_showdown_check.callback(cog, interaction)

    mock_browser.assert_not_called()
    sent_text = interaction.followup.send.call_args[0][0]
    assert "❌" in sent_text
    assert "NOT" in sent_text


# ── ConfirmResetView ──────────────────────────────────────────────────────────

async def test_confirm_reset_view_confirm_resets_draft():
    """Pressing Confirm calls reset_draft and sends success message."""
    draft_service = MagicMock()
    draft_service.reset_draft = AsyncMock()

    view = ConfirmResetView(guild_id="1234", draft_service=draft_service)
    interaction = make_interaction()
    button = MagicMock()

    # @discord.ui.button creates a descriptor — call via the class to get the raw function
    await ConfirmResetView.confirm(view, interaction, button)

    draft_service.reset_draft.assert_awaited_once_with("1234")
    interaction.response.send_message.assert_awaited_once()
    sent_text = interaction.response.send_message.call_args[0][0]
    assert "reset" in sent_text.lower()


async def test_confirm_reset_view_cancel_sends_cancelled():
    """Pressing Cancel sends 'cancelled' without touching the draft."""
    draft_service = MagicMock()
    draft_service.reset_draft = AsyncMock()

    view = ConfirmResetView(guild_id="1234", draft_service=draft_service)
    interaction = make_interaction()
    button = MagicMock()

    await ConfirmResetView.cancel(view, interaction, button)

    draft_service.reset_draft.assert_not_awaited()
    sent_text = interaction.response.send_message.call_args[0][0]
    assert "cancel" in sent_text.lower()


# ── _try_edit ─────────────────────────────────────────────────────────────────

async def test_try_edit_none_msg_is_noop():
    """_try_edit with None message does nothing and does not raise."""
    embed = MagicMock()
    await _try_edit(None, embed)  # should complete silently


async def test_try_edit_with_msg_calls_edit():
    """_try_edit with a real message calls msg.edit(embed=embed)."""
    msg = MagicMock()
    msg.edit = AsyncMock()
    embed = MagicMock()

    await _try_edit(msg, embed)

    msg.edit.assert_awaited_once_with(embed=embed)


async def test_try_edit_suppresses_edit_exception():
    """_try_edit silently swallows any exception from msg.edit."""
    msg = MagicMock()
    msg.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500), "error"))
    embed = MagicMock()

    # Must not raise
    await _try_edit(msg, embed)
