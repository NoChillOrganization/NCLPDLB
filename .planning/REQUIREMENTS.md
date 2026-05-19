# Requirements — NCLPDLB v1.1 Full ML Integration

*Generated: 2026-05-19*

---

## Validated (from v1.0)

- ✓ REQ-01 — Type effectiveness obs expansion (OBS_DIM 44→48) — delivered
- ✓ REQ-02 — MaxBasePowerPlayer curriculum opponent — delivered
- ✓ REQ-03 — Behavioral cloning pre-training (pretrain.py, --pretrain flag) — delivered

---

## v1.1 Requirements

### Browser Training

- [ ] **BRWS-01**: Bot executes a full self-play match via Playwright against pokemonshowdown.com
- [ ] **BRWS-02**: Experience collected from browser battles updates PPO policy weights
- [ ] **BRWS-03**: Browser training loop runs without a local Showdown server
- [ ] **BRWS-04**: Discord slash command triggers a browser training session and reports result

### Transformer + MCTS Training

- [ ] **MCTS-01**: `self_play.py` MCTSPlayer is fully tested (unit + integration)
- [ ] **MCTS-02**: MCTSPlayer is wired into the training pipeline (replaces/augments PPO self-play)
- [ ] **MCTS-03**: BattleTransformer trains to convergence via MCTS self-play

### /spar Inference

- [ ] **SPAR-01**: `showdown_player.py` `use_mcts=True` path fully wired (transformer+MCTS inference)
- [ ] **SPAR-02**: `/spar` uses transformer+MCTS when a trained transformer model exists
- [ ] **SPAR-03**: `/spar` falls back to PPO when no transformer model exists (backward-compatible)

---

## Future Requirements (Deferred)

- STAB flag per move (4 binary floats) — OBS_DIM 48→52
- Speed tier comparison (2 floats) — OBS_DIM 52→54
- Opponent moveset tracking / opponent modeling
- Ability/item awareness in observation space
- Full Smogon tier data integration
- Multi-GPU / CUDA training support
- Live tournament / league integration

---

## Out of Scope

- CUDA/GPU training — CPU-only constraint maintained
- Replacing PPO entirely — transformer+MCTS is additive, PPO path preserved
- Live tournament integration — separate milestone after bot proves out in /spar
- OBS_DIM expansion beyond 48 — validate current obs before expanding

---

## Constraints

- Must not break existing `train_all.py` invocations (backward-compatible)
- No local Showdown server required for browser training path
- Playwright must support headless mode (GitHub Actions compatible)
- Transformer+MCTS inference must work on CPU (no CUDA required)
- All existing tests must continue passing

---

## Traceability

| REQ-ID   | Phase | Notes |
|----------|-------|-------|
| BRWS-01  | TBD   | —     |
| BRWS-02  | TBD   | —     |
| BRWS-03  | TBD   | —     |
| BRWS-04  | TBD   | —     |
| MCTS-01  | TBD   | —     |
| MCTS-02  | TBD   | —     |
| MCTS-03  | TBD   | —     |
| SPAR-01  | TBD   | —     |
| SPAR-02  | TBD   | —     |
| SPAR-03  | TBD   | —     |
