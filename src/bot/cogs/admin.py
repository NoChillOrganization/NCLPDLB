"""
Admin Cog — Commissioner and admin override commands.
"""

import asyncio
import logging
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from src.bot.permissions import ROLE_GUILDMASTER, ROLE_MOD, require_role
from src.config import settings
from src.ml.train_all import TRAINING_MAP
from src.services.draft_service import DraftService

# Re-exported for backward compatibility: training orchestration logic lives in
# admin_training.py (extracted to keep this file under the 800-line guideline),
# but tests and other modules still import some of these names from here.
from src.bot.cogs.admin_training import (  # noqa: F401
    ConfirmResetView,
    _build_progress_embed,
    _build_queue_embed,
    _chunk_lines,
    _model_exists,
    _pull_models,
    _run_training,
    _run_training_all,
    _try_edit,
)

log = logging.getLogger(__name__)

# Retain strong references to fire-and-forget tasks so GC cannot cancel them (M8)
_background_tasks: set[asyncio.Task] = set()


def _create_background_task(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    task.add_done_callback(_log_task_exception)
    return task


def _log_task_exception(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.error(
            "Background task raised an exception: %s",
            task.exception(),
            exc_info=task.exception(),
        )


def is_commissioner():
    """Alias for require_role(ROLE_GUILDMASTER) — kept for backward compatibility."""
    return require_role(ROLE_GUILDMASTER)


class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.draft_service = DraftService()

    @app_commands.command(
        name="admin-skip", description="Force-skip a player's turn (moderator+)"
    )
    @app_commands.describe(user="Player to skip")
    @require_role(ROLE_MOD)
    async def admin_skip(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        await interaction.response.defer()
        result = await self.draft_service.force_skip(
            guild_id=str(interaction.guild_id),
            player_id=str(user.id),
        )
        await interaction.followup.send(
            f"Skipped {user.display_name}'s turn. Next: {result.next_player}"
        )

    @app_commands.command(
        name="admin-pause", description="Pause the active draft (moderator+)"
    )
    @require_role(ROLE_MOD)
    async def admin_pause(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self.draft_service.pause_draft(str(interaction.guild_id))
        await interaction.followup.send("Draft paused.")

    @app_commands.command(
        name="admin-resume", description="Resume a paused draft (moderator+)"
    )
    @require_role(ROLE_MOD)
    async def admin_resume(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self.draft_service.resume_draft(str(interaction.guild_id))
        await interaction.followup.send("Draft resumed!")

    @app_commands.command(
        name="admin-override-pick",
        description="Override a pick in-memory (moderator+) — ⚠ run /sheet-result to persist",
    )
    @app_commands.describe(
        user="Player whose pick to change",
        old_pokemon="Pokemon to remove",
        new_pokemon="Pokemon to add",
    )
    @require_role(ROLE_MOD)
    async def admin_override_pick(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        old_pokemon: str,
        new_pokemon: str,
    ) -> None:
        await interaction.response.defer()
        await self.draft_service.override_pick(
            guild_id=str(interaction.guild_id),
            player_id=str(user.id),
            old_pokemon=old_pokemon,
            new_pokemon=new_pokemon,
        )
        await interaction.followup.send(
            f"Override: removed **{old_pokemon}**, added **{new_pokemon}** for {user.display_name}."
        )

    # ── /admin-sync ────────────────────────────────────────────
    @app_commands.command(
        name="admin-sync",
        description="Sync slash commands with Discord (push new/updated commands)",
    )
    @app_commands.describe(
        scope="guild = instant (test guild only), global = up to 1 hour to propagate everywhere"
    )
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="guild (instant)", value="guild"),
            app_commands.Choice(name="global (up to 1 hour)", value="global"),
        ]
    )
    @is_commissioner()
    async def admin_sync(
        self,
        interaction: discord.Interaction,
        scope: app_commands.Choice[str] = None,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        use_guild = (scope is None) or (scope.value == "guild")

        try:
            if use_guild and interaction.guild:
                # copy_global_to ensures global commands are in the guild namespace before sync
                interaction.client.tree.copy_global_to(guild=interaction.guild)
                synced = await interaction.client.tree.sync(guild=interaction.guild)
                await interaction.followup.send(
                    f"✅ Synced **{len(synced)} command(s)** to this server (instant).",
                    ephemeral=True,
                )
            else:
                synced = await interaction.client.tree.sync()
                await interaction.followup.send(
                    f"✅ Synced **{len(synced)} command(s)** globally. May take up to 1 hour to appear.",
                    ephemeral=True,
                )
        except discord.HTTPException as exc:
            retry = getattr(exc, "retry_after", None)
            hint = f" Retry after {retry:.0f}s." if retry else ""
            await interaction.followup.send(
                f"❌ Sync failed (HTTP {exc.status}).{hint}\n`{exc.text}`",
                ephemeral=True,
            )
        except Exception as exc:
            await interaction.followup.send(f"❌ Sync error: {exc}", ephemeral=True)

    # ── /admin-update ──────────────────────────────────────────
    @app_commands.command(
        name="admin-update",
        description="Pull latest code from git, reload all cogs, and re-sync commands",
    )
    @is_commissioner()
    async def admin_update(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)

        project_root = Path(__file__).parents[3]
        lines: list[str] = []

        # ── 1. git pull ─────────────────────────────────────────
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "pull",
                "--ff-only",
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            git_out = (stdout or b"").decode(errors="replace").strip()
            ok = proc.returncode == 0
            lines.append(f"{'✅' if ok else '❌'} **git pull**\n```\n{git_out}\n```")
        except asyncio.TimeoutError:
            lines.append("❌ **git pull** timed out after 30 s")
            ok = False
        except Exception as exc:
            lines.append(f"❌ **git pull** failed: `{exc}`")
            ok = False

        # ── 2. Reload cogs ──────────────────────────────────────
        from src.bot.main import COGS

        reload_results: list[str] = []
        for cog in COGS:
            try:
                await interaction.client.reload_extension(cog)
                reload_results.append(f"✅ `{cog}`")
            except Exception as exc:
                reload_results.append(f"❌ `{cog}`: {exc}")
        lines.append("**Cogs reloaded:**\n" + "\n".join(reload_results))

        # ── 3. Re-sync commands ─────────────────────────────────
        try:
            if interaction.guild:
                interaction.client.tree.copy_global_to(guild=interaction.guild)
                synced = await interaction.client.tree.sync(guild=interaction.guild)
                lines.append(
                    f"✅ **Commands synced** — {len(synced)} command(s) to this server"
                )
            else:
                synced = await interaction.client.tree.sync()
                lines.append(
                    f"✅ **Commands synced** — {len(synced)} command(s) globally"
                )
        except discord.HTTPException as exc:
            retry = getattr(exc, "retry_after", None)
            hint = f" Retry after {retry:.0f}s." if retry else ""
            lines.append(
                f"❌ **Command sync failed** (HTTP {exc.status}).{hint} `{exc.text}`"
            )
        except Exception as exc:
            lines.append(f"❌ **Command sync failed**: `{exc}`")

        await interaction.followup.send("\n\n".join(lines), ephemeral=True)

    # ── /admin-reset ───────────────────────────────────────────
    @app_commands.command(
        name="admin-reset", description="Reset the current draft (CANNOT BE UNDONE)"
    )
    @is_commissioner()
    async def admin_reset(self, interaction: discord.Interaction) -> None:
        # Confirm via button
        view = ConfirmResetView(
            guild_id=str(interaction.guild_id), draft_service=self.draft_service
        )
        await interaction.response.send_message(
            "⚠️ Are you sure you want to reset the draft? This cannot be undone.",
            view=view,
            ephemeral=True,
        )

    # ── /admin-train ───────────────────────────────────────────
    @app_commands.command(
        name="admin-train",
        description="Train the AI bot for a battle format",
    )
    @app_commands.describe(
        format="Format to train (e.g. gen9randombattle)",
        timesteps="Training steps — higher = stronger but slower (default: 500000)",
        force="Re-train even if a model already exists",
    )
    @is_commissioner()
    async def admin_train(
        self,
        interaction: discord.Interaction,
        format: str,
        timesteps: int = 500_000,
        force: bool = False,
    ) -> None:
        await interaction.response.defer(thinking=True)

        if format not in TRAINING_MAP:
            await interaction.followup.send(
                f"Unknown format `{format}`. Check `/spar` autocomplete for valid formats.",
                ephemeral=True,
            )
            return

        results_dir = Path(__file__).parents[3] / "data" / "ml" / "results"
        if not force and _model_exists(results_dir, format):
            await interaction.followup.send(
                f"Model for `{format}` already exists. Use `force: True` to retrain.",
                ephemeral=True,
            )
            return

        status_msg: discord.Message | None = None
        try:
            status_msg = await interaction.followup.send(
                embed=_build_progress_embed(format, 0, timesteps, 1),
                wait=True,
            )
        except discord.NotFound:
            log.warning(
                "[admin-train] followup.send got 10062 (interaction expired); continuing without channel embed"
            )
            try:
                await interaction.user.send(
                    "⚠️ Couldn't post the training status embed (Discord interaction expired), "
                    "but training is starting. You'll receive a DM when done."
                )
            except Exception:
                log.debug("Best-effort Discord notification failed", exc_info=True)

        _create_background_task(
            _run_training(
                interaction,
                format,
                timesteps,
                force,
                channel_msg=status_msg,
                server="showdown",
            )
        )

    @admin_train.autocomplete("format")
    async def admin_train_format_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        needle = current.lower()
        return [
            app_commands.Choice(name=fmt, value=fmt)
            for fmt in TRAINING_MAP
            if needle in fmt.lower()
        ][:25]

    # ── /admin-train-all ───────────────────────────────────────
    @app_commands.command(
        name="admin-train-all",
        description="Train AI models for all formats sequentially",
    )
    @app_commands.describe(
        timesteps="Training steps per format (default: 500000)",
        skip_existing="Skip formats that already have a final_model.zip (default: True)",
    )
    @is_commissioner()
    async def admin_train_all(
        self,
        interaction: discord.Interaction,
        timesteps: int = 500_000,
        skip_existing: bool = True,
    ) -> None:
        await interaction.response.defer(thinking=True)

        total = len([f for f, e in TRAINING_MAP.items() if e[0] is not None])
        results_dir = Path(__file__).parents[3] / "data" / "ml" / "results"
        already_done = sum(
            1
            for fmt in TRAINING_MAP
            if skip_existing and _model_exists(results_dir, fmt)
        )
        to_train = total - already_done

        status_msg: discord.Message | None = None
        try:
            status_msg = await interaction.followup.send(
                embed=_build_queue_embed(to_train, already_done, timesteps),
                wait=True,
            )
        except discord.NotFound:
            log.warning(
                "[admin-train-all] followup.send got 10062 (interaction expired); continuing without channel embed"
            )
            try:
                await interaction.user.send(
                    "⚠️ Couldn't post the train-all status embed in the channel (Discord interaction expired), "
                    "but training is starting. You'll receive DM updates per format."
                )
            except Exception:
                log.debug("Best-effort Discord notification failed", exc_info=True)

        _create_background_task(
            _run_training_all(
                interaction,
                timesteps,
                force=not skip_existing,
                channel_msg=status_msg,
                server="showdown",
            )
        )

    # ── /admin-pull-models ────────────────────────────────────
    @app_commands.command(
        name="admin-pull-models",
        description="Download trained models from the latest GitHub Release into data/ml/policy/",
    )
    @app_commands.describe(
        format="Format to download, or leave blank to download all available",
        release="Release tag (e.g. ml-models-r5-a1); blank = newest ml-models-r* release (see /admin-list-releases). Requires GITHUB_TOKEN.",
    )
    @is_commissioner()
    async def admin_pull_models(
        self,
        interaction: discord.Interaction,
        format: str | None = None,
        release: str | None = None,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        _create_background_task(
            _pull_models(interaction, fmt=format, release_tag=release)
        )

    @admin_pull_models.autocomplete("format")
    async def admin_pull_models_format_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        needle = current.lower()
        return [
            app_commands.Choice(name=fmt, value=fmt)
            for fmt in TRAINING_MAP
            if needle in fmt.lower()
        ][:25]

    # ── /admin-showdown-check ──────────────────────────────────
    @app_commands.command(
        name="admin-showdown-check",
        description="Check if the local Showdown server is running (moderator+)",
    )
    @require_role(ROLE_MOD)
    async def admin_showdown_check(self, interaction: discord.Interaction) -> None:
        import socket

        await interaction.response.defer(thinking=True, ephemeral=True)

        host, port = "127.0.0.1", 8000
        reachable = False
        try:

            def _check():
                with socket.create_connection((host, port), 3):
                    pass

            await asyncio.get_running_loop().run_in_executor(None, _check)
            reachable = True
        except OSError:
            pass

        if reachable:
            await interaction.followup.send(
                f"✅ Showdown server is reachable at `http://localhost:{port}` — open that URL in your browser.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"❌ Showdown server is **NOT** running on port `{port}`.\n"
                "Start it with:\n"
                "```\ncd pokemon-showdown && node pokemon-showdown start --no-security\n```",
                ephemeral=True,
            )

    # ── /admin-list-releases ──────────────────────────────────
    @app_commands.command(
        name="admin-list-releases",
        description="List available ml-models-r* GitHub Releases (tag, date, asset count)",
    )
    @require_role(ROLE_MOD)
    async def admin_list_releases(self, interaction: discord.Interaction) -> None:
        import httpx

        await interaction.response.defer(ephemeral=True)
        repo = settings.github_repo
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.github_token.get_secret_value():
            headers["Authorization"] = (
                f"Bearer {settings.github_token.get_secret_value()}"
            )

        try:
            async with httpx.AsyncClient(
                headers=headers, follow_redirects=True, timeout=30
            ) as client:
                resp = await client.get(f"https://api.github.com/repos/{repo}/releases")
                resp.raise_for_status()
                releases = resp.json()
        except Exception as exc:
            await interaction.followup.send(
                f"❌ GitHub API error: `{exc}`", ephemeral=True
            )
            return

        ml = [r for r in releases if r["tag_name"].startswith("ml-models-r")]
        ml.sort(key=lambda r: r["created_at"], reverse=True)
        if not ml:
            await interaction.followup.send(
                "No `ml-models-r*` releases found.", ephemeral=True
            )
            return

        lines = [
            f"**{r['tag_name']}** — {r['created_at'][:10]} — {len(r.get('assets', []))} asset(s)"
            for r in ml[:10]
        ]
        embed = discord.Embed(
            title=f"ML Model Releases ({repo})",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        embed.set_footer(
            text="Pass a tag to /admin-pull-models release: to pin a specific release"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /admin-cancel-pull ────────────────────────────────────
    @app_commands.command(
        name="admin-cancel-pull",
        description="Cancel an in-progress /admin-pull-models download",
    )
    @is_commissioner()
    async def admin_cancel_pull(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        cancelled = 0
        for task in list(_background_tasks):
            coro_name = getattr(task.get_coro(), "__name__", "")
            if coro_name == "_pull_models" and not task.done():
                task.cancel()
                cancelled += 1
        if cancelled:
            await interaction.followup.send(
                f"✅ Cancelled {cancelled} in-flight pull task(s).", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "No active pull tasks to cancel.", ephemeral=True
            )

    # ── /admin-set-repo ───────────────────────────────────────
    @app_commands.command(
        name="admin-set-repo",
        description="Override the GitHub repo used for model downloads (format: owner/repo)",
    )
    @app_commands.describe(
        repo="GitHub repository in owner/repo format (e.g. MyOrg/MyRepo)"
    )
    @is_commissioner()
    async def admin_set_repo(self, interaction: discord.Interaction, repo: str) -> None:
        await interaction.response.defer(ephemeral=True)
        if "/" not in repo or repo.count("/") != 1:
            await interaction.followup.send(
                "❌ Invalid format. Use `owner/repo` (e.g. `NoChillModeOnline/NCLPDLB`).",
                ephemeral=True,
            )
            return
        settings.github_repo = repo  # type: ignore[assignment]
        await interaction.followup.send(
            f"✅ GitHub repo set to `{repo}` for this session. Restart the bot to revert.",
            ephemeral=True,
        )




async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
