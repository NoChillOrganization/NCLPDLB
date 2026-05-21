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

from src.bot.views.draft_view import DraftPickView
from src.data.models import DraftFormat, TeraType
from src.services.draft_service import DraftService

# ── Setup Wizard Modal ────────────────────────────────────────

class DraftSetupModal(discord.ui.Modal, title="Draft League Setup"):
    """Step 1 of the setup wizard — basic league info."""

    league_name = discord.ui.TextInput(
        label="League Name",
        placeholder="e.g. No Chill League Season 2",
        max_length=80,
    )
    season = discord.ui.TextInput(
        label="Season Number",
        placeholder="1",
        default="1",
        max_length=3,
    )
    total_rounds = discord.ui.TextInput(
        label="Draft Rounds (picks per player)",
        placeholder="6",
        default="6",
        max_length=3,
    )
    timer_seconds = discord.ui.TextInput(
        label="Pick Timer (seconds, 0 = no timer)",
        placeholder="60",
        default="60",
        max_length=4,
    )
    team_name = discord.ui.TextInput(
        label="Your Team Name",
        placeholder="e.g. Team Rocket",
        max_length=60,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Stash values on the interaction for the next step
        interaction.extras["wizard_step1"] = {
            "league_name": self.league_name.value,
            "season": int(self.season.value or 1),
            "total_rounds": int(self.total_rounds.value or 6),
            "timer_seconds": int(self.timer_seconds.value or 60),
            "commissioner_team": self.team_name.value,
        }
        # Send step 2 — format + player count
        view = DraftWizardStep2View(step1=interaction.extras["wizard_step1"])
        embed = discord.Embed(
            title="Draft Setup — Step 2 of 3",
            description=(
                "**Format & Player Settings**\n\n"
                "Choose the draft format and configure player pools below."
            ),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class DraftWizardStep2View(discord.ui.View):
    """Step 2 — format, game mode, pool sizes."""

    def __init__(self, step1: dict) -> None:
        super().__init__(timeout=300)
        self.step1 = step1
        self.format = "snake"
        self.game_format = "showdown"
        self.pool_a_size = 8
        self.pool_b_size = 8

        self.add_item(self._format_select())
        self.add_item(self._game_mode_select())

    def _format_select(self) -> discord.ui.Select:
        sel = discord.ui.Select(
            placeholder="Draft Format",
            options=[
                discord.SelectOption(label="Snake Draft", value="snake", description="Alternating pick order each round", default=True),
                discord.SelectOption(label="Auction Draft", value="auction", description="Bid on Pokemon with a budget"),
                discord.SelectOption(label="Tiered Draft", value="tiered", description="Point-based tier system"),
                discord.SelectOption(label="Custom", value="custom", description="Custom rules"),
            ],
            custom_id="format_select",
        )
        async def callback(interaction: discord.Interaction) -> None:
            self.format = sel.values[0]
            await interaction.response.defer()
        sel.callback = callback
        return sel

    def _game_mode_select(self) -> discord.ui.Select:
        sel = discord.ui.Select(
            placeholder="Game Mode",
            options=[
                discord.SelectOption(label="Pokemon Showdown (Online)", value="showdown", description="Browser/PC battles", default=True),
                discord.SelectOption(label="Scarlet / Violet (Console)", value="sv", description="Nintendo Switch"),
                discord.SelectOption(label="Sword / Shield (Console)", value="swsh", description="Nintendo Switch"),
                discord.SelectOption(label="VGC (Double Battles)", value="vgc", description="Official VGC format"),
            ],
            custom_id="game_mode_select",
        )
        async def callback(interaction: discord.Interaction) -> None:
            self.game_format = sel.values[0]
            await interaction.response.defer()
        sel.callback = callback
        return sel

    @discord.ui.button(label="Next →", style=discord.ButtonStyle.primary, row=2)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        step2 = {
            "format": self.format,
            "game_format": self.game_format,
        }
        # Prompt for player count + tera rules
        modal = DraftWizardStep3Modal(step1=self.step1, step2=step2)
        await interaction.response.send_modal(modal)


class DraftWizardStep3Modal(discord.ui.Modal, title="Draft Setup — Tera Captains & Players"):
    """Step 3 — player count, pool split, tera captain rules."""

    max_players = discord.ui.TextInput(
        label="Max Players (2–16)",
        placeholder="16",
        default="16",
        max_length=2,
    )
    pool_a_size = discord.ui.TextInput(
        label="Pool A Size (0 = single pool)",
        placeholder="8",
        default="8",
        max_length=2,
    )
    tera_captains = discord.ui.TextInput(
        label="Tera Captains Per Team (0 = disabled)",
        placeholder="1  — see #rules for Tera Captain rules",
        default="0",
        max_length=2,
    )
    tera_types_per_captain = discord.ui.TextInput(
        label="Tera Types Per Tera Captain",
        placeholder="1",
        default="1",
        max_length=2,
    )

    def __init__(self, step1: dict, step2: dict) -> None:
        super().__init__()
        self.step1 = step1
        self.step2 = step2

    async def on_submit(self, interaction: discord.Interaction) -> None:
        max_p = min(16, max(2, int(self.max_players.value or 16)))
        pool_a = int(self.pool_a_size.value or 8)
        pool_b = max(0, max_p - pool_a)
        tera_cap = int(self.tera_captains.value or 0)
        tera_types = int(self.tera_types_per_captain.value or 1)

        config = {
            **self.step1,
            **self.step2,
            "max_players": max_p,
            "pool_a_size": pool_a,
            "pool_b_size": pool_b,
            "tera_captains_per_team": tera_cap,
            "tera_types_per_captain": tera_types,
            "commissioner_id": str(interaction.user.id),
            "commissioner_name": interaction.user.display_name,
            "guild_id": str(interaction.guild_id),
        }

        # Create the draft
        svc = DraftService()
        draft = await svc.create_draft_from_config(config)

        # Build confirmation embed
        tera_line = (
            f"{tera_cap} Tera Captain(s) per team · {tera_types} tera type(s) each"
            if tera_cap > 0
            else "Disabled"
        )
        pool_line = f"Pool A: {pool_a} · Pool B: {pool_b}" if pool_b > 0 else f"Single pool · {max_p} players"

        embed = discord.Embed(
            title=f"✅ {config['league_name']} — Draft Created!",
            color=discord.Color.green(),
        )
        embed.add_field(name="Format", value=config["format"].title(), inline=True)
        embed.add_field(name="Game Mode", value=config["game_format"].upper(), inline=True)
        embed.add_field(name="Rounds", value=str(config["total_rounds"]), inline=True)
        embed.add_field(name="Timer", value=f"{config['timer_seconds']}s", inline=True)
        embed.add_field(name="Players", value=pool_line, inline=False)
        embed.add_field(name="Tera Captains", value=tera_line, inline=False)
        embed.set_footer(text=f"Draft ID: {draft.draft_id} · Settings saved to spreadsheet Setup tab")

        await interaction.response.send_message(embed=embed)

        # Also announce publicly
        if interaction.channel:
            announce = discord.Embed(
                title=f"📋 {config['league_name']} — Draft Open for Registration!",
                description=(
                    f"**Format:** {config['format'].title()} · **Mode:** {config['game_format'].upper()}\n"
                    f"**Players:** {pool_line}\n"
                    f"**Tera Captains:** {tera_line}\n\n"
                    f"Use `/draft-join` to register!\n"
                    f"Commissioner: {interaction.user.mention}"
                ),
                color=discord.Color.blue(),
            )
            await interaction.channel.send(embed=announce)


# ── Cancel Confirmation View ──────────────────────────────────

class DraftCancelConfirmView(discord.ui.View):
    """Confirmation buttons for /draft-cancel."""

    def __init__(self, draft_service: "DraftService", guild_id: str) -> None:
        super().__init__(timeout=60)
        self.draft_service = draft_service
        self.guild_id = guild_id

    @discord.ui.button(label="Yes, Cancel Draft", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.draft_service.reset_draft(self.guild_id)
        self.stop()
        embed = discord.Embed(
            title="Draft Cancelled",
            description="The draft has been cancelled and all picks have been cleared.",
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=None)

        # Announce publicly
        if interaction.channel:
            await interaction.channel.send(
                embed=discord.Embed(
                    title="Draft Cancelled",
                    description=f"The draft was cancelled by {interaction.user.mention}.",
                    color=discord.Color.red(),
                )
            )

    @discord.ui.button(label="Keep Draft", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(description="Cancelled. The draft continues.", color=discord.Color.green()),
            view=None,
        )


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
    @app_commands.checks.has_permissions(manage_guild=True)
    async def draft_setup(self, interaction: discord.Interaction) -> None:
        """Walks commissioner through all questions: players, format, game mode, tera captains."""
        await interaction.response.send_modal(DraftSetupModal())

    # ── /draft-create (quick create, for power users) ─────────
    @app_commands.command(name="draft-create", description="Quickly create a draft with options")
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
            if tera_captains > 0 else ""
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
        embed.set_footer(text=f"Draft ID: {draft.draft_id} | Use /draft-join to register")
        await interaction.followup.send(embed=embed)

    # ── /draft-join ───────────────────────────────────────────
    @app_commands.command(name="draft-join", description="Join an active draft")
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
    @app_commands.command(name="draft-start", description="Start the draft (commissioner only)")
    async def draft_start(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        draft = await self.draft_service.start_draft(
            guild_id=str(interaction.guild_id),
            commissioner_id=str(interaction.user.id),
        )
        view = DraftPickView(draft=draft, bot=self.bot)
        embed = discord.Embed(
            title="The Draft Has Started! 🎉",
            description=f"Round 1 — **{draft.current_player_id}** is on the clock!",
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
    @app_commands.describe(
        pokemon="Pokemon name to pick",
        tera_type="Tera type (required if this Pokemon is a Tera Captain)",
        is_tera_captain="Mark this Pokemon as your Tera Captain",
    )
    @app_commands.choices(tera_type=[
        app_commands.Choice(name=t.value, value=t.value) for t in TeraType
    ])
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
            embed.add_field(name="Types", value=" / ".join(t.capitalize() for t in result.pokemon.types))
            embed.add_field(name="Tier", value=result.pokemon.showdown_tier)
            if tera_type:
                captain_tag = " ⭐ **TERA CAPTAIN**" if is_tera_captain else ""
                embed.add_field(name=f"Tera Type{captain_tag}", value=tera_type, inline=False)
            embed.set_footer(text=f"Next up — Round {result.round}")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ {result.error}", ephemeral=True)

    # ── /ban ──────────────────────────────────────────────────
    @app_commands.command(name="ban", description="Ban a Pokemon during the ban phase")
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
                f"Bid of **{amount}** placed! Current high: {result.current_high}", ephemeral=True
            )
        else:
            await interaction.followup.send(f"❌ {result.error}", ephemeral=True)

    # ── /draft-status ─────────────────────────────────────────
    @app_commands.command(name="draft-status", description="Show current draft status")
    async def draft_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        draft = await self.draft_service.get_active_draft(str(interaction.guild_id))
        if not draft:
            await interaction.followup.send("No active draft found.", ephemeral=True)
            return
        embed = discord.Embed(title="Draft Status", color=discord.Color.blurple())
        embed.add_field(name="Format", value=draft.format.value.title())
        embed.add_field(name="Mode", value=getattr(draft, "game_format", "showdown").upper())
        embed.add_field(name="Round", value=f"{draft.current_round}/{draft.total_rounds}")
        embed.add_field(name="Players", value=str(draft.player_count))
        embed.add_field(name="Total Picks", value=str(draft.total_picks))
        if getattr(draft, "tera_captains_per_team", 0) > 0:
            embed.add_field(
                name="Tera Captains",
                value=f"{draft.tera_captains_per_team}/team",
            )
        await interaction.followup.send(embed=embed)

    # ── /draft-board ──────────────────────────────────────────
    @app_commands.command(name="draft-board", description="Show the current draft board — all picks so far")
    async def draft_board(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        draft = await self.draft_service.get_active_draft(str(interaction.guild_id))
        if not draft:
            await interaction.followup.send("No active draft found.", ephemeral=True)
            return
        if not draft.picks:
            await interaction.followup.send("No picks have been made yet.", ephemeral=True)
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
            embed.add_field(name=f"<@{player_id}>", value=pick_str or "No picks", inline=False)

        embed.set_footer(
            text=f"{draft.total_picks} picks total · On the clock: "
            + (f"<@{draft.current_player_id}>" if draft.current_player_id else "Draft complete")
        )
        await interaction.followup.send(embed=embed)

    # ── /draft-cancel ─────────────────────────────────────────
    @app_commands.command(name="draft-cancel", description="Cancel and delete the current draft (commissioner only)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def draft_cancel(self, interaction: discord.Interaction) -> None:
        """Shows a confirmation prompt before cancelling the draft."""
        draft = await self.draft_service.get_active_draft(str(interaction.guild_id))
        if not draft:
            await interaction.response.send_message("No active draft to cancel.", ephemeral=True)
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

        view = DraftCancelConfirmView(draft_service=self.draft_service, guild_id=str(interaction.guild_id))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @draft_setup.error
    @draft_create.error
    @draft_cancel.error
    async def draft_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Only server admins can create drafts.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Error: {error}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DraftCog(bot))
