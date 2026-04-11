"""
Admin Cog — Commissioner and admin override commands.
"""
import asyncio
import logging
import sys
from collections import deque
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from src.ml.showdown_modes import MODE_LOCALHOST
from src.ml.train_all import TRAINING_MAP
from src.services.draft_service import DraftService

log = logging.getLogger(__name__)


def is_commissioner():
    """Check decorator: user must be league commissioner or have Manage Guild."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild or not hasattr(interaction.user, "guild_permissions"):
            raise app_commands.CheckFailure("This command can only be used in a server.")
        if interaction.user.guild_permissions.manage_guild:
            return True
        raise app_commands.CheckFailure("You must be a commissioner or have Manage Guild permission.")
    return app_commands.check(predicate)


class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.draft_service = DraftService()

    @app_commands.command(name="admin-skip", description="Force-skip a player's turn (commissioner only)")
    @app_commands.describe(user="Player to skip")
    @is_commissioner()
    async def admin_skip(self, interaction: discord.Interaction, user: discord.Member) -> None:
        await interaction.response.defer()
        result = await self.draft_service.force_skip(
            guild_id=str(interaction.guild_id),
            player_id=str(user.id),
        )
        await interaction.followup.send(f"Skipped {user.display_name}'s turn. Next: {result.next_player}")

    @app_commands.command(name="admin-pause", description="Pause the active draft")
    @is_commissioner()
    async def admin_pause(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self.draft_service.pause_draft(str(interaction.guild_id))
        await interaction.followup.send("Draft paused.")

    @app_commands.command(name="admin-resume", description="Resume a paused draft")
    @is_commissioner()
    async def admin_resume(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self.draft_service.resume_draft(str(interaction.guild_id))
        await interaction.followup.send("Draft resumed!")

    @app_commands.command(name="admin-override-pick", description="Override a pick (commissioner only)")
    @app_commands.describe(user="Player whose pick to change", old_pokemon="Pokemon to remove", new_pokemon="Pokemon to add")
    @is_commissioner()
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
    @app_commands.command(name="admin-sync", description="Sync slash commands with Discord (push new/updated commands)")
    @app_commands.describe(scope="guild = instant (test guild only), global = up to 1 hour to propagate everywhere")
    @app_commands.choices(scope=[
        app_commands.Choice(name="guild (instant)", value="guild"),
        app_commands.Choice(name="global (up to 1 hour)", value="global"),
    ])
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
                "git", "pull", "--ff-only",
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
                lines.append(f"✅ **Commands synced** — {len(synced)} command(s) to this server")
            else:
                synced = await interaction.client.tree.sync()
                lines.append(f"✅ **Commands synced** — {len(synced)} command(s) globally")
        except discord.HTTPException as exc:
            retry = getattr(exc, "retry_after", None)
            hint = f" Retry after {retry:.0f}s." if retry else ""
            lines.append(f"❌ **Command sync failed** (HTTP {exc.status}).{hint} `{exc.text}`")
        except Exception as exc:
            lines.append(f"❌ **Command sync failed**: `{exc}`")

        await interaction.followup.send("\n\n".join(lines), ephemeral=True)

    # ── /admin-reset ───────────────────────────────────────────
    @app_commands.command(name="admin-reset", description="Reset the current draft (CANNOT BE UNDONE)")
    @is_commissioner()
    async def admin_reset(self, interaction: discord.Interaction) -> None:
        # Confirm via button
        view = ConfirmResetView(guild_id=str(interaction.guild_id), draft_service=self.draft_service)
        await interaction.response.send_message(
            "⚠️ Are you sure you want to reset the draft? This cannot be undone.", view=view, ephemeral=True
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
            log.warning("[admin-train] followup.send got 10062 (interaction expired); continuing without channel embed")
            try:
                await interaction.user.send(
                    "⚠️ Couldn't post the training status embed (Discord interaction expired), "
                    "but training is starting. You'll receive a DM when done."
                )
            except Exception:
                pass

        asyncio.create_task(
            _run_training(interaction, format, timesteps, force, channel_msg=status_msg, server="showdown")
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
            1 for fmt in TRAINING_MAP
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
            log.warning("[admin-train-all] followup.send got 10062 (interaction expired); continuing without channel embed")
            try:
                await interaction.user.send(
                    "⚠️ Couldn't post the train-all status embed in the channel (Discord interaction expired), "
                    "but training is starting. You'll receive DM updates per format."
                )
            except Exception:
                pass

        asyncio.create_task(
            _run_training_all(
                interaction, timesteps, force=not skip_existing,
                channel_msg=status_msg, server="showdown",
            )
        )

    # ── /admin-pull-models ────────────────────────────────────
    @app_commands.command(
        name="admin-pull-models",
        description="Download trained models from the latest GitHub Release into data/ml/policy/",
    )
    @app_commands.describe(
        format="Format to download, or leave blank to download all available",
        release="Release tag (e.g. ml-models-r5); default: latest",
    )
    @is_commissioner()
    async def admin_pull_models(
        self,
        interaction: discord.Interaction,
        format: str | None = None,
        release: str | None = None,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        asyncio.create_task(
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
        description="Check if the local Showdown server is running and open it in browser",
    )
    @is_commissioner()
    async def admin_showdown_check(self, interaction: discord.Interaction) -> None:
        import socket
        import webbrowser

        await interaction.response.defer(thinking=True, ephemeral=True)

        host, port = "127.0.0.1", 8000
        reachable = False
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: socket.create_connection((host, port), 3)
            )
            reachable = True
        except OSError:
            pass

        if reachable:
            webbrowser.open(f"http://localhost:{port}")
            await interaction.followup.send(
                f"✅ Showdown server is reachable at `localhost:{port}` — opening in browser.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"❌ Showdown server is **NOT** running on port `{port}`.\n"
                "Start it with:\n"
                "```\ncd pokemon-showdown && node pokemon-showdown start --no-security\n```",
                ephemeral=True,
            )


class ConfirmResetView(discord.ui.View):
    def __init__(self, guild_id: str, draft_service: DraftService) -> None:
        super().__init__(timeout=30)
        self.guild_id = guild_id
        self.draft_service = draft_service

    @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.draft_service.reset_draft(self.guild_id)
        await interaction.response.send_message("Draft has been reset.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("Reset cancelled.", ephemeral=True)
        self.stop()


# ── Shared helpers ────────────────────────────────────────────────────────────

def _model_exists(results_dir: Path, fmt: str) -> bool:
    """Check if a trained model exists for a format (checks per-format subdir and flat root)."""
    return (
        any((results_dir / fmt).glob(f"{fmt}_*.zip"))
        or any(results_dir.glob(f"{fmt}_*.zip"))
    )


async def _try_edit(msg: discord.Message | None, embed: discord.Embed) -> None:
    """Edit a Discord message's embed, silently ignoring errors."""
    if msg:
        try:
            await msg.edit(embed=embed)
        except Exception:
            pass


# ── Background training tasks ─────────────────────────────────────────────────

async def _run_training(
    interaction: discord.Interaction,
    fmt: str,
    timesteps: int,
    force: bool,
    channel_msg: discord.Message | None = None,
    server: str = MODE_LOCALHOST,
) -> None:
    """
    Background task: train a single format with preflight, progress bar, and auto-fix.

    Flow:
      1. Preflight checks → DM any blocking issues, abort if Showdown offline.
      2. Run train_all subprocess, streaming stdout.
      3. Edit a live DM embed every 60 s with a Unicode progress bar.
      4. On failure → diagnose output → apply fixes → retry once.
      5. DM final result embed.
    """
    from src.ml.training_doctor import (
        apply_all_fixes, diagnose_output,
        parse_timestep_progress, preflight_check,
    )

    project_root = Path(__file__).parents[3]
    save_dir = project_root / "data" / "ml" / "policy"

    # ── 0. Whitelist validation ─────────────────────────────────────
    if fmt not in TRAINING_MAP:
        await interaction.user.send(f"❌ Unknown format `{fmt}`. Valid formats: {', '.join(TRAINING_MAP)}")
        return

    # ── 1. Preflight ────────────────────────────────────────────────
    issues = preflight_check(fmt, save_dir, python_exe=sys.executable, server_mode=server)
    blocking = [i for i in issues if not i["fixable"]]
    fixable  = [i for i in issues if i["fixable"]]

    if fixable:
        fix_lines = "\n".join(f"• {e['description']}" for e in fixable)
        try:
            await interaction.user.send(
                f"⚠️ **Preflight issues detected for `{fmt}` — auto-fixing…**\n{fix_lines}"
            )
        except Exception:
            pass
        for err, ok, msg in apply_all_fixes(fixable, fmt, save_dir, sys.executable):
            log.info(f"[admin-train] preflight fix: {err['type']} → {ok}: {msg}")

    if blocking:
        block_lines = "\n".join(f"• {e['description']}" for e in blocking)
        blocked_embed = discord.Embed(
            title=f"❌ Training Blocked — `{fmt}`",
            description=block_lines,
            color=discord.Color.red(),
        )
        blocked_embed.set_footer(text="Fix the blocking issue(s) above, then retry.")
        await _try_edit(channel_msg, blocked_embed)
        try:
            await interaction.user.send(
                f"❌ **Training `{fmt}` cannot start — blocking issue(s):**\n{block_lines}"
            )
        except Exception:
            pass
        return  # abort

    # ── 2. Launch subprocess ────────────────────────────────────────
    attempt = 0
    max_attempts = 2

    while attempt < max_attempts:
        attempt += 1
        label = f"`{fmt}`" + (f" (retry {attempt - 1})" if attempt > 1 else "")
        collected: deque[str] = deque(maxlen=500)
        latest_steps = 0

        # Send initial progress DM
        progress_embed = _build_progress_embed(fmt, 0, timesteps, attempt)
        try:
            dm_msg: discord.Message | None = await interaction.user.send(embed=progress_embed)
        except Exception:
            dm_msg = None

        cmd = [
            sys.executable, "-m", "src.ml.train_all",
            "--formats", fmt,
            "--timesteps", str(timesteps),
        ]
        if force:
            cmd.append("--force")
        if server != MODE_LOCALHOST:
            cmd += ["--server", server]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            last_edit_time = asyncio.get_running_loop().time()

            # Stream stdout line-by-line
            if proc.stdout is None:
                raise RuntimeError("subprocess stdout pipe is None")
            async for raw_line in proc.stdout:
                line = raw_line.decode(errors="replace").rstrip()
                collected.append(line)

                steps = parse_timestep_progress(line)
                if steps is not None:
                    latest_steps = steps

                # Edit progress embed every 60 s (both channel and DM)
                now = asyncio.get_running_loop().time()
                if now - last_edit_time >= 60:
                    prog_embed = _build_progress_embed(fmt, latest_steps, timesteps, attempt)
                    await _try_edit(dm_msg, prog_embed)
                    await _try_edit(channel_msg, prog_embed)
                    last_edit_time = now

            await proc.wait()
            ok = proc.returncode == 0

        except Exception as exc:
            log.error(f"[admin-train] subprocess error: {exc}", exc_info=True)
            ok = False
            collected.append(f"Subprocess exception: {exc}")

        output = "\n".join(collected)

        # ── 3. Success ──────────────────────────────────────────────
        if ok:
            done_embed = _build_progress_embed(fmt, timesteps, timesteps, attempt, done=True)
            await _try_edit(dm_msg, done_embed)
            await _try_edit(channel_msg, done_embed)
            result_embed = discord.Embed(
                title="✅ Training Complete",
                description=f"Format: {label}\n```\n{output[-1200:]}\n```",
                color=discord.Color.green(),
            )
            try:
                await interaction.user.send(embed=result_embed)
            except Exception:
                pass
            return

        # ── 4. Failure → diagnose + fix ─────────────────────────────
        errors = diagnose_output(output)
        if not errors:
            errors = [{"type": "UNKNOWN", "description": "Unknown failure", "fixable": False}]

        err_lines = "\n".join(f"• [{e['type']}] {e['description']}" for e in errors)
        fixable_errors = [e for e in errors if e.get("fixable")]

        if attempt < max_attempts and fixable_errors:
            fix_results = apply_all_fixes(fixable_errors, fmt, save_dir, sys.executable)
            fix_lines = "\n".join(
                f"{'✅' if ok2 else '❌'} {msg}" for _, ok2, msg in fix_results
            )
            try:
                await interaction.user.send(
                    f"⚠️ **Training {label} failed. Errors detected:**\n{err_lines}\n\n"
                    f"**Auto-fix applied:**\n{fix_lines}\n\n"
                    "🔄 Retrying…"
                )
            except Exception:
                pass
            log.info(f"[admin-train] {fmt}: attempt {attempt} failed, applied fixes, retrying")
            continue  # retry

        # No fix possible — final failure
        await _try_edit(channel_msg, _build_progress_embed(fmt, latest_steps, timesteps, attempt, failed=True))
        snippet = output[-1200:]
        fail_embed = discord.Embed(
            title="❌ Training Failed",
            description=(
                f"Format: {label}\n\n"
                f"**Detected errors:**\n{err_lines}\n\n"
                f"```\n{snippet}\n```"
            ),
            color=discord.Color.red(),
        )
        try:
            await interaction.user.send(embed=fail_embed)
        except Exception:
            pass
        return


async def _run_training_all(
    interaction: discord.Interaction,
    timesteps: int,
    force: bool,
    channel_msg: discord.Message | None = None,
    server: str = MODE_LOCALHOST,
) -> None:
    """
    Background task: train all formats sequentially.

    Sends a per-format progress DM, then a final summary.
    """
    from src.ml.training_doctor import parse_timestep_progress, preflight_check

    project_root = Path(__file__).parents[3]
    save_dir = project_root / "data" / "ml" / "policy"

    results_dir = project_root / "data" / "ml" / "results"
    formats_to_run = [
        fmt for fmt, entry in TRAINING_MAP.items()
        if entry[0] is not None
        and (force or not _model_exists(results_dir, fmt))
    ]
    skipped_count = len(TRAINING_MAP) - len(formats_to_run)

    # Check server once before starting
    issues = preflight_check(
        formats_to_run[0] if formats_to_run else "gen9randombattle",
        save_dir, sys.executable, server_mode=server,
    )
    blocking = [i for i in issues if not i["fixable"]]
    if blocking:
        block_lines = "\n".join(f"• {e['description']}" for e in blocking)
        blocked_embed = discord.Embed(
            title="❌ Train-All Blocked",
            description=block_lines,
            color=discord.Color.red(),
        )
        blocked_embed.set_footer(text="Fix the blocking issue(s) above, then retry.")
        await _try_edit(channel_msg, blocked_embed)
        try:
            await interaction.user.send(
                f"❌ **Train-All cannot start — blocking issue(s):**\n{block_lines}"
            )
        except Exception:
            pass
        return

    try:
        await interaction.user.send(
            f"🚀 **Train-All started** — {len(formats_to_run)} format(s) queued "
            f"({skipped_count} already trained, skipped).\n"
            f"Steps per format: `{timesteps:,}`. You'll receive a DM per format + final summary."
        )
    except Exception:
        pass

    results: dict[str, str] = {}
    n_done = 0
    n_failed = 0

    for fmt in formats_to_run:
        log.info(f"[admin-train-all] starting {fmt}")
        cmd = [
            sys.executable, "-m", "src.ml.train_all",
            "--formats", fmt,
            "--timesteps", str(timesteps),
        ]
        if force:
            cmd.append("--force")
        if server != MODE_LOCALHOST:
            cmd += ["--server", server]

        collected: deque[str] = deque(maxlen=500)
        latest_steps = 0

        # Update channel bar to show current format starting
        await _try_edit(channel_msg, _build_queue_embed(
            len(formats_to_run), skipped_count, timesteps,
            current_fmt=fmt, current_steps=0, n_done=n_done, n_failed=n_failed,
        ))

        progress_embed = _build_progress_embed(fmt, 0, timesteps, attempt=1)
        try:
            dm_msg: discord.Message | None = await interaction.user.send(embed=progress_embed)
        except Exception:
            dm_msg = None

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            last_edit_time = asyncio.get_running_loop().time()

            if proc.stdout is None:
                raise RuntimeError("subprocess stdout pipe is None")
            async for raw_line in proc.stdout:
                line = raw_line.decode(errors="replace").rstrip()
                collected.append(line)
                steps = parse_timestep_progress(line)
                if steps is not None:
                    latest_steps = steps
                now = asyncio.get_running_loop().time()
                if now - last_edit_time >= 60:
                    await _try_edit(dm_msg, _build_progress_embed(fmt, latest_steps, timesteps, attempt=1))
                    await _try_edit(channel_msg, _build_queue_embed(
                        len(formats_to_run), skipped_count, timesteps,
                        current_fmt=fmt, current_steps=latest_steps,
                        n_done=n_done, n_failed=n_failed,
                    ))
                    last_edit_time = now

            await proc.wait()
            ok = proc.returncode == 0

        except Exception as exc:
            log.error(f"[admin-train-all] {fmt}: {exc}", exc_info=True)
            ok = False
            collected.append(f"Exception: {exc}")

        # Update DM progress bar to final state
        await _try_edit(dm_msg, _build_progress_embed(
            fmt, timesteps if ok else latest_steps, timesteps, attempt=1, done=ok, failed=not ok
        ))

        results[fmt] = "done" if ok else "failed"
        if ok:
            n_done += 1
        else:
            n_failed += 1
        log.info(f"[admin-train-all] {fmt}: {'OK' if ok else 'FAILED'}")

        if not ok:
            from src.ml.training_doctor import diagnose_output, apply_all_fixes
            output = "\n".join(collected)
            errors = diagnose_output(output)
            fixable = [e for e in errors if e.get("fixable")]
            if fixable:
                apply_all_fixes(fixable, fmt, save_dir, sys.executable)
                results[fmt] = "failed_fixed"

    # ── Final summary ────────────────────────────────────────────────
    icons = {"done": "✅", "failed": "❌", "failed_fixed": "🔧"}
    summary_lines = [f"{icons.get(s, '?')} `{f}` — {s}" for f, s in results.items()]
    n_ok = sum(1 for s in results.values() if s == "done")
    n_fail = sum(1 for s in results.values() if "fail" in s)

    # Update channel status bar to final state
    await _try_edit(channel_msg, _build_queue_embed(
        len(formats_to_run), skipped_count, timesteps,
        n_done=n_ok, n_failed=n_fail, done=True,
    ))

    summary_embed = discord.Embed(
        title="Train-All Complete" if n_fail == 0 else "Train-All Finished With Errors",
        description=(
            f"**{n_ok} succeeded / {n_fail} failed** (+ {skipped_count} skipped)\n\n"
            + "\n".join(summary_lines)
        ),
        color=discord.Color.green() if n_fail == 0 else discord.Color.orange(),
    )
    try:
        await interaction.user.send(embed=summary_embed)
    except Exception as exc:
        log.error(f"[admin-train-all] could not DM summary: {exc}")


# ── Embed builders ────────────────────────────────────────────────────────────

def _build_queue_embed(
    total_to_train: int,
    already_skipped: int,
    timesteps: int,
    *,
    current_fmt: str | None = None,
    current_steps: int = 0,
    n_done: int = 0,
    n_failed: int = 0,
    done: bool = False,
) -> discord.Embed:
    """Build a Discord embed showing overall train-all queue progress."""
    from src.ml.training_doctor import make_progress_bar

    n_remaining = max(total_to_train - n_done - n_failed, 0)

    if done:
        title = "✅ Train-All Complete" if n_failed == 0 else f"⚠️ Train-All Finished ({n_failed} failed)"
        color = discord.Color.green() if n_failed == 0 else discord.Color.orange()
    elif current_fmt:
        title = f"⚙️ Training {n_done + 1}/{total_to_train} — `{current_fmt}`"
        color = discord.Color.blurple()
    else:
        title = f"🚀 Train-All — {total_to_train} format(s) queued"
        color = discord.Color.blurple()

    lines: list[str] = []

    if current_fmt and not done:
        bar = make_progress_bar(current_steps, timesteps)
        lines += [
            f"**Current:** `{current_fmt}`",
            bar,
            f"{current_steps:,} / {timesteps:,} steps",
            "",
        ]

    queue_summary = f"**Queue:** {n_done} done · {n_failed} failed · {n_remaining} remaining"
    if already_skipped:
        queue_summary += f" · {already_skipped} skipped"
    lines.append(queue_summary)

    if not done and current_fmt:
        lines.append("\n_Updates every 60 seconds._")

    return discord.Embed(title=title, description="\n".join(lines), color=color)


def _build_progress_embed(
    fmt: str,
    current: int,
    total: int,
    attempt: int,
    *,
    done: bool = False,
    failed: bool = False,
) -> discord.Embed:
    """Build a Discord embed with a Unicode progress bar for a training run."""
    from src.ml.training_doctor import make_progress_bar

    bar = make_progress_bar(current, total)
    pct = min(current / total * 100, 100.0) if total > 0 else 0.0

    if done:
        title = f"✅ Training complete — `{fmt}`"
        color = discord.Color.green()
    elif failed:
        title = f"❌ Training failed — `{fmt}`"
        color = discord.Color.red()
    elif attempt > 1:
        title = f"🔄 Retraining (attempt {attempt}) — `{fmt}`"
        color = discord.Color.orange()
    else:
        title = f"⚙️ Training — `{fmt}`"
        color = discord.Color.blurple()

    desc = (
        f"{bar}\n"
        f"**{current:,}** / **{total:,}** steps ({pct:.1f}%)\n"
    )
    if not done and not failed:
        desc += "\n_Updates every 60 seconds. You'll get a DM when done._"

    return discord.Embed(title=title, description=desc, color=color)


async def _pull_models(
    interaction: discord.Interaction,
    fmt: str | None,
    release_tag: str | None,
) -> None:
    """Background task: download trained model zips from a GitHub Release."""
    import httpx
    from src.config import settings

    repo = settings.github_repo
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    project_root = Path(__file__).parents[3]
    policy_dir = project_root / "data" / "ml" / "policy"
    formats_to_download = [fmt] if fmt else list(TRAINING_MAP.keys())

    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=300) as client:
            # Resolve release
            # Treat "latest" (typed literally) the same as omitting the tag —
            # both fall through to find the newest ml-models-r* release.
            specific_tag = release_tag and release_tag.lower() not in ("latest", "")
            if specific_tag:
                resp = await client.get(
                    f"https://api.github.com/repos/{repo}/releases/tags/{release_tag}"
                )
            else:
                resp = await client.get(
                    f"https://api.github.com/repos/{repo}/releases"
                )
                resp.raise_for_status()
                releases = resp.json()
                ml_releases = [r for r in releases if r["tag_name"].startswith("ml-models-r")]
                if not ml_releases:
                    await interaction.followup.send(
                        "No `ml-models-r*` releases found on GitHub. Run the Train ML Models workflow first.",
                        ephemeral=True,
                    )
                    return
                resp = await client.get(
                    f"https://api.github.com/repos/{repo}/releases/{ml_releases[0]['id']}"
                )

            resp.raise_for_status()
            release = resp.json()
            tag = release["tag_name"]
            assets: list[dict] = release.get("assets", [])
            asset_map = {a["name"]: a for a in assets}

            results: dict[str, str] = {}
            for target_fmt in formats_to_download:
                asset_name = f"{target_fmt}_final_model.zip"
                asset = asset_map.get(asset_name)
                if asset is None:
                    results[target_fmt] = "not in release"
                    continue

                save_path = policy_dir / target_fmt / "final_model.zip"
                save_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    dl = await client.get(asset["browser_download_url"])
                    dl.raise_for_status()
                    save_path.write_bytes(dl.content)
                    size_kb = len(dl.content) // 1024
                    results[target_fmt] = f"✅ {size_kb} KB"
                except Exception as exc:
                    results[target_fmt] = f"❌ {exc}"

    except Exception as exc:
        await interaction.followup.send(f"❌ GitHub API error: `{exc}`", ephemeral=True)
        return

    ok = sum(1 for v in results.values() if v.startswith("✅"))
    fail = len(results) - ok
    lines = [f"`{f}` — {s}" for f, s in results.items()]
    embed = discord.Embed(
        title=f"Model Download — {tag}",
        description="\n".join(lines),
        color=discord.Color.green() if fail == 0 else discord.Color.orange(),
    )
    embed.set_footer(text=f"{ok} downloaded, {fail} skipped/failed")
    await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
