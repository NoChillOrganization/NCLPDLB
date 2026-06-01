---
title: Issue Tracker
updated: 2026-06-01
closed: 2026-06-01
open: 3
in-progress: 3
---

# Issue Tracker — NCLPDLB

> Source of truth for open work. Individual notes in `issues/`. Add new issues by creating `issues/ISS-NNN-slug.md` with the same frontmatter schema, then add a row here.

---

## Open

| ID                                              | Title                                          | Phase   | Priority | Labels         | Status      |
| ----------------------------------------------- | ---------------------------------------------- | ------- | -------- | -------------- | ----------- |
| [[ISS-006-ml-training-environment\|ISS-006]]    | ML training — provision x86 Linux environment  | backlog | medium   | ml, infra      | in-progress |
| [[ISS-007-obs-stab-speed-tier\|ISS-007]]        | Observation space — STAB and speed tier        | backlog | low      | ml, obs-space  | in-progress |
| [[ISS-008-ability-item-obs-awareness\|ISS-008]] | Observation space — ability and item awareness | backlog | low      | ml, obs-space  | in-progress |

---

## Roadmap Status

| Phase | Name | Status |
|-------|------|--------|
| 01 | Observation Space Expansion (OBS_DIM 44→48) | ✅ done |
| 02 | Curriculum Opponent (MaxBasePowerPlayer) | ✅ done |
| 03 | BC Pre-Training | ✅ done |
| 04 | Browser Training (Playwright self-play) | ✅ done |
| 05 | MCTSPlayer + Transformer Training | ✅ done |
| 06 | /spar Inference (transformer+MCTS) | 🔄 in progress |

---

## Schema

New issue frontmatter:

```yaml
---
id: ISS-NNN
title: Short title
status: open | in-progress | done | blocked
priority: high | medium | low
phase: "05" | "06" | backlog
labels: [tag1, tag2]
created: YYYY-MM-DD
---
```

Status transitions: `open` → `in-progress` → `done`. Move done rows to a **Closed** section below.

---

## Closed

| ID | Title | Phase | Priority | Labels | Status |
|----|-------|-------|----------|--------|--------|
| [[ISS-001-mcts-unit-integration-tests\|ISS-001]] | MCTSPlayer — unit and integration tests | 05 | high | testing, ml | done |
| [[ISS-002-mcts-wire-training-opponent\|ISS-002]] | MCTSPlayer — wire as training pipeline opponent | 05 | high | ml, training | done |
| [[ISS-003-transformer-train-mcts-selfplay\|ISS-003]] | BattleTransformer — train to convergence via MCTS self-play | 05 | high | ml, training | done |
| [[ISS-004-spar-wire-mcts-inference\|ISS-004]] | /spar — wire use_mcts=True inference path | 06 | high | bot, inference | done |
| [[ISS-005-spar-fallback-ppo\|ISS-005]] | /spar — graceful PPO fallback | 06 | high | bot, inference | done |
