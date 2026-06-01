---
id: ISS-006
title: ML training — provision x86 Linux environment
status: in-progress
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

- [ ] `pip install torch stable-baselines3` succeeds on target environment
- [ ] `python -m src.ml.train_all` runs at least one format to completion
- [ ] Models saved to `data/ml/policy/<format>/final_model.zip`
- [ ] Document environment setup in `docs/DEPLOYMENT.md`

## Dependencies

None — parallel to Phases 05-06

## Notes

Training all 22 formats sequentially takes ~8-12 hours on adequate hardware.

## Progress (2026-06-01)

VirtualBox "Discord Bot" VM identified as the x86-64 Linux environment (Ubuntu 64-bit, 6 vCPU,
20 GB RAM, already running). Shared folder `NCLPDLB → F:\NCLPDLB` maps the project directly
into the guest — no file copying needed. NAT port-forward `host:2222 → guest:22` added live.

**Pending (needs guest credentials):**
- Step 1: verify `pip install torch stable-baselines3` in-guest (AC1)
- Step 2: start Showdown server (`node pokemon-showdown start --no-security` on port 8000)
- Step 3: run `python -m src.ml.train_transformer` → produces `transformer_checkpoint.pt` on share
- Step 4: run `python -m src.ml.train_all` ≥1 format to completion (AC2/AC3)
- Step 5: write/update `docs/DEPLOYMENT.md` + fix `STATUS.md` (AC4)

See `docs/DEPLOYMENT.md` (in progress) for setup script.

**To connect:** `ssh -p 2222 <user>@127.0.0.1` (sshd must be running in guest).
