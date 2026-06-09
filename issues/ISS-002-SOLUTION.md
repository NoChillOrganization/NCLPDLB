---
id: ISS-002
title: MCTSPlayer — wire as training pipeline opponent
status: done
phase: "05"
closed: 2026-06-01
---

# ISS-002 Solution — MCTSPlayer as Training Pipeline Opponent

## Analysis

`train_policy.train()` hard-wired `CurriculumOpponent` at a single construction point (line 804). Two blockers prevented dropping `MCTSPlayer` into that slot:

1. `MCTSPlayer.__init__` required `replay_buffer` and `stats` with no defaults — could not be constructed without a live buffer.
2. `CurriculumCallback.on_step` calls `opponent.load_policy(latest_zip)` every swap interval; `MCTSPlayer` had no such method, so the callback would crash immediately.

## Approach

**Minimum-viable changes, backward-compatible at every call site:**

### `src/ml/self_play.py`
- `__init__` signature: `replay_buffer: Any = None`, `stats: SharedStats | None = None` — existing callers pass by keyword, unaffected.
- Added no-op `load_policy(self, path) -> None` — satisfies `CurriculumCallback`'s swap contract without mutating the fixed-strength tree-search opponent.
- `_battle_finished_callback`: wrapped `add_game` call in `if self._replay_buffer is not None:` — prevents crash when player is used as an opponent (no buffer configured). Also guarded the `len(self._replay_buffer)` debug log inside the same branch.

### `src/ml/train_policy.py`
- `train()` signature gains `opponent_type: str = "curriculum"`, `opponent_checkpoint: str | None = None`.
- Single construction point replaced with branch:
  - `mcts`: loads `BattleTransformer` (from checkpoint or random weights), constructs `MCTSPlayer(model, MCTSConfig(), replay_buffer=None, stats=None, **mcts_kwargs)`. Strips `is_doubles` from kwargs (MCTSPlayer is singles-only) and raises `ValueError` for doubles formats.
  - `curriculum` (default): unchanged `CurriculumOpponent(**opp_kwargs)`.
- CLI: `--opponent {curriculum,mcts}` (default `curriculum`), `--opponent-checkpoint TRANSFORMER.pt`.
- `__main__` threads `args.opponent` / `args.opponent_checkpoint` into `train()`.

### `src/ml/train_all.py`
**Unchanged.** Never passes `--opponent`; argparse default `curriculum` exactly reproduces prior behaviour.

## Code Changes

```diff
# self_play.py — MCTSPlayer.__init__
-    replay_buffer: Any,
-    stats: SharedStats,
+    replay_buffer: Any = None,
+    stats: "SharedStats | None" = None,

# self_play.py — new method (before choose_move)
+    def load_policy(self, path: Any) -> None:
+        """No-op: MCTS opponent uses a fixed transformer; ignore PPO checkpoint swaps."""
+        log.debug("[MCTSPlayer] load_policy(%s) ignored — fixed MCTS opponent", path)

# self_play.py — _battle_finished_callback
-    try:
-        self._replay_buffer.add_game(...)
+    if self._replay_buffer is not None:
+        try:
+            self._replay_buffer.add_game(...)

# train_policy.py — opponent branch
-    opponent = CurriculumOpponent(**opp_kwargs)
+    if opponent_type == "mcts":
+        ...
+        opponent = MCTSPlayer(model=tmodel, mcts_config=MCTSConfig(),
+                              replay_buffer=None, stats=None, **mcts_kwargs)
+    else:
+        opponent = CurriculumOpponent(**opp_kwargs)
```

## Verification

```bash
# Argparse flag present, default is curriculum
python -m src.ml.train_policy --help | grep -A2 opponent

# Unit tests
pytest tests/unit/test_train_policy_opponent.py -v
```

## Related

- [[ISS-001-mcts-unit-integration-tests]] — MCTSPlayer unit/integration tests (prerequisite)
- [[ISS-003-transformer-train-mcts-selfplay|ISS-003]] — offline MCTS self-play trainer (next step)
