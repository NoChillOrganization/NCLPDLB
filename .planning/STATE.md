---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: milestone
status: Phase 04 fully executed; competitive data pipeline hardened
stopped_at: ""
last_updated: "2026-05-25T21:00:00.000Z"
last_activity: 2026-05-25 — hardened prepare_competitive_data.py; added 10 per-tier Smogon CSVs (SPWA v3 schema, all URLs verified live)
progress:
  total_phases: 6
  completed_phases: 1
  total_plans: 2
  completed_plans: 2
  percent: 17
---

# Project State — NCLPDLB Full ML Integration

*Last updated: 2026-05-20*

---

## Current Position

Phase: 04 — Browser Training
Plan: 04-01 ✅ complete; 04-02 ✅ complete
Status: Phase 04 fully executed; no further plans in this phase
Last activity: 2026-05-20 — 04-01 (3 bug fixes + playwright dep) and 04-02 (14 unit tests) committed

Progress: `[x][ ][ ]` 1/3 phases complete (Phase 04 done)

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

Last session: 2026-05-25T19:50:31.832Z
Stopped at: context exhaustion at 75% (2026-05-25)
