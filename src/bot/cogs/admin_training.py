"""
Admin Cog — background training orchestration.

Extracted from admin.py (which had grown past the project's 800-line
guideline): the AdminCog class and its /admin-* commands stay in admin.py;
the training subprocess orchestration, progress embeds, and model-pull
logic those commands kick off via _create_background_task live here.
"""

import asyncio
import logging
import sys
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path

import discord

from src.config import PROJECT_ROOT, settings
from src.ml.showdown_modes import MODE_LOCALHOST
from src.ml.train_all import TRAINING_MAP
from src.services.draft_service import DraftService
from src.services.model_pull_service import _chunk_lines

log = logging.getLogger(__name__)


class ConfirmResetView(discord.ui.View):
    def __init__(self, guild_id: str, draft_service: DraftService) -> None:
        super().__init__(timeout=30)
        self.guild_id = guild_id
        self.draft_service = draft_service

    @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.draft_service.reset_draft(self.guild_id)
        await interaction.response.send_message("Draft has been reset.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_message("Reset cancelled.", ephemeral=True)
        self.stop()


# ── Shared helpers ────────────────────────────────────────────────────────────


def _model_exists(results_dir: Path, fmt: str) -> bool:
    """Check if a trained model exists for a format (checks per-format subdir and flat root)."""
    return any((results_dir / fmt).glob(f"{fmt}_*.zip")) or any(
        results_dir.glob(f"{fmt}_*.zip")
    )


async def _try_dm(
    user: discord.abc.User,
    text: str = "",
    *,
    embed: discord.Embed | None = None,
) -> None:
    """Best-effort DM; failure (DMs closed, etc.) is logged and swallowed."""
    try:
        if embed is not None:
            await user.send(embed=embed)
        else:
            await user.send(text)
    except Exception:
        log.debug("Best-effort Discord notification failed", exc_info=True)


async def _try_edit(msg: discord.Message | None, embed: discord.Embed) -> None:
    """Edit a Discord message's embed, silently ignoring errors."""
    if msg:
        try:
            await msg.edit(embed=embed)
        except Exception:
            log.debug("Best-effort Discord notification failed", exc_info=True)


async def _stream_training(
    proc: asyncio.subprocess.Process,
    collected: deque[str],
    latest_steps: list[int],
    parse_timestep_progress: Callable[[str], int | None],
    on_progress: Callable[[int], Awaitable[None]],
) -> None:
    """Stream proc stdout into `collected`; track steps; call on_progress every 60 s.

    `latest_steps` is a one-element holder so callers still see the last value
    if the stream raises midway.
    """
    last_edit_time = asyncio.get_running_loop().time()
    if proc.stdout is None:
        raise RuntimeError("subprocess stdout pipe is None")
    async for raw_line in proc.stdout:
        line = raw_line.decode(errors="replace").rstrip()
        collected.append(line)
        steps = parse_timestep_progress(line)
        if steps is not None:
            latest_steps[0] = steps
        now = asyncio.get_running_loop().time()
        if now - last_edit_time >= 60:
            await on_progress(latest_steps[0])
            last_edit_time = now


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
        apply_all_fixes,
        diagnose_output,
        parse_timestep_progress,
        preflight_check,
    )

    project_root = PROJECT_ROOT
    save_dir = project_root / settings.ml_policy_dir

    # ── 0. Whitelist validation ─────────────────────────────────────
    if fmt not in TRAINING_MAP:
        await interaction.user.send(
            f"❌ Unknown format `{fmt}`. Valid formats: {', '.join(TRAINING_MAP)}"
        )
        return

    # ── 1. Preflight ────────────────────────────────────────────────
    issues = preflight_check(
        fmt, save_dir, python_exe=sys.executable, server_mode=server
    )
    blocking = [i for i in issues if not i["fixable"]]
    fixable = [i for i in issues if i["fixable"]]

    if fixable:
        fix_lines = "\n".join(f"• {e['description']}" for e in fixable)
        await _try_dm(
            interaction.user,
            f"⚠️ **Preflight issues detected for `{fmt}` — auto-fixing…**\n{fix_lines}",
        )
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
        await _try_dm(
            interaction.user,
            f"❌ **Training `{fmt}` cannot start — blocking issue(s):**\n{block_lines}",
        )
        return  # abort

    # ── 2. Launch subprocess ────────────────────────────────────────
    attempt = 0
    max_attempts = 2

    while attempt < max_attempts:
        attempt += 1
        label = f"`{fmt}`" + (f" (retry {attempt - 1})" if attempt > 1 else "")
        collected: deque[str] = deque(maxlen=500)
        latest_steps = [0]

        # Send initial progress DM
        progress_embed = _build_progress_embed(fmt, 0, timesteps, attempt)
        try:
            dm_msg: discord.Message | None = await interaction.user.send(
                embed=progress_embed
            )
        except Exception:
            log.debug("Could not DM user, continuing without DM channel", exc_info=True)
            dm_msg = None

        cmd = [
            sys.executable,
            "-m",
            "src.ml.train_all",
            "--formats",
            fmt,
            "--timesteps",
            str(timesteps),
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

            async def on_progress(steps: int) -> None:
                # Edit progress embed every 60 s (both channel and DM)
                prog_embed = _build_progress_embed(fmt, steps, timesteps, attempt)
                await _try_edit(dm_msg, prog_embed)
                await _try_edit(channel_msg, prog_embed)

            await _stream_training(
                proc, collected, latest_steps, parse_timestep_progress, on_progress
            )

            await proc.wait()
            ok = proc.returncode == 0

        except Exception as exc:
            log.error(f"[admin-train] subprocess error: {exc}", exc_info=True)
            ok = False
            collected.append(f"Subprocess exception: {exc}")

        output = "\n".join(collected)

        # ── 3. Success ──────────────────────────────────────────────
        if ok:
            done_embed = _build_progress_embed(
                fmt, timesteps, timesteps, attempt, done=True
            )
            await _try_edit(dm_msg, done_embed)
            await _try_edit(channel_msg, done_embed)
            result_embed = discord.Embed(
                title="✅ Training Complete",
                description=f"Format: {label}\n```\n{output[-1200:]}\n```",
                color=discord.Color.green(),
            )
            await _try_dm(interaction.user, embed=result_embed)
            return

        # ── 4. Failure → diagnose + fix ─────────────────────────────
        errors = diagnose_output(output)
        if not errors:
            errors = [
                {"type": "UNKNOWN", "description": "Unknown failure", "fixable": False}
            ]

        err_lines = "\n".join(f"• [{e['type']}] {e['description']}" for e in errors)
        fixable_errors = [e for e in errors if e.get("fixable")]

        if attempt < max_attempts and fixable_errors:
            fix_results = apply_all_fixes(fixable_errors, fmt, save_dir, sys.executable)
            fix_lines = "\n".join(
                f"{'✅' if ok2 else '❌'} {msg}" for _, ok2, msg in fix_results
            )
            await _try_dm(
                interaction.user,
                f"⚠️ **Training {label} failed. Errors detected:**\n{err_lines}\n\n"
                f"**Auto-fix applied:**\n{fix_lines}\n\n"
                "🔄 Retrying…",
            )
            log.info(
                f"[admin-train] {fmt}: attempt {attempt} failed, applied fixes, retrying"
            )
            continue  # retry

        # No fix possible — final failure
        await _try_edit(
            channel_msg,
            _build_progress_embed(
                fmt, latest_steps[0], timesteps, attempt, failed=True
            ),
        )
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
        await _try_dm(interaction.user, embed=fail_embed)
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

    project_root = PROJECT_ROOT
    save_dir = project_root / settings.ml_policy_dir

    results_dir = project_root / "data" / "ml" / "results"
    formats_to_run = [
        fmt
        for fmt, entry in TRAINING_MAP.items()
        if entry[0] is not None and (force or not _model_exists(results_dir, fmt))
    ]
    skipped_count = len(TRAINING_MAP) - len(formats_to_run)

    # Check server once before starting
    issues = preflight_check(
        formats_to_run[0] if formats_to_run else "gen9randombattle",
        save_dir,
        sys.executable,
        server_mode=server,
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
        await _try_dm(
            interaction.user,
            f"❌ **Train-All cannot start — blocking issue(s):**\n{block_lines}",
        )
        return

    await _try_dm(
        interaction.user,
        f"🚀 **Train-All started** — {len(formats_to_run)} format(s) queued "
        f"({skipped_count} already trained, skipped).\n"
        f"Steps per format: `{timesteps:,}`. You'll receive a DM per format + final summary.",
    )

    results: dict[str, str] = {}
    n_done = 0
    n_failed = 0

    for fmt in formats_to_run:
        log.info(f"[admin-train-all] starting {fmt}")
        cmd = [
            sys.executable,
            "-m",
            "src.ml.train_all",
            "--formats",
            fmt,
            "--timesteps",
            str(timesteps),
        ]
        if force:
            cmd.append("--force")
        if server != MODE_LOCALHOST:
            cmd += ["--server", server]

        collected: deque[str] = deque(maxlen=500)
        latest_steps = [0]

        # Update channel bar to show current format starting
        await _try_edit(
            channel_msg,
            _build_queue_embed(
                len(formats_to_run),
                skipped_count,
                timesteps,
                current_fmt=fmt,
                current_steps=0,
                n_done=n_done,
                n_failed=n_failed,
            ),
        )

        progress_embed = _build_progress_embed(fmt, 0, timesteps, attempt=1)
        try:
            dm_msg: discord.Message | None = await interaction.user.send(
                embed=progress_embed
            )
        except Exception:
            log.debug("Could not DM user, continuing without DM channel", exc_info=True)
            dm_msg = None

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            async def on_progress(steps: int) -> None:
                await _try_edit(
                    dm_msg,
                    _build_progress_embed(fmt, steps, timesteps, attempt=1),
                )
                await _try_edit(
                    channel_msg,
                    _build_queue_embed(
                        len(formats_to_run),
                        skipped_count,
                        timesteps,
                        current_fmt=fmt,
                        current_steps=steps,
                        n_done=n_done,
                        n_failed=n_failed,
                    ),
                )

            await _stream_training(
                proc, collected, latest_steps, parse_timestep_progress, on_progress
            )

            await proc.wait()
            ok = proc.returncode == 0

        except Exception as exc:
            log.error(f"[admin-train-all] {fmt}: {exc}", exc_info=True)
            ok = False
            collected.append(f"Exception: {exc}")

        # Update DM progress bar to final state
        await _try_edit(
            dm_msg,
            _build_progress_embed(
                fmt,
                timesteps if ok else latest_steps[0],
                timesteps,
                attempt=1,
                done=ok,
                failed=not ok,
            ),
        )

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
    await _try_edit(
        channel_msg,
        _build_queue_embed(
            len(formats_to_run),
            skipped_count,
            timesteps,
            n_done=n_ok,
            n_failed=n_fail,
            done=True,
        ),
    )

    summary_embed = discord.Embed(
        title="Train-All Complete" if n_fail == 0 else "Train-All Finished With Errors",
        description=f"**{n_ok} succeeded / {n_fail} failed** (+ {skipped_count} skipped)",
        color=discord.Color.green() if n_fail == 0 else discord.Color.orange(),
    )
    # Split per-format results into ≤1024-char fields to avoid embed overflow.
    for chunk in _chunk_lines(summary_lines):
        summary_embed.add_field(name="​", value=chunk, inline=False)
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
        title = (
            "✅ Train-All Complete"
            if n_failed == 0
            else f"⚠️ Train-All Finished ({n_failed} failed)"
        )
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

    queue_summary = (
        f"**Queue:** {n_done} done · {n_failed} failed · {n_remaining} remaining"
    )
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

    desc = f"{bar}\n**{current:,}** / **{total:,}** steps ({pct:.1f}%)\n"
    if not done and not failed:
        desc += "\n_Updates every 60 seconds. You'll get a DM when done._"

    return discord.Embed(title=title, description=desc, color=color)
