---
id: ISS-001
title: MCTSPlayer — unit and integration tests
status: done
priority: high
phase: "05"
labels: [testing, ml, mcts]
created: 2026-05-31
closed: 2026-05-31
---

# ISS-001 — MCTSPlayer: Unit and Integration Tests

## Summary

`self_play.py` MCTSPlayer has no passing tests. Phase 05 cannot ship until coverage is meaningful.

## Context

MCTSPlayer exists in `self_play.py` but was never covered by tests. Phase 05 (MCTSPlayer + Transformer Training) requires it to be production-ready before it can be wired into the training pipeline.

## Acceptance Criteria

- [x] Unit tests cover MCTSPlayer node expansion, backprop, and move selection
- [x] Integration test: MCTSPlayer completes a full battle against RandomPlayer without error
- [x] Tests pass on GitHub Actions (Linux) in CI matrix
- [x] Coverage ≥ 80% on `self_play.py`

## Dependencies

- Phase 04 complete ✅

## Files Touched

- `src/ml/self_play.py` (no changes — already correct)
- `tests/unit/test_ml_self_play.py` (pre-existing; unit coverage was already 100%)
- `tests/integration/test_mcts_battle.py` (created)
- `.github/workflows/tests.yml` (created — unit matrix + integration job)
- `pytest.ini` (added `integration` marker registration)

## Notes

Phase 05 roadmap success criterion: "self_play.py MCTSPlayer has passing unit and integration tests
with meaningful coverage."

**Implementation notes (2026-05-31):**
- The issue's "no passing tests" claim was stale. `tests/unit/test_ml_self_play.py` already
  existed with 46 passing tests and 100% coverage on `src/ml/self_play.py`.
- MCTS tree expansion/backprop (`MCTSNode`, `MCTS._expand/_select/_backprop`) lives in
  `src/ml/mcts.py` and is covered by `tests/unit/test_mcts.py`.
- The "Files Likely Touched" in the original issue named `tests/unit/test_self_play.py` — the
  real file uses the `ml_` prefix (`test_ml_self_play.py`) matching the `src/ml/` module path.
  No duplicate was created.
- Integration test auto-skips when no server on `localhost:8000`; CI `integration` job starts
  a real local Showdown server so the battle executes on Linux.
