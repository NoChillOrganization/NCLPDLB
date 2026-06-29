"""
Draft View — Interactive Discord UI for picking Pokemon during a draft.
Uses discord.py Views (buttons + selects) for a rich interactive experience.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import discord

from src.data.models import Draft
from src.data.pokeapi import pokemon_db

# Service timer (DraftService._start_timer) is the single timeout authority.
# Views use timeout=None so Discord never fires on_timeout independently.
OnTimeoutCb = Callable[[str, str], Awaitable[None]]


class DraftPickView(discord.ui.View):
    """Interactive view shown during a snake/tiered draft pick.

    The service timer owns auto-skip; this view owns interactive picks only.
    Pass on_timeout_cb so make_pick re-registers the callback for the next player.
    """

    def __init__(
        self,
        draft: Draft,
        bot: discord.Client,
        on_timeout_cb: OnTimeoutCb | None = None,
    ) -> None:
        super().__init__(timeout=None)  # service timer is the sole authority
        self.draft = draft
        self.bot = bot
        self.add_item(PokemonSearchSelect(draft=draft, on_timeout_cb=on_timeout_cb))


class PokemonSearchSelect(discord.ui.Select):
    """Dropdown select for choosing a Pokemon (shows top 25 by tier)."""

    def __init__(self, draft: Draft, on_timeout_cb: OnTimeoutCb | None = None) -> None:
        self.draft = draft
        self._on_timeout_cb = on_timeout_cb
        picked_names = {p.pokemon_name.lower() for p in draft.picks}
        banned_names = {b.pokemon_name.lower() for b in draft.bans}

        # Build options from top available Pokemon
        available = [
            p
            for p in pokemon_db.all()
            if p.name.lower() not in picked_names and p.name.lower() not in banned_names
        ][:25]

        options = [
            discord.SelectOption(
                label=p.name,
                description=f"{p.type_string} | {p.showdown_tier} | Gen {p.generation}",
                value=p.name,
                emoji="⚔️" if p.base_stats.atk > 100 or p.base_stats.spa > 100 else "🛡️",
            )
            for p in available
        ]

        if not options:
            options = [discord.SelectOption(label="No Pokemon available", value="none")]

        super().__init__(
            placeholder="Search and pick a Pokemon...",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.values[0] == "none":
            await interaction.response.send_message(
                "No Pokemon available.", ephemeral=True
            )
            return

        if str(interaction.user.id) != self.draft.current_player_id:
            await interaction.response.send_message(
                "It's not your turn!", ephemeral=True
            )
            return

        from src.services.draft_service import DraftService

        svc = DraftService()
        result = await svc.make_pick(
            guild_id=self.draft.guild_id,
            player_id=str(interaction.user.id),
            pokemon_name=self.values[0],
            on_timeout=self._on_timeout_cb,  # thread callback to next service timer
        )

        if result.success:
            embed = discord.Embed(
                title=f"{interaction.user.display_name} picked {result.pokemon.name}!",
                color=discord.Color.green(),
            )
            embed.set_thumbnail(url=result.pokemon.sprite_url)
            embed.add_field(name="Types", value=result.pokemon.type_string)
            embed.add_field(name="Tier", value=result.pokemon.showdown_tier)
            embed.set_footer(text=f"Next: {result.next_player_name}")
            await interaction.response.edit_message(embed=embed, view=None)

            # M4: post a fresh interactive view for the next player
            from src.services.draft_service import DraftStatus

            updated = svc.get_draft(self.draft.guild_id)
            if (
                updated
                and updated.status == DraftStatus.ACTIVE
                and updated.current_player_id
                and interaction.channel
            ):
                next_embed = discord.Embed(
                    title=f"<@{updated.current_player_id}> — you're on the clock!",
                    description=f"Round {updated.current_round} · Pick your Pokémon.",
                    color=discord.Color.blue(),
                )
                next_view = DraftPickView(
                    draft=updated,
                    bot=self.view.bot,
                    on_timeout_cb=self._on_timeout_cb,
                )
                await interaction.channel.send(embed=next_embed, view=next_view)
        else:
            await interaction.response.send_message(
                f"Error: {result.error}", ephemeral=True
            )


class AuctionView(discord.ui.View):
    """Auction draft — bid buttons with budget display."""

    def __init__(
        self,
        draft: Draft,
        nominated_pokemon: str,
        current_high: int,
        current_bidder: str,
    ) -> None:
        super().__init__(timeout=30)
        self.draft = draft
        self.nominated_pokemon = nominated_pokemon
        self.current_high = current_high
        self.current_bidder = current_bidder

    @discord.ui.button(label="+10", style=discord.ButtonStyle.primary)
    async def bid_10(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._place_bid(interaction, self.current_high + 10)

    @discord.ui.button(label="+50", style=discord.ButtonStyle.primary)
    async def bid_50(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._place_bid(interaction, self.current_high + 50)

    @discord.ui.button(label="+100", style=discord.ButtonStyle.primary)
    async def bid_100(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._place_bid(interaction, self.current_high + 100)

    @discord.ui.button(label="Pass", style=discord.ButtonStyle.secondary)
    async def pass_bid(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_message(
            "You passed on this Pokemon.", ephemeral=True
        )

    async def _place_bid(self, interaction: discord.Interaction, amount: int) -> None:
        from src.services.draft_service import DraftService

        svc = DraftService()
        result = await svc.place_bid(
            guild_id=self.draft.guild_id,
            player_id=str(interaction.user.id),
            amount=amount,
        )
        if result.success:
            self.current_high = amount
            self.current_bidder = interaction.user.display_name
            embed = discord.Embed(
                title=f"Auction: {self.nominated_pokemon}",
                description=f"Current high bid: **{amount}** by **{self.current_bidder}**",
                color=discord.Color.gold(),
            )
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message(
                f"Bid failed: {result.error}", ephemeral=True
            )


class BanPhaseView(discord.ui.View):
    """Ban phase — select Pokemon to ban before drafting starts."""

    def __init__(self, draft: Draft) -> None:
        super().__init__(timeout=120)
        self.draft = draft
        self.add_item(BanSelect(draft=draft))


class BanSelect(discord.ui.Select):
    def __init__(self, draft: Draft) -> None:
        self.draft = draft
        top_pokemon = sorted(
            pokemon_db.all(), key=lambda p: p.base_stats.total, reverse=True
        )[:25]
        options = [
            discord.SelectOption(
                label=p.name,
                description=f"{p.showdown_tier} | BST: {p.base_stats.total}",
                value=p.name,
            )
            for p in top_pokemon
        ]
        super().__init__(placeholder="Choose a Pokemon to ban...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        user_id = str(interaction.user.id)
        # C4: only draft participants may ban
        if user_id not in self.draft.player_order:
            await interaction.response.send_message(
                "❌ Only draft participants can ban Pokémon.", ephemeral=True
            )
            return
        from src.services.draft_service import DraftService

        svc = DraftService()
        result = await svc.ban_pokemon(
            guild_id=self.draft.guild_id,
            player_id=user_id,
            pokemon_name=self.values[0],
        )
        if result.success:
            await interaction.response.send_message(
                f"**{self.values[0]}** has been banned!", ephemeral=False
            )
        else:
            await interaction.response.send_message(
                f"Ban failed: {result.error}", ephemeral=True
            )
