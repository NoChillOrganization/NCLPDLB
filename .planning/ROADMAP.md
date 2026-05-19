# Roadmap — NCLPDLB ML Knowledge Injection + Full Integration

*Generated: 2026-03-17 | Last updated: 2026-05-19 (v1.1 phases added)*

---

## Phases

- [x] **Phase 01: Observation Space Expansion** - OBS_DIM 44→48; per-move type-effectiveness floats
- [x] **Phase 02: Curriculum Opponent** - MaxBasePowerPlayer at epoch 0; win-rate graduation threshold
- [x] **Phase 03: BC Pre-Training** - pretrain.py + --pretrain flag + GitHub Actions workflow update
- [ ] **Phase 04: Browser Training** - Full Playwright self-play loop updates PPO weights without a local Showdown server
- [ ] **Phase 05: MCTSPlayer + Transformer Training** - MCTSPlayer tested, wired into pipeline, transformer trains to convergence via MCTS self-play
- [ ] **Phase 06: /spar Inference** - /spar wired to use transformer+MCTS at inference; falls back to PPO when no transformer model exists

---

## Phase Details

### Phase 01: Observation Space Expansion
**Goal**: Battle observations encode type effectiveness so the agent stops discovering it from scratch
**Depends on**: Nothing
**Requirements**: REQ-01
**Success Criteria** (what must be TRUE):
  1. OBS_DIM is 48 in battle_env.py; existing OBS_DIM=44 checkpoints are documented as incompatible
  2. Each of the four move slots in the obs vector carries a type-effectiveness float vs the active opponent
  3. train_all.py runs without modification (backward-compatible)
  4. All existing tests pass with the new obs dimension
**Plans**: Complete
**Status**: Done

### Phase 02: Curriculum Opponent
**Goal**: Self-play training opponent applies meaningful pressure from epoch 0
**Depends on**: Phase 01
**Requirements**: REQ-02
**Success Criteria** (what must be TRUE):
  1. SelfPlayOpponent uses MaxBasePowerPlayer at epoch 0 instead of RandomPlayer
  2. Agent graduates to self-play only after rolling win rate >= 70% over last 500 episodes (or force-graduation at N_MAX_EPOCH0_STEPS)
  3. BattleEnv and SelfPlayCallback are unchanged; train_all.py call signature is unchanged
**Plans**: Complete
**Status**: Done

### Phase 03: BC Pre-Training
**Goal**: PPO policy starts from a replay-informed initialization rather than random weights
**Depends on**: Phase 01
**Requirements**: REQ-03
**Success Criteria** (what must be TRUE):
  1. pretrain.py runs end-to-end against scraped replay data and writes a bc_actor_checkpoint.pt containing actor-only keys
  2. train_policy.py --pretrain flag loads actor weights before PPO training begins; step counter resets to 0
  3. --pretrain and --resume are mutually exclusive; passing both raises ValueError
  4. GitHub Actions workflow executes scrape → pretrain → RL in sequence
  5. train_all.py invocations without --pretrain are unaffected
**Plans**: Complete
**Status**: Done

### Phase 04: Browser Training
**Goal**: PPO policy can be trained via live browser self-play against pokemonshowdown.com with no local Showdown server required
**Depends on**: Phase 03
**Requirements**: BRWS-01, BRWS-02, BRWS-03, BRWS-04
**Success Criteria** (what must be TRUE):
  1. browser_trainer.py executes a complete self-play match via two Playwright browser sessions against pokemonshowdown.com without a local Showdown server running
  2. After a browser training session, PPO policy weights on disk differ from the pre-session checkpoint (experience was applied to the policy)
  3. The training loop runs headlessly on GitHub Actions Linux without Playwright errors
  4. A Discord user can invoke /train-browser and receive a completion embed reporting battles played and reward summary
**Plans**: TBD
**UI hint**: yes

### Phase 05: MCTSPlayer + Transformer Training
**Goal**: MCTSPlayer is production-ready and the BattleTransformer trains to convergence via MCTS self-play
**Depends on**: Phase 04
**Requirements**: MCTS-01, MCTS-02, MCTS-03
**Success Criteria** (what must be TRUE):
  1. self_play.py MCTSPlayer has passing unit and integration tests with meaningful coverage
  2. The training pipeline accepts MCTSPlayer as the self-play opponent (replaces or augments the PPO self-play opponent)
  3. A training run using MCTSPlayer self-play produces a saved BattleTransformer checkpoint with decreasing validation loss across epochs
  4. The existing PPO-only training path (train_all.py) continues to work unchanged
**Plans**: TBD

### Phase 06: /spar Inference
**Goal**: /spar uses the strongest available inference engine and degrades gracefully when no transformer model exists
**Depends on**: Phase 05
**Requirements**: SPAR-01, SPAR-02, SPAR-03
**Success Criteria** (what must be TRUE):
  1. showdown_player.py use_mcts=True path loads the transformer model and routes battle decisions through MCTS lookahead
  2. A Discord user running /spar with a trained transformer checkpoint present observes MCTS-selected moves in battle
  3. A Discord user running /spar when no transformer checkpoint exists receives a normal PPO-powered battle with no error or degraded UX
  4. Switching between inference modes requires no code change — only the presence or absence of the transformer checkpoint file
**Plans**: TBD
**UI hint**: yes

---

## Dependency Graph

```
Phase 01 (obs expansion) ✅
     |
     +---> Phase 02 (curriculum) ✅
     |
     +---> Phase 03 (BC pretrain) ✅
                  |
                  +---> Phase 04 (browser training)
                              |
                              +---> Phase 05 (MCTSPlayer + transformer training)
                                          |
                                          +---> Phase 06 (/spar inference)
```

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 01. Observation Space Expansion | — | Done | 2026-05-18 |
| 02. Curriculum Opponent | — | Done | 2026-05-18 |
| 03. BC Pre-Training | — | Done | 2026-05-18 |
| 04. Browser Training | 0/? | Not started | - |
| 05. MCTSPlayer + Transformer Training | 0/? | Not started | - |
| 06. /spar Inference | 0/? | Not started | - |

---

*Last updated: 2026-05-19 — v1.1 phases 04–06 added*
