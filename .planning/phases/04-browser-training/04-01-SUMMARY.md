---
phase: 04-browser-training
plan: 01
status: complete
completed: "2026-05-20"
---

# Summary — Plan 04-01: Fix Browser Trainer Bugs

## What Was Done

Three bugs blocking browser training fixed; playwright dependency added.

### Bug 1 — Credential routing (showdown_modes.py:51)
- Changed `if mode == MODE_SHOWDOWN:` → `if mode in (MODE_SHOWDOWN, MODE_BROWSER):`
- Updated ValueError message: "Public Showdown training" → "Browser/Showdown training"
- Verified: `account_configs_for_mode(MODE_BROWSER)` now raises `ValueError` without env vars

### Bug 2 — Wrong results dir (browser_trainer.py)
- Changed module-level `DEFAULT_RESULTS_DIR = "src/ml/models/results"` → `"data/ml/results"`
- Function-level import from `train_policy` inside `train_browser()` already imports correct value
- Module-level constant retained for external importers (test_showdown_player.py verifies this)

### Bug 3a — playwright dependency (requirements.txt)
- Added: `playwright>=1.52.0          # Headless browser automation for browser training`

### Bug 3b — PPO never learns (browser_trainer.py)
- Added `_ReplayEnv` class at module level (directly importable for Plan 02 tests)
  - Lazy imports in `__init__` (gymnasium, OBS_DIM, N_ACTIONS_GEN9) — no heavy deps at module load
  - `reset()` returns zeros; `step()` pops transitions or returns terminal zeros
- Added `all_transitions: list[tuple] = []` before outer battle loop
- Added `transitions: list[tuple] = []` per-battle alongside `rewards`
- Appends `(obs.copy(), 0.0, False)` after each `_pick_move_from_obs` call
- Appends `(build_observation_from_dom(page1), reward, True)` at battle end
- Extends `all_transitions` after each battle
- Calls `policy.learn()` at each checkpoint interval (clears `all_transitions` after)
- Calls `policy.learn()` with remaining transitions before final `policy.save()`
- Lambda capture bug avoided: `lambda t=all_transitions: _ReplayEnv(t)` default-arg pattern

## Verification

- `ast.parse(browser_trainer.py)` → OK
- `ruff check src/ml/browser_trainer.py src/ml/showdown_modes.py` → All checks passed
- `account_configs_for_mode(MODE_BROWSER)` without env vars → raises `ValueError` ✓
- `grep -c "policy\.learn(" browser_trainer.py` → 2 ✓
- `grep -c "_ReplayEnv" browser_trainer.py` → 5 ✓
- Existing tests: 94 passed, 0 failed after DEFAULT_RESULTS_DIR fix

## Files Modified

- `src/ml/showdown_modes.py` — credential routing fix
- `src/ml/browser_trainer.py` — results dir fix, _ReplayEnv class, policy.learn() calls
- `requirements.txt` — playwright>=1.52.0
