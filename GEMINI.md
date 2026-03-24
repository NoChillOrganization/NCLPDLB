# GEMINI.md — NCLPDLB AI Log

## Current Intent

Implementing the ML training improvement phases (01–03) for the PPO battle agent.

## Phase Status

| Phase | Name | Status |
|---|---|---|
| 01 | Observation Space Expansion (OBS_DIM 44 → 48) | ✅ COMPLETE |
| 02 | Curriculum Opponent (MaxBasePowerPlayer) | 🔲 NEXT |
| 03 | Behavioral Cloning (BC) Pre-training | 🔲 PENDING |

---

## Phase 01 — VERIFIED COMPLETE (2026-03-24)

- `src/ml/battle_env.py`: `OBS_DIM = 48`, `MOVE_FEATS = 5` (was 44 / 4)
- `src/ml/type_chart.py`: `get_type_effectiveness_float()` exists — log2 normalized [-1, 1]
- `tests/unit/test_battle_env.py`: **43 passed, 2 skipped** (100% coverage on `battle_env.py`)
- `type_chart.py` at 89% (line 28 is `pragma: no cover` fallback — acceptable)

---

## Phase 02 — Plan (NEXT TO IMPLEMENT)

**Goal:** Use `MaxBasePowerPlayer` as the epoch-0 curriculum opponent instead of pure random.
Graduate to self-play when agent achieves ≥70% win-rate over a rolling 500-episode window.

**Changes needed in `src/ml/train_policy.py`:**

1. Add `MaxBasePowerPlayer` import in the `poke_env` guard block (line 58):
   ```python
   from poke_env.player import MaxBasePowerPlayer, RandomPlayer
   ```

2. Add a `CurriculumCallback(BaseCallback)` class (new, below `SelfPlayCallback`):
   - Fields: `opponent_player`, `save_dir`, `swap_every`, `win_threshold` (0.70), `min_episodes` (500)
   - Rolling window: deque of last `min_episodes` episode outcomes (from `ep_info_buffer`)
   - State machine: `_phase` ∈ `{"warmup", "selfplay"}`
   - `_on_step()`:
     - Extract episode outcomes from `self.locals["infos"]` (reward > 0 = win)
     - When `_phase == "warmup"` and window full and win_rate ≥ threshold → call `_graduate()`
     - When `_phase == "selfplay"` and `num_timesteps - _last_swap >= swap_every` → call `_save_and_swap()`
   - `_graduate()`: saves first checkpoint, loads it into `opponent_player`, logs graduation
   - `_save_and_swap()`: same as current `SelfPlayCallback._save_and_swap()`

3. Add `CurriculumOpponent(MaxBasePowerPlayer)` class (when `POKE_ENV_OK`):
   - Has `load_policy(path)` method (loads PPO, graduates from max-base-power play to PPO play)
   - Has `_policy: PPO | None = None`, `_is_doubles: bool`
   - `choose_move()`: if `_policy` is None → delegate to `MaxBasePowerPlayer.choose_move(battle)`;
     else → use PPO obs/predict same as current `SelfPlayOpponent.choose_move()`

4. In `train()`: replace `SelfPlayOpponent(...)` with `CurriculumOpponent(...)` and replace
   `[checkpoint_cb, selfplay_cb]` callbacks with `[checkpoint_cb, curriculum_cb]`.

**Tests to add/update in `tests/unit/test_train_policy.py`:**
- `TestCurriculumCallback`: init, warmup→selfplay graduation, win-rate threshold, swap in selfplay phase
- `TestCurriculumOpponent` (mock-based): `load_policy`, `choose_move` with/without policy

**Key invariants:**
- `train()` public signature unchanged (`fmt`, `total_timesteps`, `swap_every`, `save_dir`, `results_dir`, `resume`, `team_format`, `server`)
- `SelfPlayCallback` class stays (it's tested and exported)
- `CurriculumCallback` is the new default used by `train()`

---

## Context Notes

- Python 3.14.3, pytest-9.0.2
- `poke_env` is installed (`POKE_ENV_AVAILABLE = True`, `POKE_ENV_OK = True`)
- `stable_baselines3` is installed (`SB3_OK = True`)
- PowerShell — use `Select-Object -First N` instead of `head -N`
- Output to file trick: `cmd > tmp/out.txt 2>&1` then `view_file`
- `tests/unit/test_battle_env.py` has 564 lines — full reference available
- `STATUS.md` and `.planning/STATE.md` still need updating (low priority)
