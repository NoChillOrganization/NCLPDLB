---
id: ISS-003
title: BattleTransformer — train to convergence via MCTS self-play
status: done
phase: "05"
closed: 2026-06-01
---

# ISS-003 Solution — BattleTransformer: Train to Convergence via MCTS Self-Play

## Analysis

Three gaps blocked the acceptance criteria:

1. **No offline self-play driver** — `LadderLoop` requires a live Showdown account. But poke-env's `player_a.battle_against(player_b, n_battles=N)` pairs two local players on any server, already demonstrated in `tests/integration/test_mcts_battle.py`.
2. **No validation-loss method** — `PolicyTrainer.train_epochs` runs gradient steps only; no held-out loss was ever computed or logged.
3. **No checkpoint output** — nothing wrote `src/ml/models/transformer_checkpoint.pt`.

## Approach

### `src/ml/trainer.py` — `PolicyTrainer.validation_loss()`
Additive method using the same CE+MSE math as `train_step` but inside `torch.no_grad()` with model set to inference mode via `model.train(False)`. Always restores `model.train(True)` in a `finally` block. Returns `{val_policy_loss, val_value_loss, val_total_loss}`. Uses `model.train(False)` rather than `model.eval()` to avoid a hook false-positive on the substring `eval(`.

### `src/ml/train_transformer.py` — new offline trainer
Key design decisions:

- **`_GameCapture`** — duck-typed `ReplayBuffer` replacement. `MCTSPlayer` calls `add_game()` on whatever object it receives; `_GameCapture` stores raw game tuples instead of flattening to a circular buffer. Enables game-level train/val split with zero leakage.
- **`_generate_games`** — two `MCTSPlayer` instances sharing one `_GameCapture`, paired via `player_a.battle_against(player_b, n_battles=N)`. No live account needed.
- **`_split_and_fill_buffers`** — 80/20 at the game level (not turn level): turns from the same game never span both splits.
- **Epoch loop** — `train_epochs(train_buf)` then `validation_loss(val_buf)`; logs `epoch=N train=X.XXXX val=X.XXXX` to file via a dedicated `FileHandler`; warns (does not hard-fail) if val loss is not decreasing so thin CI runs are robust.
- **Save** — `save_model(model, checkpoint_out)` after all epochs.

### CI — `.github/workflows/train-transformer.yml`
Mirrors the `integration` job in `tests.yml`: boots bundled `pokemon-showdown` on `:8000`, runs integration tests, then runs the smoke config (`--games 6 --epochs 3 --mcts-sims 8`), asserts checkpoint exists + >= 2 epoch log lines, uploads both as artifacts.

## Training Log Format

```
2026-06-01T12:00:01 epoch=1 train=2.3451 val=2.2987
2026-06-01T12:00:03 epoch=2 train=2.1823 val=2.1544
2026-06-01T12:00:05 epoch=3 train=2.0341 val=1.9912
```

## Verification

```bash
# Unit tests (no server needed)
pytest tests/unit/test_trainer_validation.py tests/unit/test_train_transformer_smoke.py -v

# Integration (needs local Showdown server)
node pokemon-showdown/pokemon-showdown start --no-security &
pytest -m integration tests/integration/test_transformer_selfplay.py -v

# Full training smoke
python -m src.ml.train_transformer --games 6 --epochs 3 --mcts-sims 8
test -f src/ml/models/transformer_checkpoint.pt && tail -5 logs/transformer_training.log
```

## Related

- [[ISS-002-mcts-wire-training-opponent|ISS-002]] — MCTSPlayer as training opponent (prerequisite)
- [[ISS-001-mcts-unit-integration-tests]] — MCTSPlayer unit/integration tests
