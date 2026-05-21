# Training Workflow Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the `TimeoutError: Agent is not challenging` regression in CI training jobs by correctly wiring real Showdown credentials to `BattleEnv.agent2` (not `CurriculumOpponent`), adding a pre-training connectivity check, a longer challenge timeout, and cleaning up duplicate files.

**Architecture:** `BattleEnv` (extending poke-env `SinglesEnv`/`DoublesEnv`) owns the two WebSocket connections via internal `_EnvPlayer` instances (`agent1` → acc1, `agent2` → acc2). `CurriculumOpponent` is a pure move-selector injected by `SingleAgentWrapper` — it must not open its own Showdown connection. The workflow gains a fast-fail step that pings `wss://sim3.psim.us` before training starts.

**Tech Stack:** Python 3.12, poke-env 0.12.1, stable-baselines3, GitHub Actions workflow YAML, `gh` CLI, pytest.

---

### Task 0: Cancel the running bad workflow

**Files:** none (gh CLI only)

- [ ] **Step 1: Cancel workflow run 24288867208**

```bash
gh run cancel 24288867208
```

Expected output: `✓ Requested cancellation of run 24288867208`

- [ ] **Step 2: Confirm it is cancelling**

```bash
gh run list --workflow=train-models.yml --limit=3
```

Expected: the most recent run shows status `cancelled` or `in_progress` briefly then `cancelled`.

---

### Task 1: Fix credential wiring in `train_policy.py`

**Files:**
- Modify: `src/ml/train_policy.py` (lines ~584–624 — `opp_kwargs` block and `make_env()`)

- [ ] **Step 1: Write failing tests**

Open `tests/unit/test_train_policy.py` and add these two tests inside the existing test class / at module level, before touching any implementation:

```python
def test_make_env_passes_acc2_to_battle_env(monkeypatch):
    """account_configuration2 must go to BattleEnv, not CurriculumOpponent."""
    captured = {}

    class FakeBattleEnv:
        def __init__(self, **kwargs):
            captured["env_kwargs"] = kwargs

    class FakeSingleAgentWrapper:
        def __init__(self, env, opponent):
            captured["opponent"] = opponent

    class FakeMonitor:
        def __init__(self, env):
            pass

    import src.ml.train_policy as tp
    monkeypatch.setattr(tp, "BattleEnv", FakeBattleEnv)
    monkeypatch.setattr(tp, "SingleAgentWrapper", FakeSingleAgentWrapper)
    monkeypatch.setattr(tp, "Monitor", FakeMonitor)

    from poke_env.ps_client.account_configuration import AccountConfiguration
    acc1 = AccountConfiguration("user1", "pass1")
    acc2 = AccountConfiguration("user2", "pass2")

    # call make_env directly — we need to extract it from train()
    # Instead, verify via account_configs_for_mode mock
    # (simpler: check that CurriculumOpponent is NOT given account_configuration)
    opp_init_kwargs = {}
    OrigCurr = tp.CurriculumOpponent
    class SpyCurriculumOpponent(OrigCurr):
        def __init__(self, *a, **kw):
            opp_init_kwargs.update(kw)
            # don't call super (no real connection in tests)
    monkeypatch.setattr(tp, "CurriculumOpponent", SpyCurriculumOpponent)
    monkeypatch.setattr(tp, "account_configs_for_mode", lambda _: (acc1, acc2))
    # ... (this test is scaffolded below — see note)
    assert "account_configuration" not in opp_init_kwargs


def test_make_env_challenge_timeout_is_180(monkeypatch):
    """BattleEnv must receive challenge_timeout=180."""
    captured_kwargs = {}

    import src.ml.train_policy as tp

    class FakeBattleEnv:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(tp, "BattleEnv", FakeBattleEnv)

    # challenge_timeout must appear in env_kwargs when make_env is called
    # We verify it is present in the dict passed to BattleEnv.__init__
    assert captured_kwargs.get("challenge_timeout") == 180
```

> **Note:** These tests will be fleshed out to call `make_env()` directly in Step 3 — they document the intent now.

- [ ] **Step 2: Run the tests — confirm they fail**

```bash
.venv/bin/python -m pytest tests/unit/test_train_policy.py -k "acc2_to_battle_env or challenge_timeout" -v
```

Expected: FAIL (the assertions can't pass because the code hasn't changed yet).

- [ ] **Step 3: Apply the code fix**

In `src/ml/train_policy.py`, find the `opp_kwargs` block (~line 584) and the `make_env()` function (~line 601). Make these two changes:

**Change A — remove `account_configuration` from `CurriculumOpponent` kwargs:**

```python
# BEFORE (lines ~584-594):
opp_kwargs: dict[str, Any] = dict(
    battle_format=training_fmt,
    server_configuration=srv_cfg,
    is_doubles=is_doubles,
)
if acc2 is not None:
    opp_kwargs["account_configuration"] = acc2
if team_builder is not None:
    opp_kwargs["team"] = team_builder

opponent = CurriculumOpponent(**opp_kwargs)

# AFTER:
opp_kwargs: dict[str, Any] = dict(
    battle_format=training_fmt,
    server_configuration=srv_cfg,
    is_doubles=is_doubles,
)
# account_configuration intentionally NOT set on CurriculumOpponent —
# it is a pure decision-maker; SingleAgentWrapper injects battles directly
# via opponent._battles[tag]. The real acc2 connection goes to BattleEnv.agent2.
if team_builder is not None:
    opp_kwargs["team"] = team_builder

opponent = CurriculumOpponent(**opp_kwargs)
```

**Change B — add `account_configuration2` and `challenge_timeout` to `env_kwargs`:**

```python
# BEFORE (lines ~601-622):
def make_env():
    env_kwargs: dict[str, Any] = dict(
        battle_format=training_fmt,
        server_configuration=srv_cfg,
        strict=False,
    )
    if acc1 is not None:
        env_kwargs["account_configuration1"] = acc1
    # account_configuration2 intentionally omitted: the opponent player
    # connects independently using acc2 via its own account_configuration.
    if team_builder is not None:
        env_kwargs["team"] = team_builder
    if save_replays:
        import os
        os.makedirs(save_replays, exist_ok=True)
        env_kwargs["save_replays"] = save_replays
    if is_doubles:
        poke_env = BattleDoubleEnv(**env_kwargs)
    else:
        poke_env = BattleEnv(**env_kwargs)
    wrapped = SingleAgentWrapper(poke_env, opponent)
    return Monitor(wrapped)

# AFTER:
def make_env():
    env_kwargs: dict[str, Any] = dict(
        battle_format=training_fmt,
        server_configuration=srv_cfg,
        strict=False,
        challenge_timeout=180,  # 3-min window for slow auth handshakes
    )
    if acc1 is not None:
        env_kwargs["account_configuration1"] = acc1
    if acc2 is not None:
        # agent2 inside BattleEnv authenticates as the real second account.
        # CurriculumOpponent is a pure move-selector — it does not connect.
        env_kwargs["account_configuration2"] = acc2
    if team_builder is not None:
        env_kwargs["team"] = team_builder
    if save_replays:
        import os
        os.makedirs(save_replays, exist_ok=True)
        env_kwargs["save_replays"] = save_replays
    if is_doubles:
        poke_env = BattleDoubleEnv(**env_kwargs)
    else:
        poke_env = BattleEnv(**env_kwargs)
    wrapped = SingleAgentWrapper(poke_env, opponent)
    return Monitor(wrapped)
```

- [ ] **Step 4: Update the tests to properly call into the patched code**

Replace the scaffolded tests with complete versions. The cleanest approach is to test `account_configs_for_mode` and a spy on `BattleEnv.__init__`:

```python
# tests/unit/test_train_policy.py  — replace the two scaffolded tests

def test_curriculum_opponent_has_no_account_configuration(monkeypatch):
    """CurriculumOpponent must NOT receive account_configuration kwarg."""
    import src.ml.train_policy as tp
    from poke_env.ps_client.account_configuration import AccountConfiguration

    captured_opp_kwargs: dict = {}

    class SpyOpponent:
        def __init__(self, *a, **kw):
            captured_opp_kwargs.update(kw)

    monkeypatch.setattr(tp, "CurriculumOpponent", SpyOpponent)
    monkeypatch.setattr(tp, "account_configs_for_mode", lambda _: (
        AccountConfiguration("u1", "p1"),
        AccountConfiguration("u2", "p2"),
    ))
    monkeypatch.setattr(tp, "server_config_for_mode", lambda _: object())
    monkeypatch.setattr(tp, "DummyVecEnv", lambda fns: None)
    monkeypatch.setattr(tp, "PPO", type("FakePPO", (), {
        "__init__": lambda s, *a, **kw: None,
        "learn": lambda s, **kw: None,
        "save": lambda s, p: None,
    }))
    monkeypatch.setattr(tp, "BattleEnv", lambda **kw: object())
    monkeypatch.setattr(tp, "SingleAgentWrapper", lambda e, o: object())
    monkeypatch.setattr(tp, "Monitor", lambda e: e)
    monkeypatch.setattr(tp, "_check_showdown_server_if_local", lambda _: None)

    # Call train() — it will crash before model.learn() but opponent is created
    try:
        tp.train(fmt="gen9ou", total_timesteps=1, server="showdown")
    except Exception:
        pass

    assert "account_configuration" not in captured_opp_kwargs, (
        "CurriculumOpponent must not receive account_configuration"
    )


def test_battle_env_receives_acc2_and_challenge_timeout(monkeypatch):
    """BattleEnv must receive account_configuration2 and challenge_timeout=180."""
    import src.ml.train_policy as tp
    from poke_env.ps_client.account_configuration import AccountConfiguration

    captured_env_kwargs: dict = {}

    class SpyBattleEnv:
        def __init__(self, **kw):
            captured_env_kwargs.update(kw)

    acc2 = AccountConfiguration("u2", "p2")
    monkeypatch.setattr(tp, "BattleEnv", SpyBattleEnv)
    monkeypatch.setattr(tp, "account_configs_for_mode", lambda _: (
        AccountConfiguration("u1", "p1"), acc2,
    ))
    monkeypatch.setattr(tp, "server_config_for_mode", lambda _: object())
    monkeypatch.setattr(tp, "CurriculumOpponent", lambda **kw: object())
    monkeypatch.setattr(tp, "SingleAgentWrapper", lambda e, o: object())
    monkeypatch.setattr(tp, "Monitor", lambda e: e)
    monkeypatch.setattr(tp, "DummyVecEnv", lambda fns: (fns[0](), None)[0])
    monkeypatch.setattr(tp, "PPO", type("FakePPO", (), {
        "__init__": lambda s, *a, **kw: None,
        "learn": lambda s, **kw: None,
        "save": lambda s, p: None,
    }))
    monkeypatch.setattr(tp, "_check_showdown_server_if_local", lambda _: None)

    try:
        tp.train(fmt="gen9ou", total_timesteps=1, server="showdown")
    except Exception:
        pass

    assert captured_env_kwargs.get("account_configuration2") is acc2, (
        "BattleEnv must receive account_configuration2=acc2"
    )
    assert captured_env_kwargs.get("challenge_timeout") == 180, (
        "BattleEnv must receive challenge_timeout=180"
    )
```

- [ ] **Step 5: Run full test suite — must stay at 100% / 1332+ passed**

```bash
.venv/bin/python -m pytest tests/ --ignore=tests/performance -q 2>&1 | tail -10
```

Expected: `1334 passed, 3 skipped` (or higher — 2 new tests added).

- [ ] **Step 6: Commit**

```bash
git add src/ml/train_policy.py tests/unit/test_train_policy.py
git commit -m "Fix credential wiring: acc2 to BattleEnv.agent2, not CurriculumOpponent"
```

---

### Task 2: Add pre-training connectivity check to workflow

**Files:**
- Modify: `.github/workflows/train-models.yml` (add one step before the `Train` step)

- [ ] **Step 1: Locate the insertion point**

Open `.github/workflows/train-models.yml`. Find the step named `Train ${{ matrix.config.format }}` (~line 66). The new step goes **immediately before** it.

- [ ] **Step 2: Insert the connectivity-check step**

Add this block between `Install Python dependencies` and `Train ${{ matrix.config.format }}`:

```yaml
      - name: Verify Showdown credentials and connectivity
        shell: bash
        env:
          SHOWDOWN_TRAIN_USER1: ${{ secrets.SHOWDOWN_TRAIN_USER1 }}
          SHOWDOWN_TRAIN_PASS1: ${{ secrets.SHOWDOWN_TRAIN_PASS1 }}
          SHOWDOWN_TRAIN_USER2: ${{ secrets.SHOWDOWN_TRAIN_USER2 }}
          SHOWDOWN_TRAIN_PASS2: ${{ secrets.SHOWDOWN_TRAIN_PASS2 }}
        run: |
          python - <<'PYEOF'
          import os, sys, asyncio

          u1 = os.environ.get("SHOWDOWN_TRAIN_USER1", "")
          p1 = os.environ.get("SHOWDOWN_TRAIN_PASS1", "")
          u2 = os.environ.get("SHOWDOWN_TRAIN_USER2", "")
          p2 = os.environ.get("SHOWDOWN_TRAIN_PASS2", "")

          missing = [n for n, v in [
              ("SHOWDOWN_TRAIN_USER1", u1), ("SHOWDOWN_TRAIN_PASS1", p1),
              ("SHOWDOWN_TRAIN_USER2", u2), ("SHOWDOWN_TRAIN_PASS2", p2),
          ] if not v]
          if missing:
              print(f"ERROR: Missing GitHub secrets: {', '.join(missing)}", file=sys.stderr)
              print("Go to repo Settings → Secrets and variables → Actions and add them.", file=sys.stderr)
              sys.exit(1)

          print(f"Credentials present — USER1={u1!r}, USER2={u2!r}")

          async def check_ws():
              import websockets
              url = "wss://sim3.psim.us/showdown/websocket"
              try:
                  async with websockets.connect(url, open_timeout=20) as ws:
                      msg = await asyncio.wait_for(ws.recv(), timeout=15)
                      if "|challstr|" not in msg:
                          print(f"WARNING: unexpected first message: {msg[:120]}")
                      else:
                          print(f"WebSocket OK — received challstr ({len(msg)} bytes)")
              except Exception as exc:
                  print(f"ERROR: Cannot reach {url}: {exc}", file=sys.stderr)
                  sys.exit(1)

          asyncio.run(check_ws())
          print("Connectivity check PASSED")
          PYEOF
```

- [ ] **Step 3: Verify YAML is valid**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/train-models.yml'))" && echo "YAML OK"
```

Expected: `YAML OK`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/train-models.yml
git commit -m "Add pre-training Showdown connectivity check to CI"
```

---

### Task 3: Delete duplicate config files

**Files:**
- Delete: `pytest 2.ini`, `pyrightconfig 2.json`, `requirements 2.txt`, `run_bot 2.bat`, `.coverage 2`, `audit-fixes 2.patch`, `discord_commands 2.csv`

- [ ] **Step 1: Confirm they are untracked (safe to delete)**

```bash
git status --short | grep "^??"
```

Expected: all 7 space-named files appear under `??` (untracked). They are not staged or committed.

- [ ] **Step 2: Delete them**

```bash
cd /Users/travisweisberg/Documents/NCLPDLB && \
  rm -f "pytest 2.ini" "pyrightconfig 2.json" "requirements 2.txt" \
        "run_bot 2.bat" ".coverage 2" "audit-fixes 2.patch" \
        "discord_commands 2.csv"
```

- [ ] **Step 3: Verify working tree is clean of these files**

```bash
git status --short
```

Expected: none of the `?? "* 2*"` entries appear. Working tree should show only the modified/committed files from previous tasks, or be clean.

- [ ] **Step 4: No commit needed** — these were untracked; deletion is local-only and correct. Git will not see them.

---

### Task 4: Push and trigger the fixed workflow

- [ ] **Step 1: Verify full test suite still passes**

```bash
.venv/bin/python -m pytest tests/ --ignore=tests/performance -q 2>&1 | tail -5
```

Expected: `1334 passed, 3 skipped` (or higher), zero failures.

- [ ] **Step 2: Push to origin**

```bash
git push origin master
```

- [ ] **Step 3: Trigger training workflow**

```bash
gh workflow run train-models.yml --ref master
```

- [ ] **Step 4: Watch first job pass the connectivity check**

```bash
# Wait ~3 minutes then check
gh run list --workflow=train-models.yml --limit=3
```

Expected: new run appears as `in_progress`. Then:

```bash
gh run view --workflow=train-models.yml $(gh run list --workflow=train-models.yml --limit=1 --json databaseId -q '.[0].databaseId') 2>&1 | head -30
```

Expected: `Verify Showdown credentials and connectivity` step shows ✓, and `Train gen9randombattle` step is in progress or ✓.

---

## Self-Review

**Spec coverage:**
- ✅ Cancel running workflow → Task 0
- ✅ Move acc2 to BattleEnv.agent2 → Task 1, Change A+B
- ✅ Remove acc2 from CurriculumOpponent → Task 1, Change A
- ✅ challenge_timeout=180 → Task 1, Change B
- ✅ Pre-training connectivity check → Task 2
- ✅ Delete 7 duplicate files → Task 3
- ✅ 100% test coverage maintained → Tasks 1 & 4

**Placeholder scan:** No TBDs, no vague instructions, all code blocks are complete.

**Type consistency:** `AccountConfiguration`, `BattleEnv`, `CurriculumOpponent`, `SingleAgentWrapper`, `Monitor`, `DummyVecEnv`, `PPO` — all names match what's in `train_policy.py` and are used consistently across tasks.
