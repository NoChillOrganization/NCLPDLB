# Training Workflow Fix — Design Spec
**Date:** 2026-04-11  
**Status:** Approved  

## Problem

GitHub Actions training jobs have been failing with `TimeoutError: Agent is not challenging` since commit `88f58f0`. The root cause is a mis-wiring of credentials introduced by that fix:

- `BattleEnv` uses two internal poke-env `_EnvPlayer` instances (`agent1`, `agent2`) for the real WebSocket connections to Showdown.
- `SingleAgentWrapper` injects battles into `CurriculumOpponent` directly via `_battles[battle_tag]` — it is a pure **decision-maker** and needs no Showdown connection.
- The fix in `88f58f0` put `account_configuration=acc2` on `CurriculumOpponent`, not on `env.agent2` where it belongs.
- Result: `agent2` connects as an auto-generated guest while `CurriculumOpponent` opens a redundant third authenticated connection that can interfere with the challenge handshake.

## Solution (3 parts)

### Part 1 — Code fix (`src/ml/train_policy.py`)

1. Add `account_configuration2=acc2` to `env_kwargs` in `make_env()` so `BattleEnv.agent2` authenticates as `SHOWDOWN_TRAIN_USER2`.
2. Remove `account_configuration` from `CurriculumOpponent`'s kwargs — it is a move-selector only.
3. Add `challenge_timeout=180` to `env_kwargs` as a 3-minute safety net (up from 60s default) for slow auth handshakes.

### Part 2 — Pre-training connectivity step (`train-models.yml`)

Add a new step **before** `Train ${{ matrix.config.format }}` that:
- Verifies all four credential env vars are non-empty (fast fail).
- Opens `wss://sim3.psim.us/showdown/websocket` and reads the `|challstr|` greeting to confirm the server is reachable from the GitHub Actions runner.
- Exits 0 on success, exits 1 with a clear human-readable error on any failure.

### Part 3 — Cancel running bad workflow

Cancel workflow run `24288867208` via `gh run cancel` before pushing the fix.

### Part 4 — Delete duplicate config files

Remove 7 untracked "space-copy" files (`pytest 2.ini`, `pyrightconfig 2.json`, `requirements 2.txt`, `run_bot 2.bat`, `.coverage 2`, `audit-fixes 2.patch`, `discord_commands 2.csv`) that are identical to (or obsolete vs.) their originals.

## Non-goals

- No changes to `max-parallel: 1` — this constraint is still correct and prevents a different nametaken issue with `agent2`'s auto-generated name if we ever re-enable parallel jobs.
- No changes to poke-env version or PPO hyperparameters.

## Test Plan

- Full test suite (`1332 tests`) must continue to pass at 100% coverage after code changes.
- Trigger `train-models.yml` workflow manually after push; first job should pass the connectivity check and begin training without `TimeoutError`.
