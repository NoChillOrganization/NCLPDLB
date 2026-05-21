import pytest
from unittest.mock import AsyncMock, MagicMock
from src.bot.views.team_import_view import build_confirm_embed, TeamImportConfirmView

def test_build_confirm_embed():
    embed = build_confirm_embed("gen9ou", ["Pikachu @ Light Ball", "Charizard @ Heavy-Duty Boots"])
    assert embed.title == "Confirm Team Import — Gen 9 OU"
    assert embed.fields[0].value == "Pikachu @ Light Ball\nCharizard @ Heavy-Duty Boots"

    embed = build_confirm_embed("unknown", [])
    assert embed.title == "Confirm Team Import — unknown"
    assert embed.fields[0].value == "No Pokemon found."

@pytest.mark.asyncio
async def test_team_import_confirm_view_confirm_success():
    team_service = AsyncMock()
    result = MagicMock()
    result.success = True
    result.pokemon = [MagicMock()]
    team_service.import_showdown.return_value = result

    view = TeamImportConfirmView(team_service, "123", "456", "text", "gen9ou")
    interaction = AsyncMock()
    button = MagicMock()

    await TeamImportConfirmView.confirm(view, interaction, button)

    team_service.import_showdown.assert_called_once_with(
        guild_id="123", player_id="456", showdown_text="text", format_key="gen9ou"
    )
    interaction.response.defer.assert_called_once_with(ephemeral=True)
    interaction.followup.send.assert_called_once_with(
        "Team saved for **Gen 9 OU**! 1 Pokemon loaded.", ephemeral=True
    )

@pytest.mark.asyncio
async def test_team_import_confirm_view_confirm_fail():
    team_service = AsyncMock()
    result = MagicMock()
    result.success = False
    result.error = "Parse error"
    team_service.import_showdown.return_value = result

    view = TeamImportConfirmView(team_service, "123", "456", "text", "gen9ou")
    interaction = AsyncMock()
    button = MagicMock()

    await TeamImportConfirmView.confirm(view, interaction, button)

    interaction.followup.send.assert_called_once_with("Import failed: Parse error", ephemeral=True)

@pytest.mark.asyncio
async def test_team_import_confirm_view_cancel():
    view = TeamImportConfirmView(AsyncMock(), "123", "456", "text", "gen9ou")
    interaction = AsyncMock()
    button = MagicMock()

    await TeamImportConfirmView.cancel(view, interaction, button)

    interaction.response.send_message.assert_called_once_with("Team import cancelled.", ephemeral=True)
