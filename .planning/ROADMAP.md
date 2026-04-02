# Roadmap — NCLPDLB ML Knowledge Injection

*Generated: 2026-03-17 | Last updated: 2026-04-02 (spec panel review)*

---

## Phase Overview

| Phase | Name | Status | Goal |
|-------|------|--------|------|
| 01 | Observation Space Expansion | ✅ complete | Add type effectiveness to obs vector; OBS_DIM 44→48 |
| 02 | Curriculum Opponent | ⬜ pending | MaxBasePowerPlayer at epoch 0; win-rate threshold |
| 03 | Behavioral Cloning Pre-Training | ⬜ pending | pretrain.py + --pretrain flag + workflow update |

---

## Phase 01 — Observation Space Expansion

**Goal:** Expand observation vector from 44 to 48 floats by adding per-move type effectiveness
signals, enabling the agent to learn type matchups from reward signal instead of discovering
them blindly.

**Success Criteria:**
- `OBS_DIM == 48` in `battle_env.py` (and `OBS_DIM_DOUBLES` updated atomically)
- New `src/ml/type_chart.py` module with `get_type_effectiveness(move, defender)` function
- `_move_features()` in `battle_env.py` returns 5 values (power, acc, type_id, prio, **type_eff**)
- Log2 normalization: `log2(e)/2.0` → [-1,1]; unknown type → 0.0; immunity → -1.0
- Stellar Tera type special-cased before matrix lookup
- Assertion at env init catches future OBS_DIM mismatches
- `train_all.py` runs without modification (backward-compatible)
- All OBS_DIM=44 checkpoints deprecated (documented in commit message)

**Research flag:** None — type chart math and poke-env API fully documented in research.

**Key files:**
- `src/ml/type_chart.py` (NEW)
- `src/ml/battle_env.py` (MODIFIED)

**Blocks:** Phase 02 (type_eff obs needed to validate curriculum), Phase 03 (BC Transitions must use OBS_DIM=48)

---

## Phase 02 — Curriculum Opponent

**Goal:** Replace RandomPlayer epoch-0 opponent with MaxBasePowerPlayer to give the agent
meaningful training signal during early exploration, and gate self-play graduation behind
an explicit win-rate threshold.

**Pre-condition:** Phase 01 complete (OBS_DIM=48 settled).

**Success Criteria:**
- `train_policy.py` `SelfPlayOpponent` epoch-0 path uses `MaxBasePowerPlayer`
- Import is `from poke_env.player import MaxBasePowerPlayer` (verified)
- Win-rate threshold: rolling `win_rate(last=500) >= 0.70` required before graduation to self-play
  - "last=500" means a deque-based rolling window of the most recent 500 episodes
  - Window is per-format; each format tracks its own rolling window independently
  - Graduation resets the window (fresh 500-episode window post-graduation)
- `SelfPlayOpponent` gains a `WinRateTracker` attribute (deque capacity=500); state lives in
  `train_policy.py`, not in `BattleEnv` or `SelfPlayCallback`
- Force-graduation escape hatch: if `win_rate(last=500) < 0.70` after `N_MAX_EPOCH0_STEPS`
  (configurable, default: 2_000_000), force-graduate to self-play and emit
  `WARNING: forced graduation after {N} steps — win rate {rate:.2%} below threshold`
- `BattleEnv` and `SelfPlayCallback` unchanged
- `train_all.py` call signature unchanged
- On graduation, log: `INFO: Graduated to self-play at episode {N} (win_rate={rate:.2%})`

**State transition (explicit):**
```
epoch 0:  opponent = MaxBasePowerPlayer  →  tracks rolling win rate
          win_rate >= 0.70 (OR steps >= N_MAX_EPOCH0_STEPS)  →  graduation
epoch 1+: opponent = SelfPlayCheckpoint  →  MaxBasePowerPlayer fully replaced (no fallback)
```

**Executable scenarios:**
```
Given: SelfPlayOpponent initialised for gen9randombattle at epoch 0
When:  Training starts
Then:  opponent is MaxBasePowerPlayer instance

Given: Rolling window has 499 episodes at win_rate = 69.8%
When:  Episode 500 completes with a win (window now 500, rate still <70%)
Then:  Opponent remains MaxBasePowerPlayer

Given: Rolling window reaches win_rate = 70.2% at episode 523
When:  Graduation check runs after episode 523
Then:  Opponent swaps to self-play checkpoint
And:   Log emits "Graduated to self-play at episode 523 (win_rate=70.20%)"

Given: Steps reach N_MAX_EPOCH0_STEPS with rolling win_rate = 61%
When:  Force-graduation check triggers
Then:  Opponent swaps to self-play checkpoint
And:   WARNING log emitted with actual rate
```

**Required tests (must be added to `tests/unit/test_train_policy.py`):**
- `test_curriculum_epoch0_uses_maxbasepower` — mock poke-env; assert opponent type at epoch 0
- `test_graduation_at_threshold` — inject 70% win sequence into rolling window; assert swap
- `test_no_graduation_below_threshold` — inject 69% sequence; assert no swap
- `test_graduation_timeout` — advance steps to N_MAX_EPOCH0_STEPS; assert force-graduation
- `test_win_rate_tracker_rolling_window` — assert deque evicts oldest episode at capacity=500

**Research flag:** None — MaxBasePowerPlayer constructor is a one-liner; already verified.

**Key files:**
- `src/ml/train_policy.py` (MODIFIED — WinRateTracker, MaxBasePowerPlayer, graduation logic)

**Depends on:** Phase 01

---

## Phase 03 — Behavioral Cloning Pre-Training

**Goal:** Build a BC pre-training pipeline that extracts (state, action) pairs from human
Showdown replays and initializes PPO actor weights, giving the agent a head start on move
selection before any RL updates.

**Pre-condition (research gate):** Run `/gsd:research-phase 03` before planning this phase.
Evaluate Metamon (https://github.com/UT-Austin-RPL/metamon) action space compatibility.
- If unmappable turn rate on held-out replays > 15%: use simplified BC fallback
  (top-N move heuristic; document decision in commit message)
- If unmappable rate ≤ 15%: proceed with full BC pipeline as specified below

**Success Criteria:**
- `src/ml/pretrain.py` BC training loop using `imitation` library
- BC input: BattleRecords from replay_parser.py → feature_extractor.py (OBS_DIM=48 arrays)
- BC output: `bc_actor_checkpoint.pt` (actor-only keys: `mlp_extractor.*` + `action_net.*`)
  - `value_net.*` keys must be absent from checkpoint
- `train_policy.py` `--pretrain <path>` flag:
  - Loads actor-only keys from `.pt` file
  - Resets step counter to 0 (distinct from `--resume` which restores optimizer state + counter)
  - Ignores optimizer state if present in the file
- `ent_coef` schedule after BC init:
  - Steps 0–100k: `ent_coef = 0.05`
  - Steps 100k+: linear anneal from 0.05 → 0.01 over the next 100k steps, then hold at 0.01
- Action index mapping:
  - If `unmappable_turns / total_turns > 0.05` across the full dataset:
    raise `ActionMappingError(rate=<float>, samples=<list[str]>)` with the actual rate and
    up to 5 sample unmapped turns (for debugging)
  - If rate ≤ 0.05: log `INFO: Action mapping complete — {n} turns mapped, {k} skipped ({rate:.2%})`
- `pip install imitation` added to `requirements.txt`
- GitHub Actions workflow updated: scrape replays → pretrain → RL

**`pretrain.py` CLI interface:**
```
python -m src.ml.pretrain \
  --replays  data/replays/gen9ou/      # path to replay JSON directory
  --output   data/ml/bc/bc_actor.pt    # output checkpoint path
  --format   gen9ou                    # Showdown format (for action space)
  --epochs   10                        # BC training epochs (default: 10)
  --lr       1e-3                      # learning rate (default: 1e-3)
  --max-unmappable 0.05                # abort threshold (default: 0.05)
```

**`--pretrain` vs `--resume` semantic distinction (explicit):**
- `--pretrain <path>`: actor weights only, step counter = 0, no optimizer state restored
- `--resume <path>`:   full checkpoint restore (actor + critic + optimizer + step counter)
These flags are mutually exclusive; passing both raises `ValueError`.

**Executable scenarios:**
```
Given: replay dataset with 1,000 battles (OBS_DIM=48)
When:  pretrain.py runs to completion
Then:  bc_actor_checkpoint.pt exists
And:   checkpoint keys match mlp_extractor.* and action_net.* only
And:   value_net.* keys are absent

Given: --pretrain bc_actor.pt passed to train_policy.py
When:  PPO initialises at step 0
Then:  Actor weights loaded from checkpoint (differ from random init)
And:   ent_coef == 0.05 at step 0
And:   ent_coef == 0.05 at step 99_999
And:   ent_coef == 0.04 at step 150_000  (midpoint of anneal)
And:   ent_coef == 0.01 at step 200_000  (anneal complete)
And:   ent_coef == 0.01 at step 500_000  (held)

Given: dataset where 6% of turns are unmappable
When:  pretrain.py runs
Then:  ActionMappingError raised with rate ≈ 0.06 and ≤ 5 sample turns

Given: --pretrain and --resume both passed
When:  train_policy.py parses args
Then:  ValueError raised: "--pretrain and --resume are mutually exclusive"
```

**Required tests (must be added to `tests/unit/test_train_policy.py` and new `tests/unit/test_pretrain.py`):**
- `test_bc_checkpoint_keys` — assert actor-only keys in output; assert value_net absent
- `test_pretrain_weight_loading` — assert loaded weights differ from random init
- `test_ent_coef_at_step_0` — assert ent_coef == 0.05
- `test_ent_coef_at_step_100k` — assert ent_coef == 0.05 (boundary)
- `test_ent_coef_midpoint_anneal` — assert ent_coef == 0.04 at step 150k
- `test_ent_coef_after_anneal` — assert ent_coef == 0.01 at step 200k+
- `test_action_mapping_abort_above_threshold` — inject >5% unmappable; assert ActionMappingError
- `test_action_mapping_ok_below_threshold` — inject 4% unmappable; assert completes
- `test_pretrain_resume_mutex` — assert ValueError when both flags passed

**Key files:**
- `src/ml/pretrain.py` (NEW)
- `src/ml/train_policy.py` (MODIFIED — --pretrain flag, ent_coef schedule)
- `.github/workflows/train.yml` (MODIFIED — scrape + pretrain steps)
- `requirements.txt` (MODIFIED — add imitation)

**Depends on:** Phase 01 (BC Transitions must use OBS_DIM=48 obs vectors)

---

## Dependency Graph

```
Phase 01 (obs expansion) ✅
     |
     +---> Phase 02 (curriculum) — validates Phase 01 encoding
     |
     +---> Phase 03 (BC pretrain) — requires OBS_DIM=48 settled
                  ^
                  research gate: /gsd:research-phase 03 required before planning
```

---

*Last updated: 2026-04-02 after spec panel review (Wiegers, Adzic, Nygard, Fowler, Crispin)*
