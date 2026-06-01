---
id: ISS-002
title: MCTSPlayer — wire as training pipeline opponent
status: done
priority: high
phase: "05"
labels: [ml, training, mcts]
created: 2026-05-31
closed: 2026-06-01
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

## Implementation (2026-06-01)

- `src/ml/self_play.py` — `MCTSPlayer.__init__`: `replay_buffer`/`stats` now optional (default `None`); no-op `load_policy()` added; `_battle_finished_callback` guards `add_game` with `if self._replay_buffer is not None:`
- `src/ml/train_policy.py` — `train()` gains `opponent_type: str = "curriculum"` and `opponent_checkpoint: str | None = None`; CLI gets `--opponent {curriculum,mcts}` + `--opponent-checkpoint`; MCTSPlayer branch raises `ValueError` for doubles formats
- `src/ml/train_all.py` — **unchanged** (never passes `--opponent`; argparse default = `curriculum`)
- `tests/unit/test_train_policy_opponent.py` — new; covers argparse defaults, `load_policy` no-op, doubles guard
