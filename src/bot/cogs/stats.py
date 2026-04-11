"""
Stats Cog — Team analytics, battle simulation, ELO, Showdown replays, video uploads, /spar.
"""
import asyncio
import logging
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from src.data.pokeapi import pokemon_db
from src.services.analytics_service import AnalyticsService
from src.services.battle_sim import BattleSimService
from src.services.elo_service import EloService
from src.services.video_service import VideoService

log = logging.getLogger(__name__)

REPLAY_DOMAIN = "replay.pokemonshowdown.com"

# ── Supported spar formats (must have a trained model) ────────────────────────
SPAR_FORMATS = [
    # Random Battle
    "gen9randombattle",
    "gen9monorandom",
    "gen9randomdoublesbattle",
    "gen7randombattle",
    "gen6randombattle",
    # Smogon Singles
    "gen9ou",
    "gen9ubers",
    "gen9uu",
    "gen9ru",
    "gen9nu",
    "gen9pu",
    "gen9zu",
    "gen9lc",
    "gen9monotype",
    "gen9nationaldex",
    "gen9anythinggoes",
    # Smogon Doubles
    "gen9doublesou",
    "gen9doublesubers",
    "gen9doublesuu",
    "gen9doublesnu",
    # VGC 2025
    "gen9vgc2025regg",
    "gen9vgc2025regh",
    "gen9vgc2025regi",
    "gen9vgc2025reggbo3",
    "gen9vgc2025reghbo3",
    "gen9vgc2025regibo3",
    # VGC 2026
    "gen9vgc2026regf",
    "gen9vgc2026regi",
    "gen9vgc2026regfbo3",
    "gen9vgc2026regibo3",
    # Champions
    "gen9championsou",
    "gen9championsbssregma",
    "gen9championsvgc2026regma",
    "gen9championsvgc2026regmabo3",
]

_FORMAT_DISPLAY = {
    # Random Battle
    "gen9randombattle"       : "Gen 9 Random Battle",
    "gen9monorandom"         : "Gen 9 Monotype Random",
    "gen9randomdoublesbattle": "Gen 9 Random Doubles",
    "gen7randombattle"       : "Gen 7 Random Battle",
    "gen6randombattle"       : "Gen 6 Random Battle",
    # Smogon Singles
    "gen9ou"                 : "Gen 9 OU",
    "gen9ubers"              : "Gen 9 Ubers",
    "gen9uu"                 : "Gen 9 UU",
    "gen9ru"                 : "Gen 9 RU",
    "gen9nu"                 : "Gen 9 NU",
    "gen9pu"                 : "Gen 9 PU",
    "gen9zu"                 : "Gen 9 ZU",
    "gen9lc"                 : "Gen 9 LC",
    "gen9monotype"           : "Gen 9 Monotype",
    "gen9nationaldex"        : "Gen 9 National Dex",
    "gen9anythinggoes"       : "Gen 9 Anything Goes",
    # Smogon Doubles
    "gen9doublesou"          : "Gen 9 Doubles OU",
    "gen9doublesubers"       : "Gen 9 Doubles Ubers",
    "gen9doublesuu"          : "Gen 9 Doubles UU",
    "gen9doublesnu"          : "Gen 9 Doubles NU",
    # VGC 2025
    "gen9vgc2025regg"        : "VGC 2025 Reg G",
    "gen9vgc2025regh"        : "VGC 2025 Reg H",
    "gen9vgc2025regi"        : "VGC 2025 Reg I",
    "gen9vgc2025reggbo3"     : "VGC 2025 Reg G (Bo3)",
    "gen9vgc2025reghbo3"     : "VGC 2025 Reg H (Bo3)",
    "gen9vgc2025regibo3"     : "VGC 2025 Reg I (Bo3)",
    # VGC 2026
    "gen9vgc2026regf"             : "VGC 2026 Reg F",
    "gen9vgc2026regi"             : "VGC 2026 Reg I",
    "gen9vgc2026regfbo3"          : "VGC 2026 Reg F (Bo3)",
    "gen9vgc2026regibo3"          : "VGC 2026 Reg I (Bo3)",
    # Champions
    "gen9championsou"             : "Champions OU",
    "gen9championsbssregma"       : "Champions BSS Reg M-A",
    "gen9championsvgc2026regma"   : "Champions VGC 2026 Reg M-A",
    "gen9championsvgc2026regmabo3": "Champions VGC 2026 Reg M-A (Bo3)",
}


async def spar_format_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Dynamic autocomplete for /spar format — no 25-choice limit."""
    needle = current.lower()
    matches = [
        app_commands.Choice(name=_FORMAT_DISPLAY.get(fmt, fmt), value=fmt)
        for fmt in SPAR_FORMATS
        if needle in fmt.lower() or needle in _FORMAT_DISPLAY.get(fmt, "").lower()
    ]
    return matches[:25]


class StatsCog(commands.Cog, name="Stats"):
    """Analytics, battle simulation, and match management commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.analytics = AnalyticsService()
        self.battle_sim = BattleSimService()
        self.elo = EloService()

    # ── /analysis ─────────────────────────────────────────────
    @app_commands.command(name="analysis", description="Full team analysis: coverage, weaknesses, roles")
    @app_commands.describe(user="Player to analyze (leave blank for yourself)")
    async def analysis(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        await interaction.response.defer()
        target = user or interaction.user
        report = await self.analytics.analyze_team(
            guild_id=str(interaction.guild_id),
            player_id=str(target.id),
        )
        embed = discord.Embed(
            title=f"Team Analysis — {target.display_name}",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Type Coverage", value=report.coverage_summary, inline=False)
        embed.add_field(name="Weaknesses", value=report.weakness_summary, inline=False)
        embed.add_field(name="Speed Tiers", value=report.speed_summary, inline=False)
        embed.add_field(name="Team Archetype", value=report.archetype, inline=True)
        embed.add_field(name="Threat Score", value=str(report.threat_score), inline=True)
        embed.set_footer(text="Based on Smogon OU + VGC competitive data")
        await interaction.followup.send(embed=embed)

    # ── /matchup ──────────────────────────────────────────────
    @app_commands.command(name="matchup", description="Compare two teams head-to-head")
    @app_commands.describe(
        player1="First player",
        player2="Second player",
    )
    async def matchup(
        self,
        interaction: discord.Interaction,
        player1: discord.Member,
        player2: discord.Member,
    ) -> None:
        await interaction.response.defer()
        result = await self.battle_sim.compare_teams(
            guild_id=str(interaction.guild_id),
            player1_id=str(player1.id),
            player2_id=str(player2.id),
        )
        embed = discord.Embed(
            title=f"Head-to-Head: {player1.display_name} vs {player2.display_name}",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Advantage", value=result.advantage_summary, inline=False)
        embed.add_field(name=f"{player1.display_name} Threats", value=result.p1_threats, inline=True)
        embed.add_field(name=f"{player2.display_name} Threats", value=result.p2_threats, inline=True)
        embed.add_field(name="Type Advantages", value=result.type_summary, inline=False)
        embed.set_footer(text="Simulation based on base stats + type matchups. Not a guarantee!")
        await interaction.followup.send(embed=embed)

    # ── /standings ────────────────────────────────────────────
    @app_commands.command(name="standings", description="Show league standings and ELO ratings")
    async def standings(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        standings = await self.elo.get_standings(guild_id=str(interaction.guild_id))
        if not standings:
            await interaction.followup.send("No standings data yet.", ephemeral=True)
            return
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, player in enumerate(standings):
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(
                f"{medal} **{player.display_name}** — {player.wins}W/{player.losses}L — ELO: **{player.elo}**"
            )
        embed = discord.Embed(
            title="League Standings",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        await interaction.followup.send(embed=embed)

    # ── /replay submit ────────────────────────────────────────
    @app_commands.command(name="replay", description="Submit a Pokemon Showdown replay link for a match")
    @app_commands.describe(url="Pokemon Showdown replay URL (replay.pokemonshowdown.com/...)")
    async def replay(self, interaction: discord.Interaction, url: str) -> None:
        await interaction.response.defer()
        if REPLAY_DOMAIN not in url:
            await interaction.followup.send(f"Please provide a valid {REPLAY_DOMAIN} link.", ephemeral=True)
            return
        result = await self.battle_sim.parse_replay(
            guild_id=str(interaction.guild_id),
            player_id=str(interaction.user.id),
            replay_url=url,
        )
        if result.success:
            embed = discord.Embed(
                title="Replay Recorded!",
                description=f"**Winner:** {result.winner_name}\n**Turns:** {result.turns}",
                color=discord.Color.green(),
                url=url,
            )
            embed.add_field(name="Player 1 Team", value=", ".join(result.p1_team), inline=False)
            embed.add_field(name="Player 2 Team", value=", ".join(result.p2_team), inline=False)
            embed.set_footer(text="Match result recorded. ELO updated.")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"Replay error: {result.error}", ephemeral=True)

    # ── /match upload ─────────────────────────────────────────
    @app_commands.command(name="match-upload", description="Upload a capture card video of your match")
    @app_commands.describe(
        video="Video file (MP4, MOV, AVI) — max 25MB via Discord",
        opponent="Your opponent in this match",
        notes="Optional notes about the match",
    )
    async def match_upload(
        self,
        interaction: discord.Interaction,
        video: discord.Attachment,
        opponent: discord.Member,
        notes: str = "",
    ) -> None:
        await interaction.response.defer()
        allowed_types = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/avi"}
        if video.content_type not in allowed_types:
            await interaction.followup.send(
                "Unsupported file type. Please upload MP4, MOV, or AVI.", ephemeral=True
            )
            return
        video_svc = VideoService()
        result = await video_svc.upload_match_video(
            guild_id=str(interaction.guild_id),
            uploader_id=str(interaction.user.id),
            opponent_id=str(opponent.id),
            attachment=video,
            notes=notes,
        )
        if result.success:
            embed = discord.Embed(
                title="Match Video Uploaded!",
                description=f"**vs {opponent.display_name}**\n{notes}",
                color=discord.Color.green(),
            )
            embed.add_field(name="Video URL", value=result.public_url or "Private (league members only)")
            embed.set_footer(text=f"Video ID: {result.video_id}")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"Upload failed: {result.error}", ephemeral=True)


    # ── /pokemon ──────────────────────────────────────────────
    @app_commands.command(name="pokemon", description="Look up a Pokemon's stats and competitive info")
    @app_commands.describe(name="Pokemon name (e.g. Garchomp, Rotom-Wash)")
    async def pokemon_lookup(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer()
        mon = pokemon_db.find(name)
        if not mon:
            await interaction.followup.send(
                f"Pokemon **{name}** not found. Check spelling or run `/sheet-pokedex` to sync data.",
                ephemeral=True,
            )
            return
        stats = mon.base_stats
        embed = discord.Embed(
            title=f"#{mon.national_dex} {mon.name}",
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=mon.sprite_url)
        embed.add_field(name="Type", value=mon.type_string, inline=True)
        embed.add_field(name="Generation", value=str(mon.generation), inline=True)
        embed.add_field(name="Tier", value=mon.showdown_tier, inline=True)
        bst = stats.total
        stat_line = (
            f"HP {stats.hp} · Atk {stats.atk} · Def {stats.def_} · "
            f"SpA {stats.spa} · SpD {stats.spd} · Spe {stats.spe} · **BST {bst}**"
        )
        embed.add_field(name="Base Stats", value=stat_line, inline=False)
        if mon.abilities:
            embed.add_field(name="Abilities", value=", ".join(mon.abilities), inline=True)
        if mon.hidden_ability:
            embed.add_field(name="Hidden Ability", value=mon.hidden_ability, inline=True)
        flags = []
        if mon.is_legendary:
            flags.append("Legendary")
        if mon.is_mythical:
            flags.append("Mythical")
        if mon.is_paradox:
            flags.append("Paradox")
        if flags:
            embed.add_field(name="Classification", value=" · ".join(flags), inline=False)
        console = mon.console_legal
        legal_line = " · ".join(
            f"{k.upper()} {'✅' if v else '❌'}"
            for k, v in console.items()
        )
        embed.add_field(name="Console Legality", value=legal_line, inline=False)
        embed.set_footer(text=f"Speed tier: {mon.speed_tier}")
        await interaction.followup.send(embed=embed)


    # ── /spar ─────────────────────────────────────────────────
    @app_commands.command(
        name="spar",
        description="Challenge the bot to a practice battle on Pokemon Showdown",
    )
    @app_commands.describe(
        showdown_name="Your Pokemon Showdown username",
        format="Battle format (default: gen9randombattle)",
    )
    @app_commands.autocomplete(format=spar_format_autocomplete)
    async def spar(
        self,
        interaction: discord.Interaction,
        showdown_name: str,
        format: str | None = None,
    ) -> None:
        await interaction.response.defer(thinking=True)

        fmt = format if format else "gen9randombattle"

        # Check if a trained model is available for this format
        from src.ml.showdown_player import best_model_for_format
        model_path = best_model_for_format(fmt)

        if model_path is None:
            embed = discord.Embed(
                title="No Trained Model Available",
                description=(
                    f"The bot hasn't been trained for **{fmt}** yet.\n\n"
                    "Available formats after training:\n"
                    + "\n".join(f"• `{f}`" for f in SPAR_FORMATS)
                ),
                color=discord.Color.orange(),
            )
            embed.set_footer(text="Run: python -m src.ml.train_policy --format gen9randombattle")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Bot Showdown credentials from settings
        try:
            from src.config import settings
            bot_username = getattr(settings, "showdown_username", None)
            bot_password = getattr(settings, "showdown_password", None)
        except Exception:
            bot_username = None
            bot_password = None

        if not bot_username or not bot_password:
            # No live bot configured — give instructions instead
            embed = discord.Embed(
                title="Spar with the AI Bot",
                description=(
                    f"The bot AI is trained and ready for **{fmt}**!\n\n"
                    "To spar, run the bot player locally and challenge it on Showdown:"
                ),
                color=discord.Color.blurple(),
            )
            embed.add_field(
                name="Step 1 — Start the bot player",
                value=(
                    f"```\npython -m src.ml.showdown_player \\\n"
                    f"  --model {model_path} \\\n"
                    f"  --format {fmt} \\\n"
                    f"  --username YOUR_BOT_ACCOUNT \\\n"
                    f"  --password YOUR_BOT_PASSWORD \\\n"
                    f"  --accept-challenges\n```"
                ),
                inline=False,
            )
            embed.add_field(
                name="Step 2 — Send a challenge",
                value=(
                    f"On Pokemon Showdown, challenge the bot's account in format `{fmt}`."
                ),
                inline=False,
            )
            embed.add_field(
                name="Your Showdown name",
                value=f"`{showdown_name}`",
                inline=True,
            )
            embed.add_field(
                name="Model",
                value=f"`{model_path.name}`",
                inline=True,
            )
            embed.set_footer(
                text="Configure SHOWDOWN_USERNAME and SHOWDOWN_PASSWORD in .env for live challenges."
            )
            await interaction.followup.send(embed=embed)
            return

        # Live mode — actually send the challenge
        embed_waiting = discord.Embed(
            title="Challenging you on Showdown...",
            description=(
                f"The bot (**{bot_username}**) is sending you a challenge in **{fmt}**.\n"
                f"Please check Pokemon Showdown, **{showdown_name}**."
            ),
            color=discord.Color.yellow(),
        )
        embed_waiting.set_footer(text="Battle will begin once you accept. Timeout: 5 min.")
        await interaction.followup.send(embed=embed_waiting)

        # Run the challenge in the background so Discord doesn't time out
        asyncio.create_task(
            _run_spar_challenge(
                interaction=interaction,
                model_path=model_path,
                fmt=fmt,
                bot_username=bot_username,
                bot_password=bot_password,
                target_username=showdown_name,
            )
        )

    @spar.error
    async def spar_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        msg = str(error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Spar error: {msg}", ephemeral=True)
            else:
                await interaction.followup.send(f"Spar error: {msg}", ephemeral=True)
        except discord.NotFound:
            log.warning("[/spar] Interaction expired before error could be reported: %s", msg)


async def _run_spar_challenge(
    interaction: discord.Interaction,
    model_path: Path,
    fmt: str,
    bot_username: str,
    bot_password: str,
    target_username: str,
) -> None:
    """Background task: run a live spar challenge and post the result."""
    try:
        from src.ml.showdown_player import BotChallenger
        challenger = BotChallenger(
            model_path=model_path,
            fmt=fmt,
            username=bot_username,
            password=bot_password,
            server="showdown",
        )
        result = await challenger.challenge_user(target_username, timeout=360)

        winner_label = (
            f"**{bot_username}** (Bot)" if result["winner"] == "bot"
            else f"**{target_username}** (You)" if result["winner"] == "opponent"
            else "Tie"
        )
        color = (
            discord.Color.red() if result["winner"] == "bot"
            else discord.Color.green() if result["winner"] == "opponent"
            else discord.Color.greyple()
        )
        embed = discord.Embed(
            title="Spar Complete!",
            description=f"Winner: {winner_label}",
            color=color,
        )
        embed.add_field(name="Format", value=fmt, inline=True)
        embed.add_field(name="Turns", value=str(result["turns"]), inline=True)
        embed.set_footer(text="GG! Use /analysis to review your team's strengths and weaknesses.")
        await interaction.followup.send(embed=embed)

    except Exception as exc:
        log.error(f"[/spar] Live challenge failed: {exc}", exc_info=True)
        await interaction.followup.send(
            f"The spar battle encountered an error: `{exc}`\n"
            "Make sure your Showdown username is correct and you are online.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatsCog(bot))
