"""
Tests for src/bot/cogs/team.py — 100% coverage of all command handlers,
ShowdownImportModal, autocomplete, and setup().
"""
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from src.bot.cogs.team import (
    ShowdownImportModal,
    TeamCog,
    setup,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def make_interaction(guild_id="1234", user_id="5678"):
    """Build a minimal mock discord.Interaction."""
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
    interaction.channel = MagicMock()
    interaction.channel.send = AsyncMock()
    return interaction


def make_cog():
    """Build a TeamCog with mocked services."""
    bot = MagicMock()
    with patch("src.bot.cogs.team.TeamService"), \
         patch("src.bot.cogs.team.AnalyticsService"):
        cog = TeamCog(bot)
    cog.team_service = MagicMock()
    cog.analytics = MagicMock()
    return cog


# ── /team ─────────────────────────────────────────────────────────────────────

async def test_team_cmd_no_roster_sends_no_team_message():
    """/team: empty roster → ephemeral 'no team yet' message."""
    cog = make_cog()
    cog.team_service.get_team = AsyncMock(return_value=None)

    interaction = make_interaction()
    target_user = MagicMock()
    target_user.id = "9999"
    target_user.display_name = "OtherPlayer"

    await cog.team.callback(cog, interaction, user=target_user)

    interaction.response.defer.assert_awaited_once()
    sent_text = interaction.followup.send.call_args[0][0]
    assert "no team" in sent_text.lower()


async def test_team_cmd_with_roster_sends_embed():
    """/team: non-empty roster → embed sent."""
    cog = make_cog()
    roster = [MagicMock()]
    cog.team_service.get_team = AsyncMock(return_value=roster)

    interaction = make_interaction()

    mock_view = MagicMock()
    mock_embed = MagicMock()
    mock_view.build_embed.return_value = mock_embed

    with patch("src.bot.cogs.team.TeamEmbedView", return_value=mock_view):
        await cog.team.callback(cog, interaction, user=None)

    interaction.followup.send.assert_awaited_once_with(embed=mock_embed, view=mock_view)


async def test_team_cmd_defaults_to_self_when_user_is_none():
    """/team with no user arg shows the interaction user's team."""
    cog = make_cog()
    cog.team_service.get_team = AsyncMock(return_value=None)

    interaction = make_interaction()
    await cog.team.callback(cog, interaction, user=None)

    call_kwargs = cog.team_service.get_team.call_args[1]
    assert call_kwargs["player_id"] == str(interaction.user.id)


# ── /team-register ─────────────────────────────────────────────────────────────

async def test_team_register_no_logo_sends_embed():
    """/team-register without logo registers and sends confirmation embed."""
    cog = make_cog()
    cog.team_service.register_team = AsyncMock()

    interaction = make_interaction()
    await cog.team_register.callback(cog, interaction, team_name="LandoLords", pool="A", logo=None)

    cog.team_service.register_team.assert_awaited_once()
    interaction.followup.send.assert_awaited_once()
    embed_arg = interaction.followup.send.call_args[1]["embed"]
    assert "LandoLords" in embed_arg.title


async def test_team_register_with_valid_logo_uses_logo_url():
    """/team-register with valid PNG logo stores the url."""
    cog = make_cog()
    cog.team_service.register_team = AsyncMock()

    interaction = make_interaction()
    logo = MagicMock()
    logo.content_type = "image/png"
    logo.size = 1024
    logo.url = "https://cdn.example.com/logo.png"

    await cog.team_register.callback(cog, interaction, team_name="DragonForce", pool="B", logo=logo)

    call_kwargs = cog.team_service.register_team.call_args[1]
    assert call_kwargs["team_logo_url"] == "https://cdn.example.com/logo.png"


async def test_team_register_invalid_logo_type_sends_error():
    """/team-register with non-image content_type → early error, no defer."""
    cog = make_cog()
    cog.team_service.register_team = AsyncMock()

    interaction = make_interaction()
    logo = MagicMock()
    logo.content_type = "application/pdf"
    logo.size = 1024

    await cog.team_register.callback(cog, interaction, team_name="Team1", pool="A", logo=logo)

    interaction.response.send_message.assert_awaited_once()
    sent_text = interaction.response.send_message.call_args[0][0]
    assert "❌" in sent_text
    cog.team_service.register_team.assert_not_awaited()


async def test_team_register_oversized_logo_sends_error():
    """/team-register with > 8 MB logo → size error, no registration."""
    cog = make_cog()
    cog.team_service.register_team = AsyncMock()

    interaction = make_interaction()
    logo = MagicMock()
    logo.content_type = "image/png"
    logo.size = 9 * 1024 * 1024  # 9 MB

    await cog.team_register.callback(cog, interaction, team_name="BigTeam", pool="A", logo=logo)

    interaction.response.send_message.assert_awaited_once()
    sent_text = interaction.response.send_message.call_args[0][0]
    assert "8 MB" in sent_text
    cog.team_service.register_team.assert_not_awaited()


async def test_team_register_sends_public_announcement_when_channel_exists():
    """/team-register also sends a public embed to the channel."""
    cog = make_cog()
    cog.team_service.register_team = AsyncMock()

    interaction = make_interaction()
    await cog.team_register.callback(cog, interaction, team_name="PublicTeam", pool="A", logo=None)

    interaction.channel.send.assert_awaited_once()


# ── /trade ────────────────────────────────────────────────────────────────────

async def test_trade_success_sends_embed_and_dms_target():
    """/trade success: embed sent + DM to target player."""
    cog = make_cog()
    trade_result = MagicMock()
    trade_result.success = True
    trade_result.trade_id = "TRD-001"
    cog.team_service.propose_trade = AsyncMock(return_value=trade_result)

    interaction = make_interaction()
    target = MagicMock()
    target.id = "9999"
    target.mention = "<@9999>"
    target.send = AsyncMock()

    await cog.trade.callback(cog, interaction, target=target, offer="Garchomp", request="Dragonite")

    interaction.followup.send.assert_awaited_once()
    embed_arg = interaction.followup.send.call_args[1]["embed"]
    assert "Garchomp" in embed_arg.description
    target.send.assert_awaited_once()


async def test_trade_failure_sends_error_message():
    """/trade failure: ephemeral error message sent."""
    cog = make_cog()
    trade_result = MagicMock()
    trade_result.success = False
    trade_result.error = "Pokemon not in roster"
    cog.team_service.propose_trade = AsyncMock(return_value=trade_result)

    interaction = make_interaction()
    target = MagicMock()
    target.id = "9999"
    target.send = AsyncMock()

    await cog.trade.callback(cog, interaction, target=target, offer="Pikachu", request="Raichu")

    sent_text = interaction.followup.send.call_args[0][0]
    assert "Trade failed" in sent_text


async def test_trade_dm_forbidden_is_silently_ignored():
    """/trade: Forbidden DM to target doesn't crash the command."""
    cog = make_cog()
    trade_result = MagicMock()
    trade_result.success = True
    trade_result.trade_id = "TRD-002"
    cog.team_service.propose_trade = AsyncMock(return_value=trade_result)

    interaction = make_interaction()
    target = MagicMock()
    target.id = "9999"
    target.mention = "<@9999>"
    target.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "Cannot DM"))

    # Should not raise
    await cog.trade.callback(cog, interaction, target=target, offer="Garchomp", request="Dragonite")
    interaction.followup.send.assert_awaited_once()


# ── /trade-accept ─────────────────────────────────────────────────────────────

async def test_trade_accept_success_sends_confirmation():
    """/trade-accept success → '✅ Trade accepted' message."""
    cog = make_cog()
    result = MagicMock()
    result.success = True
    result.summary = "Both rosters updated."
    cog.team_service.accept_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.trade_accept.callback(cog, interaction, trade_id="TRD-001")

    sent_text = interaction.followup.send.call_args[0][0]
    assert "✅" in sent_text
    assert "accepted" in sent_text.lower()


async def test_trade_accept_failure_sends_error():
    """/trade-accept failure → ephemeral '❌ Trade error' message."""
    cog = make_cog()
    result = MagicMock()
    result.success = False
    result.error = "Trade not found"
    cog.team_service.accept_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.trade_accept.callback(cog, interaction, trade_id="TRD-999")

    sent_text = interaction.followup.send.call_args[0][0]
    assert "❌" in sent_text
    assert "Trade error" in sent_text


# ── /trade-decline ────────────────────────────────────────────────────────────

async def test_trade_decline_success_sends_declined():
    """/trade-decline success → confirmation that trade was declined."""
    cog = make_cog()
    result = MagicMock()
    result.success = True
    cog.team_service.decline_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.trade_decline.callback(cog, interaction, trade_id="TRD-001")

    sent_text = interaction.followup.send.call_args[0][0]
    assert "TRD-001" in sent_text


async def test_trade_decline_failure_sends_error():
    """/trade-decline failure → '❌' error message."""
    cog = make_cog()
    result = MagicMock()
    result.success = False
    result.error = "Already declined"
    cog.team_service.decline_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.trade_decline.callback(cog, interaction, trade_id="TRD-999")

    sent_text = interaction.followup.send.call_args[0][0]
    assert "❌" in sent_text


# ── /teamimport ───────────────────────────────────────────────────────────────

async def test_teamimport_non_txt_sends_error():
    """/teamimport: non-.txt attachment → early error."""
    cog = make_cog()
    interaction = make_interaction()
    team_file = MagicMock()
    team_file.filename = "team.docx"

    await cog.teamimport.callback(cog, interaction, format="gen9ou", team_file=team_file)

    interaction.response.send_message.assert_awaited_once()
    sent_text = interaction.response.send_message.call_args[0][0]
    assert ".txt" in sent_text


async def test_teamimport_empty_file_sends_error():
    """/teamimport: empty file content → 'appears to be empty' followup."""
    cog = make_cog()
    interaction = make_interaction()
    team_file = MagicMock()
    team_file.filename = "team.txt"
    team_file.read = AsyncMock(return_value=b"   ")

    await cog.teamimport.callback(cog, interaction, format="gen9ou", team_file=team_file)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "empty" in sent_text.lower()


async def test_teamimport_valid_file_sends_confirm_view():
    """/teamimport with valid showdown text → confirmation embed+view sent."""
    cog = make_cog()
    interaction = make_interaction()
    team_file = MagicMock()
    team_file.filename = "team.txt"
    showdown_text = (
        "Garchomp @ Choice Scarf\n"
        "Ability: Rough Skin\n"
        "EVs: 252 Atk / 4 SpD / 252 Spe\n"
        "Jolly Nature\n"
        "- Earthquake\n"
        "\n"
        "Dragonite @ Lum Berry\n"
        "Ability: Multiscale\n"
        "EVs: 252 Atk / 4 SpD / 252 Spe\n"
        "Adamant Nature\n"
        "- Dragon Dance\n"
    )
    team_file.read = AsyncMock(return_value=showdown_text.encode("utf-8"))

    mock_view = MagicMock()
    mock_embed = MagicMock()

    with patch("src.bot.cogs.team.TeamImportConfirmView", return_value=mock_view), \
         patch("src.bot.cogs.team.build_confirm_embed", return_value=mock_embed):
        await cog.teamimport.callback(cog, interaction, format="gen9ou", team_file=team_file)

    interaction.followup.send.assert_awaited_once_with(
        embed=mock_embed, view=mock_view, ephemeral=True
    )


async def test_teamimport_parses_pokemon_names():
    """/teamimport correctly extracts Pokemon names for the preview."""
    cog = make_cog()
    interaction = make_interaction()
    team_file = MagicMock()
    team_file.filename = "team.txt"
    team_file.read = AsyncMock(
        return_value=b"Garchomp @ Choice Scarf\nAbility: Rough Skin\n"
    )

    captured_preview = []

    def capture_preview(fmt, preview):
        captured_preview.extend(preview)
        return MagicMock()

    with patch("src.bot.cogs.team.TeamImportConfirmView", return_value=MagicMock()), \
         patch("src.bot.cogs.team.build_confirm_embed", side_effect=capture_preview):
        await cog.teamimport.callback(cog, interaction, format="gen9ou", team_file=team_file)

    assert any("Garchomp" in p for p in captured_preview)


# ── /teamimport autocomplete ──────────────────────────────────────────────────

async def test_teamimport_autocomplete_filters_by_current():
    """Autocomplete returns choices matching partial input."""
    cog = make_cog()
    interaction = make_interaction()

    choices = await cog.teamimport_format_autocomplete(interaction, "gen9")

    assert len(choices) > 0
    for choice in choices:
        assert "gen9" in choice.name.lower() or "gen9" in choice.value.lower()


async def test_teamimport_autocomplete_empty_returns_up_to_25():
    """Empty current → up to 25 choices."""
    from src.bot.constants import SUPPORTED_FORMATS
    cog = make_cog()
    interaction = make_interaction()

    choices = await cog.teamimport_format_autocomplete(interaction, "")
    assert len(choices) == min(len(SUPPORTED_FORMATS), 25)


async def test_teamimport_autocomplete_no_match_returns_empty():
    """No matching format → empty list."""
    cog = make_cog()
    interaction = make_interaction()

    choices = await cog.teamimport_format_autocomplete(interaction, "zzznomatch999xyz")
    assert choices == []


# ── /teamexport ───────────────────────────────────────────────────────────────

async def test_teamexport_sends_showdown_text():
    """/teamexport defers and sends showdown export in a code block."""
    cog = make_cog()
    cog.team_service.export_showdown = AsyncMock(return_value="Garchomp @ Choice Scarf\n...")

    interaction = make_interaction()
    await cog.teamexport.callback(cog, interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    sent_text = interaction.followup.send.call_args[0][0]
    assert "Garchomp" in sent_text
    assert "```" in sent_text


# ── /legality ─────────────────────────────────────────────────────────────────

async def test_legality_legal_pokemon_sends_green_embed():
    """/legality: legal Pokemon → green embed."""
    cog = make_cog()
    result = MagicMock()
    result.legal = True
    result.reason = "Garchomp is obtainable in Scarlet/Violet."
    cog.team_service.check_legality = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.legality.callback(cog, interaction, pokemon="Garchomp", game="sv")

    interaction.followup.send.assert_awaited_once()
    embed_arg = interaction.followup.send.call_args[1]["embed"]
    assert "Garchomp" in embed_arg.title
    assert embed_arg.color == discord.Color.green()


async def test_legality_illegal_pokemon_sends_red_embed():
    """/legality: illegal Pokemon → red embed."""
    cog = make_cog()
    result = MagicMock()
    result.legal = False
    result.reason = "Mewtwo is not obtainable in Scarlet/Violet."
    cog.team_service.check_legality = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.legality.callback(cog, interaction, pokemon="Mewtwo", game="sv")

    embed_arg = interaction.followup.send.call_args[1]["embed"]
    assert embed_arg.color == discord.Color.red()


# ── ShowdownImportModal ───────────────────────────────────────────────────────

async def test_showdown_import_modal_success_sends_count():
    """Modal on_submit success → sends '... Pokemon loaded' message."""
    team_service = MagicMock()
    result = MagicMock()
    result.success = True
    result.pokemon = ["Garchomp", "Dragonite", "Tyranitar"]
    team_service.import_showdown = AsyncMock(return_value=result)

    modal = ShowdownImportModal(team_service=team_service)
    modal.team_text = MagicMock()
    modal.team_text.value = "Garchomp @ Choice Scarf\n..."

    interaction = make_interaction()
    await modal.on_submit(interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    sent_text = interaction.followup.send.call_args[0][0]
    assert "3" in sent_text
    assert "Pokemon" in sent_text


async def test_showdown_import_modal_failure_sends_error():
    """Modal on_submit failure → sends 'Import failed' message."""
    team_service = MagicMock()
    result = MagicMock()
    result.success = False
    result.error = "Invalid format"
    team_service.import_showdown = AsyncMock(return_value=result)

    modal = ShowdownImportModal(team_service=team_service)
    modal.team_text = MagicMock()
    modal.team_text.value = "bad data"

    interaction = make_interaction()
    await modal.on_submit(interaction)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "Import failed" in sent_text
    assert "Invalid format" in sent_text


# ── setup ─────────────────────────────────────────────────────────────────────

async def test_team_cog_setup_adds_cog():
    """setup() adds TeamCog to the bot."""
    bot = MagicMock()
    bot.add_cog = AsyncMock()

    await setup(bot)

    bot.add_cog.assert_awaited_once()
    cog_arg = bot.add_cog.call_args[0][0]
    assert isinstance(cog_arg, TeamCog)
