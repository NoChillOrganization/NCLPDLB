---
id: ISS-008
title: Observation space — ability and item awareness
status: done
phase: backlog
closed: 2026-06-05
---

# ISS-008 Solution — Observation space: Ability and Item Awareness

## Analysis

After ISS-007 validated STAB+speed (OBS_DIM 48→53), the next milestone encodes held-item and
ability effects so the agent can learn to play around Leftovers, Choice items, Intimidate, etc.
Explicitly deferred in PROJECT.md ("Ability/item awareness in obs — follow-on milestone after
type chart proves out"). Gate override applied 2026-06-03: ISS-007 + ISS-008 folded into one
78-dim checkpoint break instead of two sequential training runs.

## Approach

- `src/ml/battle_env.py` — lookup maps, two bucket helpers, extended `build_observation()` and
  `build_doubles_observation()`; `OBS_DIM = 53 → 78`; `OBS_DIM_DOUBLES = 90 → 140`
- `src/ml/feature_extractor.py` — `_species_to_id_normalized` fixed (H11) to delegate to
  `_stable_species_id` (MD5-based, cross-process deterministic); `extract_features` delegates
  to `build_observation()` as single source of truth
- `tests/unit/test_battle_env.py` — `TestAbilityBuckets` (11 tests) + `TestItemBuckets` (9 tests)
  + slot-range integration tests

## Code Changes

### Lookup maps (`battle_env.py`)

```python
SPEED_BOOST_ABILITIES   = {"speedboost", "swiftswim", "chlorophyll", "sandrush", "slushrush", ...}
ATK_BOOST_ABILITIES     = {"hugepower", "purepower", "gorillatacitics", ...}
REGEN_ABILITIES         = {"regenerator"}
PRIORITY_ABILITIES      = {"prankster", "galewings", "triage"}
CONTACT_PUNISH_ABILITIES= {"roughskin", "ironbarbs", "flamebody", ...}
CONDITIONAL_BOOST_ABILITIES = {"technician", "sheerforce", "adaptability", ...}
ABSORB_TYPE_ABILITIES   = {"voltabsorb": "electric", "waterabsorb": "water", ...}
ENTRY_EFFECT_ABILITIES  = {"intimidate", "download", "trace", ...}
CHOICE_ITEMS = {"choiceband", "choicespecs", "choicescarf"}
HEAL_ITEMS   = {"leftovers", "blacksludge", "shellbell"}
# ... STATUS_ITEMS, SASH_ITEMS, OFFENCE_ITEMS, DEFENSIVE_ITEMS, SPEED_ITEMS
```

### Bucket helpers

```python
def _ability_buckets(mon) -> list[float]:
    """8 own-ability floats + 6 opp-ability floats = 14 total."""
    ...

def _item_buckets(mon) -> list[float]:
    """7 own-item floats + 4 opp-item floats = 11 total."""
    ...
```

### Observation extension (`build_observation`)

```python
# Slots [53..66]: ability buckets (own 8 + opp 6)
obs.extend(_ability_buckets(my_active))
obs.extend(_ability_buckets(opp_active, own=False))
# Slots [67..77]: item buckets (own 7 + opp 4)
obs.extend(_item_buckets(my_active))
obs.extend(_item_buckets(opp_active, own=False))
assert len(obs) == OBS_DIM  # == 78
```

`build_doubles_observation()` extended with 50-float ability+item tail (2 slots × 25).
`OBS_DIM_DOUBLES = 90 → 140`.

### feature_extractor fixes (H11)

```python
def _species_to_id_normalized(self, species: str) -> float:
    # Delegates to battle_env._stable_species_id (MD5-based, cross-process deterministic)
    return battle_env._stable_species_id(species)

def extract_features(self, battle) -> np.ndarray:
    # Delegates to build_observation() — single source of truth
    return np.array(build_observation(battle), dtype=np.float32)
```

## Verification

```bash
cd F:\NCLPDLB
python -m pytest tests/unit/test_battle_env.py -v
# 137 tests pass, 2 skipped (poke_env import-skip on Windows)
# TestAbilityBuckets (11), TestItemBuckets (9), slot-range integration all green

# Cross-process determinism check
python -c "from src.ml.battle_env import _stable_species_id; print(_stable_species_id('Garchomp'))"
# 0.11927...  (same across fresh processes)
```

Commit `4b67013`, PR #139. 48-dim AND 53-dim checkpoints incompatible with 78-dim; one fresh
training run on x86 VM covers both (follow-on infra milestone, not a code AC).

## Related

- [[ISS-008-ability-item-obs-awareness]] — source issue
- [[ISS-007-obs-stab-speed-tier]] — STAB+speed (folded into same 78-dim break)
