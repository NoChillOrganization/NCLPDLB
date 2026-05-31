---
id: ISS-002
title: MCTSPlayer — wire as training pipeline opponent
status: open
priority: high
phase: "05"
labels: [ml, training, mcts]
created: 2026-05-31
---

# ISS-002 — MCTSPlayer: Wire into Training Pipeline

## Summary

The training pipeline must accept MCTSPlayer as the self-play opponent, replacing or augmenting the current PPO self-play opponent.

## Context

Current pipeline (`train_all.py`, `train_policy.py`) uses a PPO checkpoint as self-play opponent. MCTSPlayer should be a selectable opponent so the transformer can train against tree-search quality play.

## Acceptance Criteria

- [ ] `train_policy.py` accepts `--opponent mcts` flag
- [ ] MCTSPlayer can be substituted for the PPO self-play opponent without breaking existing `train_all.py` invocations (backward-compatible)
- [ ] A training run with MCTSPlayer opponent completes without error
- [ ] Existing `train_all.py` (PPO-only path) continues to work unchanged

## Dependencies

- [[ISS-001-mcts-unit-integration-tests]] — MCTSPlayer must be tested before wiring

## Files Likely Touched

- `src/ml/train_policy.py`
- `src/ml/self_play.py`
- `src/ml/train_all.py` (must remain unchanged)

## Notes

Phase 05 success criterion: "The training pipeline accepts MCTSPlayer as the self-play opponent (replaces or augments the PPO self-play opponent)."
