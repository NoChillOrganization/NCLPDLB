"""
Pokemon Draft League Bot — Main entrypoint.
Discord.py 2.x with slash commands, views, and cogs.
Cross-platform compatible (Windows, macOS, Linux).
"""
import asyncio
import csv
import hashlib
import json
import logging
import sys
from pathlib import Path

import discord
from discord.ext import commands

# Ensure src/ is on path (cross-platform)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import settings
from src.data.db import init_db
from src.services.draft_service import DraftService as _DraftService
from src.services.elo_service import EloService as _EloService

# ── Logging Setup ─────────────────────────────────────────────
log_dir = settings.log_file.parent
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.log_file, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


_SYNC_HASH_FILE = Path(__file__).parent.parent.parent / ".discord_sync_hash"


def _command_fingerprint(commands) -> str:
    """Stable hash of command names + descriptions + parameter names.

    Used to skip Discord sync when nothing has changed between restarts,
    avoiding the guild-commands rate limit (429 / 355 s retry).
    """
    parts = []
    for cmd in sorted(commands, key=lambda c: c.name):
        entry: dict = {"n": cmd.name, "d": getattr(cmd, "description", "")}
        if hasattr(cmd, "parameters"):
            entry["p"] = sorted(p.name for p in cmd.parameters)
        parts.append(entry)
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def drift_check_commands(csv_names: set[str], registered_names: set[str]) -> set[str]:
    """Return commands registered in the bot tree but absent from commands.csv.

    Args:
        csv_names: Set of command names from CSV (leading '/' stripped).
        registered_names: Set of command names from bot.tree.get_commands().

    Returns:
        Set of names in registered_names but not in csv_names (drift).
    """
    return registered_names - csv_names

# ── Bot Setup ─────────────────────────────────────────────────
COGS = [
    "src.bot.cogs.draft",
    "src.bot.cogs.team",
    "src.bot.cogs.league",
    "src.bot.cogs.admin",
    "src.bot.cogs.stats",
    "src.bot.cogs.sheet",    # Google Sheets management commands
    "src.bot.cogs.misc",     # /help and utility commands
]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class DraftLeagueBot(commands.Bot):
    def __init__(self) -> None:  # pragma: no cover
        super().__init__(
            command_prefix="!",  # Fallback prefix; primary interface is slash commands
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        """Called once before the bot starts. Load cogs and sync slash commands."""
        # Initialise SQLite tables and restore in-progress state
        await init_db()
        await _DraftService().restore_active_drafts()
        await _EloService().restore_ratings_from_db()

        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info(f"Loaded cog: {cog}")
            except Exception as e:
                log.error(f"Failed to load cog {cog}: {e}", exc_info=True)

        # CSV drift check — log any commands registered but missing from discord_commands.csv
        csv_path = Path(__file__).parent.parent.parent / "discord_commands.csv"
        if csv_path.exists():
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                csv_names = {row["Command"].lstrip("/") for row in reader}
            registered = {cmd.name for cmd in self.tree.get_commands()}
            drift = drift_check_commands(csv_names, registered)
            if drift:
                log.warning(
                    "Commands registered but missing from commands.csv: %s",
                    sorted(drift),
                )
            else:
                log.info("Command registry drift check passed — no missing CSV entries.")
        else:
            log.warning("discord_commands.csv not found at %s — skipping drift check.", csv_path)

        # Hash-gated sync: only call the Discord API when commands actually changed.
        # The guild-commands PUT endpoint is rate-limited (~2–5 calls/10 min per app).
        # Syncing on every restart burns through that budget; the hash avoids it.
        current_hash = _command_fingerprint(self.tree.get_commands())
        stored_hash = _SYNC_HASH_FILE.read_text().strip() if _SYNC_HASH_FILE.exists() else ""
        commands_changed = current_hash != stored_hash

        if settings.discord_guild_id:
            guild = discord.Object(id=int(settings.discord_guild_id))
            self.tree.copy_global_to(guild=guild)
            if commands_changed:
                await self.tree.sync(guild=guild)
                _SYNC_HASH_FILE.write_text(current_hash)
                log.info("Slash commands synced to guild %s (commands changed)", settings.discord_guild_id)
            else:
                log.info("Slash commands unchanged — skipping sync (hash: %s)", current_hash)
        elif settings.sync_commands_on_startup:
            if commands_changed:
                await self.tree.sync()
                _SYNC_HASH_FILE.write_text(current_hash)
                log.info("Slash commands synced globally (commands changed)")
            else:
                log.info("Slash commands unchanged — skipping global sync (hash: %s)", current_hash)
        else:
            log.info("Skipping command sync — set DISCORD_GUILD_ID for auto-sync or use /admin-sync")

    async def on_ready(self) -> None:
        log.info(f"Bot ready! Logged in as {self.user} (ID: {self.user.id})")
        log.info(f"Bot name: {settings.bot_name}")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=settings.bot_status,
            )
        )

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        log.error(f"Command error: {error}", exc_info=True)


async def main() -> None:  # pragma: no cover
    creds = settings.google_sheets_credentials_file
    if not creds.exists():
        raise FileNotFoundError(
            f"Google Sheets credentials not found at '{creds}'. "
            "Download your service account JSON and place it there, or set "
            "GOOGLE_SHEETS_CREDENTIALS_FILE in .env."
        )
    bot = DraftLeagueBot()
    async with bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
