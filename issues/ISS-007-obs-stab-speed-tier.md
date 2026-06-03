---
id: ISS-007
title: Observation space — add STAB and speed tier features
status: in-progress
priority: low
phase: backlog
labels: [ml, obs-space]
created: 2026-05-31
---

# ISS-007 — Observation Space: STAB + Speed Tier Expansion

## Summary

After the 4-float type-effectiveness expansion (OBS_DIM 44→48) proves out, add STAB bonus flags and relative speed tier to the observation vector.

## Context

From PROJECT.md Key Decisions: "OBS_DIM 44→48 (not 54) — Validate 4-float expansion before adding STAB + speed tier." This is the explicit next step deferred from v1.0.

## Acceptance Criteria

- [ ] OBS_DIM expanded from 48 → N (TBD based on STAB + speed tier encoding)
- [ ] Each move slot encodes STAB flag (1 float)
- [ ] Active mon relative speed tier encoded (1 float)
- [ ] Existing model checkpoints documented as incompatible (new training runs required)
- [ ] All tests pass with new obs dimension

## Dependencies

- Phase 05 complete (don't expand obs mid-transformer training)

## Notes

OBS_DIM changes invalidate saved checkpoints — this must be a planned milestone boundary, not an incremental change.

## Progress (2026-06-01)

Design doc written: `docs/design/ISS-007-obs-stab-speed-tier.md`.

Specifies:
- STAB flag per move slot: 4 floats at [48..51]
- Relative speed tier: 1 float at [52]
- OBS_DIM 48 → 53

Implementation checklist, doubles parity, gate conditions, and full file list documented.
Code on branch `feat/obs-dim-53-stab-speed` — **gated behind Phase 06 + CI run #41 completion**.
Do not implement while 48-dim training (Actions run 26753447485) is in flight.

## Progress (2026-06-02)

Gate conditions cleared: ISS-004/005 closed, 22-format 500k training run complete (ISS-006).

**Implementation complete on `feat/obs-dim-53-stab-speed`:**
- [x] `_stab_flag()` helper added — returns 1.0 if move type ∈ active mon's types
- [x] `_speed_tier()` helper added — base-stat comparison: 1.0=faster, 0.5=unknown, 0.0=slower
- [x] `build_observation()` extended: floats appended at [48..52]
- [x] `OBS_DIM = 48 → 53` (literal + computed form both updated)
- [x] `OBS_DIM_DOUBLES = 80 → 90` (STAB+speed for 2 active slots, 5 floats each)
- [x] `build_doubles_observation()` extended with per-slot STAB+speed trailing section
- [x] `tests/unit/test_battle_env.py`: literal `== 48` updated; turn/terrain tests fixed to
      explicit indices (47 / 45); 12 new unit tests for `_stab_flag`, `_speed_tier`, new obs slots
- [x] 113 tests pass, 0 failures
- [ ] Dispatch fresh training run with OBS_DIM=53 (next milestone)
