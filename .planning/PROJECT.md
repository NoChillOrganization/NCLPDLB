# NCLPDLB ML Full Integration

## What This Is

A reinforcement learning Pokemon battle bot (poke-env + stable-baselines3 PPO) with domain
knowledge injection (type effectiveness, curriculum opponent, BC pre-training). This milestone
wires the existing transformer/MCTS infrastructure into a complete training + inference
pipeline: browser-based self-play against pokemonshowdown.com and MCTS-powered /spar.

## Core Value

The bot must be fully playable via /spar using the strongest available inference engine
(transformer + MCTS), trainable without a local Showdown server, and ready for real league use.

## Current Milestone: v1.1 Full ML Integration

**Goal:** Wire transformer/MCTS infrastructure into complete training + inference pipeline.

**Target features:**
- Browser-based self-play training via Playwright (no local server required)
- Discord command to trigger browser training sessions
- MCTSPlayer (self_play.py) tested and wired into training pipeline
- Transformer trains via MCTS self-play
- /spar uses transformer+MCTS at inference; falls back to PPO if no transformer model

## Requirements

### Validated

- ✓ PPO self-play training pipeline (train_policy.py) — existing
- ✓ Battle observation space (battle_env.py, OBS_DIM=44) — existing
- ✓ Replay scraper and parser (replay_scraper.py, replay_parser.py) — existing
- ✓ Feature extractor for offline datasets (feature_extractor.py) — existing
- ✓ Multi-format training runner (train_all.py, 22 formats) — existing

### Active (v1.1)

- [ ] browser_trainer.py: full Playwright self-play loop updating PPO weights (no local server)
- [ ] Discord command triggers browser training session
- [ ] self_play.py MCTSPlayer tested and wired into training pipeline
- [ ] Transformer model trains via MCTS self-play
- [ ] showdown_player.py use_mcts=True path fully wired (transformer+MCTS inference)
- [ ] /spar uses transformer+MCTS when model exists; falls back to PPO

### Out of Scope

- Full Smogon tier data integration — too large a dependency for this milestone
- Ability/item awareness in obs — follow-on milestone after type chart proves out
- Opponent moveset tracking — requires opponent modeling, separate milestone

## Context

**Architecture:**
- battle_env.py: Gymnasium wrapper; embed_battle() builds obs vector, calc_reward() shapes reward
- train_policy.py: PPO training; SelfPlayOpponent starts as RandomPlayer (epoch 0), swaps checkpoint every swap_every steps
- replay_scraper.py / replay_parser.py: async scraper + log parser -> BattleRecord objects
- feature_extractor.py: converts BattleRecords to numpy arrays for offline ML

**Type effectiveness gap:** Move features include type_id but NOT effectiveness vs opponent.
Agent must discover through reward signal that Fire is weak to Water — requires thousands of
redundant battles currently.

**Curriculum gap:** SelfPlayOpponent starts as RandomPlayer. Epoch 0 training signal is weak
because random play doesn't pressure the agent to learn defensive timing or type selection.

**Initialization gap:** PPO starts from random weights. Human replays encode patterns like
"use your best super-effective move" that BC can teach in minutes of supervised training.

## Constraints

- **Compatibility**: Must not break existing train_all.py invocations (backward-compatible API only)
- **OBS_DIM**: Changing OBS_DIM invalidates saved model checkpoints — new training runs required
- **poke-env API**: MaxBasePowerPlayer exists in poke-env; verify exact class name before coding
- **Action mapping**: BC pre-training must map replay moves to the same 0-25 action space as PPO
- **Platform**: Training runs on GitHub Actions (Linux); local dev may be Windows

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Add 4 type-effectiveness floats (one per move slot) | Minimal obs expansion, directly encodes most important battle mechanic | ✓ Delivered v1.0 |
| Use MaxBasePowerPlayer as curriculum opponent | Built into poke-env, zero external deps | ✓ Delivered v1.0 |
| BC pre-training from replays initializes PPO | Replay data already scraped; BC is supervised so fast to train | ✓ Delivered v1.0 |
| Keep BC as optional --pretrain flag | Backward compatible, lets existing workflows continue | ✓ Delivered v1.0 |
| OBS_DIM 44→48 (not 54) | Validate 4-float expansion before adding STAB + speed tier | ✓ Delivered v1.0 |
| Browser training before MCTS integration | No local server is the bigger unblock; transformer already tested | v1.1 decision |
| Transformer+MCTS in /spar falls back to PPO | Backward-compatible; users without transformer model unaffected | v1.1 decision |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-19 — milestone v1.1 started*
