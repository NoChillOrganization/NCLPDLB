"""
Team Import Confirm View — shows parsed team preview with Confirm/Cancel buttons.
"""
from __future__ import annotations

import discord

from src.bot.constants import SUPPORTED_FORMATS


def build_confirm_embed(format_key: str, pokemon_list: list[str]) -> discord.Embed:
    """Build the confirmation embed shown before saving an imported team.

    Args:
        format_key: Showdown format string key (e.g. "gen9ou"). Must be a key in
            SUPPORTED_FORMATS; falls back to format_key itself if not found.
        pokemon_list: List of "Pokemon @ Item" strings from the parsed team.

    Returns:
        discord.Embed with title containing the format display name and a Pokemon field.
    """
    display_name = SUPPORTED_FORMATS.get(format_key, format_key)
    embed = discord.Embed(
        title=f"Confirm Team Import — {display_name}",
        color=discord.Color.green(),
    )
    pokemon_value = "\n".join(pokemon_list) if pokemon_list else "No Pokemon found."
    embed.add_field(name="Pokemon", value=pokemon_value, inline=False)
    return embed


class TeamImportConfirmView(discord.ui.View):
    """Ephemeral confirmation view for /teamimport — user must confirm before team is saved."""

    def __init__(
        self,
        team_service,
        guild_id: str,
        player_id: str,
        showdown_text: str,
        format_key: str,
    ) -> None:
        super().__init__(timeout=120)
        self.team_service = team_service
        self.guild_id = guild_id
        self.player_id = player_id
        self.showdown_text = showdown_text
        self.format_key = format_key

    @discord.ui.button(label="Confirm Save", style=discord.ButtonStyle.success)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Save the parsed team to the player's per-format roster slot."""
        await interaction.response.defer(ephemeral=True)
        result = await self.team_service.import_showdown(
            guild_id=self.guild_id,
            player_id=self.player_id,
            showdown_text=self.showdown_text,
            format_key=self.format_key,
        )
        if result.success:
            display_name = SUPPORTED_FORMATS.get(self.format_key, self.format_key)
            await interaction.followup.send(
                f"Team saved for **{display_name}**! {len(result.pokemon)} Pokemon loaded.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"Import failed: {result.error}", ephemeral=True
            )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Discard the import without saving."""
        await interaction.response.send_message(
            "Team import cancelled.", ephemeral=True
        )
        self.stop()
