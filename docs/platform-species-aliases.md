# Species Alias Review Workflow

Reference for operators reviewing unresolved or low-confidence species matches produced
by `src/platform/normalize/species.py`.

---

## Why this exists

The platform resolves raw Pokémon names to `canonical_species_id` in two stages:

1. **Offline** (`canonicalize_species`) — pure Python, no DB. Maps the raw name to a
   canonical slug using exact slug matching, the `FORM_OVERRIDES` table, and a fuzzy
   fallback. Returns a `SpeciesMatch` with a `confidence` score and `method` label.

2. **DB** (`resolve_species` in `repositories.py`) — looks up `species_alias.normalized_key`
   and returns `canonical_species_id`. Receives the `canonical_slug` from stage 1.

When stage 2 returns `None` (no DB alias), the mon is dropped from analytics with no
signal. The `confidence` and `method` from stage 1 tell you *why* it was dropped and
what to do about it.

---

## Confidence triage buckets

| `method`        | `confidence` | Meaning                                        | Action                       |
|-----------------|:------------:|------------------------------------------------|------------------------------|
| `exact`         | 1.0          | Slug already in slug set and DB alias          | None — healthy               |
| `form_override` | 1.0          | Hard-coded form map in `FORM_OVERRIDES`        | None — healthy               |
| `fuzzy`         | 0.85–0.99    | Best-effort guess; may be wrong                | **Spot-check, then promote** |
| `unresolved`    | 0.0          | No match found                                 | **Investigate and fix**      |

---

## Resolution workflow

### Fuzzy hits (conf 0.85–0.99)

1. Collect all `method="fuzzy"` rows from a normalization run.
2. For each, confirm the `canonical_slug` is the intended species.
3. If correct: add a `species_alias` row so future runs hit `method="exact"`:
   ```sql
   INSERT INTO species_alias (canonical_species_id, source_id, raw_name, normalized_key)
   SELECT cs.id, s.id, '<raw_name>', '<normalized_key>'
   FROM canonical_species cs, source s
   WHERE cs.slug = '<canonical_slug>' AND s.name = '<source_name>';
   ```
   Or re-seed via `python -m src.platform.seed` after updating `data/pokemon.json` or
   `pokemon-showdown/data/aliases.ts`.
4. If wrong: add the correct mapping to `FORM_OVERRIDES` (see below) or `species_alias`.

### Unresolved (conf 0.0)

Two sub-cases:

**A — The species genuinely has no row in `canonical_species`** (e.g. newly released DLC
or a form variant like Urshifu-Rapid-Strike):
1. Add the missing species to `data/pokemon.json` with the correct `name` and
   `national_dex` fields.
2. Re-run `python -m src.platform.seed` against a database with 0001_init applied.
3. Add any source-specific aliases to `pokemon-showdown/data/aliases.ts` if the source
   uses non-standard names.
4. The next normalization run resolves this mon as `method="exact"`.

**B — The species exists in the DB but the source spells it differently** (typo, regional
name, legacy format):
1. If it's a battle-state or cosmetic form that should collapse to a base form, add to
   `FORM_OVERRIDES` in `species.py`:
   ```python
   "rawslugifiedkey": "targetslug",   # one-line comment explaining collapse
   ```
   Both the key (slugified raw) and the value (canonical slug) must be checked against
   `_build_slug_set()` — the module warns at import if a value is stale.
2. If it's a genuine alias (same species, just a different spelling), add it as a
   `species_alias` row (preferred — persists in DB across code deploys).

---

## Two homes for aliases

| Type                        | Where to add                            | Persists across deploys? |
|-----------------------------|-----------------------------------------|:------------------------:|
| Canonical species (new mon) | `data/pokemon.json` → `seed.py`         | Yes (DB row)             |
| Source-specific spelling    | `species_alias` row (or `aliases.ts`)   | Yes (DB row)             |
| Battle/cosmetic form        | `FORM_OVERRIDES` in `species.py`        | Yes (code)               |

Prefer DB (`species_alias`) over code (`FORM_OVERRIDES`) for aliases: DB aliases survive
code refactors and are queryable. Use `FORM_OVERRIDES` only for forms that have **no own
`canonical_species` row** (e.g. Mimikyu-Busted, Zygarde-Complete).

---

## Known gaps (forms not yet in pokemon.json)

These species are competitively distinct but absent from the slug set. They resolve as
`unresolved` until seeded:

| Raw form                  | Correct canonical slug (add to pokemon.json) |
|---------------------------|----------------------------------------------|
| Urshifu-Rapid-Strike      | `urshifurapidstrike`                         |
| Indeedee-F / Indeedee Female | `indeedeefemale` (new entry needed)       |
| Basculin-Blue-Striped     | `basculinbluestriped` (new entry needed)     |
| Basculin-White-Striped    | `basculinwhitestriped` (new entry needed)    |
| Tauros-Paldea-Aqua        | `taurospaldeanaqua` (new entry needed)       |
| Tauros-Paldea-Blaze       | `taurospaldeanblaze` (new entry needed)      |

Add these by appending entries to `data/pokemon.json` and re-running `seed.py`.

---

## Quick-check commands

```bash
# Smoke test the module + see all case results
python -m src.platform.normalize.species

# Run unit tests (no DB needed)
python -m pytest tests/platform/test_normalize_species.py -v

# Verify FORM_OVERRIDES values are all valid slugs
python -c "
from src.platform.normalize.species import FORM_OVERRIDES, _build_slug_set
s = _build_slug_set()
bad = {k:v for k,v in FORM_OVERRIDES.items() if v not in s}
print('stale overrides:', bad or 'none')
"
```
