---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Full ML Integration
status: planning
last_updated: "2026-05-19T17:28:00.000Z"
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State — NCLPDLB Full ML Integration

*Last updated: 2026-05-19*

---

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-05-19 — Milestone v1.1 started

---

## Key Decisions Carried Forward

| Decision | Rationale |
|----------|-----------|
| OBS_DIM 44→48 (not 54) | Validate 4-float expansion before adding STAB + speed tier |
| log2 normalization for type_eff | Centers neutral at 0.0; symmetric extremes; immunity=-1.0 |
| Unknown type defaults to 0.0 (log2 neutral) | Avoids false immunity signal from 0.0 fallback |
| MaxBasePowerPlayer (not MaxDamagePlayer) | Verified in poke-env baselines.py; MaxDamagePlayer does not exist |
| `imitation` library for BC | Official SB3-endorsed library; provides BC class compatible with ActorCriticPolicy |
| Actor-only BC weight transfer | Value head has no BC signal; partial state dict with actor keys only |
| ent_coef=0.05 for first 100k steps after BC | Prevents entropy collapse; SB3 default 0.01 insufficient |
| Browser training before MCTS integration | No local server is the bigger unblock; transformer already tested |
| Transformer+MCTS in /spar falls back to PPO | Backward-compatible; users without transformer model unaffected |

---

## Repo Location

- Local clone: `/home/vboxuser/Documents/No Chill Draft League Bot/NCLPDLB`
- Remote: `NoChillModeOnline/NCLPDLB`
- Branch: `master` (push directly)

---

## Blockers

None currently.

---

## Session Continuity

Last session: 2026-05-19
Stopped at: Milestone v1.1 started, proceeding to define requirements and roadmap
