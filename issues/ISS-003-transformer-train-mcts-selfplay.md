---
id: ISS-003
title: BattleTransformer — train to convergence via MCTS self-play
status: open
priority: high
phase: "05"
labels: [ml, training, transformer]
created: 2026-05-31
---

# ISS-003 — BattleTransformer: Train to Convergence via MCTS Self-Play

## Summary

Run a full training session using MCTSPlayer self-play that produces a saved BattleTransformer checkpoint with demonstrably decreasing validation loss.

## Context

The transformer architecture exists but has never been trained via MCTS self-play. This is the culminating deliverable of Phase 05 — without a trained checkpoint, Phase 06 (/spar inference) cannot proceed.

## Acceptance Criteria

- [ ] Training run using MCTSPlayer self-play completes without error
- [ ] Saved `BattleTransformer` checkpoint exists at `src/ml/models/transformer_checkpoint.pt`
- [ ] Validation loss decreases across epochs (logged to `logs/transformer_training.log`)
- [ ] PPO-only training path (`train_all.py`) continues to work unchanged

## Dependencies

- [[ISS-001-mcts-unit-integration-tests]]
- [[ISS-002-mcts-wire-training-opponent]]

## Files Likely Touched

- `src/ml/transformer.py` (or equivalent model file)
- `src/ml/train_policy.py`
- GitHub Actions workflow (may need new training job)

## Notes

Phase 05 success criterion 3: "A training run using MCTSPlayer self-play produces a saved BattleTransformer checkpoint with decreasing validation loss across epochs."
