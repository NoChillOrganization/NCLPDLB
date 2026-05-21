# NCLPDLB Full Audit Report — v2 (Fresh Re-Audit)
**Repository:** https://github.com/NoChillModeOnline/NCLPDLB  
**Branches Audited:** `master` (105 files) + `main` (3 files) — freshly downloaded  
**Date:** 2026-03-26  
**Files Checked:** 108 total (104 .py + 4 .yml across both branches)

---

## Quick Summary

| Severity | Count | Status |
|---|---|---|
| 🔴 Critical | 1 | ✅ RESOLVED (secrets removed from repo) |
| 🟡 Real Bugs | 3 | Needs fixing |
| 🟡 Code Quality | 4 | Should fix |
| 🟢 Minor / Warnings | 3 | Low priority |
| ✅ Clean | 9 categories | No issues |

---

## ✅ Previously Critical — NOW RESOLVED

`.env` and `credentials.json` are **no longer accessible** on either `main` or `master`. Both branches confirmed clean. Google Service Account key and Discord tokens are no longer exposed.

---

## 🟡 Real Bugs

### 1. Auction Bid Stub — `src/services/draft_service.py:340`

`place_bid()` is not finished. It validates the player's budget but never checks whether another player has already bid higher, and never records the bid:

```python
# CURRENT (broken):
# TODO: track current bids per nomination
return BidResult(success=True, current_high=amount)

# FIX — needs something like:
current_bids = draft.nomination_bids.setdefault(draft.current_nomination_id, {})
current_high_val = max(current_bids.values(), default=0)
if amount <= current_high_val:
    return BidResult(success=False, error=f"Bid must exceed current high of {current_high_val}")
current_bids[player_id] = amount
return BidResult(success=True, current_high=amount)
```
This means auction drafts currently let any player "win" with any bid amount.

---

### 2. `stellar` Type Missing from `feature_extractor.py` TYPE_IDS

`src/ml/battle_env.py` has `"stellar": 19` in its TYPE_IDS (19 types total).  
`src/ml/feature_extractor.py` stops at `"fairy": 18` (18 types, no stellar).

Both files use TYPE_IDS independently, but both normalize type lookups by dividing by their respective max ID. The inconsistency becomes a problem if stellar-type Pokémon or moves are encountered:
- `battle_env.py` returns ID `19` for stellar
- `feature_extractor.py` would return `0` (unknown) for stellar, and normalizes by `/18.0` instead of `/19.0`

**Fix — add stellar to feature_extractor.py:**
```python
# src/ml/feature_extractor.py line 69 — change:
"bug": 12, "rock": 13, "ghost": 14, "dragon": 15, "dark": 16, "steel": 17, "fairy": 18
# to:
"bug": 12, "rock": 13, "ghost": 14, "dragon": 15, "dark": 16, "steel": 17, "fairy": 18, "stellar": 19
```
And update the `/18.0` normalization on line 280 to `/19.0`.

---

### 3. Misleading Comment in `feature_extractor.py:54-60`

The comment block above `STATE_FEATURE_DIM = 19` shows a layout that sums to 48 — which is `battle_env.py`'s observation space, not feature_extractor's. The value `19` is actually correct (2 + 12 + 2 + 1 + 2 = 19 from the actual feature vector). The comment was copy-pasted from the wrong file.

```python
# CURRENT (wrong comment, correct value):
# State feature vector layout (per turn): MATCHES BattleEnv.py build_observation()
#   Active mon:    [species_id, hp, 4×(5-feats), status, 6×boosts] = 2 + 20 + 1 + 6 = 29
#   ...
#   TOTAL:         48
STATE_FEATURE_DIM = 19

# FIX — correct the comment:
# State feature vector layout (per turn, offline replay pipeline):
#   [p1_active_id, p2_active_id]       = 2
#   p1 team HPs (6 slots)              = 6
#   p2 team HPs (6 slots)              = 6
#   [p1_fainted, p2_fainted]           = 2
#   [turn_norm]                        = 1
#   [last_move_p1, last_move_p2]       = 2
#   TOTAL:                             = 19
STATE_FEATURE_DIM = 19
```

---

## 🟡 Code Quality

### 4. `print()` in Production `src/` Functions

These files use `print()` inside functions that are called at runtime (not just in `__main__`). Since `logging` is already imported and configured in each file, these should be converted:

| File | Lines | Count |
|---|---|---|
| `src/ml/train_policy.py` | 548–559, 575, 626, 638–641 | 17 calls |
| `src/ml/train_all.py` | 229–257 | 10 calls |
| `src/data/smogon.py` | 40, 131, 141, 153 | 4 calls |
| `src/ml/replay_parser.py` | 507 | 1 call |
| `src/ml/replay_scraper.py` | 211–212 | 2 calls |

During GitHub Actions CI these mix raw stdout with structured CI step logs, making failures harder to trace. All have `log = logging.getLogger(__name__)` already defined — just swap:
```python
print(f"...") → log.info("...")
print(f"[smogon] Warning: ...") → log.warning("...")
print(f"[parser] Skipping ...: {exc}") → log.warning("...")
```

---

## 🟢 Minor / Warnings

### 5. `tmp/check_obs.py:59` — Invalid Escape Sequence (SyntaxWarning)
```python
# CURRENT:
const_match = re.search(f"{inc} = (\d+)", content)
# FIX:
const_match = re.search(rf"{inc} = (\d+)", content)
```

### 6. `scripts/sync_commands.py:6` — Docstring Escape (SyntaxWarning)
```python
# CURRENT (in docstring):
.venv\Scripts\python scripts\sync_commands.py
# FIX:
.venv/Scripts/python scripts/sync_commands.py
```

### 7. `docker-compose.yml` (main branch):1 — Deprecated `version` Key
```yaml
# CURRENT:
version: "3.9"
# FIX: delete this line entirely (Compose v2 doesn't need it)
```

---

## ✅ All-Clear Items

| Area | Result |
|---|---|
| `train-models.yml` actions | All correct: `checkout@v6`, `setup-python@v6`, `setup-node@v6`, `upload-artifact@v7`, `download-artifact@v8` |
| Node version vs env var | Node `24` ✅ matches `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` |
| `python-publish.yml` | All action versions correct (`checkout@v4`, `setup-python@v5`, `upload/download-artifact@v4`) |
| Python syntax | All 104 `.py` files parse cleanly — zero SyntaxErrors |
| Internal imports | All `src.*` cross-module imports resolve — no missing modules |
| Type chart | `analytics_service.py` — all 18 attacking types defined, 6 spot-checked matchups all correct |
| `.gitignore` | Covers `.env`, `credentials.json`, `__pycache__`, `*.py[cod]`, `*.pt`, `*.pth`, ML model dirs, logs |
| `pytest.ini` | `asyncio_mode = auto`, `--cov=src`, `--cov-report=term-missing` all correct |
| `requirements.txt` | Torch commented out intentionally; CI installs it separately via `pip install torch` |
| `replay_parser.py:20` | That `print()` is inside a docstring example, not executed code |

---

## Priority Action List

| # | Priority | File | What to Do |
|---|---|---|---|
| 1 | 🟡 P1 | `src/services/draft_service.py:340` | Implement bid deduplication — store bids, reject if ≤ current high |
| 2 | 🟡 P1 | `src/ml/feature_extractor.py:69,280` | Add `"stellar": 19` to TYPE_IDS; change `/18.0` → `/19.0` |
| 3 | 🟡 P2 | `src/ml/feature_extractor.py:54-60` | Fix the wrong comment (says TOTAL=48, should say TOTAL=19) |
| 4 | 🟡 P2 | `train_policy.py`, `train_all.py`, `smogon.py`, `replay_parser.py`, `replay_scraper.py` | Replace `print()` with `log.info()` / `log.warning()` |
| 5 | 🟢 P3 | `tmp/check_obs.py:59` | Add `r` prefix: `rf"..."` |
| 6 | 🟢 P3 | `scripts/sync_commands.py:6` | Forward slashes in docstring path |
| 7 | 🟢 P4 | `docker-compose.yml` | Remove deprecated `version: "3.9"` line |

