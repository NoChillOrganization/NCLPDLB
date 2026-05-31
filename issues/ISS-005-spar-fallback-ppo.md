---
id: ISS-005
title: /spar — graceful PPO fallback when no transformer checkpoint
status: open
priority: high
phase: "06"
labels: [bot, inference]
created: 2026-05-31
---

# ISS-005 — /spar: Graceful PPO Fallback

## Summary

When no transformer checkpoint exists, `/spar` must fall back to PPO silently — no error, no degraded UX for the Discord user.

## Context

This is the backward-compatibility guarantee for Phase 06. Users who haven't run a transformer training session should still get a working `/spar` command powered by PPO.

## Acceptance Criteria

- [ ] `/spar` with no `transformer_checkpoint.pt` on disk completes successfully using PPO
- [ ] No error message or degraded embed shown to the Discord user
- [ ] Log line emitted indicating fallback mode (for ops visibility)
- [ ] Unit test: mock missing checkpoint → assert PPO path taken

## Dependencies

- [[ISS-004-spar-wire-mcts-inference]] — must be implemented before fallback path can be tested end-to-end

## Files Likely Touched

- `src/bot/showdown_player.py`
- `tests/unit/test_showdown_player.py`

## Notes

Phase 06 success criterion 3–4: "A Discord user running /spar when no transformer checkpoint exists receives a normal PPO-powered battle with no error or degraded UX."
