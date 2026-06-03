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

## Progress (2026-06-03)

Gate override applied (see ISS-008 plan): fold ISS-007 + ISS-008 into one 78-dim checkpoint break
instead of two sequential training runs.

**Implementation complete on `feat/obs-ability-item` (base: `feat/obs-dim-53-stab-speed`):**

- [x] Design doc written: `docs/design/ISS-008-ability-item-obs.md` (AC1 ✓)
- [x] `build_observation()` extended with ability + item buckets (AC2 ✓)
  - Added lookup maps: `SPEED_BOOST_ABILITIES`, `ATK_BOOST_ABILITIES`, `REGEN_ABILITIES`,
    `PRIORITY_ABILITIES`, `CONTACT_PUNISH_ABILITIES`, `CONDITIONAL_BOOST_ABILITIES`,
    `ABSORB_TYPE_ABILITIES`, `ENTRY_EFFECT_ABILITIES`, `CHOICE_ITEMS`, `HEAL_ITEMS`,
    `STATUS_ITEMS`, `SASH_ITEMS`, `OFFENCE_ITEMS`, `DEFENSIVE_ITEMS`, `SPEED_ITEMS`
  - Added helpers: `_norm()`, `_ability_buckets()` (8 own / 6 opp), `_item_buckets()` (7 own / 4 opp)
  - `absorb_type_id` slot implemented via `ABSORB_TYPE_ABILITIES` map (not stub 0.0)
  - `build_doubles_observation()` extended with 50-float ability+item tail (2 slots × 25)
- [x] `OBS_DIM = 53 → 78` (literal + computed); `OBS_DIM_DOUBLES = 90 → 140` (AC3 ✓)
  - Existing 48-dim AND 53-dim checkpoints incompatible; one fresh 78-dim training run covers both
- [x] 136 tests pass, 2 skipped (poke_env import-skip, expected on Windows) (AC4 ✓)
  - `TestAbilityBuckets` (11 tests) + `TestItemBuckets` (9 tests) + slot-range integration tests added
- [ ] Dispatch fresh 78-dim training run on x86 VM (next milestone)
