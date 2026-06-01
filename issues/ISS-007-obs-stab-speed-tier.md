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
