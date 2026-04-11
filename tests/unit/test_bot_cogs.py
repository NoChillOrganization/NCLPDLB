"""Tests for pure helper functions in bot cogs and views."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord

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

    def _close_task(coro):
        coro.close()
        return MagicMock()

    with patch("src.bot.cogs.admin._model_exists", return_value=False), \
         patch("src.bot.cogs.admin._run_training", new_callable=AsyncMock), \
         patch("asyncio.create_task", side_effect=_close_task) as mock_task:
        await cog.admin_train.callback(cog, interaction, format=fmt, timesteps=10_000)

    # followup.send called (status embed) and create_task called
    interaction.followup.send.assert_awaited_once()
    mock_task.assert_called_once()


# ── admin_train_format_autocomplete ───────────────────────────────────────────

async def test_admin_train_autocomplete_returns_matching_formats():
    """Autocomplete filters TRAINING_MAP keys by the current input."""
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

    def _close_task(coro):
        coro.close()
        return MagicMock()

    with patch("src.bot.cogs.admin._model_exists", return_value=False), \
         patch("src.bot.cogs.admin._run_training_all", new_callable=AsyncMock), \
         patch("asyncio.create_task", side_effect=_close_task) as mock_task:
        await cog.admin_train_all.callback(
            cog, interaction, timesteps=10_000, skip_existing=False
        )

    interaction.response.defer.assert_awaited_once_with(thinking=True)
    interaction.followup.send.assert_awaited_once()
    mock_task.assert_called_once()


async def test_admin_train_all_skips_existing_when_flag_set():
    """With skip_existing=True, already-existing models are counted as skipped."""
    bot = MagicMock()
    cog = AdminCog(bot)

    interaction = make_interaction()

    # All models "exist" so they should all be skipped
    with patch("src.bot.cogs.admin._model_exists", return_value=True), \
         patch("src.bot.cogs.admin._run_training_all", new_callable=AsyncMock), \
         patch("asyncio.create_task", side_effect=lambda c: c.close() or MagicMock()):
        await cog.admin_train_all.callback(
            cog, interaction, timesteps=10_000, skip_existing=True
        )

    # followup.send was still called (even with 0 formats to train)
    interaction.followup.send.assert_awaited_once()


async def test_admin_train_all_followup_not_found_sends_dm_warning():
    """discord.NotFound on followup.send → DM warning sent, task still created."""
    bot = MagicMock()
    cog = AdminCog(bot)

    interaction = make_interaction()
    interaction.followup.send = AsyncMock(
        side_effect=discord.NotFound(MagicMock(status=404), "Unknown interaction")
    )

    def _close_task(coro):
        coro.close()
        return MagicMock()

    with patch("src.bot.cogs.admin._model_exists", return_value=False), \
         patch("src.bot.cogs.admin._run_training_all", new_callable=AsyncMock), \
         patch("asyncio.create_task", side_effect=_close_task) as mock_task:
        await cog.admin_train_all.callback(
            cog, interaction, timesteps=10_000, skip_existing=False
        )

    # DM warning sent, task still spawned
    interaction.user.send.assert_awaited()
    dm_text = interaction.user.send.call_args[0][0]
    assert "training is starting" in dm_text.lower() or "interaction expired" in dm_text.lower()
    mock_task.assert_called_once()


async def test_admin_train_followup_not_found_sends_dm_warning():
    """discord.NotFound on admin_train followup.send → DM warning, task created."""
    from src.ml.train_all import TRAINING_MAP
    fmt = next(iter(TRAINING_MAP))

    bot = MagicMock()
    cog = AdminCog(bot)

    interaction = make_interaction()
    interaction.followup.send = AsyncMock(
        side_effect=discord.NotFound(MagicMock(status=404), "Unknown interaction")
    )

    def _close_task(coro):
        coro.close()
        return MagicMock()

    with patch("src.bot.cogs.admin._model_exists", return_value=False), \
         patch("src.bot.cogs.admin._run_training", new_callable=AsyncMock), \
         patch("asyncio.create_task", side_effect=_close_task) as mock_task:
        await cog.admin_train.callback(cog, interaction, format=fmt, timesteps=10_000)

    interaction.user.send.assert_awaited()
    mock_task.assert_called_once()


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


# ── Async subprocess helper ───────────────────────────────────────────────────

class _AsyncLineIter:
    """Minimal async iterator for mocking proc.stdout in _run_training tests."""
    def __init__(self, lines=()):
        self._lines = list(lines)
        self._pos = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._pos >= len(self._lines):
            raise StopAsyncIteration
        val = self._lines[self._pos]
        self._pos += 1
        return val


def _make_proc(returncode=0, lines=()):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = _AsyncLineIter(lines)
    proc.wait = AsyncMock()
    proc.communicate = MagicMock(return_value=(b"output text", None))
    return proc


# ── admin_update ──────────────────────────────────────────────────────────────

async def test_admin_update_success_all_ok():
    """Full success path: git pull OK, cogs reload OK, guild sync OK."""
    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()
    proc = _make_proc(returncode=0)

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc), \
         patch("asyncio.wait_for", new_callable=AsyncMock, return_value=(b"Already up to date.", None)):
        await cog.admin_update.callback(cog, interaction)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "✅" in sent_text
    assert "git pull" in sent_text
    assert "Cogs reloaded" in sent_text


async def test_admin_update_git_pull_timeout():
    """asyncio.wait_for raises TimeoutError → 'timed out' in response."""
    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()
    proc = _make_proc()

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc), \
         patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        await cog.admin_update.callback(cog, interaction)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "timed out" in sent_text.lower()


async def test_admin_update_git_pull_exception():
    """create_subprocess_exec raises → 'failed' in response."""
    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, side_effect=OSError("no git")):
        await cog.admin_update.callback(cog, interaction)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "failed" in sent_text.lower()


async def test_admin_update_cog_reload_failure():
    """reload_extension raises for one cog → ❌ appears for that cog."""
    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()
    proc = _make_proc()

    from src.bot.main import COGS
    fail_cog = COGS[0] if COGS else "src.bot.cogs.admin"

    def reload_side_effect(name):
        if name == fail_cog:
            raise Exception("load error")

    interaction.client.reload_extension = AsyncMock(side_effect=reload_side_effect)

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc), \
         patch("asyncio.wait_for", new_callable=AsyncMock, return_value=(b"ok", None)):
        await cog.admin_update.callback(cog, interaction)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "❌" in sent_text


async def test_admin_update_sync_no_guild():
    """interaction.guild = None → global sync (no guild kwarg)."""
    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()
    interaction.guild = None
    proc = _make_proc()

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc), \
         patch("asyncio.wait_for", new_callable=AsyncMock, return_value=(b"ok", None)):
        await cog.admin_update.callback(cog, interaction)

    interaction.client.tree.sync.assert_awaited_once_with()
    sent_text = interaction.followup.send.call_args[0][0]
    assert "globally" in sent_text


async def test_admin_update_sync_http_exception():
    """HTTPException from tree.sync → ❌ Command sync failed in response."""
    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()
    proc = _make_proc()

    http_exc = discord.HTTPException(MagicMock(status=429), "Rate limited")
    http_exc.status = 429
    http_exc.text = "Rate limited"
    interaction.client.tree.sync = AsyncMock(side_effect=http_exc)

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc), \
         patch("asyncio.wait_for", new_callable=AsyncMock, return_value=(b"ok", None)):
        await cog.admin_update.callback(cog, interaction)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "❌" in sent_text
    assert "sync failed" in sent_text.lower()


async def test_admin_update_sync_general_exception():
    """General exception from tree.sync → ❌ Command sync failed in response."""
    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()
    proc = _make_proc()
    interaction.client.tree.sync = AsyncMock(side_effect=RuntimeError("unexpected"))

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc), \
         patch("asyncio.wait_for", new_callable=AsyncMock, return_value=(b"ok", None)):
        await cog.admin_update.callback(cog, interaction)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "❌" in sent_text


# ── _run_training ─────────────────────────────────────────────────────────────

async def test_run_training_blocking_preflight_aborts():
    """Blocking preflight issue → sends DM and returns without launching subprocess."""
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()

    blocking = [{"type": "SHOWDOWN_OFFLINE", "description": "server down", "fixable": False}]
    with patch("src.ml.training_doctor.preflight_check", return_value=blocking), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        await _run_training(interaction, "gen9ou", 100_000, channel_msg=None, force=False)

    mock_exec.assert_not_called()


async def test_run_training_fixable_preflight_applies_fix():
    """Fixable preflight issue → apply_all_fixes called before launching subprocess.
    Returns a non-empty list to cover the log.info line inside the for loop (line 418).
    """
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()

    fixable = [{"type": "CORRUPT_CHECKPOINT", "description": "bad ckpt", "fixable": True}]
    proc = _make_proc(returncode=0)
    # Return one result tuple so the for loop body (line 418) is executed
    fix_result = [(fixable[0], True, "checkpoint deleted")]

    with patch("src.ml.training_doctor.preflight_check", return_value=fixable), \
         patch("src.ml.training_doctor.apply_all_fixes", return_value=fix_result) as mock_fix, \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("src.ml.training_doctor.diagnose_output", return_value=[]), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training(interaction, "gen9ou", 100_000, channel_msg=None, force=False)

    mock_fix.assert_called_once()


async def test_run_training_success_sends_done_embed():
    """Subprocess returns 0 → user.send called with ✅ Training Complete embed.
    parse_timestep_progress returns a non-None value to cover line 482 (latest_steps = steps).
    """
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()
    proc = _make_proc(returncode=0, lines=[b"step 1000/100000\n"])

    with patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=1000), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training(interaction, "gen9ou", 100_000, channel_msg=None, force=False)

    interaction.user.send.assert_awaited()
    embed_arg = interaction.user.send.call_args[1].get("embed") or interaction.user.send.call_args[0][0] if interaction.user.send.call_args[0] else interaction.user.send.call_args[1]["embed"]
    assert "Complete" in embed_arg.title or "✅" in embed_arg.title


async def test_run_training_failure_unfixable_sends_fail_embed():
    """Both attempts fail with unfixable errors → fail embed sent."""
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()
    proc = _make_proc(returncode=1)

    unfixable = [{"type": "UNKNOWN", "description": "mystery", "fixable": False}]
    with patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("src.ml.training_doctor.diagnose_output", return_value=unfixable), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training(interaction, "gen9ou", 100_000, channel_msg=None, force=False)

    interaction.user.send.assert_awaited()
    embed_arg = interaction.user.send.call_args[1].get("embed")
    assert embed_arg is not None
    assert "Failed" in embed_arg.title or "❌" in embed_arg.title


async def test_run_training_failure_with_fixable_retries_and_succeeds():
    """First attempt fails with fixable errors → fix applied → second attempt succeeds."""
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()

    fail_proc = _make_proc(returncode=1)
    success_proc = _make_proc(returncode=0)
    procs = [fail_proc, success_proc]

    fixable = [{"type": "CORRUPT_CHECKPOINT", "description": "bad ckpt", "fixable": True}]
    with patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("src.ml.training_doctor.diagnose_output", return_value=fixable), \
         patch("src.ml.training_doctor.apply_all_fixes", return_value=[]) as mock_fix, \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, side_effect=procs):
        await _run_training(interaction, "gen9ou", 100_000, channel_msg=None, force=False)

    mock_fix.assert_called()
    # Last send should be success embed
    last_embed = interaction.user.send.call_args[1].get("embed")
    assert last_embed is not None
    assert "Complete" in last_embed.title or "✅" in last_embed.title


async def test_run_training_subprocess_exception_sends_fail_embed():
    """Subprocess raises exception → fail embed sent."""
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()

    unfixable = [{"type": "UNKNOWN", "description": "crash", "fixable": False}]
    with patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.diagnose_output", return_value=unfixable), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock,
               side_effect=OSError("exec failed")):
        await _run_training(interaction, "gen9ou", 100_000, channel_msg=None, force=False)

    interaction.user.send.assert_awaited()


# ── _run_training_all ─────────────────────────────────────────────────────────

async def test_run_training_all_no_formats_sends_summary():
    """All models exist → 0 formats queued → final summary DM sent."""
    from src.bot.cogs.admin import _run_training_all
    interaction = make_interaction()

    with patch("src.bot.cogs.admin._model_exists", return_value=True), \
         patch("src.ml.training_doctor.preflight_check", return_value=[]):
        await _run_training_all(interaction, 100_000, force=False)

    interaction.user.send.assert_awaited()


async def test_run_training_all_blocking_preflight_aborts():
    """Blocking preflight → returns early, no subprocess spawned."""
    from src.bot.cogs.admin import _run_training_all
    interaction = make_interaction()

    blocking = [{"type": "SHOWDOWN_OFFLINE", "description": "down", "fixable": False}]
    with patch("src.bot.cogs.admin._model_exists", return_value=False), \
         patch("src.ml.training_doctor.preflight_check", return_value=blocking), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        await _run_training_all(interaction, 100_000, force=False)

    mock_exec.assert_not_called()


async def test_run_training_all_one_format_success():
    """One format runs successfully → n_done=1, summary sent with ✅."""
    from src.bot.cogs.admin import _run_training_all
    from src.ml.train_all import TRAINING_MAP

    interaction = make_interaction()
    one_fmt = next(iter(TRAINING_MAP))
    proc = _make_proc(returncode=0)

    def model_exists_fn(results_dir, fmt):
        # only the first format lacks a model
        return fmt != one_fmt

    with patch("src.bot.cogs.admin._model_exists", side_effect=model_exists_fn), \
         patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training_all(interaction, 100_000, force=False)

    interaction.user.send.assert_awaited()
    # At least two sends: startup DM + summary
    assert interaction.user.send.await_count >= 2


async def test_run_training_all_failure_applies_fix():
    """Format fails → diagnose finds fixable error → apply_all_fixes called."""
    from src.bot.cogs.admin import _run_training_all
    from src.ml.train_all import TRAINING_MAP

    interaction = make_interaction()
    one_fmt = next(iter(TRAINING_MAP))
    proc = _make_proc(returncode=1)

    fixable = [{"type": "CORRUPT_CHECKPOINT", "description": "bad", "fixable": True}]

    def model_exists_fn(results_dir, fmt):
        return fmt != one_fmt

    with patch("src.bot.cogs.admin._model_exists", side_effect=model_exists_fn), \
         patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("src.ml.training_doctor.diagnose_output", return_value=fixable), \
         patch("src.ml.training_doctor.apply_all_fixes", return_value=[]) as mock_fix, \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training_all(interaction, 100_000, force=False)

    mock_fix.assert_called()


# ── _pull_models ──────────────────────────────────────────────────────────────

async def test_pull_models_latest_release_fetched_by_id():
    """When no specific tag, the first ml-models-r* release is fetched by its numeric ID (line 895)."""
    from src.bot.cogs.admin import _pull_models
    from src.config import settings

    interaction = make_interaction()

    list_resp = MagicMock()
    list_resp.raise_for_status = MagicMock()
    list_resp.json = MagicMock(return_value=[
        {"tag_name": "ml-models-r1", "id": 999},
    ])

    release_detail_resp = MagicMock()
    release_detail_resp.raise_for_status = MagicMock()
    release_detail_resp.json = MagicMock(return_value={
        "tag_name": "ml-models-r1",
        "assets": [],
    })

    mock_client = AsyncMock()
    # First call → list releases; second call → fetch by id (line 895)
    mock_client.get = AsyncMock(side_effect=[list_resp, release_detail_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch.object(settings, "github_repo", "owner/repo", create=True), \
         patch.object(settings, "github_token", None, create=True), \
         patch("pathlib.Path.mkdir"):
        await _pull_models(interaction, fmt=None, release_tag=None)

    # Two GET calls: list releases + fetch by id
    assert mock_client.get.await_count == 2
    second_url = mock_client.get.call_args_list[1][0][0]
    assert "999" in second_url


async def test_pull_models_download_exception_recorded():
    """Individual asset download failure is recorded as ❌ in results (lines 921-922)."""
    from src.bot.cogs.admin import _pull_models
    from src.config import settings

    interaction = make_interaction()
    fmt = "gen9randombattle"

    list_resp = MagicMock()
    list_resp.raise_for_status = MagicMock()
    list_resp.json = MagicMock(return_value=[{"tag_name": "ml-models-r1", "id": 1}])

    release_resp = MagicMock()
    release_resp.raise_for_status = MagicMock()
    release_resp.json = MagicMock(return_value={
        "tag_name": "ml-models-r1",
        "assets": [{"name": f"{fmt}_final_model.zip", "browser_download_url": "https://example.com/model.zip"}],
    })

    boom_resp = MagicMock()
    boom_resp.raise_for_status = MagicMock(side_effect=Exception("connection reset"))

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[list_resp, release_resp, boom_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch.object(settings, "github_repo", "owner/repo", create=True), \
         patch.object(settings, "github_token", None, create=True), \
         patch("pathlib.Path.mkdir"):
        await _pull_models(interaction, fmt=fmt, release_tag=None)

    # followup.send(embed=embed, ephemeral=True) — check the embed's description
    send_kwargs = interaction.followup.send.call_args[1]
    embed = send_kwargs["embed"]
    assert "❌" in embed.description


# ── TeamCog command handlers ───────────────────────────────────────────────────

async def test_team_cog_team_no_roster():
    """team command with no roster → ephemeral 'no team yet' message."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()
    cog.team_service.get_team = AsyncMock(return_value=None)

    interaction = make_interaction()
    await cog.team.callback(cog, interaction, user=None)

    interaction.response.defer.assert_awaited_once()
    sent_text = interaction.followup.send.call_args[0][0]
    assert "no team" in sent_text.lower()


async def test_team_cog_team_with_roster():
    """team command with roster → embed+view sent."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()

    mock_roster = [MagicMock()]
    cog.team_service.get_team = AsyncMock(return_value=mock_roster)

    interaction = make_interaction()
    with patch("src.bot.cogs.team.TeamEmbedView") as MockView:
        mock_view = MagicMock()
        mock_view.build_embed.return_value = MagicMock()
        MockView.return_value = mock_view
        await cog.team.callback(cog, interaction, user=None)

    interaction.followup.send.assert_awaited_once()
    call_kwargs = interaction.followup.send.call_args[1]
    assert "embed" in call_kwargs
    assert "view" in call_kwargs


async def test_team_cog_team_register_invalid_content_type():
    """logo with wrong MIME type → immediate error, no defer."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)

    logo = MagicMock()
    logo.content_type = "application/pdf"
    logo.size = 1024

    interaction = make_interaction()
    await cog.team_register.callback(cog, interaction, team_name="TestTeam", pool="A", logo=logo)

    interaction.response.send_message.assert_awaited_once()
    err_text = interaction.response.send_message.call_args[0][0]
    assert "PNG" in err_text or "JPG" in err_text or "❌" in err_text


async def test_team_cog_team_register_logo_too_large():
    """logo > 8 MB → immediate error."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)

    logo = MagicMock()
    logo.content_type = "image/png"
    logo.size = 9 * 1024 * 1024  # 9 MB

    interaction = make_interaction()
    await cog.team_register.callback(cog, interaction, team_name="TestTeam", pool="A", logo=logo)

    err_text = interaction.response.send_message.call_args[0][0]
    assert "8 MB" in err_text or "❌" in err_text


async def test_team_cog_team_register_no_logo():
    """team_register without logo → registers, sends ephemeral + public embed."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()
    cog.team_service.register_team = AsyncMock()

    interaction = make_interaction()
    await cog.team_register.callback(cog, interaction, team_name="TestTeam", pool="A", logo=None)

    interaction.response.defer.assert_awaited_once()
    cog.team_service.register_team.assert_awaited_once()
    interaction.followup.send.assert_awaited_once()
    # Public channel announcement
    interaction.channel.send.assert_awaited_once()


async def test_team_cog_trade_success():
    """trade success → embed with offer/request names sent."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()

    result = MagicMock()
    result.success = True
    result.trade_id = "trade-001"
    cog.team_service.propose_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    target = MagicMock()
    target.id = "9999"
    target.mention = "<@9999>"
    target.send = AsyncMock()

    await cog.trade.callback(cog, interaction, target=target, offer="Garchomp", request="Tyranitar")

    interaction.followup.send.assert_awaited_once()
    embed = interaction.followup.send.call_args[1]["embed"]
    assert "Garchomp" in embed.description
    assert "Tyranitar" in embed.description


async def test_team_cog_trade_success_dm_forbidden():
    """trade success but DM to target raises Forbidden → no crash."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()

    result = MagicMock()
    result.success = True
    result.trade_id = "trade-002"
    cog.team_service.propose_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    target = MagicMock()
    target.id = "9999"
    target.mention = "<@9999>"
    target.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "blocked"))

    await cog.trade.callback(cog, interaction, target=target, offer="Garchomp", request="Tyranitar")

    # embed still sent to channel
    interaction.followup.send.assert_awaited_once()


async def test_team_cog_trade_failure():
    """trade failure → error followup."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()

    result = MagicMock()
    result.success = False
    result.error = "No such Pokemon in your pool"
    cog.team_service.propose_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    target = MagicMock()
    target.id = "9999"
    target.mention = "<@9999>"

    await cog.trade.callback(cog, interaction, target=target, offer="Pikachu", request="Raichu")

    sent_text = interaction.followup.send.call_args[0][0]
    assert "failed" in sent_text.lower() or "error" in sent_text.lower()


async def test_team_cog_trade_accept_success():
    """trade_accept success → ✅ message."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()

    result = MagicMock()
    result.success = True
    result.summary = "Garchomp → Tyranitar"
    cog.team_service.accept_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.trade_accept.callback(cog, interaction, trade_id="trade-001")

    sent_text = interaction.followup.send.call_args[0][0]
    assert "✅" in sent_text


async def test_team_cog_trade_accept_failure():
    """trade_accept failure → ❌ error message."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()

    result = MagicMock()
    result.success = False
    result.error = "Trade not found"
    cog.team_service.accept_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.trade_accept.callback(cog, interaction, trade_id="bad-id")

    sent_text = interaction.followup.send.call_args[0][0]
    assert "❌" in sent_text


async def test_team_cog_trade_decline_success():
    """trade_decline success → 'declined' message."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()

    result = MagicMock()
    result.success = True
    cog.team_service.decline_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.trade_decline.callback(cog, interaction, trade_id="trade-001")

    sent_text = interaction.followup.send.call_args[0][0]
    assert "declined" in sent_text.lower() or "trade-001" in sent_text


async def test_team_cog_trade_decline_failure():
    """trade_decline failure → ❌ error message."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()

    result = MagicMock()
    result.success = False
    result.error = "Not your trade"
    cog.team_service.decline_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.trade_decline.callback(cog, interaction, trade_id="bad-id")

    sent_text = interaction.followup.send.call_args[0][0]
    assert "❌" in sent_text


async def test_team_cog_teamimport_non_txt():
    """teamimport with non-.txt attachment → immediate error response."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)

    attachment = MagicMock()
    attachment.filename = "team.json"
    attachment.read = AsyncMock(return_value=b"...")

    interaction = make_interaction()
    await cog.teamimport.callback(cog, interaction, format="gen9ou", team_file=attachment)

    interaction.response.send_message.assert_awaited_once()
    err_text = interaction.response.send_message.call_args[0][0]
    assert ".txt" in err_text


async def test_team_cog_teamimport_empty_file():
    """teamimport with empty .txt → 'empty' error."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)

    attachment = MagicMock()
    attachment.filename = "team.txt"
    attachment.read = AsyncMock(return_value=b"   ")

    interaction = make_interaction()
    await cog.teamimport.callback(cog, interaction, format="gen9ou", team_file=attachment)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "empty" in sent_text.lower()


async def test_team_cog_teamimport_valid():
    """teamimport with valid team .txt → confirmation embed+view sent."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()

    showdown_text = (
        "Garchomp @ Choice Scarf\n"
        "Ability: Rough Skin\n"
        "EVs: 252 Atk / 4 SpD / 252 Spe\n"
        "Jolly Nature\n"
        "- Earthquake\n"
        "- Dragon Claw\n"
    )
    attachment = MagicMock()
    attachment.filename = "team.txt"
    attachment.read = AsyncMock(return_value=showdown_text.encode())

    interaction = make_interaction()
    with patch("src.bot.cogs.team.TeamImportConfirmView") as MockView, \
         patch("src.bot.cogs.team.build_confirm_embed") as mock_embed:
        mock_embed.return_value = MagicMock()
        MockView.return_value = MagicMock()
        await cog.teamimport.callback(cog, interaction, format="gen9ou", team_file=attachment)

    interaction.followup.send.assert_awaited_once()
    call_kwargs = interaction.followup.send.call_args[1]
    assert "embed" in call_kwargs
    assert "view" in call_kwargs


async def test_teamimport_format_autocomplete_matches():
    """Autocomplete returns matching format choices for a prefix."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    interaction = make_interaction()

    choices = await cog.teamimport_format_autocomplete(interaction, "gen9")

    assert len(choices) > 0
    for c in choices:
        assert "gen9" in c.value.lower() or "gen9" in c.name.lower()


async def test_teamimport_format_autocomplete_empty_returns_all():
    """Empty current string returns up to 25 choices."""
    from src.bot.cogs.team import TeamCog
    from src.bot.constants import SUPPORTED_FORMATS
    bot = MagicMock()
    cog = TeamCog(bot)
    interaction = make_interaction()

    choices = await cog.teamimport_format_autocomplete(interaction, "")
    assert len(choices) == min(len(SUPPORTED_FORMATS), 25)


async def test_team_cog_teamexport():
    """teamexport calls export_showdown and sends result in code block."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()
    cog.team_service.export_showdown = AsyncMock(return_value="Garchomp @ Choice Scarf\n...")

    interaction = make_interaction()
    await cog.teamexport.callback(cog, interaction)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "Garchomp" in sent_text
    assert "```" in sent_text


async def test_team_cog_legality_legal():
    """legality legal → green embed."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()

    result = MagicMock()
    result.legal = True
    result.reason = "Fully legal in SV."
    cog.team_service.check_legality = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.legality.callback(cog, interaction, pokemon="Garchomp", game="sv")

    embed = interaction.followup.send.call_args[1]["embed"]
    assert embed.color == discord.Color.green()


async def test_team_cog_legality_illegal():
    """legality illegal → red embed."""
    from src.bot.cogs.team import TeamCog
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()

    result = MagicMock()
    result.legal = False
    result.reason = "Not available in SV Dex."
    cog.team_service.check_legality = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.legality.callback(cog, interaction, pokemon="Mewtwo", game="sv")

    embed = interaction.followup.send.call_args[1]["embed"]
    assert embed.color == discord.Color.red()


async def test_team_cog_setup_adds_cog():
    """setup() registers TeamCog to the bot."""
    bot = MagicMock()
    bot.add_cog = AsyncMock()
    from src.bot.cogs.team import setup
    await setup(bot)
    bot.add_cog.assert_awaited_once()
    from src.bot.cogs.team import TeamCog
    assert isinstance(bot.add_cog.call_args[0][0], TeamCog)


# ── is_commissioner predicate (lines 24-26) ───────────────────────────────────

async def test_is_commissioner_predicate_with_manage_guild_returns_true():
    """Lines 24-25: predicate returns True when user has manage_guild permission."""
    from src.bot.cogs.admin import is_commissioner

    # The predicate is stored in the closure of the check decorator
    check_decorator = is_commissioner()
    predicate = check_decorator.__closure__[0].cell_contents

    interaction = make_interaction()
    interaction.user.guild_permissions.manage_guild = True

    result = await predicate(interaction)
    assert result is True


async def test_is_commissioner_predicate_without_manage_guild_raises():
    """Line 26: predicate raises CheckFailure when user lacks permission."""
    from src.bot.cogs.admin import is_commissioner
    from discord import app_commands

    check_decorator = is_commissioner()
    predicate = check_decorator.__closure__[0].cell_contents

    interaction = make_interaction()
    interaction.user.guild_permissions.manage_guild = False

    try:
        await predicate(interaction)
        assert False, "Expected CheckFailure to be raised"
    except app_commands.CheckFailure:
        pass


# ── _run_training: additional branch coverage ──────────────────────────────────

async def test_run_training_invalid_fmt_sends_dm():
    """Lines 401-402: unknown format sends DM and returns early."""
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        await _run_training(interaction, "totally_invalid_format_xyz", 100_000, force=False)

    interaction.user.send.assert_awaited_once()
    sent_text = interaction.user.send.call_args[0][0]
    assert "Unknown format" in sent_text
    mock_exec.assert_not_called()


async def test_run_training_fixable_preflight_dm_send_raises():
    """Lines 415-416: DM send exception for fixable issues is silently swallowed."""
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()
    # Make the DM send raise on first call (fixable notify), succeed after
    proc = _make_proc(returncode=0)
    interaction.user.send = AsyncMock(
        side_effect=[Exception("DM blocked"), None]
    )

    fixable = [{"type": "CORRUPT_CHECKPOINT", "description": "bad ckpt", "fixable": True}]
    with patch("src.ml.training_doctor.preflight_check", return_value=fixable), \
         patch("src.ml.training_doctor.apply_all_fixes", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("src.ml.training_doctor.diagnose_output", return_value=[]), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        # Should not raise even though DM failed
        await _run_training(interaction, "gen9ou", 100_000, force=False)


async def test_run_training_blocking_dm_send_raises():
    """Lines 433-434: DM send exception for blocking issues is silently swallowed."""
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()
    interaction.user.send = AsyncMock(side_effect=Exception("DM blocked"))

    blocking = [{"type": "SHOWDOWN_OFFLINE", "description": "server down", "fixable": False}]
    channel_msg = MagicMock()
    channel_msg.edit = AsyncMock()

    with patch("src.ml.training_doctor.preflight_check", return_value=blocking), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        await _run_training(interaction, "gen9ou", 100_000, force=False, channel_msg=channel_msg)

    mock_exec.assert_not_called()


async def test_run_training_user_send_raises_for_dm_msg():
    """Lines 451-452: dm_msg is None when interaction.user.send raises for initial DM."""
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()
    proc = _make_proc(returncode=0)
    # First call (initial progress DM) raises; subsequent calls (success embed) succeed
    call_count = {"n": 0}

    async def send_side_effect(*args, **kwargs):
        n = call_count["n"]
        call_count["n"] += 1
        if n == 0:
            raise Exception("DM blocked")
        return MagicMock()

    interaction.user.send = AsyncMock(side_effect=send_side_effect)

    with patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        # Must complete without raising even though dm_msg is None
        await _run_training(interaction, "gen9ou", 100_000, force=False)


async def test_run_training_force_and_server_flags():
    """Lines 460, 462: force=True and non-localhost server add flags to cmd."""
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()
    proc = _make_proc(returncode=0)
    captured_cmds = []

    async def fake_exec(*cmd, **kwargs):
        captured_cmds.append(list(cmd))
        return proc

    with patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        await _run_training(
            interaction, "gen9ou", 100_000,
            force=True, server="showdown",
        )

    assert len(captured_cmds) == 1
    cmd = captured_cmds[0]
    assert "--force" in cmd
    assert "--server" in cmd
    assert "showdown" in cmd


async def test_run_training_success_dm_send_raises():
    """Lines 514-515: success embed DM exception is silently swallowed."""
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()
    proc = _make_proc(returncode=0)
    # Initial DM send succeeds; success embed send raises
    call_count = {"n": 0}

    async def send_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] > 1:
            raise Exception("DM blocked")
        return MagicMock()

    interaction.user.send = AsyncMock(side_effect=send_side_effect)

    with patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training(interaction, "gen9ou", 100_000, force=False)


async def test_run_training_failure_no_diagnosed_errors_uses_unknown():
    """Line 521: When diagnose_output returns [], uses UNKNOWN error."""
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()
    proc = _make_proc(returncode=1)

    with patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("src.ml.training_doctor.diagnose_output", return_value=[]), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training(interaction, "gen9ou", 100_000, force=False)

    # Should still send a fail embed
    interaction.user.send.assert_awaited()
    embed_arg = interaction.user.send.call_args[1].get("embed")
    assert embed_arg is not None


async def test_run_training_retry_dm_send_raises():
    """Lines 537-538: retry notification DM exception is silently swallowed."""
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()

    fail_proc = _make_proc(returncode=1)
    success_proc = _make_proc(returncode=0)
    procs = [fail_proc, success_proc]

    fixable = [{"type": "CORRUPT_CHECKPOINT", "description": "bad ckpt", "fixable": True}]

    # First two calls succeed (initial DM + retry DM raises), final call (success embed) succeeds
    call_count = {"n": 0}

    async def send_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise Exception("DM blocked")
        return MagicMock()

    interaction.user.send = AsyncMock(side_effect=send_side_effect)

    with patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("src.ml.training_doctor.diagnose_output", return_value=fixable), \
         patch("src.ml.training_doctor.apply_all_fixes", return_value=[]), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, side_effect=procs):
        await _run_training(interaction, "gen9ou", 100_000, force=False)


async def test_run_training_final_fail_dm_send_raises():
    """Lines 556-557: final failure DM exception is silently swallowed."""
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()
    proc = _make_proc(returncode=1)

    unfixable = [{"type": "UNKNOWN", "description": "crash", "fixable": False}]

    # Make all user.send calls raise
    interaction.user.send = AsyncMock(side_effect=Exception("DM blocked"))

    with patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("src.ml.training_doctor.diagnose_output", return_value=unfixable), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        # Should complete without raising
        await _run_training(interaction, "gen9ou", 100_000, force=False)


async def test_run_training_progress_update_when_time_elapsed():
    """Lines 487-490: progress embed is edited when 60s have elapsed."""
    from src.bot.cogs.admin import _run_training
    interaction = make_interaction()
    proc = _make_proc(returncode=0, lines=[b"step 1000\n"])

    channel_msg = MagicMock()
    channel_msg.edit = AsyncMock()

    # Mock event loop time so 'now - last_edit_time >= 60' is True on first line
    mock_loop = MagicMock()
    # First call = last_edit_time (0), second call = now (61)
    mock_loop.time = MagicMock(side_effect=[0, 61])

    with patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("asyncio.get_event_loop", return_value=mock_loop), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training(
            interaction, "gen9ou", 100_000,
            force=False, channel_msg=channel_msg,
        )

    # _try_edit should have been called on channel_msg (in addition to the success path)
    channel_msg.edit.assert_awaited()


# ── _run_training_all: additional branch coverage ─────────────────────────────

async def test_run_training_all_blocking_dm_send_raises():
    """Lines 605-606: DM exception for blocking preflight is silently swallowed."""
    from src.bot.cogs.admin import _run_training_all
    interaction = make_interaction()
    interaction.user.send = AsyncMock(side_effect=Exception("DM blocked"))

    blocking = [{"type": "SHOWDOWN_OFFLINE", "description": "down", "fixable": False}]
    with patch("src.bot.cogs.admin._model_exists", return_value=False), \
         patch("src.ml.training_doctor.preflight_check", return_value=blocking), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        await _run_training_all(interaction, 100_000, force=False)

    mock_exec.assert_not_called()


async def test_run_training_all_startup_dm_raises():
    """Lines 615-616: startup DM exception is silently swallowed."""
    from src.bot.cogs.admin import _run_training_all

    interaction = make_interaction()
    # All models already exist → 0 formats queued → goes straight to summary
    # Startup DM send raises (line 610-616 block)
    call_count = {"n": 0}

    async def send_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise Exception("DM blocked")
        return MagicMock()

    interaction.user.send = AsyncMock(side_effect=send_side_effect)

    with patch("src.bot.cogs.admin._model_exists", return_value=True), \
         patch("src.ml.training_doctor.preflight_check", return_value=[]):
        # Should complete without raising
        await _run_training_all(interaction, 100_000, force=False)


async def test_run_training_all_force_and_server_flags():
    """Lines 630, 632: force=True and non-localhost server add flags to cmd.

    With force=True, _model_exists is skipped (all formats run). We use a
    small TRAINING_MAP with only one entry to keep the test fast — the key
    assertion is that --force and --server flags appear in every cmd.
    """
    from src.bot.cogs.admin import _run_training_all
    from src.ml.train_all import TRAINING_MAP

    interaction = make_interaction()
    one_fmt = next(iter(TRAINING_MAP))
    proc = _make_proc(returncode=0)
    captured_cmds = []

    async def fake_exec(*cmd, **kwargs):
        captured_cmds.append(list(cmd))
        return proc

    # Limit TRAINING_MAP to one entry so only one subprocess is spawned
    single_entry = {one_fmt: TRAINING_MAP[one_fmt]}
    with patch("src.bot.cogs.admin.TRAINING_MAP", single_entry), \
         patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        await _run_training_all(
            interaction, 100_000,
            force=True, server="showdown",
        )

    assert len(captured_cmds) == 1
    cmd = captured_cmds[0]
    assert "--force" in cmd
    assert "--server" in cmd
    assert "showdown" in cmd


async def test_run_training_all_progress_dm_raises():
    """Lines 646-647: initial per-format DM exception sets dm_msg=None."""
    from src.bot.cogs.admin import _run_training_all
    from src.ml.train_all import TRAINING_MAP

    interaction = make_interaction()
    one_fmt = next(iter(TRAINING_MAP))
    proc = _make_proc(returncode=0)

    # First send = startup DM (succeeds), second send = per-format DM (raises),
    # third send = summary DM (succeeds)
    call_count = {"n": 0}

    async def send_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise Exception("DM blocked")
        return MagicMock()

    interaction.user.send = AsyncMock(side_effect=send_side_effect)

    def model_exists_fn(results_dir, fmt):
        return fmt != one_fmt

    with patch("src.bot.cogs.admin._model_exists", side_effect=model_exists_fn), \
         patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training_all(interaction, 100_000, force=False)


async def test_run_training_all_subprocess_streaming_lines():
    """Lines 660-673: async for loop processes stdout lines and updates progress.
    parse_timestep_progress returns a non-None value to cover line 664 (latest_steps = steps).
    """
    from src.bot.cogs.admin import _run_training_all
    from src.ml.train_all import TRAINING_MAP

    interaction = make_interaction()
    one_fmt = next(iter(TRAINING_MAP))
    # Provide some lines to stream through the async for loop
    proc = _make_proc(returncode=0, lines=[b"step 500\n", b"step 1000\n"])

    def model_exists_fn(results_dir, fmt):
        return fmt != one_fmt

    with patch("src.bot.cogs.admin._model_exists", side_effect=model_exists_fn), \
         patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=500), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training_all(interaction, 100_000, force=False)

    interaction.user.send.assert_awaited()


async def test_run_training_all_subprocess_exception_continues():
    """Lines 678-681: subprocess exception is caught, ok=False, loop continues."""
    from src.bot.cogs.admin import _run_training_all
    from src.ml.train_all import TRAINING_MAP

    interaction = make_interaction()
    one_fmt = next(iter(TRAINING_MAP))

    def model_exists_fn(results_dir, fmt):
        return fmt != one_fmt

    with patch("src.bot.cogs.admin._model_exists", side_effect=model_exists_fn), \
         patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("src.ml.training_doctor.diagnose_output", return_value=[]), \
         patch("asyncio.create_subprocess_exec",
               new_callable=AsyncMock, side_effect=OSError("exec failed")):
        # Should complete with n_failed=1 and still send summary
        await _run_training_all(interaction, 100_000, force=False)

    interaction.user.send.assert_awaited()


async def test_run_training_all_summary_dm_raises():
    """Lines 726-727: summary DM exception is logged, not re-raised."""
    from src.bot.cogs.admin import _run_training_all

    interaction = make_interaction()
    # All models exist → 0 formats → goes straight to summary
    # Make summary send (last call) raise
    call_count = {"n": 0}

    async def send_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise Exception("DM blocked")
        return MagicMock()

    interaction.user.send = AsyncMock(side_effect=send_side_effect)

    with patch("src.bot.cogs.admin._model_exists", return_value=True), \
         patch("src.ml.training_doctor.preflight_check", return_value=[]):
        # Should complete without re-raising
        await _run_training_all(interaction, 100_000, force=False)


async def test_run_training_all_progress_update_when_time_elapsed():
    """Lines 666-673: progress embed is edited when 60s elapsed during streaming."""
    from src.bot.cogs.admin import _run_training_all
    from src.ml.train_all import TRAINING_MAP

    interaction = make_interaction()
    one_fmt = next(iter(TRAINING_MAP))
    proc = _make_proc(returncode=0, lines=[b"step 500\n"])
    channel_msg = MagicMock()
    channel_msg.edit = AsyncMock()

    # Mock time so the 60s check triggers
    mock_loop = MagicMock()
    mock_loop.time = MagicMock(side_effect=[0, 61])

    def model_exists_fn(results_dir, fmt):
        return fmt != one_fmt

    with patch("src.bot.cogs.admin._model_exists", side_effect=model_exists_fn), \
         patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("asyncio.get_event_loop", return_value=mock_loop), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training_all(
            interaction, 100_000,
            force=False, channel_msg=channel_msg,
        )


# ── admin_pull_models command ─────────────────────────────────────────────────

async def test_admin_pull_models_defers_and_creates_task():
    """Lines 315-316: command defers interaction and creates background task."""
    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()

    with patch("asyncio.create_task") as mock_create_task:
        await cog.admin_pull_models.callback(cog, interaction, format=None, release=None)

    interaction.response.defer.assert_awaited_once_with(thinking=True, ephemeral=True)
    mock_create_task.assert_called_once()


async def test_admin_pull_models_format_autocomplete_filters():
    """Lines 326-327: autocomplete filters TRAINING_MAP by current prefix."""
    from src.ml.train_all import TRAINING_MAP
    bot = MagicMock()
    cog = AdminCog(bot)
    interaction = make_interaction()

    # Patch TRAINING_MAP to two known entries
    fake_map = {"gen9ou": ..., "gen9randombattle": ...}
    with patch("src.bot.cogs.admin.TRAINING_MAP", fake_map):
        choices = await cog.admin_pull_models_format_autocomplete(
            interaction, current="gen9o"
        )

    assert len(choices) == 1
    assert choices[0].value == "gen9ou"


# ── _run_training: proc.stdout=None branch ────────────────────────────────────

async def test_run_training_proc_stdout_none_sends_fail_embed():
    """Line 510: RuntimeError when proc.stdout is None is caught by outer except."""
    from src.bot.cogs.admin import _run_training

    interaction = make_interaction()
    proc = _make_proc(returncode=0)
    proc.stdout = None   # triggers RuntimeError("subprocess stdout pipe is None")

    with patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training(interaction, "gen9ou", 100_000, force=False)

    # The subprocess exception path ends with a fail DM
    interaction.user.send.assert_awaited()


# ── _run_training: 60s time throttle (asyncio.get_running_loop) ───────────────

async def test_run_training_time_throttle_edits_progress():
    """Lines 521-525: progress embed is edited when get_running_loop().time() >= 60s."""
    from src.bot.cogs.admin import _run_training

    interaction = make_interaction()
    proc = _make_proc(returncode=0, lines=[b"step 1000\n"])
    channel_msg = MagicMock()
    channel_msg.edit = AsyncMock()

    mock_loop = MagicMock()
    # First call → last_edit_time=0, second call → now=61  (triggers throttle)
    mock_loop.time = MagicMock(side_effect=[0, 61])

    with patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("asyncio.get_running_loop", return_value=mock_loop), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training(
            interaction, "gen9ou", 100_000,
            force=False, channel_msg=channel_msg,
        )

    channel_msg.edit.assert_awaited()


# ── _run_training_all: proc.stdout=None branch ───────────────────────────────

async def test_run_training_all_proc_stdout_none_continues():
    """Line 694: RuntimeError when proc.stdout is None is caught; training continues."""
    from src.bot.cogs.admin import _run_training_all
    from src.ml.train_all import TRAINING_MAP

    interaction = make_interaction()
    one_fmt = next(iter(TRAINING_MAP))
    proc = _make_proc(returncode=0)
    proc.stdout = None   # triggers RuntimeError("subprocess stdout pipe is None")

    def model_exists_fn(results_dir, fmt):
        return fmt != one_fmt  # only one format needs training

    with patch("src.bot.cogs.admin._model_exists", side_effect=model_exists_fn), \
         patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training_all(interaction, 100_000, force=False)

    # Should complete (exception caught internally) and send summary DM
    interaction.user.send.assert_awaited()


# ── _run_training_all: 60s time throttle (asyncio.get_running_loop) ──────────

async def test_run_training_all_time_throttle_edits_progress():
    """Lines 702-709: queue embed is edited when get_running_loop().time() >= 60s."""
    from src.bot.cogs.admin import _run_training_all
    from src.ml.train_all import TRAINING_MAP

    interaction = make_interaction()
    one_fmt = next(iter(TRAINING_MAP))
    proc = _make_proc(returncode=0, lines=[b"step 500\n"])
    channel_msg = MagicMock()
    channel_msg.edit = AsyncMock()

    mock_loop = MagicMock()
    mock_loop.time = MagicMock(side_effect=[0, 61])

    def model_exists_fn(results_dir, fmt):
        return fmt != one_fmt

    with patch("src.bot.cogs.admin._model_exists", side_effect=model_exists_fn), \
         patch("src.ml.training_doctor.preflight_check", return_value=[]), \
         patch("src.ml.training_doctor.parse_timestep_progress", return_value=None), \
         patch("asyncio.get_running_loop", return_value=mock_loop), \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
        await _run_training_all(
            interaction, 100_000,
            force=False, channel_msg=channel_msg,
        )

    channel_msg.edit.assert_awaited()


# ── _pull_models: GitHub API paths ───────────────────────────────────────────

async def test_pull_models_with_specific_release_downloads_asset():
    """Lines 878-922: direct release_tag path downloads matching asset."""
    from src.bot.cogs.admin import _pull_models

    interaction = make_interaction()

    mock_release = {
        "tag_name": "ml-models-r1",
        "assets": [
            {
                "name": "gen9ou_final_model.zip",
                "browser_download_url": "https://example.com/gen9ou.zip",
            }
        ],
    }
    release_resp = MagicMock()
    release_resp.raise_for_status = MagicMock()
    release_resp.json.return_value = mock_release

    dl_resp = MagicMock()
    dl_resp.raise_for_status = MagicMock()
    dl_resp.content = b"fake model bytes"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[release_resp, dl_resp])

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_ctx), \
         patch("src.config.settings") as ms, \
         patch("pathlib.Path.mkdir"), \
         patch("pathlib.Path.write_bytes"):
        ms.github_repo = "test/repo"
        ms.github_token = ""
        await _pull_models(interaction, fmt="gen9ou", release_tag="ml-models-r1")

    interaction.followup.send.assert_awaited_once()


async def test_pull_models_latest_release_no_ml_release_sends_message():
    """Lines 888-894: when no ml-models-r* release exists, followup message is sent."""
    from src.bot.cogs.admin import _pull_models

    interaction = make_interaction()

    releases_resp = MagicMock()
    releases_resp.raise_for_status = MagicMock()
    releases_resp.json.return_value = [
        {"tag_name": "v1.0", "id": 1},
        {"tag_name": "other-release", "id": 2},
    ]

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=releases_resp)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_ctx), \
         patch("src.config.settings") as ms:
        ms.github_repo = "test/repo"
        ms.github_token = "tok"
        await _pull_models(interaction, fmt=None, release_tag=None)

    interaction.followup.send.assert_awaited_once()
    call_kwargs = interaction.followup.send.call_args
    assert "No" in call_kwargs.args[0]


async def test_pull_models_asset_not_in_release_marks_not_found():
    """Line 910: asset missing from release → result marked 'not in release'."""
    from src.bot.cogs.admin import _pull_models

    interaction = make_interaction()

    mock_release = {"tag_name": "ml-models-r2", "assets": []}  # no assets
    release_resp = MagicMock()
    release_resp.raise_for_status = MagicMock()
    release_resp.json.return_value = mock_release

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=release_resp)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_ctx), \
         patch("src.config.settings") as ms:
        ms.github_repo = "test/repo"
        ms.github_token = ""
        await _pull_models(interaction, fmt="gen9ou", release_tag="ml-models-r2")

    interaction.followup.send.assert_awaited_once()
    embed_arg = interaction.followup.send.call_args.kwargs.get("embed")
    assert embed_arg is not None
    assert "not in release" in embed_arg.description


async def test_pull_models_github_api_error_sends_error_message():
    """Lines 924-926: httpx error → followup error message, no embed."""
    from src.bot.cogs.admin import _pull_models

    interaction = make_interaction()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("network failure"))

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_ctx), \
         patch("src.config.settings") as ms:
        ms.github_repo = "test/repo"
        ms.github_token = ""
        await _pull_models(interaction, fmt=None, release_tag="ml-models-r1")

    call_args = interaction.followup.send.call_args
    assert "GitHub API error" in call_args.args[0]
