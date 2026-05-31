---
id: ISS-006
title: ML training — provision x86 Linux environment
status: open
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
