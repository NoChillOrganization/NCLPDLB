"""
Draft Cog — All draft-related slash commands.

Supports: Snake, Auction, Tiered, Adaptive Ban formats.
Includes a /draft-setup wizard that walks the commissioner through
all configuration questions before writing to the spreadsheet.
Tera Captain system fully integrated with rules saved to the Rules tab.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from src.bot.permissions import ROLE_COACH, ROLE_GUILDMASTER, require_role
from src.bot.views.draft_view import DraftPickView
from src.bot.views.draft_wizard import DraftCancelConfirmView, DraftSetupModal
from src.data.models import DraftFormat, TeraType
from src.services.draft_service import DraftService

# ── Main Cog ──────────────────────────────────────────────────


class DraftCog(commands.Cog, name="Draft"):
    """Commands for managing Pokemon draft sessions."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.draft_service = DraftService()

    # ── /draft-setup (full wizard) ────────────────────────────
    @app_commands.command(
        name="draft-setup",
        description="Interactive setup wizard — configure the draft and save to spreadsheet",
    )
    @require_role(ROLE_GUILDMASTER)
    async def draft_setup(self, interaction: discord.Interaction) -> None:
        """Walks commissioner through all questions: players, format, game mode, tera captains."""
        await interaction.response.send_modal(DraftSetupModal())

    # ── /draft-create (quick create, for power users) ─────────
    @app_commands.command(
        name="draft-create", description="Quickly create a draft with options"
    )
    @require_role(ROLE_GUILDMASTER)
    @app_commands.describe(
        format="Draft format",
        rounds="Number of rounds (default: 6)",
        timer="Pick timer in seconds (default: 60)",
        game_mode="Showdown or console format",
        tera_captains="Tera Captains per team (0 = off)",
        tera_types="Tera types per captain (default: 1)",
    )
    @app_commands.choices(
        format=[
            app_commands.Choice(name="Snake Draft", value="snake"),
            app_commands.Choice(name="Auction Draft", value="auction"),
            app_commands.Choice(name="Tiered Draft", value="tiered"),
        ],
        game_mode=[
            app_commands.Choice(name="Pokemon Showdown", value="showdown"),
            app_commands.Choice(name="Scarlet / Violet", value="sv"),
            app_commands.Choice(name="Sword / Shield", value="swsh"),
            app_commands.Choice(name="VGC", value="vgc"),
        ],
    )
    async def draft_create(
        self,
        interaction: discord.Interaction,
        format: str = "snake",
        rounds: int = 6,
        timer: int = 60,
        game_mode: str = "showdown",
        tera_captains: int = 0,
        tera_types: int = 1,
    ) -> None:
        await interaction.response.defer()
        draft = await self.draft_service.create_draft(
            guild_id=str(interaction.guild_id),
            commissioner_id=str(interaction.user.id),
            format=DraftFormat(format),
            rounds=rounds,
            timer_seconds=timer,
            game_format=game_mode,
            tera_captains_per_team=tera_captains,
            tera_types_per_captain=tera_types,
        )
        tera_info = (
            f"\n**Tera Captains:** {tera_captains}/team · {tera_types} type(s) each"
            if tera_captains > 0
            else ""
        )
        embed = discord.Embed(
            title="Draft Created!",
            description=(
                f"**Format:** {format.title()} Draft\n"
                f"**Mode:** {game_mode.upper()}\n"
                f"**Rounds:** {rounds} · **Timer:** {timer}s{tera_info}"
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(
            text=f"Draft ID: {draft.draft_id} | Use /draft-join to register"
        )
        await interaction.followup.send(embed=embed)

    # ── /draft-join ───────────────────────────────────────────
    @app_commands.command(name="draft-join", description="Join an active draft")
    @require_role(ROLE_COACH)
    @app_commands.describe(
        team_name="Your team name",
        pool="Pool assignment (A or B, default: auto)",
        draft_id="Draft ID (leave blank for current draft)",
    )
    async def draft_join(
        self,
        interaction: discord.Interaction,
        team_name: str = "",
        pool: str = "A",
        draft_id: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        result = await self.draft_service.add_player(
            guild_id=str(interaction.guild_id),
            player_id=str(interaction.user.id),
            player_name=interaction.user.display_name,
            team_name=team_name or f"{interaction.user.display_name}'s Team",
            pool=pool.upper(),
            draft_id=draft_id,
        )
        if result.success:
            await interaction.followup.send(
                f"✅ Joined the draft as **{team_name or interaction.user.display_name}**!"
                f" Pool {pool.upper()} · {result.player_count} players registered.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(f"❌ {result.error}", ephemeral=True)

    # ── /draft-start ──────────────────────────────────────────
    @app_commands.command(
        name="draft-start", description="Start the draft (Guildmaster only)"
    )
    @require_role(ROLE_GUILDMASTER)
    async def draft_start(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        channel = interaction.channel
        bot = self.bot

        # Single on_timeout closure threaded through the entire draft session.
        # Called by the service timer (the sole auto-skip authority) whenever a
        # player's timer expires — posts a skip notice and the next player's view.
        async def _on_pick_timeout(guild_id: str, skipped_player_id: str) -> None:
            active = self.draft_service.get_draft(guild_id)
            from src.services.draft_service import DraftStatus

            next_mention = (
                f"<@{active.current_player_id}>"
                if active and active.current_player_id
                else "Draft complete!"
            )
            skip_embed = discord.Embed(
                title="⏰ Pick timer expired",
                description=f"<@{skipped_player_id}>'s turn was skipped. Now up: {next_mention}",
                color=discord.Color.orange(),
            )
            if (
                active
                and active.status == DraftStatus.ACTIVE
                and active.current_player_id
                and channel
            ):
                next_view = DraftPickView(
                    draft=active, bot=bot, on_timeout_cb=_on_pick_timeout
                )
                await channel.send(embed=skip_embed, view=next_view)
            elif channel:
                await channel.send(embed=skip_embed)

        draft = await self.draft_service.start_draft(
            guild_id=str(interaction.guild_id),
            commissioner_id=str(interaction.user.id),
            on_timeout=_on_pick_timeout,
        )
        view = DraftPickView(draft=draft, bot=self.bot, on_timeout_cb=_on_pick_timeout)
        embed = discord.Embed(
            title="The Draft Has Started! 🎉",
            description=f"Round 1 — <@{draft.current_player_id}> is on the clock!",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Format", value=draft.format.value.title())
        embed.add_field(name="Mode", value=draft.game_format.upper())
        if draft.tera_captains_per_team > 0:
            embed.add_field(
                name="Tera Captains",
                value=f"{draft.tera_captains_per_team}/team · {draft.tera_types_per_captain} type(s)",
                inline=False,
            )
        await interaction.followup.send(embed=embed, view=view)

    # ── /pick ─────────────────────────────────────────────────
    @app_commands.command(name="pick", description="Pick a Pokemon during the draft")
    @require_role(ROLE_COACH)
    @app_commands.describe(
        pokemon="Pokemon name to pick",
        tera_type="Tera type (required if this Pokemon is a Tera Captain)",
        is_tera_captain="Mark this Pokemon as your Tera Captain",
    )
    @app_commands.choices(
        tera_type=[app_commands.Choice(name=t.value, value=t.value) for t in TeraType]
    )
    async def pick(
        self,
        interaction: discord.Interaction,
        pokemon: str,
        tera_type: str = "",
        is_tera_captain: bool = False,
    ) -> None:
        await interaction.response.defer()
        result = await self.draft_service.make_pick(
            guild_id=str(interaction.guild_id),
            player_id=str(interaction.user.id),
            pokemon_name=pokemon,
            tera_type=tera_type,
            is_tera_captain=is_tera_captain,
        )
        if result.success:
            embed = discord.Embed(
                title=f"{interaction.user.display_name} picked {result.pokemon.name}!",
                color=discord.Color.green(),
            )
            embed.set_thumbnail(url=result.pokemon.sprite_url)
            embed.add_field(
                name="Types",
                value=" / ".join(t.capitalize() for t in result.pokemon.types),
            )
            embed.add_field(name="Tier", value=result.pokemon.showdown_tier)
            if tera_type:
                captain_tag = " ⭐ **TERA CAPTAIN**" if is_tera_captain else ""
                embed.add_field(
                    name=f"Tera Type{captain_tag}", value=tera_type, inline=False
                )
            embed.set_footer(text=f"Next up — Round {result.round}")
            await interaction.followup.send(embed=embed)
            if not result.persistence_ok:
                await interaction.followup.send(
                    "⚠️ **Draft state failed to save.** If the bot restarts before "
                    "the next successful save, this draft will need to be resumed "
                    "manually. Commissioners should retry the next pick if this "
                    "keeps happening.",
                    ephemeral=True,
                )
        else:
            await interaction.followup.send(f"❌ {result.error}", ephemeral=True)

    # ── /ban ──────────────────────────────────────────────────
    @app_commands.command(name="ban", description="Ban a Pokemon during the ban phase")
    @require_role(ROLE_COACH)
    @app_commands.describe(pokemon="Pokemon name to ban")
    async def ban(self, interaction: discord.Interaction, pokemon: str) -> None:
        await interaction.response.defer()
        result = await self.draft_service.ban_pokemon(
            guild_id=str(interaction.guild_id),
            player_id=str(interaction.user.id),
            pokemon_name=pokemon,
        )
        if result.success:
            embed = discord.Embed(
                title=f"🚫 {result.pokemon.name} has been banned!",
                color=discord.Color.red(),
            )
            embed.set_thumbnail(url=result.pokemon.sprite_url)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ {result.error}", ephemeral=True)

    # ── /bid ──────────────────────────────────────────────────
    @app_commands.command(name="bid", description="Place a bid during auction draft")
    @require_role(ROLE_COACH)
    @app_commands.describe(amount="Bid amount")
    async def bid(self, interaction: discord.Interaction, amount: int) -> None:
        await interaction.response.defer(ephemeral=True)
        result = await self.draft_service.place_bid(
            guild_id=str(interaction.guild_id),
            player_id=str(interaction.user.id),
            amount=amount,
        )
        if result.success:
            await interaction.followup.send(
                f"Bid of **{amount}** placed! Current high: {result.current_high}",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(f"❌ {result.error}", ephemeral=True)

    # ── /draft-status ─────────────────────────────────────────
    @app_commands.command(name="draft-status", description="Show current draft status")
    @require_role(ROLE_COACH)
    async def draft_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        draft = await self.draft_service.get_active_draft(str(interaction.guild_id))
        if not draft:
            await interaction.followup.send("No active draft found.", ephemeral=True)
            return
        embed = discord.Embed(title="Draft Status", color=discord.Color.blurple())
        embed.add_field(name="Format", value=draft.format.value.title())
        embed.add_field(
            name="Mode", value=getattr(draft, "game_format", "showdown").upper()
        )
        embed.add_field(
            name="Round", value=f"{draft.current_round}/{draft.total_rounds}"
        )
        embed.add_field(name="Players", value=str(draft.player_count))
        embed.add_field(name="Total Picks", value=str(draft.total_picks))
        if getattr(draft, "tera_captains_per_team", 0) > 0:
            embed.add_field(
                name="Tera Captains",
                value=f"{draft.tera_captains_per_team}/team",
            )
        await interaction.followup.send(embed=embed)

    # ── /draft-board ──────────────────────────────────────────
    @app_commands.command(
        name="draft-board",
        description="Show the current draft board — all picks so far",
    )
    @require_role(ROLE_COACH)
    async def draft_board(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        draft = await self.draft_service.get_active_draft(str(interaction.guild_id))
        if not draft:
            await interaction.followup.send("No active draft found.", ephemeral=True)
            return
        if not draft.picks:
            await interaction.followup.send(
                "No picks have been made yet.", ephemeral=True
            )
            return

        # Group picks by player
        by_player: dict[str, list[str]] = {}
        for pick in draft.picks:
            by_player.setdefault(pick.player_id, []).append(pick.pokemon_name)

        embed = discord.Embed(
            title=f"Draft Board — Round {draft.current_round}/{draft.total_rounds}",
            color=discord.Color.blurple(),
        )
        for player_id, picks in by_player.items():
            pick_str = " · ".join(picks)
            embed.add_field(
                name=f"<@{player_id}>", value=pick_str or "No picks", inline=False
            )

        embed.set_footer(
            text=f"{draft.total_picks} picks total · On the clock: "
            + (
                f"<@{draft.current_player_id}>"
                if draft.current_player_id
                else "Draft complete"
            )
        )
        await interaction.followup.send(embed=embed)

    # ── /draft-cancel ─────────────────────────────────────────
    @app_commands.command(
        name="draft-cancel",
        description="Cancel and delete the current draft (Guildmaster only)",
    )
    @require_role(ROLE_GUILDMASTER)
    async def draft_cancel(self, interaction: discord.Interaction) -> None:
        """Shows a confirmation prompt before cancelling the draft."""
        draft = await self.draft_service.get_active_draft(str(interaction.guild_id))
        if not draft:
            await interaction.response.send_message(
                "No active draft to cancel.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Cancel Draft?",
            description=(
                f"This will permanently cancel the **{draft.format.value.title()}** draft "
                f"and remove all picks.\n\n"
                f"**{draft.total_picks}** pick(s) · **{draft.player_count}** player(s) registered\n\n"
                "This cannot be undone."
            ),
            color=discord.Color.red(),
        )

        view = DraftCancelConfirmView(
            draft_service=self.draft_service, guild_id=str(interaction.guild_id)
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @draft_setup.error
    @draft_create.error
    @draft_cancel.error
    @draft_start.error
    async def draft_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        msg = (
            str(error)
            if isinstance(error, app_commands.CheckFailure)
            else f"❌ Error: {error}"
        )
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DraftCog(bot))
