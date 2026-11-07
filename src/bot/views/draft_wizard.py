"""
Draft setup wizard views — modal/select steps and the cancel-confirm view.
Split out of cogs/draft.py; behavior unchanged.
"""

from __future__ import annotations

import discord

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
        def _safe_int(val: str, default: int) -> int:
            try:
                return int(val) if val.strip() else default
            except ValueError:
                return default

        interaction.extras["wizard_step1"] = {
            "league_name": self.league_name.value,
            "season": _safe_int(self.season.value, 1),
            "total_rounds": _safe_int(self.total_rounds.value, 6),
            "timer_seconds": _safe_int(self.timer_seconds.value, 60),
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
                discord.SelectOption(
                    label="Snake Draft",
                    value="snake",
                    description="Alternating pick order each round",
                    default=True,
                ),
                discord.SelectOption(
                    label="Auction Draft",
                    value="auction",
                    description="Bid on Pokemon with a budget",
                ),
                discord.SelectOption(
                    label="Tiered Draft",
                    value="tiered",
                    description="Point-based tier system",
                ),
                discord.SelectOption(
                    label="Custom", value="custom", description="Custom rules"
                ),
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
                discord.SelectOption(
                    label="Pokemon Showdown (Online)",
                    value="showdown",
                    description="Browser/PC battles",
                    default=True,
                ),
                discord.SelectOption(
                    label="Scarlet / Violet (Console)",
                    value="sv",
                    description="Nintendo Switch",
                ),
                discord.SelectOption(
                    label="Sword / Shield (Console)",
                    value="swsh",
                    description="Nintendo Switch",
                ),
                discord.SelectOption(
                    label="VGC (Double Battles)",
                    value="vgc",
                    description="Official VGC format",
                ),
            ],
            custom_id="game_mode_select",
        )

        async def callback(interaction: discord.Interaction) -> None:
            self.game_format = sel.values[0]
            await interaction.response.defer()

        sel.callback = callback
        return sel

    @discord.ui.button(label="Next →", style=discord.ButtonStyle.primary, row=2)
    async def next_step(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        step2 = {
            "format": self.format,
            "game_format": self.game_format,
        }
        # Prompt for player count + tera rules
        modal = DraftWizardStep3Modal(step1=self.step1, step2=step2)
        await interaction.response.send_modal(modal)


class DraftWizardStep3Modal(
    discord.ui.Modal, title="Draft Setup — Tera Captains & Players"
):
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
        def _safe_int(val: str, default: int) -> int:
            try:
                return int(val) if val.strip() else default
            except ValueError:
                return default

        max_p = min(16, max(2, _safe_int(self.max_players.value, 16)))
        pool_a = _safe_int(self.pool_a_size.value, 8)
        pool_b = max(0, max_p - pool_a)
        tera_cap = _safe_int(self.tera_captains.value, 0)
        tera_types = _safe_int(self.tera_types_per_captain.value, 1)

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
        pool_line = (
            f"Pool A: {pool_a} · Pool B: {pool_b}"
            if pool_b > 0
            else f"Single pool · {max_p} players"
        )

        embed = discord.Embed(
            title=f"✅ {config['league_name']} — Draft Created!",
            color=discord.Color.green(),
        )
        embed.add_field(name="Format", value=config["format"].title(), inline=True)
        embed.add_field(
            name="Game Mode", value=config["game_format"].upper(), inline=True
        )
        embed.add_field(name="Rounds", value=str(config["total_rounds"]), inline=True)
        embed.add_field(name="Timer", value=f"{config['timer_seconds']}s", inline=True)
        embed.add_field(name="Players", value=pool_line, inline=False)
        embed.add_field(name="Tera Captains", value=tera_line, inline=False)
        embed.set_footer(
            text=f"Draft ID: {draft.draft_id} · Settings saved to spreadsheet Setup tab"
        )

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
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
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
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(
                description="Cancelled. The draft continues.",
                color=discord.Color.green(),
            ),
            view=None,
        )
