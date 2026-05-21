"""
Sheet Cog — Discord commands that read/write directly to the Google Spreadsheet.

Commissioner-only commands (manage_guild permission):
  /sheet-standings update     — Recalculate and write standings
  /sheet-schedule add         — Add a match to the Schedule tab
  /sheet-result set           — Record a match result
  /sheet-transaction log      — Log a trade/drop/add
  /sheet-rule add / remove    — Manage the Rules tab
  /sheet-setup view           — Display current Setup tab values
  /sheet-setup edit           — Edit a setup value by key
  /sheet-player set-team      — Update a player's team name and pool
  /sheet-pokedex sync         — Push local pokemon.json to Pokedex tab
  /sheet-playoff add          — Record a playoff match

All commands respond ephemerally (visible only to the commander).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from src.data.sheets import Tab, sheets


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ── Modals ────────────────────────────────────────────────────

class ScheduleAddModal(discord.ui.Modal, title="Add Schedule Match"):
    week      = discord.ui.TextInput(label="Week Number", placeholder="1", max_length=3)
    pool      = discord.ui.TextInput(label="Pool (A or B)", placeholder="A", max_length=1, default="A")
    p1_name   = discord.ui.TextInput(label="Player 1 Name / @mention", max_length=60)
    p2_name   = discord.ui.TextInput(label="Player 2 Name / @mention", max_length=60)
    game_fmt  = discord.ui.TextInput(label="Game Format (showdown/sv/vgc…)", placeholder="showdown", max_length=20, default="showdown")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        match_id = str(uuid.uuid4())[:8]
        sheets.save_schedule_match({
            "match_id": match_id,
            "week": int(self.week.value or 1),
            "pool": self.pool.value.upper() or "A",
            "player1_name": self.p1_name.value,
            "player2_name": self.p2_name.value,
            "game_format": self.game_fmt.value or "showdown",
        })
        await interaction.response.send_message(
            f"✅ Match added to Schedule tab — Week {self.week.value}, {self.p1_name.value} vs {self.p2_name.value}",
            ephemeral=True,
        )


class ResultSetModal(discord.ui.Modal, title="Record Match Result"):
    match_id    = discord.ui.TextInput(label="Match ID (leave blank = latest)", max_length=20, required=False)
    winner_name = discord.ui.TextInput(label="Winner Name", max_length=60)
    replay_url  = discord.ui.TextInput(label="Replay URL (optional)", max_length=300, required=False)
    video_url   = discord.ui.TextInput(label="Video URL (optional)", max_length=300, required=False)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        mid = self.match_id.value.strip() or ""
        sheets.save_match_stats({
            "match_id": mid or str(uuid.uuid4())[:8],
            "winner_name": self.winner_name.value,
            "replay_url": self.replay_url.value.strip(),
            "video_url": self.video_url.value.strip(),
            "timestamp": _now(),
        })
        await interaction.response.send_message(
            f"✅ Result recorded — Winner: **{self.winner_name.value}**",
            ephemeral=True,
        )


class TransactionModal(discord.ui.Modal, title="Log Transaction"):
    txn_type      = discord.ui.TextInput(label="Type (trade/drop/add/waiver)", placeholder="trade", max_length=20)
    from_player   = discord.ui.TextInput(label="From Player Name", max_length=60)
    to_player     = discord.ui.TextInput(label="To Player Name", max_length=60)
    pokemon_given = discord.ui.TextInput(label="Pokemon Given", max_length=60)
    pokemon_recv  = discord.ui.TextInput(label="Pokemon Received", max_length=60)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        sheets.save_transaction({
            "transaction_id": str(uuid.uuid4())[:8],
            "type": self.txn_type.value or "trade",
            "from_player_name": self.from_player.value,
            "to_player_name": self.to_player.value,
            "pokemon_given": self.pokemon_given.value,
            "pokemon_received": self.pokemon_recv.value,
            "status": "pending",
            "approved_by": interaction.user.display_name,
            "timestamp": _now(),
        })
        await interaction.response.send_message(
            f"✅ Transaction logged: {self.from_player.value} ↔ {self.to_player.value} "
            f"({self.pokemon_given.value} / {self.pokemon_recv.value})",
            ephemeral=True,
        )


class RuleAddModal(discord.ui.Modal, title="Add Rule"):
    category    = discord.ui.TextInput(label="Category (e.g. Tera Captains, Trading)", max_length=60)
    title_      = discord.ui.TextInput(label="Rule Title", max_length=80)
    description = discord.ui.TextInput(label="Rule Description", style=discord.TextStyle.paragraph, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        sheets.append_row(Tab.RULES, [
            str(uuid.uuid4())[:8],
            self.category.value,
            self.title_.value,
            self.description.value,
            _now(),
        ])
        await interaction.response.send_message(
            f"✅ Rule added: **{self.title_.value}** in category *{self.category.value}*",
            ephemeral=True,
        )


class SetupEditModal(discord.ui.Modal, title="Edit Setup Value"):
    field_name  = discord.ui.TextInput(label="Field Name (see /sheet-setup view)", max_length=60)
    field_value = discord.ui.TextInput(label="New Value", max_length=200)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild_id = str(interaction.guild_id)
        row = sheets.get_league_setup(guild_id)
        if not row:
            await interaction.response.send_message("❌ No setup found for this server.", ephemeral=True)
            return
        key = self.field_name.value.strip().lower()
        if key not in row:
            await interaction.response.send_message(
                f"❌ Field '{key}' not found in Setup tab.", ephemeral=True
            )
            return
        row[key] = self.field_value.value
        sheets.save_league_setup(row)
        await interaction.response.send_message(
            f"✅ Updated **{key}** → `{self.field_value.value}`", ephemeral=True
        )


class PlayerTeamModal(discord.ui.Modal, title="Update Player Team"):
    player_id  = discord.ui.TextInput(label="Discord User ID", max_length=30)
    team_name  = discord.ui.TextInput(label="Team Name", max_length=60)
    pool       = discord.ui.TextInput(label="Pool (A or B)", max_length=1, default="A")
    logo_url   = discord.ui.TextInput(label="Logo URL (optional)", max_length=300, required=False)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        sheets.upsert_team_page({
            "player_id": self.player_id.value,
            "team_name": self.team_name.value,
            "pool": self.pool.value.upper() or "A",
            "team_logo_url": self.logo_url.value.strip(),
        })
        await interaction.response.send_message(
            f"✅ Team page updated for `{self.player_id.value}` → **{self.team_name.value}**",
            ephemeral=True,
        )


class PlayoffAddModal(discord.ui.Modal, title="Add Playoff Match"):
    round_       = discord.ui.TextInput(label="Round (e.g. Quarterfinals)", max_length=40)
    pool         = discord.ui.TextInput(label="Pool (A/B or Finals)", max_length=10, default="A")
    p1           = discord.ui.TextInput(label="Player 1 Name · Seed", placeholder="TravisT · 1", max_length=60)
    p2           = discord.ui.TextInput(label="Player 2 Name · Seed", placeholder="Rival · 2", max_length=60)
    winner       = discord.ui.TextInput(label="Winner Name (leave blank if not played)", required=False, max_length=60)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        def parse_seed(s: str) -> tuple[str, int]:
            parts = [x.strip() for x in s.split("·")]
            name = parts[0] if parts else s
            seed = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            return name, seed
        p1_name, p1_seed = parse_seed(self.p1.value)
        p2_name, p2_seed = parse_seed(self.p2.value)
        sheets.save_playoff_match({
            "bracket_id": str(uuid.uuid4())[:8],
            "round": self.round_.value,
            "pool": self.pool.value.upper(),
            "player1_name": p1_name, "player1_seed": p1_seed,
            "player2_name": p2_name, "player2_seed": p2_seed,
            "winner_name": self.winner.value.strip(),
            "timestamp": _now(),
        })
        await interaction.response.send_message(
            f"✅ Playoff match added: **{p1_name}** vs **{p2_name}** ({self.round_.value})",
            ephemeral=True,
        )


# ── Sheet Cog ─────────────────────────────────────────────────

class SheetCog(commands.Cog, name="Sheet"):
    """Commands for managing the Google Spreadsheet from Discord."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /sheet-standings update ───────────────────────────────
    @app_commands.command(
        name="sheet-standings",
        description="Recalculate and write standings to the spreadsheet",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(pool="Filter to a specific pool (A or B), or leave blank for all")
    async def sheet_standings(self, interaction: discord.Interaction, pool: str = "") -> None:
        await interaction.response.defer(ephemeral=True)
        from src.services.elo_service import EloService
        svc = EloService()
        standings = await svc.get_standings(guild_id=str(interaction.guild_id))
        filtered = standings  # EloService already returns all guild standings
        for rank, s in enumerate(filtered, 1):
            sheets.upsert_standing({
                "player_id": s.player_id,
                "player_name": s.display_name,
                "elo": s.elo,
                "wins": s.wins,
                "losses": s.losses,
                "streak": s.streak,
                "win_pct": round(s.win_rate, 2),
                "rank": rank,
            })
        await interaction.followup.send(
            f"✅ Standings updated — {len(filtered)} players written to **Standings** tab.",
            ephemeral=True,
        )

    # ── /sheet-schedule add ───────────────────────────────────
    @app_commands.command(name="sheet-schedule", description="Add a match to the Schedule tab")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sheet_schedule(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ScheduleAddModal())

    # ── /sheet-result set ─────────────────────────────────────
    @app_commands.command(name="sheet-result", description="Record a match result in the spreadsheet")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sheet_result(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ResultSetModal())

    # ── /sheet-transaction ────────────────────────────────────
    @app_commands.command(name="sheet-transaction", description="Log a trade, drop, or add to Transactions tab")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sheet_transaction(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TransactionModal())

    # ── /sheet-rule add ───────────────────────────────────────
    @app_commands.command(name="sheet-rule", description="Add a rule to the Rules tab")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sheet_rule(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RuleAddModal())

    # ── /sheet-setup view ─────────────────────────────────────
    @app_commands.command(name="sheet-setup", description="View or edit the league Setup tab")
    @app_commands.describe(action="view to read, edit to change a value")
    @app_commands.choices(action=[
        app_commands.Choice(name="View current setup", value="view"),
        app_commands.Choice(name="Edit a value", value="edit"),
    ])
    async def sheet_setup(self, interaction: discord.Interaction, action: str = "view") -> None:
        if action == "edit":
            await interaction.response.send_modal(SetupEditModal())
            return

        await interaction.response.defer(ephemeral=True)
        row = sheets.get_league_setup(str(interaction.guild_id))
        if not row:
            await interaction.followup.send("❌ No setup found. Run `/draft-setup` first.", ephemeral=True)
            return
        embed = discord.Embed(title="League Setup", color=discord.Color.blurple())
        for k, v in row.items():
            if k and v != "":
                embed.add_field(name=k, value=str(v), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /sheet-player ─────────────────────────────────────────
    @app_commands.command(name="sheet-player", description="Update a player's team name, pool, or logo in the spreadsheet")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sheet_player(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(PlayerTeamModal())

    # ── /sheet-pokedex sync ───────────────────────────────────
    @app_commands.command(name="sheet-pokedex", description="Sync local Pokemon data to the Pokedex tab (slow)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sheet_pokedex(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        import json

        from src.config import settings
        pokemon_file = settings.data_dir / "pokemon.json"
        if not pokemon_file.exists():
            await interaction.followup.send(
                "❌ `data/pokemon.json` not found. Run `python scripts/seed_pokemon_data.py` first.",
                ephemeral=True,
            )
            return
        with pokemon_file.open(encoding="utf-8") as f:
            pokemon_list = json.load(f)
        sheets.bulk_write_pokedex(pokemon_list)
        await interaction.followup.send(
            f"✅ Pokedex tab updated — {len(pokemon_list)} Pokemon synced.",
            ephemeral=True,
        )

    # ── /sheet-playoff add ────────────────────────────────────
    @app_commands.command(name="sheet-playoff", description="Add a playoff match to the Playoffs tab")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sheet_playoff(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(PlayoffAddModal())

    # ── Error handler ─────────────────────────────────────────
    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ You need **Manage Server** permission to use sheet commands."
        else:
            msg = f"❌ Error: {error}"
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except discord.NotFound:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SheetCog(bot))
