# Phase 04: Browser Training - Pattern Map

**Mapped:** 2026-05-19
**Files analyzed:** 5
**Analogs found:** 5 / 5

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/ml/browser_trainer.py` | service | batch (PPO rollout) | `src/ml/train_policy.py` | role-match (same ML layer, same PPO/SB3 pattern) |
| `src/ml/showdown_modes.py` | config/factory | request-response | `src/ml/showdown_modes.py` itself (MODE_SHOWDOWN branch) | exact (add sibling branch) |
| `requirements.txt` | config | — | existing `requirements.txt` entries | exact |
| `src/bot/cogs/admin.py` | controller (cog) | event-driven (Discord interaction) | `src/bot/cogs/admin.py` `admin-train` command + `_run_training` | exact |
| `tests/unit/test_browser_trainer.py` | test | — | `tests/unit/test_train_policy.py` | role-match |

---

## Pattern Assignments

### `src/ml/browser_trainer.py` — Fix PPO learning gap + credential routing + results dir

**Analog:** `src/ml/train_policy.py`

**Bug 1 — DEFAULT_RESULTS_DIR mismatch** (browser_trainer.py line 31 vs train_policy.py line 158):
```python
# CURRENT (wrong) — browser_trainer.py line 31:
DEFAULT_RESULTS_DIR = "src/ml/models/results"

# CORRECT — match train_policy.py line 158:
DEFAULT_RESULTS_DIR = "data/ml/results"
```

**Bug 2 — PPO never learns: _FakeEnv must replay collected transitions.**

Current `_FakeEnv` in `browser_trainer.py` (lines 267-278) returns zeros unconditionally from `step()`. SB3's `PPO.learn()` is never called anywhere in the battle loop. The fix is:

1. Collect `(obs, reward, done)` tuples during the browser battle loop (alongside the existing `rewards` list).
2. Add a `_ReplayEnv` subclass (or extend `_FakeEnv`) whose `step()` pops from that collected list.
3. Call `policy.set_env(_ReplayEnv(transitions))` then `policy.learn(total_timesteps=len(transitions))` at each checkpoint interval.

**PPO model instantiation pattern** (train_policy.py lines 843-849) — copy this exact form for the `_FakeEnv`-based init in browser_trainer.py:
```python
# train_policy.py lines 843-849
model = PPO(
    "MlpPolicy",
    vec_env,
    tensorboard_log=str(log_dir),
    **PPO_HYPERPARAMS,
)
```

**PPO learn() call pattern** (train_policy.py lines 883-889):
```python
# train_policy.py lines 883-889
model.learn(
    total_timesteps=total_timesteps,
    callback=[checkpoint_cb, curriculum_cb],
    reset_num_timesteps=(resume is None),
    tb_log_name=f"ppo_{fmt}",
)
```
For browser_trainer.py, the equivalent at each checkpoint interval is:
```python
policy.set_env(DummyVecEnv([lambda: _ReplayEnv(transitions)]))
policy.learn(total_timesteps=len(transitions), reset_num_timesteps=False)
transitions.clear()
```

**Checkpoint save pattern** (train_policy.py `SelfPlayCallback._save_and_swap`, lines 367-374):
```python
# train_policy.py lines 367-374
self._swap_count += 1
ckpt_path = self.save_dir / f"swap_{self._swap_count:04d}.zip"
latest_path = self.save_dir / "latest.zip"
self.model.save(str(ckpt_path))
self.model.save(str(latest_path))
```
The browser_trainer.py already replicates this at lines 376-382 — the pattern is correct, keep it.

**Dependency guard pattern** (train_policy.py lines 48-63):
```python
# train_policy.py lines 48-58
try:  # pragma: no cover
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv
    SB3_OK = True
except ImportError:  # pragma: no cover
    SB3_OK = False
    PPO = None  # type: ignore
    DummyVecEnv = None  # type: ignore
```
`browser_trainer.py` already has an equivalent guard (lines 235-291) — same pattern, no change needed.

---

### `src/ml/showdown_modes.py` — Add MODE_BROWSER branch to `account_configs_for_mode`

**Analog:** `src/ml/showdown_modes.py` — the existing `MODE_SHOWDOWN` branch (lines 51-63), which is the exact pattern to replicate for `MODE_BROWSER`.

**Current function** (showdown_modes.py lines 44-64):
```python
def account_configs_for_mode(mode: str) -> tuple:
    import os
    if mode == MODE_SHOWDOWN:
        from poke_env.ps_client.account_configuration import AccountConfiguration
        u1 = os.environ.get("SHOWDOWN_TRAIN_USER1", "")
        p1 = os.environ.get("SHOWDOWN_TRAIN_PASS1", "")
        u2 = os.environ.get("SHOWDOWN_TRAIN_USER2", "")
        p2 = os.environ.get("SHOWDOWN_TRAIN_PASS2", "")
        if not all([u1, p1, u2, p2]):
            raise ValueError(
                "Public Showdown training requires 4 env vars: "
                "SHOWDOWN_TRAIN_USER1, SHOWDOWN_TRAIN_PASS1, "
                "SHOWDOWN_TRAIN_USER2, SHOWDOWN_TRAIN_PASS2"
            )
        return AccountConfiguration(u1, p1), AccountConfiguration(u2, p2)
    return None, None
```

**Fix — change the condition to cover MODE_BROWSER** (one-line change, line 51):
```python
# Change:
if mode == MODE_SHOWDOWN:
# To:
if mode in (MODE_SHOWDOWN, MODE_BROWSER):
```
The ValueError message should be updated to mention "Browser/Showdown training" instead of "Public Showdown training" — copy the wording from RESEARCH.md Pattern 1 code example (line 394).

---

### `requirements.txt` — Add playwright

**Analog:** existing ML dependency entries in `requirements.txt` (lines 55, 63).

**Pattern to copy** (requirements.txt lines 63-66):
```
stable-baselines3>=2.8.0   # PPO/DQN for battle policy RL
```

**New entry to add** — follow same `>=version  # comment` format:
```
playwright>=1.52.0         # Headless browser automation for browser training
```
Insert near the other ML dependencies (after `stable-baselines3`). No other requirements.txt changes needed.

---

### `src/bot/cogs/admin.py` — Add `/train-browser` command + `_run_browser_training` helper

**Analog:** `src/bot/cogs/admin.py` — `/admin-train` command (lines 192-258) and `_run_training` background coroutine (lines 419-605).

**Imports pattern** (admin.py lines 1-18):
```python
import asyncio
import logging
import sys
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from src.ml.showdown_modes import MODE_LOCALHOST
from src.ml.train_all import TRAINING_MAP
from src.services.draft_service import DraftService

log = logging.getLogger(__name__)
```
For `/train-browser`, no new imports are needed beyond what admin.py already has. `train_browser` is imported lazily inside `_run_browser_training` (same pattern as `_run_training` lazy-importing `training_doctor`).

**`is_commissioner()` guard pattern** (admin.py lines 21-29):
```python
def is_commissioner():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild or not hasattr(interaction.user, "guild_permissions"):
            raise app_commands.CheckFailure("This command can only be used in a server.")
        if interaction.user.guild_permissions.manage_guild:
            return True
        raise app_commands.CheckFailure("You must be a commissioner or have Manage Guild permission.")
    return app_commands.check(predicate)
```
Apply `@is_commissioner()` to `/train-browser` exactly as it is applied to `admin_train` (line 202).

**Command registration pattern** (admin.py lines 192-245 — the `admin_train` command):
```python
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

    status_msg: discord.Message | None = None
    try:
        status_msg = await interaction.followup.send(
            embed=_build_progress_embed(format, 0, timesteps, 1),
            wait=True,
        )
    except discord.NotFound:
        log.warning("[admin-train] followup.send got 10062 ...")
        try:
            await interaction.user.send("⚠️ Couldn't post embed but training is starting...")
        except Exception:
            pass

    asyncio.create_task(
        _run_training(interaction, format, timesteps, force, channel_msg=status_msg, server="showdown")
    )
```
Copy this structure verbatim for `train_browser_cmd`, replacing:
- `name="admin-train"` → `name="train-browser"`
- `description` → `"Train the AI via browser self-play (no local server required)"`
- `timesteps` default → `1_000` (browser training is slow; see RESEARCH.md Open Question 1)
- `force` parameter → omit (browser training always runs; no skip-existing gate needed)
- `_build_progress_embed(...)` → `_build_browser_embed(...)` (new helper, see below)
- `_run_training(...)` → `_run_browser_training(...)`

**Background task pattern** (admin.py `_run_training`, lines 419-605). The `_run_browser_training` helper is a simplified version — it does not need preflight or retry logic. Copy the structural skeleton:
```python
async def _run_browser_training(
    interaction: discord.Interaction,
    fmt: str,
    timesteps: int,
    channel_msg: discord.Message | None = None,
) -> None:
    from src.ml.browser_trainer import train_browser
    import functools

    # Validate format against whitelist (security: V5 input validation)
    if fmt not in TRAINING_MAP:
        await interaction.user.send(f"Unknown format `{fmt}`.")
        return

    project_root = Path(__file__).parents[3]
    results_dir = project_root / "data" / "ml" / "results"

    loop = asyncio.get_running_loop()
    try:
        final_path = await loop.run_in_executor(
            None,
            functools.partial(
                train_browser,
                fmt=fmt,
                total_timesteps=timesteps,
                results_dir=results_dir,
            ),
        )
        done_embed = _build_browser_embed(fmt, timesteps, timesteps, done=True)
        await _try_edit(channel_msg, done_embed)
        result_embed = discord.Embed(
            title="Browser Training Complete",
            description=f"Format: `{fmt}`\nModel saved to `{final_path}`",
            color=discord.Color.green(),
        )
        try:
            await interaction.user.send(embed=result_embed)
        except Exception:
            pass
    except Exception as exc:
        log.error(f"[train-browser] {fmt}: {exc}", exc_info=True)
        await _try_edit(channel_msg, _build_browser_embed(fmt, 0, timesteps, failed=True))
        try:
            await interaction.user.send(f"Browser training `{fmt}` failed: {exc}")
        except Exception:
            pass
```

**`_try_edit` helper** (admin.py lines 408-414) — reuse as-is, no copy needed:
```python
async def _try_edit(msg: discord.Message | None, embed: discord.Embed) -> None:
    if msg:
        try:
            await msg.edit(embed=embed)
        except Exception:
            pass
```

**Embed builder pattern** (admin.py `_build_progress_embed`, lines 828-863):
```python
def _build_progress_embed(
    fmt: str,
    current: int,
    total: int,
    attempt: int,
    *,
    done: bool = False,
    failed: bool = False,
) -> discord.Embed:
    from src.ml.training_doctor import make_progress_bar
    bar = make_progress_bar(current, total)
    pct = min(current / total * 100, 100.0) if total > 0 else 0.0
    if done:
        title = f"Training complete — `{fmt}`"
        color = discord.Color.green()
    elif failed:
        title = f"Training failed — `{fmt}`"
        color = discord.Color.red()
    else:
        title = f"Training — `{fmt}`"
        color = discord.Color.blurple()
    desc = f"{bar}\n**{current:,}** / **{total:,}** steps ({pct:.1f}%)\n"
    if not done and not failed:
        desc += "\n_Updates every 60 seconds. You'll get a DM when done._"
    return discord.Embed(title=title, description=desc, color=color)
```
Copy this as `_build_browser_embed` — remove the `attempt` parameter (browser training does not retry), keep the `done`/`failed` keyword args. The progress bar from `training_doctor.make_progress_bar` is shared.

**Autocomplete pattern** (admin.py lines 247-258):
```python
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
```
Add an identical autocomplete on `train_browser_cmd` for its `format` parameter — copy verbatim, rename the method to `train_browser_format_autocomplete`.

---

### `tests/unit/test_browser_trainer.py` — New test file

**Analog:** `tests/unit/test_train_policy.py`

**File header and import pattern** (test_train_policy.py lines 1-26):
```python
"""
Tests for src/ml/browser_trainer.py

Covers pure-logic functions only (no real browser, no real network):
  - build_observation_from_dom() — zero vector on empty mock page
  - DEFAULT_RESULTS_DIR — matches train_policy.py
  - train_browser() credential validation — raises ValueError when env vars absent
  - account_configs_for_mode(MODE_BROWSER) — raises ValueError without env vars
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.ml.battle_env import OBS_DIM
```

**Class-per-function test grouping pattern** (test_train_policy.py lines 31-63):
```python
class TestCheckShowdownServer:
    def test_reachable_does_not_raise(self):
        with patch("socket.create_connection"):
            _check_showdown_server()

    def test_unreachable_raises_runtime_error(self):
        with patch("socket.create_connection", side_effect=OSError("refused")):
            with pytest.raises(RuntimeError, match="Cannot reach local Showdown server"):
                _check_showdown_server()
```
Follow the same `class Test<FunctionName>` grouping. Each class tests one function. Each method tests one behaviour.

**MagicMock page pattern** (from RESEARCH.md Code Examples, line 406-416):
```python
def test_build_observation_from_dom_zeros_on_empty_page():
    mock_page = MagicMock()
    mock_page.locator.return_value.count.return_value = 0

    from src.ml.browser_trainer import build_observation_from_dom
    obs = build_observation_from_dom(mock_page)
    assert obs.shape == (OBS_DIM,)
    assert obs.dtype.name == "float32"
```
This is the core mock pattern for all `build_observation_from_dom` tests. `MagicMock()` stubs the entire Playwright `Page` API without importing playwright.

**SB3/PPO availability skip pattern** (test_trainer.py lines 18-24):
```python
try:
    import torch
    TORCH_OK = True
except ImportError:
    TORCH_OK = False

pytestmark = pytest.mark.skipif(not TORCH_OK, reason="PyTorch not installed")
```
Apply the same pattern for SB3 availability:
```python
try:
    from stable_baselines3 import PPO
    SB3_OK = True
except ImportError:
    SB3_OK = False
```
Tests that exercise `policy.predict()` or policy construction should be decorated with `@pytest.mark.skipif(not SB3_OK, reason="stable-baselines3 not installed")`.

**patch for lazy imports pattern** (test_train_policy.py lines 51-53):
```python
with patch("src.ml.train_policy._check_showdown_server") as mock_check:
    _check_showdown_server_if_local("localhost")
    mock_check.assert_called_once()
```
For browser_trainer tests that trigger the `account_configs_for_mode` call inside `train_browser()`, patch at the call site: `patch("src.ml.browser_trainer.account_configs_for_mode")`.

---

## Shared Patterns

### `is_commissioner()` access guard
**Source:** `src/bot/cogs/admin.py` lines 21-29
**Apply to:** `train_browser_cmd` in `AdminCog`
```python
@is_commissioner()
async def train_browser_cmd(self, interaction: discord.Interaction, ...) -> None:
```

### `asyncio.create_task()` + `defer()` + `followup.send()` trio
**Source:** `src/bot/cogs/admin.py` lines 210, 229-244
**Apply to:** `train_browser_cmd`
```python
await interaction.response.defer(thinking=True)
status_msg: discord.Message | None = None
try:
    status_msg = await interaction.followup.send(embed=..., wait=True)
except discord.NotFound:
    log.warning("[train-browser] followup.send got 10062; continuing without channel embed")
    try:
        await interaction.user.send("Training is starting. You'll receive a DM when done.")
    except Exception:
        pass
asyncio.create_task(_run_browser_training(interaction, format, timesteps, channel_msg=status_msg))
```

### TRAINING_MAP format whitelist validation
**Source:** `src/bot/cogs/admin.py` lines 212-217 and lines 446-447
**Apply to:** Both `train_browser_cmd` and `_run_browser_training`
```python
if format not in TRAINING_MAP:
    await interaction.followup.send(
        f"Unknown format `{format}`. Check `/spar` autocomplete for valid formats.",
        ephemeral=True,
    )
    return
```
This satisfies ASVS V5 input validation and the STRIDE tampering threat (arbitrary format string injection).

### `run_in_executor` for blocking sync code
**Source:** `src/bot/cogs/admin.py` lines 358-366 (pull-models pattern)
**Apply to:** `_run_browser_training` — `train_browser()` uses `sync_playwright()` and must not run on the event loop
```python
loop = asyncio.get_running_loop()
final_path = await loop.run_in_executor(
    None,
    functools.partial(train_browser, fmt=fmt, total_timesteps=timesteps, results_dir=results_dir),
)
```

### `_try_edit` for live embed updates
**Source:** `src/bot/cogs/admin.py` lines 408-414
**Apply to:** `_run_browser_training` — edit both channel embed and send DM on completion
```python
await _try_edit(channel_msg, done_embed)
```

### Dependency guard with `# pragma: no cover`
**Source:** `src/ml/train_policy.py` lines 48-63 and `src/ml/browser_trainer.py` lines 227-291
**Apply to:** Any new SB3 or playwright import block added to browser_trainer.py
```python
try:  # pragma: no cover
    from playwright.sync_api import sync_playwright
except ImportError:
    raise RuntimeError("Playwright is not installed. Run: pip install playwright && playwright install chromium")
```

---

## No Analog Found

All five files have close analogs in the codebase. No files require falling back to RESEARCH.md patterns exclusively.

| File | Note |
|------|------|
| `tests/unit/test_browser_trainer.py` | Closest analog is `test_train_policy.py`; the MagicMock Playwright page pattern comes from RESEARCH.md Code Examples (no existing codebase test uses it yet) |

---

## Metadata

**Analog search scope:** `src/ml/`, `src/bot/cogs/`, `tests/unit/`, `requirements.txt`
**Files scanned:** 5 primary reads + targeted grep searches
**Pattern extraction date:** 2026-05-19
