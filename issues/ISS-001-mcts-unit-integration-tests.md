---
id: ISS-001
title: MCTSPlayer — unit and integration tests
status: open
priority: high
phase: "05"
labels: [testing, ml, mcts]
created: 2026-05-31
---

# ISS-001 — MCTSPlayer: Unit and Integration Tests

## Summary

`self_play.py` MCTSPlayer has no passing tests. Phase 05 cannot ship until coverage is meaningful.

## Context

MCTSPlayer exists in `self_play.py` but was never covered by tests. Phase 05 (MCTSPlayer + Transformer Training) requires it to be production-ready before it can be wired into the training pipeline.

## Acceptance Criteria

- [ ] Unit tests cover MCTSPlayer node expansion, backprop, and move selection
- [ ] Integration test: MCTSPlayer completes a full battle against RandomPlayer without error
- [ ] Tests pass on GitHub Actions (Linux) in CI matrix
- [ ] Coverage ≥ 80% on `self_play.py`

## Dependencies

- Phase 04 complete ✅

## Files Likely Touched

- `src/ml/self_play.py`
- `tests/unit/test_self_play.py` (create)
- `tests/integration/test_mcts_battle.py` (create)

## Notes

Phase 05 roadmap success criterion: "self_play.py MCTSPlayer has passing unit and integration tests with meaningful coverage."
