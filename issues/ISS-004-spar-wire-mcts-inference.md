---
id: ISS-004
title: /spar — wire use_mcts=True inference path
status: open
priority: high
phase: "06"
labels: [bot, inference, mcts, transformer]
created: 2026-05-31
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
