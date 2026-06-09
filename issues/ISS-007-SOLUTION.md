---
id: ISS-007
title: Observation space — add STAB and speed tier features
status: done
phase: backlog
closed: 2026-06-05
---

# ISS-007 Solution — Observation space: STAB + Speed Tier

## Analysis

The observation vector was fixed at OBS_DIM=48 (4-float type effectiveness, positions [44..47]).
STAB flags and relative speed tier were explicitly deferred after the 48-dim expansion validated.
This issue implements the next step: OBS_DIM 48→53.

## Approach

- `src/ml/battle_env.py` — two helpers + extended `build_observation()` and `build_doubles_observation()`
- `tests/unit/test_battle_env.py` — literal index updates + 12 new unit tests
- `OBS_DIM` constant updated everywhere (literal + computed form)

## Code Changes

### New helpers (`battle_env.py`)

```python
def _stab_flag(move, active_mon) -> float:
    """1.0 if move type is in active_mon's types, else 0.0."""
    if active_mon is None:
        return 0.0
    return 1.0 if move.type in active_mon.types else 0.0

def _speed_tier(my_mon, opp_mon) -> float:
    """1.0=faster, 0.5=unknown, 0.0=slower (base-stat comparison)."""
    if my_mon is None or opp_mon is None:
        return 0.5
    my_spd  = getattr(my_mon,  "base_stats", {}).get("spe", 0)
    opp_spd = getattr(opp_mon, "base_stats", {}).get("spe", 0)
    if my_spd == 0 and opp_spd == 0:
        return 0.5
    if my_spd > opp_spd:
        return 1.0
    if my_spd < opp_spd:
        return 0.0
    return 0.5
```

### Observation extension (`build_observation`)

```python
# Slots [48..51]: STAB flag per move slot (4 moves)
for move in moves[:4]:
    obs.append(_stab_flag(move, my_active))
# Slot [52]: relative speed tier
obs.append(_speed_tier(my_active, opp_active))
# OBS_DIM = 53
```

`build_doubles_observation()` extended with per-slot STAB+speed trailing section (5 floats × 2 slots).
`OBS_DIM_DOUBLES = 80 → 90`.

## Verification

```bash
cd F:\NCLPDLB
python -m pytest tests/unit/test_battle_env.py -v
# 113 tests pass, 0 failures (at merge)
# 137 tests pass, 2 skipped after ISS-008 folded in (commit 4b67013, PR #139)
```

OBS_DIM 53 superseded by ISS-008 gate override — single 78-dim checkpoint break instead of two
sequential training runs. ISS-007 + ISS-008 folded into one branch `feat/obs-ability-item`.

## Related

- [[ISS-007-obs-stab-speed-tier]] — source issue
- [[ISS-008-ability-item-obs-awareness]] — folded into same 78-dim checkpoint break
