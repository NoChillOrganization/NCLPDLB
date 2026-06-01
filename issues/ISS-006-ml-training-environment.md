---
id: ISS-006
title: ML training — provision x86 Linux environment
status: done
priority: medium
phase: backlog
labels: [ml, training, infra]
created: 2026-05-31
---

# ISS-006 — ML Training: Provision x86 Linux Environment

## Summary

ARM64 Windows cannot install PyTorch + stable-baselines3 natively. A Linux or x86 environment is required to run local training outside of GitHub Actions.

## Context

From STATUS.md: "PyTorch + stable-baselines3: Cannot install on ARM64 Windows natively." GitHub Actions (Linux x86) works for CI training, but local dev and iteration are blocked.

## Options

- Cloud VM (e.g., AWS EC2 g4dn/g5, GCP n1 with GPU)
- WSL2 x86 on Windows (if hardware supports)
- Dedicated Linux machine

## Acceptance Criteria

- [x] `pip install torch stable-baselines3` succeeds on target environment
      (torch 2.12.0+cpu, SB3 2.8.0 in `/home/vmboxguest/nclpdlb-venv` — 2026-06-01)
- [x] `python -m src.ml.train_all` runs at least one format to completion
      (gen9randombattle smoke run, 5k steps — 2026-06-01)
- [x] Models saved to `data/ml/policy/<format>/final_model.zip`
      (`data/ml/policy/gen9randombattle/final_model.zip` + dated copy in `data/ml/results/`)
- [x] Document environment setup in `docs/DEPLOYMENT.md`
      (Added *ML Training Environment* section — 2026-06-01)

## Dependencies

None — parallel to Phases 05-06

## Notes

Training all 22 formats sequentially takes ~8-12 hours on adequate hardware.

## Progress (2026-06-01)

VirtualBox "Discord Bot" VM identified as the x86-64 Linux environment (Ubuntu 64-bit, 6 vCPU,
20 GB RAM, already running). Shared folder `NCLPDLB → F:\NCLPDLB` maps the project directly
into the guest — no file copying needed. NAT port-forward `host:2222 → guest:22` added live.

**Completed (2026-06-01):**
- [x] Step 1: torch 2.12.0+cpu + SB3 2.8.0 verified in `/home/vmboxguest/nclpdlb-venv` (AC1)
- [x] Step 2: Showdown server running on `ws://localhost:8000` (node pokemon-showdown start --no-security)
- [x] Step 3: `transformer_checkpoint.pt` already present at `src/ml/models/` (done prior session)
- [x] Step 4: gen9randombattle smoke run (5k steps) → `final_model.zip` written (AC2/AC3)
- [x] Step 5: `docs/DEPLOYMENT.md` ML Training section added; `STATUS.md` updated (AC4)

**Full 500k run:** kicked off in background (VM PID 74506, `nohup`, `/tmp/train_all.log`).
Monitor: `ssh -p 2222 vmboxguest@127.0.0.1 "tail -f /tmp/train_all.log"`
When complete, `final_model.zip` will be overwritten with the production-quality model.
