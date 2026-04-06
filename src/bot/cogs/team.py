"""
Team Cog — Roster management, trades, Showdown import/export, console legality.
"""
import re

import discord
from discord import app_commands
from discord.ext import commands

from src.bot.constants import SUPPORTED_FORMATS
from src.bot.views.team_import_view import TeamImportConfirmView, build_confirm_embed
from src.bot.views.team_view import TeamEmbedView
from src.services.analytics_service import AnalyticsService
from src.services.team_service import TeamService


def decode_attachment_bytes(data: bytes) -> str:
    """Decode raw bytes from a Discord .txt attachment into a UTF-8 string.

    Args:
        data: Raw bytes from discord.Attachment.read().

    Returns:
        Decoded string using UTF-8; undecodable bytes are replaced with the
        Unicode replacement character (U+FFFD).
    """
    return data.decode("utf-8", errors="replace")


# NOTE: ShowdownImportModal is kept as a fallback. The primary import path is now
# the /teamimport file-attachment command. This modal may be removed in a future phase.
class ShowdownImportModal(discord.ui.Modal, title="Import Showdown Team"):
    team_text = discord.ui.TextInput(
        label="Paste your Showdown team export below",
        style=discord.TextStyle.paragraph,
        placeholder="Garchomp @ Choice Scarf\n...",
        required=True,
        max_length=4000,
    )

    def __init__(self, team_service: TeamService) -> None:
        super().__init__()
        self.team_service = team_service

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        result = await self.team_service.import_showdown(
            guild_id=str(interaction.guild_id),
            player_id=str(interaction.user.id),
            showdown_text=self.team_text.value,
        )
        if result.success:
            await interaction.followup.send(
                f"Team imported successfully! {len(result.pokemon)} Pokemon loaded.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(f"Import failed: {result.error}", ephemeral=True)


class TeamCog(commands.Cog, name="Team"):
    """Commands for managing your drafted team."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.team_service = TeamService()
        self.analytics = AnalyticsService()

    # ── /team ────────────────────────────────────────────────
    @app_commands.command(name="team", description="View your current drafted team")
    @app_commands.describe(user="View another player's team (leave blank for yours)")
    async def team(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        await interaction.response.defer()
        target = user or interaction.user
        roster = await self.team_service.get_team(
            guild_id=str(interaction.guild_id),
            player_id=str(target.id),
        )
        if not roster:
            await interaction.followup.send(f"{target.display_name} has no team yet.", ephemeral=True)
            return
        view = TeamEmbedView(roster=roster, owner=target)
        await interaction.followup.send(embed=view.build_embed(), view=view)

    # ── /team-register ───────────────────────────────────────
    @app_commands.command(name="team-register", description="Register your team name and logo for the league")
    @app_commands.describe(
        team_name="Your team name",
        pool="Pool assignment (A or B)",
        logo="Team logo image (attach a PNG/JPG)",
    )
    async def team_register(
        self,
        interaction: discord.Interaction,
        team_name: str,
        pool: str = "A",
        logo: discord.Attachment | None = None,
    ) -> None:
        logo_url = ""
        if logo:
            if logo.content_type not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
                await interaction.response.send_message(
                    "❌ Logo must be a PNG, JPG, GIF, or WebP image.", ephemeral=True
                )
                return
            if logo.size > 8 * 1024 * 1024:
                await interaction.response.send_message("❌ Logo must be under 8 MB.", ephemeral=True)
                return
            logo_url = logo.url

        await interaction.response.defer(ephemeral=True)
        await self.team_service.register_team(
            guild_id=str(interaction.guild_id),
            player_id=str(interaction.user.id),
            player_name=interaction.user.display_name,
            team_name=team_name,
            team_logo_url=logo_url,
            pool=pool.upper(),
        )
        embed = discord.Embed(title=f"✅ {team_name} Registered!", color=discord.Color.green())
        embed.add_field(name="Pool", value=pool.upper())
        if logo_url:
            embed.set_thumbnail(url=logo_url)
        embed.set_footer(text="Saved to spreadsheet • Team Page Template tab")
        await interaction.followup.send(embed=embed, ephemeral=True)

        if interaction.channel:
            pub = discord.Embed(
                title=f"🏆 {team_name} has entered the league!",
                description=f"**{interaction.user.mention}** · Pool **{pool.upper()}**",
                color=discord.Color.blurple(),
            )
            if logo_url:
                pub.set_thumbnail(url=logo_url)
            await interaction.channel.send(embed=pub)

    # ── /trade ───────────────────────────────────────────────
    @app_commands.command(name="trade", description="Propose a Pokemon trade")
    @app_commands.describe(
        target="Player to trade with",
        offer="Pokemon you are offering",
        request="Pokemon you want in return",
    )
    async def trade(
        self,
        interaction: discord.Interaction,
        target: discord.Member,
        offer: str,
        request: str,
    ) -> None:
        await interaction.response.defer()
        result = await self.team_service.propose_trade(
            guild_id=str(interaction.guild_id),
            from_player=str(interaction.user.id),
            to_player=str(target.id),
            offering=offer,
            requesting=request,
        )
        if result.success:
            embed = discord.Embed(
                title="Trade Proposed!",
                description=(
                    f"{interaction.user.mention} offers **{offer}** "
                    f"to {target.mention} for **{request}**"
                ),
                color=discord.Color.orange(),
            )
            embed.set_footer(text=f"Trade ID: {result.trade_id} | Use /trade-accept or /trade-decline")
            await interaction.followup.send(embed=embed)
            try:
                await target.send(
                    f"**Trade offer from {interaction.user.display_name}!**\n"
                    f"They offer **{offer}** for your **{request}**.\n"
                    f"Use `/trade-accept {result.trade_id}` to accept or "
                    f"`/trade-decline {result.trade_id}` to decline."
                )
            except discord.Forbidden:
                pass
        else:
            await interaction.followup.send(f"Trade failed: {result.error}", ephemeral=True)

    # ── /trade-accept ────────────────────────────────────────
    @app_commands.command(name="trade-accept", description="Accept a pending trade offer")
    @app_commands.describe(trade_id="Trade ID to accept")
    async def trade_accept(self, interaction: discord.Interaction, trade_id: str) -> None:
        await interaction.response.defer()
        result = await self.team_service.accept_trade(
            player_id=str(interaction.user.id),
            trade_id=trade_id,
        )
        if result.success:
            await interaction.followup.send(f"✅ Trade accepted! {result.summary}")
        else:
            await interaction.followup.send(f"❌ Trade error: {result.error}", ephemeral=True)

    # ── /trade-decline ───────────────────────────────────────
    @app_commands.command(name="trade-decline", description="Decline a pending trade offer")
    @app_commands.describe(trade_id="Trade ID to decline")
    async def trade_decline(self, interaction: discord.Interaction, trade_id: str) -> None:
        await interaction.response.defer(ephemeral=True)
        result = await self.team_service.decline_trade(
            player_id=str(interaction.user.id),
            trade_id=trade_id,
        )
        if result.success:
            await interaction.followup.send(f"Trade `{trade_id}` declined.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {result.error}", ephemeral=True)

    # ── /teamimport ──────────────────────────────────────────
    @app_commands.command(
        name="teamimport",
        description="Import a Showdown team from a .txt file attachment",
    )
    @app_commands.describe(
        format="Format to store the team under (e.g. Gen 9 OU, VGC 2024 Reg G)",
        team_file="Your Showdown team export as a .txt file",
    )
    async def teamimport(
        self,
        interaction: discord.Interaction,
        format: str,
        team_file: discord.Attachment,
    ) -> None:
        """Import a team from a .txt Showdown export with per-format storage."""
        # Validate file type
        if not team_file.filename.lower().endswith(".txt"):
            await interaction.response.send_message(
                "Please attach a `.txt` Showdown export file.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Decode attachment
        raw_bytes = await team_file.read()
        showdown_text = decode_attachment_bytes(raw_bytes)

        if not showdown_text.strip():
            await interaction.followup.send(
                "The attached file appears to be empty.", ephemeral=True
            )
            return

        # Build preview pokemon list for confirmation embed
        # Parse "Name @ Item" lines from the first non-blank, non-indented lines
        pokemon_preview: list[str] = []
        for line in showdown_text.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("-") or line.startswith("Ability:") or \
                    line.startswith("EVs:") or line.startswith("IVs:") or \
                    line.endswith("Nature") or line.startswith("Level") or \
                    line.startswith("Shiny") or line.startswith("Happiness") or \
                    line.startswith("Tera Type:"):
                continue
            # First line of a new Pokemon block — may have "@ Item"
            if re.match(r"^[A-Za-z]", line):
                pokemon_preview.append(line)

        # Build confirmation view and embed
        view = TeamImportConfirmView(
            team_service=self.team_service,
            guild_id=str(interaction.guild_id),
            player_id=str(interaction.user.id),
            showdown_text=showdown_text,
            format_key=format,
        )
        embed = build_confirm_embed(format, pokemon_preview)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @teamimport.autocomplete("format")
    async def teamimport_format_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Filter SUPPORTED_FORMATS by the user's current input."""
        current_lower = current.lower()
        return [
            app_commands.Choice(name=display, value=key)
            for key, display in SUPPORTED_FORMATS.items()
            if current_lower in display.lower() or current_lower in key.lower()
        ][:25]

    # ── /teamexport ──────────────────────────────────────────
    @app_commands.command(name="teamexport", description="Export your team in Pokemon Showdown format")
    async def teamexport(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        export = await self.team_service.export_showdown(
            guild_id=str(interaction.guild_id),
            player_id=str(interaction.user.id),
        )
        await interaction.followup.send(
            f"Your team in Showdown format:\n```\n{export}\n```",
            ephemeral=True,
        )

    # ── /legality ────────────────────────────────────────────
    @app_commands.command(name="legality", description="Check if a Pokemon is legal in a specific game")
    @app_commands.describe(pokemon="Pokemon to check", game="Game to check legality for")
    @app_commands.choices(game=[
        app_commands.Choice(name="Scarlet/Violet", value="sv"),
        app_commands.Choice(name="Sword/Shield", value="swsh"),
        app_commands.Choice(name="BDSP", value="bdsp"),
        app_commands.Choice(name="Legends: Arceus", value="legends"),
        app_commands.Choice(name="Pokemon Showdown (OU)", value="showdown_ou"),
        app_commands.Choice(name="VGC (Current)", value="vgc"),
    ])
    async def legality(self, interaction: discord.Interaction, pokemon: str, game: str) -> None:
        await interaction.response.defer()
        result = await self.team_service.check_legality(pokemon_name=pokemon, game_format=game)
        color = discord.Color.green() if result.legal else discord.Color.red()
        embed = discord.Embed(
            title=f"{pokemon} — {game.upper()} Legality",
            description=result.reason,
            color=color,
        )
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TeamCog(bot))
