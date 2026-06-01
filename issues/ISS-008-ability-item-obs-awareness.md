---
id: ISS-008
title: Observation space — ability and item awareness
status: in-progress
priority: low
phase: backlog
labels: [ml, obs-space]
created: 2026-05-31
---

# ISS-008 — Observation Space: Ability and Item Awareness

## Summary

Encode held item and ability effects in the observation vector so the agent can learn to play around Leftovers, Choice items, Intimidate, etc.

## Context

From PROJECT.md Out of Scope: "Ability/item awareness in obs — follow-on milestone after type chart proves out." This is explicitly deferred to a post-v1.1 milestone.

## Acceptance Criteria

- [ ] Design doc for ability/item encoding scheme written
- [ ] `embed_battle()` in `battle_env.py` extended with ability + item features
- [ ] OBS_DIM updated; incompatible checkpoints documented
- [ ] All tests pass

## Dependencies

- [[ISS-007-obs-stab-speed-tier]] — validate STAB expansion first
- Phase 06 complete

## Notes

This is a significant scope increase. Requires cataloguing which abilities/items have battlefield-relevant effects (100+). Recommend separate milestone.

## Progress (2026-06-01)

Design doc written (AC1 ✓): `docs/design/ISS-008-ability-item-obs.md`.

Specifies:
- Effect-bucket encoding (not one-hot / full embedding) — 14 ability floats + 11 item floats = 25 new floats
- OBS_DIM 53 → 78 (after ISS-007 lands)
- Catalogued ability categories: speed boost, atk boost, regen, priority, absorb, entry effect, contact punish, conditional
- Catalogued item categories: heal, choice lock, speed modifier, defensive, sash, offensive, status
- Python helper sketch (`_ability_buckets`, `_item_buckets`) and lookup maps
- Implementation checklist, doubles parity, gate conditions

**Gate:** ISS-007 must be merged and a 53-dim baseline validated before this branch opens.
