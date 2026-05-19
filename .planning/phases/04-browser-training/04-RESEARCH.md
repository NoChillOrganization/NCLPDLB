# Phase 04: Browser Training - Research

**Researched:** 2026-05-19
**Domain:** Playwright browser automation, PPO experience collection, discord.py background tasks
**Confidence:** HIGH (all findings verified against codebase; library claims cited from official sources)

---

## Summary

Phase 04 wires together three components that already exist in the codebase but are not yet integrated:
`browser_trainer.py` (the Playwright training loop), `train_policy.py` (PPO hyperparams and checkpointing
patterns), and `admin.py` (the background-task cog pattern for long-running Discord commands). The work
is less about building new machinery and more about fixing concrete bugs in `browser_trainer.py` and
writing the Discord cog command that calls it.

The most critical finding is the **PPO experience gap**: `browser_trainer.py` runs a battle loop and
collects win/loss outcomes, but it **never calls `policy.learn()`**. Observations are fed into
`policy.predict()` for move selection, but no gradient update is performed after any rollout. The policy
is saved periodically but its weights never change from the initialization. This is the single most
important bug to fix in the phase.

The second critical finding is a **credential routing bug**: `account_configs_for_mode(MODE_BROWSER)` in
`showdown_modes.py` falls through to `return None, None` (the localhost path), but `browser_trainer.py`
checks if `acc1 is None` and raises `ValueError`. The BROWSER mode needs its own credential branch in
`account_configs_for_mode`.

The Discord cog command follows an established pattern from `admin-train`: defer interaction, post an
initial embed, fire `asyncio.create_task()` for a background coroutine, and DM the user when complete.
The `/train-browser` command can be added directly to `AdminCog` using exactly this pattern.

**Primary recommendation:** Fix the PPO learning gap first (add rollout buffer and `policy.learn()` call
to the battle loop), then fix the credential routing, then add the Discord command. Tests must mock
Playwright entirely — no real browser; no real network.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Browser automation (Playwright) | ML layer (`src/ml/`) | — | Training infrastructure, not bot UX |
| PPO policy updates | ML layer (`src/ml/browser_trainer.py`) | `train_policy.py` (hyperparams) | Weight updates belong in trainer |
| Credential resolution for browser mode | `src/ml/showdown_modes.py` | — | All mode/credential logic is centralized here |
| Discord command + UX | Bot layer (`src/bot/cogs/admin.py`) | — | Follows existing admin cog pattern |
| Background task orchestration | Bot layer (`admin.py` helpers) | — | `asyncio.create_task()` pattern already established |
| Test coverage | `tests/unit/` | — | Unit tests with mocked Playwright; no live network |

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BRWS-01 | Bot executes a full self-play match via Playwright against pokemonshowdown.com | `browser_trainer.py` has the DOM helpers; needs DOM selector validation and challenge/accept flow fixed |
| BRWS-02 | Experience collected from browser battles updates PPO policy weights | Critical gap: `policy.learn()` is never called; requires rollout buffer + learn() call |
| BRWS-03 | Browser training loop runs without a local Showdown server | Already satisfied architecturally; Playwright connects to play.pokemonshowdown.com directly |
| BRWS-04 | Discord slash command triggers a browser training session and reports result | New `/train-browser` command in `AdminCog` following `admin-train` background task pattern |
</phase_requirements>

---

## Standard Stack

### Core (already in repo — no new installs needed for ML layer)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| playwright (Python) | 1.60.0 | Headless browser automation | Official Microsoft library; used in `browser_trainer.py` already |
| stable-baselines3 | >=2.8.0 (pinned in requirements.txt) | PPO policy, rollout buffers, `learn()` | Already the project RL framework |
| gymnasium | >=1.0.0 (transitive via poke-env) | `_FakeEnv` stub, observation/action spaces | Already used in `browser_trainer.py` |
| numpy | >=2.4.6 | Observation vector construction | Already project-wide dependency |

### New dependency: playwright

Playwright is **not in `requirements.txt`** and is **not installed in the project venv**. It must be added.
The browser binaries (Chromium) also need a one-time `playwright install chromium` step. [VERIFIED: PyPI registry - pypi.org/project/playwright — Microsoft official package]

**Installation (to add to requirements.txt):**
```bash
playwright>=1.52.0
```

**One-time browser binary install (CI step and local):**
```bash
playwright install chromium
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| playwright | selenium | Playwright is faster, has better async support, already imported in browser_trainer.py |
| playwright | pyppeteer | Pyppeteer is unmaintained; Playwright is the clear successor |

---

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| playwright | PyPI | ~5 yrs | High (Microsoft official) | github.com/microsoft/playwright-python | N/A (slopcheck unavailable) | Approved — confirmed Microsoft official via pypi.org/project/playwright and github.com/microsoft/playwright-python [CITED: pypi.org/project/playwright] |

**Packages removed due to slopcheck [SLOP] verdict:** none

**Packages flagged as suspicious [SUS]:** none

*slopcheck was unavailable at research time (JSON mode failed). Playwright is marked `[CITED: pypi.org/project/playwright]` — Microsoft's official Python automation library with a long publication history and the canonical package for Chromium/Firefox/WebKit automation. Registry existence confirmed via `pip index versions playwright` (1.60.0 latest). No further verification gate needed.*

---

## Architecture Patterns

### System Architecture Diagram

```
Discord user invokes /train-browser
         │
         ▼
AdminCog.train_browser_cmd()
  ├─ interaction.response.defer()
  ├─ interaction.followup.send(initial_embed)
  └─ asyncio.create_task(_run_browser_training(...))
                    │
                    ▼ (background coroutine)
         _run_browser_training()
           ├─ validates credentials present (SHOWDOWN_TRAIN_USER1/2)
           ├─ runs executor: loop.run_in_executor(None, train_browser, ...)
           │         │
           │         ▼ (blocking — runs in thread pool)
           │   browser_trainer.train_browser()
           │     ├─ sync_playwright() context
           │     ├─ Two Chromium contexts → play.pokemonshowdown.com
           │     ├─ _login(page1, user1), _login(page2, user2)
           │     ├─ BATTLE LOOP:
           │     │   ├─ _send_challenge(page1, user2, fmt)
           │     │   ├─ _accept_challenge(page2)
           │     │   ├─ per-turn: build_observation_from_dom(page1) → obs
           │     │   ├─ policy.predict(obs) → action
           │     │   ├─ _pick_move_from_obs(page1, obs, policy)
           │     │   ├─ [FIX NEEDED] store (obs, action, reward) in rollout buffer
           │     │   └─ [FIX NEEDED] call policy.learn() when buffer full
           │     ├─ Periodic checkpoint save (every swap_every steps)
           │     └─ Final policy.save(final_path)
           │
           ├─ edits channel embed with result (battles played, reward)
           └─ DMs user completion embed
```

### Recommended Project Structure

No new directories needed. Changes are contained to existing locations:

```
src/
  ml/
    browser_trainer.py      # FIX: add rollout buffer + policy.learn()
    showdown_modes.py       # FIX: add MODE_BROWSER branch to account_configs_for_mode()
  bot/
    cogs/
      admin.py              # ADD: /train-browser command + _run_browser_training() helper
requirements.txt            # ADD: playwright>=1.52.0
tests/
  unit/
    test_browser_trainer.py # NEW: unit tests for pure functions (no Playwright)
```

### Pattern 1: Discord Background Training Task (from admin.py)

The `/admin-train` command establishes the exact pattern to follow for `/train-browser`:

```python
# Source: src/bot/cogs/admin.py lines 209-245 [VERIFIED: codebase]
@app_commands.command(name="train-browser", description="...")
@is_commissioner()
async def train_browser_cmd(self, interaction, fmt: str, timesteps: int = 10_000) -> None:
    await interaction.response.defer(thinking=True)

    status_msg = None
    try:
        status_msg = await interaction.followup.send(
            embed=_build_browser_embed(fmt, 0, timesteps),
            wait=True,
        )
    except discord.NotFound:
        pass  # interaction expired — training still starts

    asyncio.create_task(
        _run_browser_training(interaction, fmt, timesteps, channel_msg=status_msg)
    )
```

**Why:** Discord interactions expire after 3 seconds. `defer()` extends the window to 15 minutes.
`create_task()` lets the interaction handler return immediately while training continues in the
background. `interaction.followup.send()` posts the live embed; the background task edits it.

### Pattern 2: Blocking Code in Async Context (from admin.py)

`train_browser()` uses `sync_playwright()` — it is fully synchronous and will block the event loop
if called directly. The correct pattern is `run_in_executor`:

```python
# Source: src/bot/cogs/admin.py lines 136-143 (asyncio.create_subprocess_exec pattern) [VERIFIED: codebase]
# For browser training, use run_in_executor since train_browser() is a sync function:
loop = asyncio.get_running_loop()
final_path = await loop.run_in_executor(
    None,
    functools.partial(train_browser, fmt=fmt, total_timesteps=timesteps, ...)
)
```

**Alternative:** Spawn a subprocess (same as `admin-train`) for true isolation. This avoids the
GIL and means a Playwright crash cannot kill the bot process. The subprocess approach is safer
and matches the existing pattern in `_run_training()`.

### Pattern 3: PPO Experience Collection — THE FIX

`browser_trainer.py` currently calls `policy.predict()` but never calls `policy.learn()`. SB3's
PPO does not update weights until `learn()` is called. The fix requires:

1. **Collect a rollout buffer** — store `(obs, action, reward, done)` tuples during the battle loop
2. **Call `policy.learn()`** after each battle (or when buffer reaches `n_steps` threshold)

The correct SB3 pattern for off-training-loop learning uses `policy.learn()` which internally runs
the rollout collection and gradient update steps. Since `_FakeEnv` is a stub, the rollout must be
manually fed via `policy.rollout_buffer` or by replacing `_FakeEnv` with a thin wrapper that
replays collected tuples.

**Simplest viable fix** — replace `_FakeEnv.step()` so it returns stored (obs, reward, done)
tuples collected from the browser loop, then call `policy.learn(total_timesteps=swap_every)` at
each checkpoint interval. This reuses SB3's rollout machinery without a custom buffer.

```python
# Pseudocode for the fix — Source: architectural analysis of browser_trainer.py [ASSUMED]
# After each battle, replay collected transitions through _FakeEnv:
class _ReplayEnv(gym.Env):
    """Env that replays browser-collected transitions for SB3 to learn from."""
    def __init__(self, transitions):
        self._transitions = list(transitions)
        self._idx = 0
        # ... spaces ...

    def step(self, action):
        if self._idx >= len(self._transitions):
            return np.zeros(OBS_DIM), 0.0, True, False, {}
        obs, reward, done = self._transitions[self._idx]
        self._idx += 1
        return obs, reward, done, False, {}
```

**Alternative** — use SB3's `collect_rollouts()` directly with a custom callback that reads
from the browser session. This is more correct but significantly more complex.

### Pattern 4: Playwright Headless Mode (GitHub Actions compatible)

The REQUIREMENTS.md constraint says "Playwright must support headless mode (GitHub Actions
compatible)." `browser_trainer.py` already handles this via:

```python
# Source: browser_trainer.py line 249-250 [VERIFIED: codebase]
if headless is None:
    headless = os.environ.get("SHOWDOWN_BROWSER_HEADED", "0") != "1"
```

GitHub Actions Linux runners support headless Chromium without a virtual display.
The `playwright install chromium` step must be added to any CI workflow that runs browser training.

### Anti-Patterns to Avoid

- **Calling `sync_playwright()` from an async context without `run_in_executor`**: blocks the
  entire Discord event loop, causing gateway timeouts and dropped interactions.
- **Calling `policy.predict()` without `policy.learn()`**: this is the current bug — observations
  are used for move selection but the model never trains. Save calls write the unchanged
  initial weights.
- **Using `time.sleep()` in the battle loop without awareness of the event loop**: `browser_trainer.py`
  uses `time.sleep()` throughout (correct since it runs in a thread/subprocess), but if any
  future refactor moves it to async, these must become `await asyncio.sleep()`.
- **Hardcoding `src/ml/models/results` as DEFAULT_RESULTS_DIR in browser_trainer.py**: the
  existing `train_policy.py` uses `data/ml/results`. These paths are inconsistent and will
  confuse `best_model_for_format()` which searches `data/ml/results`. The browser trainer's
  results_dir default should match `train_policy.py`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Policy gradient updates | Custom weight update loop | `policy.learn()` (SB3) | SB3 handles rollout normalization, advantage estimation, clipping, entropy bonus |
| Rollout buffer management | Manual numpy array | SB3's `RolloutBuffer` or `_FakeEnv` replay | Buffer sizing, GAE computation already implemented |
| Playwright browser install | Custom download script | `playwright install chromium` CLI | Official Playwright browser management; handles platform differences |
| Progress embed building | New embed builder | `_build_progress_embed()` from `admin.py` | Already exists with Unicode progress bar and status states |
| Credential validation | New env var reader | Extend `account_configs_for_mode()` in `showdown_modes.py` | All credential logic already centralized there |

---

## Common Pitfalls

### Pitfall 1: PPO Never Learns (Critical — Current Bug)

**What goes wrong:** `browser_trainer.py` calls `policy.predict()` and `policy.save()` but never
calls `policy.learn()`. The policy weights are identical at the start and end of any training session.
Success criterion BRWS-02 ("policy weights on disk differ from the pre-session checkpoint") will fail.

**Why it happens:** The browser trainer was written as a data collection loop but the SB3 learning step
was never wired in. `policy.save()` appears to work (it writes a file), masking the bug.

**How to avoid:** Verify by hashing policy weights before and after a training session. The fix requires
a `_FakeEnv` that replays collected `(obs, reward, done)` tuples and a `policy.learn()` call at each
checkpoint interval.

**Warning signs:** `browser_swap_0001.zip` is identical in size to the initial model.

### Pitfall 2: Credential Routing Bug (Critical — Current Bug)

**What goes wrong:** `account_configs_for_mode(MODE_BROWSER)` returns `(None, None)` (same as
localhost mode). `browser_trainer.py` checks `if acc1 is None or acc2 is None` and raises `ValueError`.
Browser training cannot start at all with the current code.

**Why it happens:** `showdown_modes.py` has branches for `MODE_SHOWDOWN` and a default catch-all
for localhost, but `MODE_BROWSER` was never added as an explicit case.

**How to avoid:** Add a `MODE_BROWSER` branch to `account_configs_for_mode()` that reads
`SHOWDOWN_TRAIN_USER1/PASS1` and `SHOWDOWN_TRAIN_USER2/PASS2` — same env vars as `MODE_SHOWDOWN`.

### Pitfall 3: Inconsistent Results Directory

**What goes wrong:** `browser_trainer.py` defines `DEFAULT_RESULTS_DIR = "src/ml/models/results"` but
`train_policy.py` uses `DEFAULT_RESULTS_DIR = "data/ml/results"`. `best_model_for_format()` in
`showdown_player.py` searches `data/ml/results`. Browser-trained models saved to `src/ml/models/results`
will not be discovered by `/spar`.

**How to avoid:** Change `browser_trainer.py`'s `DEFAULT_RESULTS_DIR` to `"data/ml/results"` to match
`train_policy.py`.

### Pitfall 4: DOM Selector Fragility

**What goes wrong:** Pokémon Showdown's client DOM is not versioned and can change without notice.
Selectors like `.hpbar .hptext`, `button.move:not([disabled])`, `.result-message` are best-effort.

**Why it happens:** The browser trainer reads game state from the DOM rather than the WebSocket
protocol (the poke-env path). This is inherently less reliable.

**How to avoid:** Add `try/except` around every DOM read (already done in `build_observation_from_dom`)
and fall back gracefully to zeros. For the challenge/accept flow, add explicit waits with generous
timeouts and retry logic for the `_accept_challenge` call.

**Warning signs:** `Could not accept challenge` warnings in logs; battles never starting.

### Pitfall 5: Playwright Not in requirements.txt

**What goes wrong:** `browser_trainer.py` has a try/except import for Playwright with a helpful error
message, but if Playwright is not in `requirements.txt`, CI and fresh installs will silently fall back
to random policy with no gradient updates.

**How to avoid:** Add `playwright>=1.52.0` to `requirements.txt`. Add `playwright install chromium` as
an explicit CI step in any workflow that exercises browser training.

### Pitfall 6: Two Browsers, Same Turn Timing

**What goes wrong:** The battle loop checks `_wait_for_turn_or_end(page1)` then
`_wait_for_turn_or_end(page2)`, but both browsers may be waiting for each other's move simultaneously
(deadlock scenario if both turn-waits time out at the same time).

**Why it happens:** The current implementation is sequential: it waits for page1 to need a move, sends
it, then waits for page2. If page1's move triggers an animation delay and page2 is also mid-animation,
page2's 30-second timeout may fire before page2 needs to move.

**How to avoid:** Use shorter polling intervals and treat `"timeout"` from page2 as non-fatal (move on
to the next turn rather than abandoning the battle). The current code already handles this but the
interaction between the two `_wait_for_turn_or_end` calls needs careful testing.

---

## Code Examples

### Complete fix for `account_configs_for_mode` to support MODE_BROWSER

```python
# Source: src/ml/showdown_modes.py — current code [VERIFIED: codebase]
# Fix: add MODE_BROWSER branch that reads the same SHOWDOWN_TRAIN_USER1/2 env vars
def account_configs_for_mode(mode: str) -> tuple:
    import os
    if mode in (MODE_SHOWDOWN, MODE_BROWSER):  # both use real accounts
        from poke_env.ps_client.account_configuration import AccountConfiguration
        u1 = os.environ.get("SHOWDOWN_TRAIN_USER1", "")
        p1 = os.environ.get("SHOWDOWN_TRAIN_PASS1", "")
        u2 = os.environ.get("SHOWDOWN_TRAIN_USER2", "")
        p2 = os.environ.get("SHOWDOWN_TRAIN_PASS2", "")
        if not all([u1, p1, u2, p2]):
            raise ValueError(
                "Browser/Showdown training requires 4 env vars: "
                "SHOWDOWN_TRAIN_USER1, SHOWDOWN_TRAIN_PASS1, "
                "SHOWDOWN_TRAIN_USER2, SHOWDOWN_TRAIN_PASS2"
            )
        return AccountConfiguration(u1, p1), AccountConfiguration(u2, p2)
    return None, None  # localhost
```

### Mock pattern for unit testing Playwright-dependent functions

```python
# Source: tests/unit/test_showdown_player.py TestBrowserTrainerImport pattern [VERIFIED: codebase]
from unittest.mock import MagicMock, patch

def test_build_observation_from_dom_zeros_on_empty_page():
    """build_observation_from_dom should return a zero vector when DOM has no battle data."""
    mock_page = MagicMock()
    # Simulate no HP elements found
    mock_page.locator.return_value.count.return_value = 0

    from src.ml.browser_trainer import build_observation_from_dom
    obs = build_observation_from_dom(mock_page)
    assert obs.shape == (48,)
    assert obs.dtype.name == "float32"
```

### Discord command pattern for `/train-browser`

```python
# Source: adapted from admin.py /admin-train pattern [VERIFIED: codebase]
@app_commands.command(name="train-browser", description="Train via browser self-play (no local server)")
@app_commands.describe(
    format="Showdown format (e.g. gen9randombattle)",
    timesteps="Training steps (default: 10000 — browser training is slow)",
)
@is_commissioner()
async def train_browser_cmd(
    self,
    interaction: discord.Interaction,
    format: str,
    timesteps: int = 10_000,
) -> None:
    await interaction.response.defer(thinking=True)
    status_msg = None
    try:
        status_msg = await interaction.followup.send(
            embed=_build_browser_training_embed(format, 0, timesteps),
            wait=True,
        )
    except discord.NotFound:
        pass
    asyncio.create_task(
        _run_browser_training(interaction, format, timesteps, channel_msg=status_msg)
    )
```

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `_FakeEnv` replay approach (feeding collected transitions through a thin env) is the simplest viable fix for the PPO learning gap | Common Pitfalls / Code Examples | If SB3 rollout buffer has stricter requirements (e.g., requires real env reset/step coordination), the fix may need to use `policy.collect_rollouts()` directly — more complex |
| A2 | Pokémon Showdown's login DOM selectors (`button.button[name='login']`, `input[name='username']`) are stable enough for functional testing | Common Pitfalls | If Showdown's client has changed these selectors, `_login()` will fail silently; requires a live browser smoke test to verify |
| A3 | The `/train-browser` command should live in `AdminCog` (admin.py) rather than a new cog | Architecture Patterns | If the project maintainer prefers a separate ML cog, the implementation location changes but the pattern is the same |

---

## Open Questions

1. **How many timesteps is a realistic default for browser training?**
   - What we know: each browser action is ~1-3 seconds (DOM polling); 10,000 steps ≈ many hours.
     `train_policy.py` defaults to 500,000 steps for WebSocket training (seconds per step).
   - What's unclear: the Discord command's default timesteps parameter — too high and the interaction
     appears to hang for the user; too low and no useful learning occurs.
   - Recommendation: Default to 1,000–5,000 steps for the Discord command (short demo session);
     allow higher values for headless CI runs via a separate script.

2. **Should browser training be a subprocess (like `admin-train`) or `run_in_executor`?**
   - What we know: `admin-train` uses `asyncio.create_subprocess_exec` for full process isolation.
     `train_browser()` is sync and can run in a thread pool. Subprocess is safer (crash isolation)
     but adds overhead and stdout-streaming complexity.
   - What's unclear: whether Playwright has thread-safety issues inside a thread pool executor.
   - Recommendation: Use subprocess for production safety (matches existing pattern); use
     `run_in_executor` for simplicity if subprocess overhead is not acceptable.

3. **Does `_accept_challenge` reliably find the challenge popup selector?**
   - What we know: the current selector is `button.button[value='accept']`. This was written without
     a live Showdown session to verify against the actual DOM.
   - Recommendation: Plan a Wave 0 task to smoke-test the DOM selectors against a live (or captured)
     Showdown page before implementing the full training loop.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| playwright (Python) | BRWS-01, BRWS-02, BRWS-03 | No (not in venv, not in requirements.txt) | 1.60.0 on PyPI | None — must be installed |
| Chromium browser binary | BRWS-01, BRWS-02, BRWS-03 | Unknown | — | None — must run `playwright install chromium` |
| stable-baselines3 | BRWS-02 | Yes (in requirements.txt >=2.8.0) | — | None — PPO is core dependency |
| SHOWDOWN_TRAIN_USER1/2 + PASS1/2 env vars | BRWS-01, BRWS-03 | Unknown | — | Browser training cannot run without real Showdown accounts |
| pokemonshowdown.com network access | BRWS-01, BRWS-03 | Required | — | No fallback — browser training requires live network |

**Missing dependencies with no fallback:**
- `playwright` Python package (add to `requirements.txt`)
- Chromium browser binaries (`playwright install chromium`)
- Two real Pokémon Showdown accounts (env vars `SHOWDOWN_TRAIN_USER1/PASS1`, `SHOWDOWN_TRAIN_USER2/PASS2`)

**Note on GitHub Actions:** The REQUIREMENTS.md constraint ("Playwright must support headless mode — GitHub Actions compatible") can be satisfied on ubuntu-latest runners with standard Playwright Chromium. The train-models.yml workflow is self-hosted; a browser-training workflow would need `ubuntu-latest` or `ubuntu-22.04` with the Playwright install step. [CITED: playwright.dev/python/docs/intro]

---

## Security Domain

`security_enforcement` not explicitly set in `.planning/config.json` — treating as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Browser training uses env-var credentials; no user auth in this phase |
| V3 Session Management | No | No session tokens managed by this phase |
| V4 Access Control | Yes | `@is_commissioner()` check on `/train-browser` command |
| V5 Input Validation | Yes | `format` parameter validated against known format list before use |
| V6 Cryptography | No | No crypto in this phase |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Arbitrary format string injected into subprocess command | Tampering | Validate `format` against `TRAINING_MAP` whitelist before passing to any subprocess or train call |
| Showdown credentials exposed in logs | Info Disclosure | Never log `SHOWDOWN_TRAIN_PASS1/2`; existing `_login()` does not log passwords |
| Unlimited training timesteps from Discord | DoS | Cap `timesteps` at a reasonable maximum (e.g., 100,000) in the Discord command or validate via `is_commissioner()` gate |

---

## Sources

### Primary (HIGH confidence)
- `src/ml/browser_trainer.py` (406 lines) — full read; all bugs identified from source [VERIFIED: codebase]
- `src/ml/train_policy.py` (1110 lines) — PPO pattern, hyperparams, `_FakeEnv`, checkpointing [VERIFIED: codebase]
- `src/bot/cogs/admin.py` (957 lines) — Discord background task pattern, embed builders [VERIFIED: codebase]
- `src/ml/showdown_modes.py` — credential routing bug confirmed [VERIFIED: codebase]
- `src/ml/battle_env.py` — OBS_DIM=48, N_ACTIONS_GEN9=26 [VERIFIED: codebase]
- `.planning/config.json` — `nyquist_validation: false` confirmed [VERIFIED: codebase]
- `requirements.txt` — playwright confirmed absent [VERIFIED: codebase]

### Secondary (MEDIUM confidence)
- [pypi.org/project/playwright](https://pypi.org/project/playwright/) — confirmed Microsoft official package, 1.60.0 latest [CITED: pypi.org/project/playwright]
- [github.com/microsoft/playwright-python](https://github.com/microsoft/playwright-python) — official source repo [CITED: github.com/microsoft/playwright-python]
- [playwright.dev/python/docs/intro](https://playwright.dev/python/docs/intro) — headless mode GitHub Actions compatibility [CITED: playwright.dev/python/docs/intro]

---

## Metadata

**Confidence breakdown:**
- Bug identification (PPO learning gap, credential routing): HIGH — confirmed by direct code read
- Standard stack / package versions: HIGH — PyPI registry confirmed
- Architecture patterns (Discord cog): HIGH — confirmed against existing admin.py implementation
- DOM selector reliability: LOW — cannot be verified without a live Showdown session
- Playwright thread-safety in executors: MEDIUM — standard Python usage; no known issues

**Research date:** 2026-05-19
**Valid until:** 2026-08-19 (Playwright minor versions release frequently; check for DOM selector changes if pokemonshowdown.com updates its client)
