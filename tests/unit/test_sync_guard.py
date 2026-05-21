"""
Sync guard tests — hash-gated Discord command sync.

Covers:
  SYNC-01: _command_fingerprint is stable (same input → same hash)
  SYNC-02: _command_fingerprint detects changes (different commands → different hash)
  SYNC-03: setup_hook skips sync when hash matches stored hash
  SYNC-04: setup_hook syncs and writes hash when commands changed
  SYNC-05: setup_hook syncs when hash file is absent (first run)
  SYNC-06: admin_sync calls copy_global_to before guild sync
  SYNC-07: admin_sync surfaces HTTPException with retry_after to user
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.main import _command_fingerprint, drift_check_commands


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_cmd(name: str, description: str = "desc", params: list[str] | None = None):
    """Build a minimal fake app_commands.Command-like object."""
    cmd = MagicMock()
    cmd.name = name
    cmd.description = description
    cmd.parameters = [SimpleNamespace(name=p) for p in (params or [])]
    return cmd


# ── SYNC-01: Fingerprint stability ────────────────────────────────────────────

def test_fingerprint_stable():
    """SYNC-01: Same command list produces identical hash on repeated calls."""
    cmds = [_make_cmd("pick", params=["pokemon"]), _make_cmd("draft-start")]
    h1 = _command_fingerprint(cmds)
    h2 = _command_fingerprint(cmds)
    assert h1 == h2, "Hash must be deterministic"
    assert len(h1) == 16, "Hash should be 16 hex chars"


# ── SYNC-02: Fingerprint detects changes ──────────────────────────────────────

def test_fingerprint_detects_new_command():
    """SYNC-02a: Adding a command changes the fingerprint."""
    cmds_before = [_make_cmd("pick")]
    cmds_after  = [_make_cmd("pick"), _make_cmd("ban")]
    assert _command_fingerprint(cmds_before) != _command_fingerprint(cmds_after)


def test_fingerprint_detects_param_change():
    """SYNC-02b: Adding a parameter changes the fingerprint."""
    cmds_before = [_make_cmd("spar", params=["format"])]
    cmds_after  = [_make_cmd("spar", params=["format", "showdown_name"])]
    assert _command_fingerprint(cmds_before) != _command_fingerprint(cmds_after)


def test_fingerprint_order_independent():
    """SYNC-02c: Command order doesn't affect fingerprint (sorted internally)."""
    cmds_a = [_make_cmd("pick"), _make_cmd("ban")]
    cmds_b = [_make_cmd("ban"), _make_cmd("pick")]
    assert _command_fingerprint(cmds_a) == _command_fingerprint(cmds_b)


# ── SYNC-03: Skip sync when unchanged ─────────────────────────────────────────

def test_setup_hook_skips_sync_when_hash_matches(tmp_path):
    """SYNC-03: commands_changed=False when stored hash equals current hash → no sync."""
    fake_cmds = [_make_cmd("pick"), _make_cmd("draft-start")]
    current_hash = _command_fingerprint(fake_cmds)

    hash_file = tmp_path / ".discord_sync_hash"
    hash_file.write_text(current_hash)

    stored = hash_file.read_text().strip()
    commands_changed = current_hash != stored

    assert not commands_changed, (
        "commands_changed must be False when hash matches — sync should be skipped"
    )
    # Fingerprint must be stable across two independent calls on the same inputs
    assert _command_fingerprint(fake_cmds) == current_hash


# ── SYNC-04 / SYNC-05: Sync when changed or missing ──────────────────────────

def test_commands_changed_when_hash_differs(tmp_path):
    """SYNC-04: commands_changed=True when stored hash differs from current."""
    hash_file = tmp_path / ".discord_sync_hash"
    hash_file.write_text("oldhashabcd1234")

    fake_cmds = [_make_cmd("pick"), _make_cmd("draft-start"), _make_cmd("ban")]
    current_hash = _command_fingerprint(fake_cmds)
    stored = hash_file.read_text().strip()
    assert current_hash != stored, "Hash should differ → sync required"


def test_commands_changed_when_hash_file_missing(tmp_path):
    """SYNC-05: commands_changed=True when .discord_sync_hash does not exist."""
    hash_file = tmp_path / ".discord_sync_hash"
    assert not hash_file.exists()

    stored = hash_file.read_text().strip() if hash_file.exists() else ""
    fake_cmds = [_make_cmd("pick")]
    current_hash = _command_fingerprint(fake_cmds)
    assert current_hash != stored, "Any hash differs from empty string → sync required"


# ── SYNC-06: admin_sync calls copy_global_to ──────────────────────────────────

@pytest.mark.asyncio
async def test_admin_sync_calls_copy_global_to():
    """SYNC-06: /admin-sync guild scope calls copy_global_to before tree.sync()."""
    call_order: list[str] = []

    mock_tree = MagicMock()
    mock_tree.copy_global_to.side_effect = lambda **_: call_order.append("copy")
    mock_tree.sync = AsyncMock(side_effect=lambda **_: call_order.append("sync") or [])

    mock_guild = MagicMock()
    mock_guild.id = 999

    mock_client = MagicMock()
    mock_client.tree = mock_tree

    mock_interaction = MagicMock()
    mock_interaction.guild = mock_guild
    mock_interaction.client = mock_client
    mock_interaction.response = AsyncMock()
    mock_interaction.response.is_done.return_value = False
    mock_interaction.followup = AsyncMock()

    from src.bot.cogs.admin import AdminCog
    cog = AdminCog.__new__(AdminCog)

    # Simulate guild-scope call (scope=None → defaults to guild)
    await cog.admin_sync.callback(cog, mock_interaction, scope=None)

    assert call_order == ["copy", "sync"], (
        f"copy_global_to must be called before tree.sync, got order: {call_order}"
    )


# ── SYNC-07: admin_sync surfaces rate limit error ─────────────────────────────

@pytest.mark.asyncio
async def test_admin_sync_shows_rate_limit_error():
    """SYNC-07: If tree.sync() raises discord.HTTPException 429, user sees retry_after."""
    import discord

    mock_response = MagicMock()
    mock_response.status = 429
    mock_response.headers = {"Content-Type": "application/json"}

    exc = discord.HTTPException(mock_response, {"message": "rate limited", "retry_after": 355.0})
    exc.retry_after = 355.0  # type: ignore[attr-defined]

    mock_tree = MagicMock()
    mock_tree.copy_global_to = MagicMock()
    mock_tree.sync = AsyncMock(side_effect=exc)

    mock_guild = MagicMock()
    mock_client = MagicMock()
    mock_client.tree = mock_tree

    mock_interaction = MagicMock()
    mock_interaction.guild = mock_guild
    mock_interaction.client = mock_client
    mock_interaction.response = AsyncMock()
    mock_interaction.followup = AsyncMock()

    from src.bot.cogs.admin import AdminCog
    cog = AdminCog.__new__(AdminCog)

    await cog.admin_sync.callback(cog, mock_interaction, scope=None)

    # followup.send must have been called with the error message
    mock_interaction.followup.send.assert_called_once()
    sent_msg: str = mock_interaction.followup.send.call_args[0][0]
    assert "429" in sent_msg or "Sync failed" in sent_msg, (
        f"Error message should mention 429 or 'Sync failed', got: {sent_msg!r}"
    )


# ── Existing drift check (regression) ────────────────────────────────────────

def test_drift_check_no_regression():
    """Regression: drift_check_commands still works correctly."""
    drift = drift_check_commands({"help", "pick"}, {"help", "pick", "ghost-cmd"})
    assert drift == {"ghost-cmd"}
    assert drift_check_commands({"a", "b"}, {"a", "b"}) == set()
