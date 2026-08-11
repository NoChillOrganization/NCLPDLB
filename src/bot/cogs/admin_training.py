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
from pathlib import Path

import discord

from src.config import settings
from src.ml.showdown_modes import MODE_LOCALHOST
from src.ml.train_all import TRAINING_MAP
from src.services.draft_service import DraftService

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


async def _try_edit(msg: discord.Message | None, embed: discord.Embed) -> None:
    """Edit a Discord message's embed, silently ignoring errors."""
    if msg:
        try:
            await msg.edit(embed=embed)
        except Exception:
            log.debug("Best-effort Discord notification failed", exc_info=True)


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

    project_root = Path(__file__).parents[3]
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
        try:
            await interaction.user.send(
                f"⚠️ **Preflight issues detected for `{fmt}` — auto-fixing…**\n{fix_lines}"
            )
        except Exception:
            log.debug("Best-effort Discord notification failed", exc_info=True)
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
            log.debug("Best-effort Discord notification failed", exc_info=True)
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
                    prog_embed = _build_progress_embed(
                        fmt, latest_steps, timesteps, attempt
                    )
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
            try:
                await interaction.user.send(embed=result_embed)
            except Exception:
                log.debug("Best-effort Discord notification failed", exc_info=True)
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
            try:
                await interaction.user.send(
                    f"⚠️ **Training {label} failed. Errors detected:**\n{err_lines}\n\n"
                    f"**Auto-fix applied:**\n{fix_lines}\n\n"
                    "🔄 Retrying…"
                )
            except Exception:
                log.debug("Best-effort Discord notification failed", exc_info=True)
            log.info(
                f"[admin-train] {fmt}: attempt {attempt} failed, applied fixes, retrying"
            )
            continue  # retry

        # No fix possible — final failure
        await _try_edit(
            channel_msg,
            _build_progress_embed(fmt, latest_steps, timesteps, attempt, failed=True),
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
        try:
            await interaction.user.send(embed=fail_embed)
        except Exception:
            log.debug("Best-effort Discord notification failed", exc_info=True)
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
        try:
            await interaction.user.send(
                f"❌ **Train-All cannot start — blocking issue(s):**\n{block_lines}"
            )
        except Exception:
            log.debug("Best-effort Discord notification failed", exc_info=True)
        return

    try:
        await interaction.user.send(
            f"🚀 **Train-All started** — {len(formats_to_run)} format(s) queued "
            f"({skipped_count} already trained, skipped).\n"
            f"Steps per format: `{timesteps:,}`. You'll receive a DM per format + final summary."
        )
    except Exception:
        log.debug("Best-effort Discord notification failed", exc_info=True)

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
        latest_steps = 0

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
                    await _try_edit(
                        dm_msg,
                        _build_progress_embed(fmt, latest_steps, timesteps, attempt=1),
                    )
                    await _try_edit(
                        channel_msg,
                        _build_queue_embed(
                            len(formats_to_run),
                            skipped_count,
                            timesteps,
                            current_fmt=fmt,
                            current_steps=latest_steps,
                            n_done=n_done,
                            n_failed=n_failed,
                        ),
                    )
                    last_edit_time = now

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
                timesteps if ok else latest_steps,
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


def _chunk_lines(lines: list[str], limit: int = 1024) -> list[str]:
    """Split *lines* into joined chunks each ≤ *limit* characters.

    Used to build Discord embed fields whose values must not exceed 1024 chars.
    """
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        needed = len(line) + (1 if current else 0)  # +1 for the joining newline
        if current_len + needed > limit:
            if current:
                chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += needed
    if current:
        chunks.append("\n".join(current))
    return chunks


async def _pull_models(
    interaction: discord.Interaction,
    fmt: str | None,
    release_tag: str | None,
) -> None:
    """Background task: download trained model zips from a GitHub Release."""
    import httpx

    repo = settings.github_repo
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.github_token.get_secret_value():
        headers["Authorization"] = f"Bearer {settings.github_token.get_secret_value()}"

    project_root = Path(__file__).parents[3]
    policy_dir = project_root / settings.ml_policy_dir
    formats_to_download = [fmt] if fmt else list(TRAINING_MAP.keys())

    try:
        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=300
        ) as client:
            # Resolve release
            # Treat "latest" (typed literally) the same as omitting the tag —
            # both fall through to find the newest ml-models-r* release.
            specific_tag = release_tag and release_tag.lower() not in ("latest", "")
            if specific_tag:
                resp = await client.get(
                    f"https://api.github.com/repos/{repo}/releases/tags/{release_tag}"
                )
            else:
                resp = await client.get(f"https://api.github.com/repos/{repo}/releases")
                resp.raise_for_status()
                releases = resp.json()
                ml_releases = [
                    r for r in releases if r["tag_name"].startswith("ml-models-r")
                ]
                ml_releases.sort(key=lambda r: r["created_at"], reverse=True)
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
                    # Use the asset API URL (not browser_download_url) so that
                    # private-repo assets are fetched with the PAT.  GitHub 302s
                    # to a signed objects.githubusercontent.com URL; httpx follows
                    # the redirect automatically (follow_redirects=True above) and
                    # drops the Authorization header on the cross-host hop.
                    dl = await client.get(
                        asset["url"],
                        headers={"Accept": "application/octet-stream"},
                    )
                    dl.raise_for_status()
                    save_path.write_bytes(dl.content)
                    size_kb = len(dl.content) // 1024
                    results[target_fmt] = f"✅ {size_kb} KB"
                except Exception as exc:
                    results[target_fmt] = f"❌ {exc}"

    except Exception as exc:
        # Download can take up to 300 s — DM in case webhook token expired.
        msg = f"❌ GitHub API error: `{exc}`"
        try:
            await interaction.followup.send(msg, ephemeral=True)
        except discord.NotFound:
            await interaction.user.send(msg)
        return

    ok = sum(1 for v in results.values() if v.startswith("✅"))
    fail = len(results) - ok
    result_lines = [f"`{f}` — {s}" for f, s in results.items()]
    embed = discord.Embed(
        title=f"Model Download — {tag}",
        color=discord.Color.green() if fail == 0 else discord.Color.orange(),
    )
    embed.set_footer(text=f"{ok} downloaded, {fail} skipped/failed")
    # Split results into ≤1024-char field values to respect Discord's embed limits.
    for chunk in _chunk_lines(result_lines):
        embed.add_field(name="​", value=chunk, inline=False)
    try:
        await interaction.followup.send(embed=embed, ephemeral=True)
    except discord.NotFound:
        await interaction.user.send(embed=embed)
    except discord.HTTPException as exc:
        # Embed still too large or malformed — fall back to a safe plain summary.
        log.warning(
            f"[admin-pull-models] embed send failed ({exc}); sending plain summary"
        )
        fallback = f"**Model Download — {tag}**\n{ok} downloaded, {fail} skipped/failed"
        try:
            await interaction.followup.send(fallback, ephemeral=True)
        except discord.NotFound:
            await interaction.user.send(fallback)


