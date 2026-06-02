---
id: ISS-001
title: MCTSPlayer — unit and integration tests
status: done
phase: "05"
closed: 2026-05-31
---

# ISS-001 Solution — MCTSPlayer: Unit and Integration Tests

## Analysis

Phase 05's readiness criterion required "MCTSPlayer has passing unit and integration tests with
meaningful coverage." Investigation found the unit side was already complete — `tests/unit/test_ml_self_play.py`
(46 tests, 100% line coverage on `src/ml/self_play.py`) and `tests/unit/test_mcts.py` (covering
`MCTSNode`, `MCTS._expand/_select/_backprop` from `src/ml/mcts.py`) both existed and passed. The
**integration side was entirely absent**: no test that ran an actual battle over a live Showdown
connection, and no CI job to start a local server for it.

Two things were genuinely missing:

1. `tests/integration/test_mcts_battle.py` — an end-to-end test that spins an `MCTSPlayer` against
   poke-env's `RandomPlayer` over a real `ws://localhost:8000` connection.
2. `.github/workflows/tests.yml` — a CI workflow providing both a **unit matrix** (Python 3.11 ×
   3.12) and an **integration job** that starts a local Showdown server before running the new test.

`pytest.ini` also lacked the `integration` marker registration, causing pytest to warn about unknown
markers.

## Approach

### `pytest.ini`

Added the `integration` marker declaration so pytest recognises the mark without warnings:

```diff
 markers =
+    integration: end-to-end tests requiring a live local Showdown server
```

### `tests/integration/test_mcts_battle.py` (new file)

Module-level `_server_reachable()` TCP-probes `127.0.0.1:8000` at import time. The `pytestmark`
block applies three marks to every test in the module:

- `pytest.mark.integration` — selectable with `-m integration`
- `skipif(not POKE_ENV_AVAILABLE)` — skips without poke-env
- `skipif(not SERVER_UP)` — auto-skips locally when no Showdown server is running

`TestMCTSBattleIntegration.test_mcts_completes_full_battle_vs_random` runs one gen9randombattle
via `mcts_player.battle_against(random_opponent, n_battles=1)` with a 120 s timeout, then asserts:

- `n_finished_battles == 1`
- outcomes sum to 1 (win + loss + tie = exactly one)
- `len(mcts_player._test_buffer) > 0` (confirms `_battle_finished_callback` pushed experience)

The MCTSPlayer is constructed with `MCTSConfig(n_simulations=8, dirichlet_eps=0.0)` — fast enough
for CI without sacrificing the code path exercised.

### `.github/workflows/tests.yml` (new file)

**`unit` job** — Python 3.11 × 3.12 matrix, `fail-fast: false`:
- `actions/checkout`, `actions/setup-python` (pip-cached), install from `requirements.txt` + CPU torch
- `pytest -m "not integration"` — all non-integration tests
- Coverage gate: `pytest tests/unit/test_ml_self_play.py --cov=src.ml.self_play --cov-fail-under=80`

**`integration` job** — Python 3.12 only, Node 20, 25 min timeout:
- Clones `pokemon-showdown`, runs `npm install --ignore-scripts`
- Writes minimal `config/config.js` (`port 8000`, `127.0.0.1`, `noipchecks`, `nothrottle`)
- Starts `node pokemon-showdown start --no-security` in background
- Polls `curl -sf http://localhost:8000` up to 30 × 2 s; exits 1 if server never comes up
- `pytest -m integration -o addopts="-v --tb=short"` (clears global `--cov` flag)

## Code Changes

```diff
# pytest.ini — added integration marker
+    integration: end-to-end tests requiring a live local Showdown server

# tests/integration/test_mcts_battle.py — new file (key excerpt)
+SERVER_UP = _server_reachable()
+
+pytestmark = [
+    pytest.mark.integration,
+    pytest.mark.skipif(not POKE_ENV_AVAILABLE, reason="poke-env not installed"),
+    pytest.mark.skipif(not SERVER_UP,
+        reason="No Showdown server on localhost:8000 — start it first"),
+]
+
+class TestMCTSBattleIntegration:
+    async def test_mcts_completes_full_battle_vs_random(self, mcts_player, random_opponent):
+        await asyncio.wait_for(
+            mcts_player.battle_against(random_opponent, n_battles=1),
+            timeout=120.0,
+        )
+        assert mcts_player.n_finished_battles == 1
+        assert (mcts_player.n_won_battles + mcts_player.n_lost_battles
+                + mcts_player.n_tied_battles == 1)
+        assert len(mcts_player._test_buffer) > 0

# .github/workflows/tests.yml — new file (integration job excerpt)
+      - name: Start local Showdown server
+        run: |
+          node pokemon-showdown start --no-security > /tmp/showdown.log 2>&1 &
+          for i in $(seq 1 30); do
+            sleep 2
+            if curl -sf --max-time 2 http://localhost:8000 >/dev/null 2>&1; then
+              echo "Showdown server ready"; break
+            fi
+          done
```

## Verification

```bash
# Unit tests (excludes integration)
pytest -m "not integration" -q

# Integration (requires local Showdown on :8000)
pytest -m integration -v

# Coverage gate
pytest tests/unit/test_ml_self_play.py -o addopts="" \
  --cov=src.ml.self_play --cov-fail-under=80 --cov-report=term-missing
```

CI: both `unit` (3.11 + 3.12) and `integration` jobs green on GitHub Actions
(run 26850017291, commit 63ff7f7).

## Related

- [[ISS-001-mcts-unit-integration-tests]] — source issue
- [[ISS-002-mcts-wire-training-opponent|ISS-002]] — next: MCTSPlayer as training opponent
- [[ISS-002-SOLUTION]] — solution for ISS-002
