"""
Tests for src/bot/cogs/team.py — TeamCog slash commands, ShowdownImportModal,
and the module-level setup() function.

Coverage target: bring team.py from ~33% to 80%+.

Patterns used throughout:
  - Slash commands: await cog.command_name.callback(cog, interaction, args...)
  - Modal on_submit: await modal.on_submit(interaction)
  - TeamService methods are replaced with AsyncMock on each cog instance
  - discord.Interaction built by make_interaction() helper
"""
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from src.bot.cogs.team import ShowdownImportModal, TeamCog, setup


# ── Shared helpers ─────────────────────────────────────────────────────────────

def make_interaction(guild_id="9999", user_id="1111"):
    """Build a minimal mock discord.Interaction usable for all TeamCog tests."""
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.guild = MagicMock()
    interaction.guild.id = int(guild_id)
    interaction.user = MagicMock()
    interaction.user.id = user_id
    interaction.user.display_name = "Trainer"
    interaction.user.mention = f"<@{user_id}>"
    interaction.user.send = AsyncMock()
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock(return_value=MagicMock())
    interaction.channel = MagicMock()
    interaction.channel.send = AsyncMock()
    return interaction


def make_cog():
    """Build a TeamCog with all service calls replaced by AsyncMock."""
    bot = MagicMock()
    cog = TeamCog(bot)
    cog.team_service = MagicMock()
    cog.analytics = MagicMock()
    return cog


# ── ShowdownImportModal ────────────────────────────────────────────────────────

async def test_modal_on_submit_success():
    """on_submit defers, calls import_showdown, sends count on success."""
    team_service = MagicMock()
    result = MagicMock()
    result.success = True
    result.pokemon = [MagicMock(), MagicMock()]
    team_service.import_showdown = AsyncMock(return_value=result)

    modal = ShowdownImportModal(team_service=team_service)
    modal.team_text = MagicMock()
    modal.team_text.value = "Garchomp @ Choice Scarf\n..."

    interaction = make_interaction()
    await modal.on_submit(interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    team_service.import_showdown.assert_awaited_once_with(
        guild_id="9999",
        player_id="1111",
        showdown_text="Garchomp @ Choice Scarf\n...",
    )
    sent_text = interaction.followup.send.call_args[0][0]
    assert "2" in sent_text
    assert "imported" in sent_text.lower() or "loaded" in sent_text.lower()


async def test_modal_on_submit_failure():
    """on_submit sends the error message when import fails."""
    team_service = MagicMock()
    result = MagicMock()
    result.success = False
    result.error = "No valid Pokemon found."
    team_service.import_showdown = AsyncMock(return_value=result)

    modal = ShowdownImportModal(team_service=team_service)
    modal.team_text = MagicMock()
    modal.team_text.value = "garbage input"

    interaction = make_interaction()
    await modal.on_submit(interaction)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "No valid Pokemon found." in sent_text
    assert "failed" in sent_text.lower() or "Import failed" in sent_text


# ── TeamCog.__init__ ───────────────────────────────────────────────────────────

def test_team_cog_init_stores_bot():
    """TeamCog stores the bot reference and creates service instances."""
    bot = MagicMock()
    cog = TeamCog(bot)
    assert cog.bot is bot
    assert cog.team_service is not None
    assert cog.analytics is not None


# ── /team ─────────────────────────────────────────────────────────────────────

async def test_team_own_roster_sends_embed():
    """/team with no user arg shows the caller's roster."""
    cog = make_cog()
    roster = MagicMock()
    cog.team_service.get_team = AsyncMock(return_value=roster)

    interaction = make_interaction()

    with patch("src.bot.cogs.team.TeamEmbedView") as MockView:
        mock_view_instance = MagicMock()
        mock_embed = MagicMock()
        mock_view_instance.build_embed.return_value = mock_embed
        MockView.return_value = mock_view_instance

        await cog.team.callback(cog, interaction, user=None)

    interaction.response.defer.assert_awaited_once()
    cog.team_service.get_team.assert_awaited_once_with(
        guild_id="9999",
        player_id="1111",
    )
    interaction.followup.send.assert_awaited_once_with(
        embed=mock_embed, view=mock_view_instance
    )


async def test_team_other_user_passes_target_id():
    """/team with a user arg passes that user's ID to the service."""
    cog = make_cog()
    roster = MagicMock()
    cog.team_service.get_team = AsyncMock(return_value=roster)

    interaction = make_interaction()
    target = MagicMock()
    target.id = "2222"
    target.display_name = "Rival"

    with patch("src.bot.cogs.team.TeamEmbedView"):
        await cog.team.callback(cog, interaction, user=target)

    cog.team_service.get_team.assert_awaited_once_with(
        guild_id="9999",
        player_id="2222",
    )


async def test_team_no_roster_sends_ephemeral_message():
    """/team sends an ephemeral message when the player has no team."""
    cog = make_cog()
    cog.team_service.get_team = AsyncMock(return_value=None)

    interaction = make_interaction()
    await cog.team.callback(cog, interaction, user=None)

    call_args = interaction.followup.send.call_args
    assert call_args[1].get("ephemeral") is True
    sent_text = call_args[0][0]
    assert "no team" in sent_text.lower()


async def test_team_no_roster_mentions_player_name():
    """/team for another player with no team includes their display name."""
    cog = make_cog()
    cog.team_service.get_team = AsyncMock(return_value=None)

    interaction = make_interaction()
    target = MagicMock()
    target.id = "3333"
    target.display_name = "GaryOak"

    await cog.team.callback(cog, interaction, user=target)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "GaryOak" in sent_text


# ── /team-register ────────────────────────────────────────────────────────────

async def test_team_register_no_logo_registers_and_sends_embed():
    """/team-register with no logo defers, calls register_team, sends embed."""
    cog = make_cog()
    cog.team_service.register_team = AsyncMock()

    interaction = make_interaction()
    await cog.team_register.callback(cog, interaction, team_name="Ash's Crew", pool="A")

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    cog.team_service.register_team.assert_awaited_once_with(
        guild_id="9999",
        player_id="1111",
        player_name="Trainer",
        team_name="Ash's Crew",
        team_logo_url="",
        pool="A",
    )
    interaction.followup.send.assert_awaited_once()


async def test_team_register_posts_public_announcement():
    """/team-register also sends a public embed to interaction.channel."""
    cog = make_cog()
    cog.team_service.register_team = AsyncMock()

    interaction = make_interaction()
    await cog.team_register.callback(cog, interaction, team_name="Elite Four", pool="B")

    # Channel announcement should have been sent
    interaction.channel.send.assert_awaited_once()
    pub_embed = interaction.channel.send.call_args[1]["embed"]
    assert "Elite Four" in pub_embed.title


async def test_team_register_invalid_logo_content_type_rejects_early():
    """/team-register rejects a non-image attachment before deferring."""
    cog = make_cog()
    cog.team_service.register_team = AsyncMock()

    interaction = make_interaction()
    bad_logo = MagicMock()
    bad_logo.content_type = "application/pdf"
    bad_logo.size = 100

    await cog.team_register.callback(
        cog, interaction, team_name="Bad Team", pool="A", logo=bad_logo
    )

    interaction.response.send_message.assert_awaited_once()
    sent_text = interaction.response.send_message.call_args[0][0]
    assert "PNG" in sent_text or "logo" in sent_text.lower()
    # register_team must NOT have been called
    cog.team_service.register_team.assert_not_awaited()


async def test_team_register_logo_too_large_rejects_early():
    """/team-register rejects logos larger than 8 MB."""
    cog = make_cog()
    cog.team_service.register_team = AsyncMock()

    interaction = make_interaction()
    large_logo = MagicMock()
    large_logo.content_type = "image/png"
    large_logo.size = 9 * 1024 * 1024  # 9 MB

    await cog.team_register.callback(
        cog, interaction, team_name="BigFile FC", pool="A", logo=large_logo
    )

    sent_text = interaction.response.send_message.call_args[0][0]
    assert "8 MB" in sent_text or "under" in sent_text.lower()
    cog.team_service.register_team.assert_not_awaited()


async def test_team_register_valid_logo_uses_url():
    """/team-register with a valid logo passes logo.url to the service."""
    cog = make_cog()
    cog.team_service.register_team = AsyncMock()

    interaction = make_interaction()
    logo = MagicMock()
    logo.content_type = "image/png"
    logo.size = 500_000
    logo.url = "https://cdn.discord.com/logo.png"

    await cog.team_register.callback(
        cog, interaction, team_name="Icon FC", pool="A", logo=logo
    )

    call_kwargs = cog.team_service.register_team.call_args[1]
    assert call_kwargs["team_logo_url"] == "https://cdn.discord.com/logo.png"


async def test_team_register_pool_is_uppercased():
    """/team-register uppercases the pool argument before storing."""
    cog = make_cog()
    cog.team_service.register_team = AsyncMock()

    interaction = make_interaction()
    await cog.team_register.callback(cog, interaction, team_name="Lower Pool", pool="b")

    call_kwargs = cog.team_service.register_team.call_args[1]
    assert call_kwargs["pool"] == "B"


async def test_team_register_no_channel_skips_public_post():
    """/team-register does not crash when interaction.channel is None."""
    cog = make_cog()
    cog.team_service.register_team = AsyncMock()

    interaction = make_interaction()
    interaction.channel = None  # channel unavailable

    # Should complete without raising
    await cog.team_register.callback(cog, interaction, team_name="Quiet Team", pool="A")

    interaction.followup.send.assert_awaited_once()


# ── /trade ────────────────────────────────────────────────────────────────────

async def test_trade_success_sends_embed_and_dm():
    """/trade on success sends a public embed and a DM to the target."""
    cog = make_cog()
    result = MagicMock()
    result.success = True
    result.trade_id = "abc12345"
    cog.team_service.propose_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    target = MagicMock()
    target.id = "4444"
    target.mention = "<@4444>"
    target.send = AsyncMock()

    await cog.trade.callback(cog, interaction, target=target, offer="Garchomp", request="Dragonite")

    interaction.response.defer.assert_awaited_once()
    cog.team_service.propose_trade.assert_awaited_once_with(
        guild_id="9999",
        from_player="1111",
        to_player="4444",
        offering="Garchomp",
        requesting="Dragonite",
    )
    # Public embed sent
    call_kwargs = interaction.followup.send.call_args[1]
    assert "embed" in call_kwargs
    # DM sent to target
    target.send.assert_awaited_once()


async def test_trade_success_embed_contains_pokemon_names():
    """/trade embed mentions both offered and requested Pokemon names."""
    cog = make_cog()
    result = MagicMock()
    result.success = True
    result.trade_id = "xyz99"
    cog.team_service.propose_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    target = MagicMock()
    target.id = "5555"
    target.mention = "<@5555>"
    target.send = AsyncMock()

    await cog.trade.callback(cog, interaction, target=target, offer="Gengar", request="Alakazam")

    embed = interaction.followup.send.call_args[1]["embed"]
    assert "Gengar" in embed.description
    assert "Alakazam" in embed.description


async def test_trade_success_dm_forbidden_no_crash():
    """/trade silently swallows discord.Forbidden when DM is blocked."""
    cog = make_cog()
    result = MagicMock()
    result.success = True
    result.trade_id = "xyz00"
    cog.team_service.propose_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    target = MagicMock()
    target.id = "6666"
    target.mention = "<@6666>"
    target.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Cannot send messages"))

    # Must not raise
    await cog.trade.callback(cog, interaction, target=target, offer="Pikachu", request="Raichu")

    interaction.followup.send.assert_awaited_once()  # embed was still sent


async def test_trade_failure_sends_ephemeral_error():
    """/trade sends an ephemeral error message when the service returns failure."""
    cog = make_cog()
    result = MagicMock()
    result.success = False
    result.error = "You don't have Mewtwo."
    cog.team_service.propose_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    target = MagicMock()
    target.id = "7777"
    target.send = AsyncMock()

    await cog.trade.callback(cog, interaction, target=target, offer="Mewtwo", request="Mew")

    call_kwargs = interaction.followup.send.call_args[1]
    assert call_kwargs.get("ephemeral") is True
    sent_text = interaction.followup.send.call_args[0][0]
    assert "You don't have Mewtwo." in sent_text


# ── /trade-accept ─────────────────────────────────────────────────────────────

async def test_trade_accept_success_sends_confirmation():
    """/trade-accept on success sends a confirmation with the summary."""
    cog = make_cog()
    result = MagicMock()
    result.success = True
    result.summary = "Trade complete! Gengar ↔ Alakazam"
    cog.team_service.accept_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.trade_accept.callback(cog, interaction, trade_id="abc123")

    interaction.response.defer.assert_awaited_once()
    cog.team_service.accept_trade.assert_awaited_once_with(
        player_id="1111",
        trade_id="abc123",
    )
    sent_text = interaction.followup.send.call_args[0][0]
    assert "Trade complete!" in sent_text
    assert "✅" in sent_text


async def test_trade_accept_failure_sends_ephemeral_error():
    """/trade-accept sends an ephemeral error when the service returns failure."""
    cog = make_cog()
    result = MagicMock()
    result.success = False
    result.error = "Trade not found."
    cog.team_service.accept_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.trade_accept.callback(cog, interaction, trade_id="bad-id")

    call_kwargs = interaction.followup.send.call_args[1]
    assert call_kwargs.get("ephemeral") is True
    sent_text = interaction.followup.send.call_args[0][0]
    assert "Trade not found." in sent_text
    assert "❌" in sent_text


# ── /trade-decline ────────────────────────────────────────────────────────────

async def test_trade_decline_success_sends_ephemeral_confirmation():
    """/trade-decline on success sends an ephemeral confirmation."""
    cog = make_cog()
    result = MagicMock()
    result.success = True
    cog.team_service.decline_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.trade_decline.callback(cog, interaction, trade_id="def456")

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    cog.team_service.decline_trade.assert_awaited_once_with(
        player_id="1111",
        trade_id="def456",
    )
    sent_text = interaction.followup.send.call_args[0][0]
    assert "def456" in sent_text
    assert "declined" in sent_text.lower()


async def test_trade_decline_failure_sends_ephemeral_error():
    """/trade-decline failure sends an ephemeral error."""
    cog = make_cog()
    result = MagicMock()
    result.success = False
    result.error = "This trade is not for you."
    cog.team_service.decline_trade = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.trade_decline.callback(cog, interaction, trade_id="ghi789")

    call_kwargs = interaction.followup.send.call_args[1]
    assert call_kwargs.get("ephemeral") is True
    sent_text = interaction.followup.send.call_args[0][0]
    assert "This trade is not for you." in sent_text


# ── /teamimport ───────────────────────────────────────────────────────────────

async def test_teamimport_rejects_non_txt_extension():
    """/teamimport sends an error when the attached file is not a .txt."""
    cog = make_cog()
    interaction = make_interaction()

    team_file = MagicMock()
    team_file.filename = "team.pdf"
    team_file.read = AsyncMock(return_value=b"irrelevant")

    await cog.teamimport.callback(cog, interaction, format="gen9ou", team_file=team_file)

    interaction.response.send_message.assert_awaited_once()
    sent_text = interaction.response.send_message.call_args[0][0]
    assert ".txt" in sent_text


async def test_teamimport_rejects_empty_file():
    """/teamimport sends an error when the .txt file is empty."""
    cog = make_cog()
    interaction = make_interaction()

    team_file = MagicMock()
    team_file.filename = "team.txt"
    team_file.read = AsyncMock(return_value=b"   \n  ")

    await cog.teamimport.callback(cog, interaction, format="gen9ou", team_file=team_file)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    sent_text = interaction.followup.send.call_args[0][0]
    assert "empty" in sent_text.lower()


async def test_teamimport_valid_file_sends_confirm_view():
    """/teamimport with a valid file sends a confirmation view."""
    cog = make_cog()
    interaction = make_interaction()

    showdown_text = (
        "Garchomp @ Choice Scarf\n"
        "Ability: Rough Skin\n"
        "EVs: 252 Atk / 4 SpD / 252 Spe\n"
        "Jolly Nature\n"
        "- Scale Shot\n"
        "\n"
        "Dragonite @ Leftovers\n"
        "Ability: Multiscale\n"
        "EVs: 252 HP / 252 SpA / 4 Spe\n"
        "Modest Nature\n"
        "- Hurricane\n"
    )
    team_file = MagicMock()
    team_file.filename = "team.txt"
    team_file.read = AsyncMock(return_value=showdown_text.encode("utf-8"))

    await cog.teamimport.callback(cog, interaction, format="gen9ou", team_file=team_file)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    interaction.followup.send.assert_awaited_once()
    call_kwargs = interaction.followup.send.call_args[1]
    assert call_kwargs.get("ephemeral") is True
    assert "embed" in call_kwargs
    assert "view" in call_kwargs


async def test_teamimport_parses_pokemon_names_into_preview():
    """/teamimport preview embed contains the Pokemon names from the file."""
    cog = make_cog()
    interaction = make_interaction()

    showdown_text = "Garchomp @ Choice Scarf\nAbility: Rough Skin\nJolly Nature\n"
    team_file = MagicMock()
    team_file.filename = "team.txt"
    team_file.read = AsyncMock(return_value=showdown_text.encode("utf-8"))

    with patch("src.bot.cogs.team.build_confirm_embed") as mock_embed_builder:
        mock_embed_builder.return_value = MagicMock()
        await cog.teamimport.callback(cog, interaction, format="gen9ou", team_file=team_file)

    # The second positional arg to build_confirm_embed should contain Garchomp
    _, pokemon_preview = mock_embed_builder.call_args[0]
    assert any("Garchomp" in p for p in pokemon_preview)


async def test_teamimport_filters_showdown_directive_lines():
    """/teamimport does not include Ability/EVs/Nature lines in the pokemon preview."""
    cog = make_cog()
    interaction = make_interaction()

    showdown_text = (
        "Garchomp @ Choice Scarf\n"
        "Ability: Rough Skin\n"
        "EVs: 252 Atk / 4 SpD / 252 Spe\n"
        "Jolly Nature\n"
        "- Scale Shot\n"
    )
    team_file = MagicMock()
    team_file.filename = "team.txt"
    team_file.read = AsyncMock(return_value=showdown_text.encode("utf-8"))

    with patch("src.bot.cogs.team.build_confirm_embed") as mock_embed_builder:
        mock_embed_builder.return_value = MagicMock()
        await cog.teamimport.callback(cog, interaction, format="gen9ou", team_file=team_file)

    _, pokemon_preview = mock_embed_builder.call_args[0]
    # Directive lines must not appear in the preview list
    assert not any("Ability:" in p for p in pokemon_preview)
    assert not any("EVs:" in p for p in pokemon_preview)
    assert not any("Nature" in p for p in pokemon_preview)
    assert not any(p.startswith("-") for p in pokemon_preview)


# ── /teamimport autocomplete ──────────────────────────────────────────────────

async def test_teamimport_autocomplete_returns_matching_formats():
    """Autocomplete returns formats whose key or display name contains the query."""
    cog = make_cog()
    interaction = make_interaction()

    choices = await cog.teamimport_format_autocomplete(interaction, current="gen9ou")

    assert len(choices) >= 1
    assert any(c.value == "gen9ou" for c in choices)


async def test_teamimport_autocomplete_empty_query_returns_up_to_25():
    """Autocomplete with an empty query returns at most 25 choices."""
    cog = make_cog()
    interaction = make_interaction()

    choices = await cog.teamimport_format_autocomplete(interaction, current="")

    assert len(choices) <= 25


async def test_teamimport_autocomplete_case_insensitive():
    """Autocomplete matches regardless of case."""
    cog = make_cog()
    interaction = make_interaction()

    choices = await cog.teamimport_format_autocomplete(interaction, current="VGC")

    assert len(choices) >= 1
    assert all("vgc" in c.value.lower() or "vgc" in c.name.lower() for c in choices)


async def test_teamimport_autocomplete_no_match_returns_empty():
    """Autocomplete returns empty list when nothing matches."""
    cog = make_cog()
    interaction = make_interaction()

    choices = await cog.teamimport_format_autocomplete(interaction, current="xyznonexistent99")

    assert choices == []


# ── /teamexport ───────────────────────────────────────────────────────────────

async def test_teamexport_sends_showdown_export():
    """/teamexport defers and sends the Showdown export in a code block."""
    cog = make_cog()
    cog.team_service.export_showdown = AsyncMock(return_value="Garchomp\n- Earthquake\n")

    interaction = make_interaction()
    await cog.teamexport.callback(cog, interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    cog.team_service.export_showdown.assert_awaited_once_with(
        guild_id="9999",
        player_id="1111",
    )
    sent_text = interaction.followup.send.call_args[0][0]
    assert "Garchomp" in sent_text
    assert "```" in sent_text


async def test_teamexport_no_team_sends_no_team_message():
    """/teamexport works when export_showdown returns 'No team found.'."""
    cog = make_cog()
    cog.team_service.export_showdown = AsyncMock(return_value="No team found.")

    interaction = make_interaction()
    await cog.teamexport.callback(cog, interaction)

    sent_text = interaction.followup.send.call_args[0][0]
    assert "No team found." in sent_text


# ── /legality ─────────────────────────────────────────────────────────────────

async def test_legality_legal_pokemon_sends_green_embed():
    """/legality builds a green embed when the Pokemon is legal."""
    cog = make_cog()
    result = MagicMock()
    result.legal = True
    result.reason = "Garchomp is legal in Scarlet/Violet."
    cog.team_service.check_legality = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.legality.callback(cog, interaction, pokemon="Garchomp", game="sv")

    interaction.response.defer.assert_awaited_once()
    cog.team_service.check_legality.assert_awaited_once_with(
        pokemon_name="Garchomp", game_format="sv"
    )
    embed = interaction.followup.send.call_args[1]["embed"]
    assert embed.color == discord.Color.green()
    assert "Garchomp" in embed.title


async def test_legality_illegal_pokemon_sends_red_embed():
    """/legality builds a red embed when the Pokemon is not legal."""
    cog = make_cog()
    result = MagicMock()
    result.legal = False
    result.reason = "Mewtwo is NOT available in Sword/Shield."
    cog.team_service.check_legality = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.legality.callback(cog, interaction, pokemon="Mewtwo", game="swsh")

    embed = interaction.followup.send.call_args[1]["embed"]
    assert embed.color == discord.Color.red()


async def test_legality_embed_title_contains_game_and_pokemon():
    """/legality embed title contains both the Pokemon name and game string."""
    cog = make_cog()
    result = MagicMock()
    result.legal = True
    result.reason = "Legal."
    cog.team_service.check_legality = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.legality.callback(cog, interaction, pokemon="Pikachu", game="vgc")

    embed = interaction.followup.send.call_args[1]["embed"]
    assert "Pikachu" in embed.title
    assert "VGC" in embed.title  # game.upper() is in the title


async def test_legality_embed_description_is_reason():
    """/legality embed description is the reason string from the service."""
    cog = make_cog()
    result = MagicMock()
    result.legal = False
    result.reason = "Not in the Paldea Dex."
    cog.team_service.check_legality = AsyncMock(return_value=result)

    interaction = make_interaction()
    await cog.legality.callback(cog, interaction, pokemon="Bulbasaur", game="sv")

    embed = interaction.followup.send.call_args[1]["embed"]
    assert "Not in the Paldea Dex." in embed.description


# ── setup() ───────────────────────────────────────────────────────────────────

async def test_setup_adds_team_cog():
    """setup() registers a TeamCog instance to the bot."""
    bot = MagicMock()
    bot.add_cog = AsyncMock()

    await setup(bot)

    bot.add_cog.assert_awaited_once()
    cog_arg = bot.add_cog.call_args[0][0]
    assert isinstance(cog_arg, TeamCog)
