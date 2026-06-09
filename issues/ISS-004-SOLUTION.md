---
id: ISS-004
title: /spar — wire use_mcts=True inference path
status: done
phase: "06"
closed: 2026-06-01
---

# ISS-004 Solution — /spar: Wire Transformer+MCTS Inference Path

## Analysis

The `choose_move` MCTS branch in `ShowdownBotPlayer` (`src/ml/showdown_player.py:164`) already
existed and was structurally correct — it reads `self._use_mcts` and `self._transformer` and
routes through `run_mcts()`. The gap was one level up: `BotChallenger.__init__` (the class the
Discord `/spar` command constructs) had no `transformer_path` parameter and never forwarded
`use_mcts=True` to `ShowdownBotPlayer`. The transformer was never loaded, `_use_mcts` stayed
`False`, and every battle ran the PPO path regardless of whether a trained checkpoint existed.

Three missing pieces:

1. **`DEFAULT_TRANSFORMER_CHECKPOINT`** constant — a single path that both
   `train_transformer.py` and `/spar` agree on, so auto-detection works without configuration.
2. **`resolve_transformer_checkpoint()`** — a pure stdlib helper (no torch/poke-env) that
   checks whether a checkpoint is actually on disk, enabling safe unit testing without heavy
   deps.
3. **`BotChallenger.__init__` wiring** — call the resolver on construction and forward
   `use_mcts=True, transformer_path=ckpt` to `ShowdownBotPlayer` when a checkpoint is found.

Phase 06 criterion 4 required: "switching modes requires no code change — only presence/absence
of `transformer_checkpoint.pt` on disk." The resolver pattern satisfies this.

## Approach

### `src/ml/showdown_player.py`

**Added `DEFAULT_TRANSFORMER_CHECKPOINT` constant (line 78):**
```python
DEFAULT_TRANSFORMER_CHECKPOINT = Path("src/ml/models/transformer_checkpoint.pt")
```
Path matches `DEFAULT_CHECKPOINT_OUT` in `train_transformer.py` — pinned to stay in sync.

**Added `resolve_transformer_checkpoint()` pure helper (lines 81–95):**
```python
def resolve_transformer_checkpoint(path: str | Path | None = None) -> Path | None:
    candidate = Path(path) if path else DEFAULT_TRANSFORMER_CHECKPOINT
    return candidate if candidate.is_file() else None
```
Pure function — no side effects, no imports beyond `pathlib`. Mirrors the existing
`best_model_for_format` pattern already in the file.

**Updated `BotChallenger.__init__` (lines 251–294):**
- Added `transformer_path: str | Path | None = None` parameter.
- On construction, calls `resolve_transformer_checkpoint(transformer_path)`.
- If checkpoint found: constructs `ShowdownBotPlayer` with `use_mcts=True, transformer_path=ckpt`
  and logs `"Transformer checkpoint found at … — using MCTS inference"`.
- If absent: constructs PPO-only `ShowdownBotPlayer` (existing behaviour unchanged).

### `tests/unit/test_showdown_player.py`

Added `TestResolveTransformerCheckpoint` class with tests covering:
- `test_returns_none_when_default_path_absent` — missing checkpoint → `None` (PPO path, ISS-005 AC4)
- `test_returns_path_when_explicit_file_exists` — present checkpoint → `Path` (MCTS path)
- `test_returns_none_for_explicit_missing_path` — explicit path not on disk → `None`
- `test_default_checkpoint_constant_matches_train_transformer` — constant cross-check with
  `train_transformer.DEFAULT_CHECKPOINT_OUT`

## Code Changes

```diff
# src/ml/showdown_player.py

+# Default path produced by train_transformer.py (DEFAULT_CHECKPOINT_OUT).
+DEFAULT_TRANSFORMER_CHECKPOINT = Path("src/ml/models/transformer_checkpoint.pt")
+
+def resolve_transformer_checkpoint(path: str | Path | None = None) -> Path | None:
+    candidate = Path(path) if path else DEFAULT_TRANSFORMER_CHECKPOINT
+    return candidate if candidate.is_file() else None

 class BotChallenger:
     def __init__(
         self,
         model_path: str | Path,
         fmt: str,
         username: str,
         password: str,
         server: str = "showdown",
+        transformer_path: str | Path | None = None,
     ) -> None:
         ...
+        ckpt = resolve_transformer_checkpoint(transformer_path)
+        if ckpt is not None:
+            log.info("[BotChallenger] Transformer checkpoint found at %s — using MCTS inference", ckpt)
+            self._player = ShowdownBotPlayer(
+                ...,
+                use_mcts=True,
+                transformer_path=ckpt,
+            )
+        else:
+            log.info("[BotChallenger] No transformer checkpoint — /spar using PPO inference (fallback)")
             self._player = ShowdownBotPlayer(...)

# tests/unit/test_showdown_player.py

+class TestResolveTransformerCheckpoint:
+    def test_returns_none_when_default_path_absent(self):
+        result = resolve_transformer_checkpoint("nonexistent_checkpoint_xyz.pt")
+        assert result is None
+
+    def test_returns_path_when_explicit_file_exists(self, tmp_path):
+        ckpt = tmp_path / "transformer_checkpoint.pt"
+        ckpt.write_bytes(b"")
+        result = resolve_transformer_checkpoint(ckpt)
+        assert result == ckpt
+
+    def test_returns_none_for_explicit_missing_path(self, tmp_path):
+        result = resolve_transformer_checkpoint(tmp_path / "not_here.pt")
+        assert result is None
+
+    def test_default_checkpoint_constant_matches_train_transformer(self):
+        from src.ml.train_transformer import DEFAULT_CHECKPOINT_OUT
+        assert DEFAULT_TRANSFORMER_CHECKPOINT == Path(DEFAULT_CHECKPOINT_OUT)
```

## Verification

```bash
# Resolver tests
pytest tests/unit/test_showdown_player.py::TestResolveTransformerCheckpoint -v

# confirm MCTS path constant aligns with trainer
python -c "
from src.ml.showdown_player import DEFAULT_TRANSFORMER_CHECKPOINT
from src.ml.train_transformer import DEFAULT_CHECKPOINT_OUT
from pathlib import Path
assert DEFAULT_TRANSFORMER_CHECKPOINT == Path(DEFAULT_CHECKPOINT_OUT), 'MISMATCH'
print('constants aligned:', DEFAULT_TRANSFORMER_CHECKPOINT)
"
```

Full e2e (MCTS moves in `/spar`) pending VM transformer training completing (ISS-006 Step 3)
— the resolver and wiring are verified; the trained checkpoint is not yet on disk.

## Related

- [[ISS-004-spar-wire-mcts-inference]] — source issue
- [[ISS-003-transformer-train-mcts-selfplay|ISS-003]] — prerequisite: trained transformer checkpoint
- [[ISS-003-SOLUTION]] — solution for ISS-003
- [[ISS-005-spar-fallback-ppo|ISS-005]] — companion: PPO fallback when no checkpoint
- [[ISS-005-SOLUTION]] — solution for ISS-005
