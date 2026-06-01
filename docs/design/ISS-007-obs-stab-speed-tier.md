# ISS-007 — Observation Space: STAB + Speed Tier Expansion

**Status:** in-progress  
**Phase:** backlog (gate: after Phase 06 + 48-dim training complete)  
**Priority:** low  
**Labels:** ml, obs-space  
**Depends on:** Phase 05 complete (checked), Phase 06 / ISS-004/005 done

---

## Current Layout (OBS_DIM = 48)

Defined in `src/ml/battle_env.py:52–67`. The vector is built by `build_observation()` at
line 145. Integrity enforced by `assert idx == OBS_DIM` at line 234.

```
Index range   Dim   Description
─────────────────────────────────────────────────────────────
[0]           1     Active mon — species hash / 10000
[1]           1     Active mon — HP fraction
[2..6]        5     Move slot 0 — (bp/250, acc/100, type_id/20, priority, type_eff)
[7..11]       5     Move slot 1
[12..16]      5     Move slot 2
[17..21]      5     Move slot 3
[22]          1     Active mon — status ID / 6
[23..28]      6     Active mon — stat boosts (atk/def/spa/spd/spe/acc), each (b+6)/12
──── active total = 29 ───────────────────────────────────────
[29]          1     Opponent active — species hash / 10000
[30]          1     Opponent active — HP fraction
[31]          1     Opponent active — status ID / 6
──── opp active = 3 ──────────────────────────────────────────
[32..37]      6     My team HP (6 slots), 0.0 if fainted/absent
[38..43]      6     Opponent team HP (6 slots), 1.0 if unknown
──── team HP = 12 ────────────────────────────────────────────
[44]          1     Weather ID / 5
[45]          1     Terrain ID / 4
[46]          1     Trick room (0/1)
[47]          1     Turn / 50
──── field = 4 ───────────────────────────────────────────────
TOTAL         48
```

---

## Proposed Additions (OBS_DIM 48 → 53)

### Feature 1 — STAB flag per move slot (4 floats)

**Rationale:** Whether a move is Same-Type Attack Bonus determines when to prefer it over a
higher-base-power non-STAB move. The type-effectiveness feature (already present) captures
what a move does *to the opponent*, but not whether the attacker gets a 1.5× boost. STAB
selection is one of the most common human heuristics in competitive play.

**Encoding:** One float per move slot appended immediately after the 4 existing 5-float slots.

```
[48]    1    Move slot 0 — STAB flag: 1.0 if active mon shares a type with move, else 0.0
[49]    1    Move slot 1 — STAB flag
[50]    1    Move slot 2 — STAB flag
[51]    1    Move slot 3 — STAB flag
```

**Computation:**
```python
def _stab_flag(move: "Move | None", mon: "Pokemon | None") -> float:
    if move is None or mon is None:
        return 0.0
    move_type = str(getattr(move, "type", "")).lower().split(".")[-1]
    mon_types = [str(t).lower().split(".")[-1] for t in (getattr(mon, "types", ()) or ())]
    return 1.0 if move_type in mon_types else 0.0
```

Append these 4 floats in `build_observation()` after the 29-dim active-mon block (before the
opponent-active block), or as a trailing section. The latter is simpler and less disruptive to
existing index constants. **Recommendation: append as new trailing section at [48..51].**

### Feature 2 — Relative speed tier (1 float)

**Rationale:** Speed determines turn order, which is critical for deciding whether to attack or
switch. If the active mon outspeeds the opponent, it moves first — aggressive plays are higher
value. If it's slower, it may need to pivot or use priority moves.

**Encoding:** One float representing the relative speed comparison.

```
[52]    1    Speed tier: 0.0 (slower), 0.5 (unknown/equal), 1.0 (faster)
```

**Computation:**
```python
def _speed_tier(active: "Pokemon | None", opp: "Pokemon | None") -> float:
    if active is None or opp is None:
        return 0.5  # unknown
    my_spe  = getattr(active, "base_stats", {}).get("spe", 0) or 0
    opp_spe = getattr(opp,    "base_stats", {}).get("spe", 0) or 0
    if my_spe == 0 and opp_spe == 0:
        return 0.5
    if my_spe > opp_spe:
        return 1.0
    if my_spe < opp_spe:
        return 0.0
    return 0.5
```

**Limitations and future refinements:**
- Base stats only — does not account for EVs, IVs, nature, or Choice Scarf / Speed boosts.
  Good enough as a first signal; the model will correlate 1.0 with priority moves and 0.0
  with defensive plays.
- Trick Room inverts speed order — the `trick_room` bit at [46] is already present, so the
  model can learn to invert the signal in that context.
- More nuanced encodings (e.g., a 5-tier ladder: much faster / slightly faster / equal /
  slightly slower / much slower) could be added in ISS-008+ but are out of scope here.

---

## Updated Layout (OBS_DIM = 53)

```
Index range   Dim   Description
─────────────────────────────────────────────────────────────
[0..28]       29    Active mon (unchanged)
[29..31]       3    Opponent active (unchanged)
[32..37]       6    My team HP (unchanged)
[38..43]       6    Opponent team HP (unchanged)
[44..47]       4    Field conditions (unchanged)
[48..51]       4    STAB flags (move slots 0–3)          ← NEW
[52]           1    Relative speed tier                  ← NEW
─────────────────────────────────────────────────────────────
TOTAL         53
```

---

## Doubles Parity (OBS_DIM_DOUBLES)

Currently `OBS_DIM_DOUBLES = 80` (`battle_env.py:55`). The doubles encoder in
`build_doubles_observation()` (line 533+) has its own layout. ISS-007 should add matching STAB
and speed features for the doubles active mon(s) and update `OBS_DIM_DOUBLES` accordingly.
Exact doubles sizing is out of scope for this design doc — track as a sub-task of ISS-007
implementation.

---

## Implementation Checklist (next milestone, after Phase 06 gate)

- [ ] Branch: `feat/obs-dim-53-stab-speed`
- [ ] `src/ml/battle_env.py`: Add `_stab_flag()` and `_speed_tier()` helpers
- [ ] `src/ml/battle_env.py`: Extend `build_observation()` to append features at [48..52]
- [ ] `src/ml/battle_env.py`: Bump `OBS_DIM = 48` → `53` (both line 53 literal and line 67 recomputation)
- [ ] `src/ml/battle_env.py`: Update assert at line 234 (auto-correct by dim math; verify)
- [ ] Update `OBS_DIM_DOUBLES` analogously (`build_doubles_observation`)
- [ ] `tests/unit/test_battle_env.py`: Update any `== 48` assertions to `== 53`
- [ ] `tests/unit/test_transformer_model.py`, `test_mcts.py`: update obs-dim fixtures (use `OBS_DIM` import, not literals)
- [ ] Document the checkpoint break in STATUS.md and issues.md — existing 48-dim checkpoints are incompatible
- [ ] Dispatch a fresh "Train ML Models" CI run and VM `train_transformer` with `OBS_DIM=53`

## Gate

**Do NOT merge this branch while any of the following are in flight:**
- GitHub Actions "Train ML Models" run #41 (22 formats, 500k steps, 48-dim)
- VM `train_transformer` producing a 48-dim `transformer_checkpoint.pt`
- Any other CI training job targeting the current 48-dim model

---

## References

- `src/ml/battle_env.py:53–67` — constants, layout comments
- `src/ml/battle_env.py:145–236` — `build_observation()` implementation
- `src/ml/battle_env.py:234` — dimension assert
- `src/ml/transformer_model.py:126` — `BattleTransformer.__init__` takes `obs_dim=OBS_DIM`
- `PROJECT_INDEX.md` Key Decisions: "OBS_DIM 44→48 (not 54) — Validate 4-float expansion before adding STAB + speed tier"
