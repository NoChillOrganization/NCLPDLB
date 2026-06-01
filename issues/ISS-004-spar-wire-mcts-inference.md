---
id: ISS-004
title: /spar — wire use_mcts=True inference path
status: done
priority: high
phase: "06"
labels: [bot, inference, mcts, transformer]
created: 2026-05-31
closed: 2026-06-01
---

# ISS-004 — /spar: Wire Transformer+MCTS Inference Path

## Summary

`showdown_player.py` `use_mcts=True` path must be fully wired so that `/spar` routes battle decisions through transformer + MCTS lookahead when a trained checkpoint is present.

## Context

Phase 06 goal: `/spar` uses the strongest available inference engine. When `transformer_checkpoint.pt` exists, battle decisions go through the transformer + MCTS. When absent, falls back to PPO.

## Acceptance Criteria

- [ ] `showdown_player.py` `use_mcts=True` path loads `transformer_checkpoint.pt` and routes decisions through MCTS lookahead
- [ ] A Discord user running `/spar` with a trained transformer checkpoint observes MCTS-selected moves in battle
- [ ] Switching inference modes requires no code change — only presence/absence of checkpoint file

## Dependencies

- [[ISS-003-transformer-train-mcts-selfplay]] — needs a trained checkpoint to test against

## Files Likely Touched

- `src/bot/showdown_player.py`
- `src/ml/self_play.py`

## Notes

Phase 06 success criteria 1–2: "showdown_player.py use_mcts=True path loads the transformer model and routes battle decisions through MCTS lookahead."

## Resolution (2026-06-01)

The `choose_move` MCTS branch (`showdown_player.py:140-156`) was already wired; the real gap was
`BotChallenger.__init__` never forwarding `use_mcts`/`transformer_path`.

**Changes made:**
- `src/ml/showdown_player.py`: Added `DEFAULT_TRANSFORMER_CHECKPOINT` constant and
  `resolve_transformer_checkpoint()` pure helper (no torch/poke-env). Added optional
  `transformer_path` param to `BotChallenger.__init__`; on construction it auto-detects the
  checkpoint and forwards `use_mcts=True, transformer_path=ckpt` to `ShowdownBotPlayer`.
- `tests/unit/test_showdown_player.py`: Added `TestResolveTransformerCheckpoint` (6 tests, all pass).

Mode switching requires no code change — only presence/absence of `transformer_checkpoint.pt`
(Phase 06 criterion 4). True e2e verification pending VM transformer training (ISS-006 Step 3).
