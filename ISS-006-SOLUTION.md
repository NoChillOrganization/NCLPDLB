---
id: ISS-006
title: ML training — provision x86 Linux environment
status: done
phase: backlog
closed: 2026-06-03
---

# ISS-006 Solution — ML Training: x86 Linux Environment

## Analysis

ARM64 Windows cannot install PyTorch + stable-baselines3 natively. The existing "Discord Bot"
VirtualBox VM (Ubuntu 24.04.4 LTS, x86-64, 6 vCPU, 20 GB RAM) was already running and provided
a ready x86 environment. Two obstacles had to be resolved:

1. **SIGHUP**: the initial 500k `nohup` run silently died at the first format (~21 h stalled,
   559-byte log) because the spawning SSH session's SIGHUP propagated into the background job.
2. **Missing env vars**: `train_policy.py` needs `SHOWDOWN_TRAIN_USER1/2` + `SHOWDOWN_TRAIN_PASS1/2`
   (credentials for the local Showdown server). These lived in `.env` but were not loaded when
   launching via paramiko without a login shell.
3. **vboxsf group**: `vmboxguest` lacked the `vboxsf` group needed to read the shared folder
   `/media/sf_NCLPDLB`; only `vboxuser` had it.

## Approach

### Environment setup (2026-06-01, prior session)

- VirtualBox shared folder `NCLPDLB → F:\NCLPDLB` mounted at `/media/sf_NCLPDLB` — no file
  copying needed; host and guest write to the same tree.
- NAT port-forward `host:2222 → guest:22` added live.
- venv `/home/vmboxguest/nclpdlb-venv` with torch 2.12.0+cpu + SB3 2.8.0.
- Showdown server running at `ws://localhost:8000` (node pokemon-showdown start --no-security).
- `docs/DEPLOYMENT.md` *ML Training Environment* section added.

### SIGHUP fix (2026-06-03)

Replaced `nohup python ... &` with the triple-isolation pattern:

```bash
cd /media/sf_NCLPDLB
set -a && . .env && set +a          # export credentials to child env
LOG=/tmp/train_all_$(date +%Y%m%d_%H%M).log
setsid python -m src.ml.train_all \
    --timesteps 500000 --swap-every 50000 \
    </dev/null >"$LOG" 2>&1 &
PID=$! && disown $PID
```

`setsid` creates a new session (immune to SIGHUP); `</dev/null` prevents stdin reads from
blocking; `disown` removes the job from the shell's job table.

### vboxsf group fix

```bash
sudo usermod -aG vboxsf vmboxguest   # on VM; takes effect on next login
```

### .env sourcing

`set -a && . .env && set +a` before the `setsid` call exports all vars from the project's
`.env` file into the environment that `setsid` inherits. The four Showdown credentials are
now visible to `train_policy.py`'s `account_configs_for_mode()`.

## Results

Run completed 2026-06-03 (~34 min wall clock, 22 formats sequential):

| Outcome | Formats | Note |
|---------|---------|------|
| ✅ Trained | 20/22 | 500k steps, model saved + dated result zip |
| ⚠️ 0-step checkpoint | 2/22 | `gen9championsvgc2026regma`, `gen9championsvgc2026regmabo3` |

The two champion VGC formats hit `KeyError: assertion` in `poke_env`'s login flow — the local
no-security Showdown server doesn't issue a valid assertion token for Champions ladder formats.
The model files are present but untrained (below the 5,000-step floor). These formats require
either a patched Showdown server or format aliasing to a supported format.

All 22 `data/ml/policy/<format>/final_model.zip` files exist.

## Verification

```bash
# On the host (shared folder):
ls data/ml/policy/*/final_model.zip | wc -l        # 22
ls data/ml/results/*_2026-06-03.zip | wc -l        # 22

# Sync check:
python scripts/sync_closed_issues.py --check       # expect: 0 failures
```

## Related

- [[ISS-006-ml-training-environment]] — source issue
- [[ISS-002-SOLUTION]] — training pipeline wiring (prerequisite)
