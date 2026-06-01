# ISS-008 — Observation Space: Ability and Item Awareness

**Status:** in-progress  
**Phase:** backlog (gate: after ISS-007 lands + Phase 06 complete)  
**Priority:** low  
**Labels:** ml, obs-space  
**Depends on:** [[ISS-007-obs-stab-speed-tier]] (validate 53-dim first), Phase 06 complete

---

## Context

The current observation vector encodes what a Pokémon *can do* (moves, power, type) and the
field state, but not *what it is carrying or what passive effects it has*. Held items and
abilities create persistent modifiers — Leftovers heals every turn, Choice Scarf locks a move
but 1.5× speed, Intimidate drops the opponent's Attack on switch-in. A model unaware of these
cannot learn to switch around them or sequence actions to exploit them.

From `PROJECT_INDEX.md` Out-of-Scope: "Ability/item awareness in obs — follow-on milestone after
type chart proves out." This doc satisfies ISS-008 AC1 ("design doc written") and defines the
scope and encoding for the implementation milestone.

---

## Scope Decision

Abilities and items are large spaces (hundreds of each). Two design pressures conflict:

1. **Expressiveness** — a full one-hot or embedding per ability/item would be maximally
   informative but inflates `OBS_DIM` dramatically and requires more training to converge.
2. **Compactness** — a small set of *effect buckets* covers ~80% of competitive relevance with
   ~10–20 extra floats.

**Recommendation: effect-bucket encoding** for v1 of this milestone. The agent learns the
*functional effect* (heal, speed boost, choice lock, etc.) rather than the identity token.
This is smaller, more generalizable, and avoids sparse representations for rare items/abilities.
A full embedding approach can be a follow-on if bucket encoding proves insufficient.

---

## Battlefield-Relevant Ability Categories

Each category maps to one or two floats. Only "active" or commonly-encountered effects are
included; abilities with negligible battlefield impact (e.g. Run Away) are omitted.

### Own-active-mon abilities

| Category | Abilities | Encoding |
|---|---|---|
| **Speed boost** | Speed Boost, Swift Swim (rain), Chlorophyll (sun), Sand Rush (sand), Slush Rush (snow), Surge Surfer (elec terrain) | `speed_boost_active: float` — 0.0 (no boost), 0.5 (conditional), 1.0 (unconditional per-turn) |
| **Attack boost** | Huge Power, Pure Power, Guts (when statused), Hustle, Gorilla Tactics | `atk_boost_ability: float` — 0.0/0.5/1.0 |
| **Pivot/entry** | Regenerator (on switch), Natural Cure (on switch), Shed Skin | `regen_ability: float` — 1.0 if active |
| **Priority** | Prankster (status moves +1), Triage (healing +3), Gale Wings (Flying +1 at full HP) | `priority_ability: float` — 1.0 if present |
| **Immunity / Absorption** | Volt Absorb, Water Absorb, Lightning Rod, Flash Fire, Storm Drain, Motor Drive, Sap Sipper | `absorb_type_id: float` — type ID / 20, 0 if none |
| **Intimidate / Def boost on entry** | Intimidate (opponent atk −1), Dauntless Shield, Intrepid Sword | `entry_effect_ability: float` — −1.0 atk drop, +1.0 own def/atk boost, 0 none |
| **Contact / Punish** | Rough Skin, Iron Barbs, Flame Body, Static, Poison Point, Effect Spore | `contact_punish: float` — 1.0 if present |
| **Unburden / conditional** | Unburden (speed ×2 after item consumed), Moxie, Beast Boost | `conditional_boost: float` — 1.0 if present |
| **Terrain/weather setter** | Drought, Drizzle, Sand Stream, Snow Warning, Grassy Surge, Misty Surge, Electric Surge, Psychic Surge | Use existing weather/terrain field features; no new float needed |
| **Unknown** | Ability not revealed by opponent | 0.0 in all ability floats |

### Opponent-active-mon abilities (known only when revealed)

Mirror the own-mon bucket set but applied to opponent:
- Add `opp_speed_boost_ability`, `opp_atk_boost_ability`, `opp_regen_ability`, `opp_priority_ability`, `opp_absorb_type_id`, `opp_contact_punish`.
- Use 0.0 for unrevealed abilities (conservative — same as "no effect").

---

## Battlefield-Relevant Item Categories

### Own-active-mon items

| Category | Items | Encoding |
|---|---|---|
| **Healing** | Leftovers (1/16 per turn), Black Sludge (1/16 or −1/8), Berry Juice, Sitrus/Berry triggers | `heal_item: float` — per-turn fraction: Leftovers = 0.0625; 0.0 if none |
| **Choice lock** | Choice Band, Choice Specs, Choice Scarf | `choice_item: float` — 0.0 none, 0.33 Band (atk ×1.5), 0.67 Specs (spa ×1.5), 1.0 Scarf (spe ×1.5) |
| **Speed modifier** | Choice Scarf (+1.5×), Iron Ball (×0.5), Lagging Tail (−1 priority) | `speed_item_modifier: float` — ratio: 1.0 neutral, 1.5 Scarf, 0.5 Iron Ball |
| **Eviolite / defense** | Eviolite (def/spd ×1.5 if not fully evolved), Assault Vest (spd ×1.5), Rocky Helmet (contact damage), Rocky Helmet | `defensive_item: float` — 0.0/0.5/1.0 tier |
| **One-time trigger** | Focus Sash (survive at 1 HP), Focus Band, Sturdy-like | `sash_item: float` — 1.0 if sash-like and HP=100%, 0.0 otherwise |
| **Offensive** | Life Orb (1.3× dmg −1/10 HP), Expert Belt (SE ×1.2), type-boosting plates/specs | `offence_item: float` — 0.0 none, 0.5 conditional (Expert Belt), 1.0 always (Life Orb) |
| **Status prevention / residual** | Lum Berry (clears status once), Flame Orb (burns self), Toxic Orb | `status_item: float` — −1.0 inflicts status, 0.0 none, 1.0 cures status |
| **Unknown / consumed** | Item unknown or already consumed | 0.0 in all item floats |

### Opponent item (partially observable)

Opponents' items are often unknown until revealed via an effect. Encode only *revealed* info:
- `opp_heal_item`, `opp_choice_item`, `opp_defensive_item`, `opp_sash_item` — same ranges,
  default 0.0 when unknown.

---

## Proposed Encoding Size

After ISS-007 lands (OBS_DIM = 53), this expansion targets:

```
Feature                         Floats
──────────────────────────────────────
Own speed-boost ability           1
Own atk-boost ability             1
Own regen ability                 1
Own priority ability              1
Own absorb type ID                1
Own entry-effect ability          1
Own contact-punish ability        1
Own conditional-boost ability     1
Opp speed-boost ability           1
Opp atk-boost ability             1
Opp regen ability                 1
Opp priority ability              1
Opp absorb type ID                1
Opp contact-punish ability        1
──── abilities = 14 ───────────────
Own heal item                     1
Own choice item                   1
Own speed item modifier           1
Own defensive item                1
Own sash item                     1
Own offence item                  1
Own status item                   1
Opp heal item                     1
Opp choice item                   1
Opp defensive item                1
Opp sash item                     1
──── items = 11 ────────────────────
TOTAL new floats                 25
──────────────────────────────────────
OBS_DIM after ISS-008:  53 + 25 = 78
```

---

## Updated Layout (OBS_DIM = 78)

```
Index range   Dim   Description
─────────────────────────────────────────────────────────────
[0..52]        53    All ISS-007 features (unchanged)
[53..66]       14    Ability buckets (own + opp)            ← NEW ISS-008
[67..77]       11    Item buckets (own + opp)               ← NEW ISS-008
─────────────────────────────────────────────────────────────
TOTAL          78
```

---

## Doubles Parity

`OBS_DIM_DOUBLES` would need a 2× active-mon and 2× opp-active-mon layout for ability/item
features. Size estimate: `OBS_DIM_DOUBLES = 80 + 2×(14+11) = 130`. Exact doubles encoding is
a sub-task of this milestone.

---

## Implementation Notes

### Data sources

- poke-env `Pokemon.ability` (own revealed ability, may be `None` or `"unknown"`)
- poke-env `Pokemon.item` (own item, may be `None` or `""`)
- poke-env `Battle.opponent_active_pokemon.ability` / `.item` (opponent, often `None`)
- Smogon/Showdown data via `src/data/showdown.py` can map ability/item strings to categories

### Bucket lookup implementation sketch

```python
# In battle_env.py — add alongside existing TYPE_IDS / STATUS_IDS maps

SPEED_BOOST_ABILITIES = frozenset({
    "speedboost", "swiftsquim", "chlorophyll", "sandrush", "slushrush", "surgesurfer",
})
ATK_BOOST_ABILITIES = frozenset({
    "hugepower", "purepower", "guts", "hustle", "gorillatactics",
})
REGEN_ABILITIES = frozenset({"regenerator", "naturalcure", "shedskin"})
PRIORITY_ABILITIES = frozenset({"prankster", "triage", "galewings"})
CONTACT_PUNISH_ABILITIES = frozenset({
    "roughskin", "ironbarbs", "flamebody", "static", "poisonpoint", "effectspore",
})
CONDITIONAL_BOOST_ABILITIES = frozenset({"unburden", "moxie", "beastboost"})

CHOICE_ITEMS = {"choiceband": 0.33, "choicespecs": 0.67, "choicescarf": 1.0}
HEAL_ITEMS = {"leftovers": 0.0625, "blacksludge": 0.0625}  # positive fraction
STATUS_ITEMS = {"lumberry": 1.0, "flameorb": -1.0, "toxicorb": -1.0}
SASH_ITEMS = frozenset({"focussash"})
OFFENCE_ITEMS = {"lifeorb": 1.0, "expertbelt": 0.5}
DEFENSIVE_ITEMS = frozenset({"eviolite", "assaultvest", "rockyhelmet"})

def _ability_buckets(ability: str | None) -> list[float]:
    """Return [speed_boost, atk_boost, regen, priority, absorb_id, entry_effect, contact, conditional]."""
    a = (ability or "").lower().replace(" ", "").replace("-", "")
    return [
        1.0 if a in SPEED_BOOST_ABILITIES else 0.0,
        1.0 if a in ATK_BOOST_ABILITIES else 0.0,
        1.0 if a in REGEN_ABILITIES else 0.0,
        1.0 if a in PRIORITY_ABILITIES else 0.0,
        0.0,  # absorb_type_id — TODO: map per-ability
        -1.0 if a == "intimidate" else (1.0 if a in {"dauntlessshield", "intrepidsword"} else 0.0),
        1.0 if a in CONTACT_PUNISH_ABILITIES else 0.0,
        1.0 if a in CONDITIONAL_BOOST_ABILITIES else 0.0,
    ]
```

### Testing plan

- `tests/unit/test_battle_env.py`: add `TestAbilityItemObs` class; mock a battle with known
  ability/item strings; assert buckets fire correctly. No poke-env live battle needed.
- Update `OBS_DIM == 78` assertions everywhere (same pattern as ISS-007 update).
- Integration smoke: `python -m pytest tests/integration/test_mcts_battle.py` — obs shape still
  consistent after dim change.

---

## Implementation Checklist (milestone after ISS-007)

- [ ] Branch: `feat/obs-ability-item` (base: `feat/obs-dim-53-stab-speed` after it lands)
- [ ] `src/ml/battle_env.py`: Add `_ability_buckets()`, `_item_buckets()` helpers + lookup maps
- [ ] `src/ml/battle_env.py`: Extend `build_observation()` to append 25 new floats at [53..77]
- [ ] `src/ml/battle_env.py`: Bump `OBS_DIM 53 → 78`; update `OBS_DIM_DOUBLES`
- [ ] `tests/unit/test_battle_env.py`: `TestAbilityItemObs` unit tests
- [ ] Update all test fixtures using `OBS_DIM` to use the imported constant (not a literal)
- [ ] Document checkpoint incompatibility; schedule fresh training run
- [ ] Dispatch new CI "Train ML Models" + VM `train_transformer` with `OBS_DIM=78`

## Gate

**Do NOT implement until:**
1. ISS-004/005 are done and `/spar` MCTS path is verified end-to-end (48-dim checkpoint)
2. ISS-007 `feat/obs-dim-53-stab-speed` is merged and a 53-dim model is trained/validated
3. The 53-dim model shows improvement over the 48-dim baseline (otherwise ISS-008 risk > reward)

---

## References

- `src/ml/battle_env.py:52–67` — `OBS_DIM` and layout constants
- `src/ml/battle_env.py:145–236` — `build_observation()` (extend here)
- `docs/design/ISS-007-obs-stab-speed-tier.md` — prerequisite expansion
- `PROJECT_INDEX.md` Out-of-Scope: "Ability/item awareness in obs — follow-on milestone"
- Issue: `issues/ISS-008-ability-item-obs-awareness.md`
