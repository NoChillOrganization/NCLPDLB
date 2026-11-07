"""Download trained model zips from GitHub Releases (used by the admin cog)."""

import hashlib
import hmac
import logging
import os

import discord

from src.config import PROJECT_ROOT, settings
from src.ml.train_all import TRAINING_MAP

log = logging.getLogger(__name__)


def github_headers() -> dict[str, str]:
    """GitHub REST API headers, with the bot's token when one is configured."""
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.github_token.get_secret_value():
        headers["Authorization"] = f"Bearer {settings.github_token.get_secret_value()}"
    return headers


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


def _digest_matches(content: bytes, digest: str | None) -> bool:
    """True if `content` hashes to `digest` ('sha256:<hex>', as in the GitHub asset API).

    A missing or unsupported digest fails closed.
    """
    algorithm, _, expected = (digest or "").partition(":")
    if algorithm != "sha256" or not expected:
        return False
    return hmac.compare_digest(hashlib.sha256(content).hexdigest(), expected.lower())


async def _pull_models(
    interaction: discord.Interaction,
    fmt: str | None,
    release_tag: str | None,
) -> None:
    """Background task: download trained model zips from a GitHub Release."""
    import httpx

    repo = settings.github_repo
    headers = github_headers()

    project_root = PROJECT_ROOT
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
                    # The zip is unpickled by PPO.load, so only install bytes that match
                    # the digest GitHub recorded for the asset.
                    if not _digest_matches(dl.content, asset.get("digest")):
                        results[target_fmt] = "❌ checksum missing or mismatched"
                        continue
                    # Write beside the target and rename, so an interrupted download
                    # cannot replace a working model with a truncated one.
                    part = save_path.with_suffix(".zip.part")
                    part.write_bytes(dl.content)
                    os.replace(part, save_path)
                    size_kb = len(dl.content) // 1024
                    results[target_fmt] = f"✅ {size_kb} KB"
                except Exception as exc:
                    results[target_fmt] = f"❌ {exc}"

    except Exception:
        # Download can take up to 300 s — DM in case webhook token expired.
        log.exception("[admin-pull-models] GitHub API call failed")
        msg = "❌ GitHub API error. Check the bot logs."
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
