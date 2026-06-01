---
id: ISS-003
title: BattleTransformer — train to convergence via MCTS self-play
status: done
priority: high
phase: "05"
labels: [ml, training, transformer]
created: 2026-05-31
closed: 2026-06-01
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

## Implementation (2026-06-01)

- `src/ml/trainer.py` — `PolicyTrainer.validation_loss(buffer, batch_size=256)` added: same CE+MSE math as `train_step`, wrapped in `torch.no_grad()` / `model.train(False)`, always restores `model.train(True)` in `finally`
- `src/ml/train_transformer.py` — new offline MCTS self-play trainer: `_GameCapture` (duck-typed buffer for game-level split), `_generate_games` (two MCTSPlayers on local Showdown via `battle_against`), `_split_and_fill_buffers` (80/20 game-level), epoch loop logging `epoch=N train=X val=X` to `logs/transformer_training.log`, saves to `src/ml/models/transformer_checkpoint.pt`
- `tests/unit/test_trainer_validation.py` — no-grad param-unchanged check, empty-buffer returns `{}`
- `tests/unit/test_train_transformer_smoke.py` — monkeypatched game gen, checkpoint written, ≥2 log lines
- `tests/integration/test_transformer_selfplay.py` — real 2-game run (auto-skip without server)
- `.github/workflows/train-transformer.yml` — CI job: boots Showdown, runs `--games 6 --epochs 3`, asserts checkpoint + ≥2 log lines, uploads artifacts
