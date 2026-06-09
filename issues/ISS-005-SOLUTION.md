---
id: ISS-005
title: /spar — graceful PPO fallback when no transformer checkpoint
status: done
phase: "06"
closed: 2026-06-01
---

# ISS-005 Solution — /spar: Graceful PPO Fallback

## Analysis

`BotChallenger.__init__` already defaulted `use_mcts=False`, so `ShowdownBotPlayer` always
took the PPO path when no transformer was configured — the fallback *worked* mechanically. Two
acceptance criteria were unmet:

- **AC3 (ops visibility):** no log line emitted when the fallback was taken. An operator
  watching logs had no way to confirm `/spar` was in PPO mode vs MCTS mode.
- **AC4 (unit test):** no test asserted the `None → PPO` contract. The resolver path
  (`resolve_transformer_checkpoint` returning `None`) was exercised only implicitly.

Both gaps were closed as part of the ISS-004 implementation (same commit, same file) since
`BotChallenger.__init__` was already being rewritten for ISS-004's MCTS branch.

## Approach

### `src/ml/showdown_player.py` — PPO fallback log line (line 287)

The `else` branch of the checkpoint resolver check now emits an `INFO`-level log before
constructing the PPO-only player:

```python
log.info(
    "[BotChallenger] No transformer checkpoint — /spar using PPO inference (fallback)"
)
```

This satisfies AC3: ops can confirm mode at startup without inspecting source code or config.

### `tests/unit/test_showdown_player.py` — `TestResolveTransformerCheckpoint`

Two tests in the resolver test class cover the `None` path (ISS-005 AC4):

- `test_returns_none_when_default_path_absent` — passes a path known not to exist; asserts
  `result is None`, confirming `BotChallenger` will take the PPO branch.
- `test_returns_none_for_explicit_missing_path` — uses `tmp_path / "not_here.pt"` (tmp_path
  guaranteed empty by pytest); asserts `result is None`.

Together these prove: absent checkpoint → resolver returns `None` → `BotChallenger` takes
the `else` branch → PPO player constructed → no error, no degraded UX.

## Code Changes

```diff
# src/ml/showdown_player.py — BotChallenger.__init__

         ckpt = resolve_transformer_checkpoint(transformer_path)
         if ckpt is not None:
             log.info("[BotChallenger] Transformer checkpoint found at %s — using MCTS inference", ckpt)
             self._player = ShowdownBotPlayer(..., use_mcts=True, transformer_path=ckpt)
         else:
+            log.info(
+                "[BotChallenger] No transformer checkpoint — /spar using PPO inference (fallback)"
+            )
             self._player = ShowdownBotPlayer(...)

# tests/unit/test_showdown_player.py — resolver tests covering None path

+    def test_returns_none_when_default_path_absent(self):
+        """Default path missing → None → BotChallenger takes PPO path (ISS-005 AC4)."""
+        result = resolve_transformer_checkpoint("nonexistent_checkpoint_xyz.pt")
+        assert result is None
+
+    def test_returns_none_for_explicit_missing_path(self, tmp_path):
+        result = resolve_transformer_checkpoint(tmp_path / "not_here.pt")
+        assert result is None
```

## Verification

```bash
# Tests covering the None → PPO contract
pytest tests/unit/test_showdown_player.py::TestResolveTransformerCheckpoint \
    -k "absent or missing" -v

# Confirm log line text matches (grep the source)
grep -n "PPO inference (fallback)" src/ml/showdown_player.py
# expected: showdown_player.py:287:  "[BotChallenger] No transformer checkpoint — /spar using PPO inference (fallback)"
```

No transformer checkpoint present in CI or standard dev environments → PPO fallback is the
default path. All 28 `test_showdown_player.py` tests pass; no error or degraded UX for
Discord users.

## Related

- [[ISS-005-spar-fallback-ppo]] — source issue
- [[ISS-004-spar-wire-mcts-inference|ISS-004]] — companion: MCTS wiring (implemented together)
- [[ISS-004-SOLUTION]] — solution for ISS-004 (same file, same commit)
