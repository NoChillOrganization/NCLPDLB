"""
Canonical species and form normalization — offline, pure, no database queries.

Feeds the DB stage (resolve_species in repositories.py) by returning the best slug
to look up, along with a confidence score and resolution method.

Resolution order in canonicalize_species():
  1. Exact slug match  — slugify(raw) is directly a known species slug    (confidence 1.0)
  2. Form override     — FORM_OVERRIDES maps the slugified form to a base  (confidence 1.0)
  3. Base-form strip   — strip last hyphen segment, retry 1–2             (confidence 0.97)
  4. Fuzzy match       — difflib SequenceMatcher ≥ FUZZY_CUTOFF           (confidence 0.85–0.99)
  5. Unresolved        — raw_name preserved for alias-review workflow      (confidence 0.0)

The known-slug set is built once from data/pokemon.json at import (1025 slugs). This
mirrors the pattern in seed.py and needs no external dependency.

Backward compatibility
----------------------
Re-exports ``_normalized_key = slugify`` so the three existing callers that import
``_normalized_key`` from replay.py continue to work unmodified:
    from src.platform.normalize.replay import _normalized_key
replay.py keeps its own definition; this module is the canonical home.

See docs/platform-species-aliases.md for the alias-review workflow.
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path
from typing import Iterable, Literal

# ---------------------------------------------------------------------------
# Slug normalization
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    """
    Lowercase + strip non-alphanumeric characters.

    Matches Showdown's ``toId()`` semantics for most Pokémon names:
    ``"Urshifu-Rapid-Strike"`` → ``"urshifurapidstrike"``.
    """
    return "".join(c for c in name.lower() if c.isalnum())


def norm(name: str) -> str:
    """
    Alias of slugify. Exists as a separate public symbol for callers that want
    the 'normalised key' concept without caring about the implementation.

    ponytail: currently identical to slugify; extend here (e.g. strip locale suffixes,
    collapse Unicode homoglyphs) only when live data shows a gap that slugify misses.
    """
    return slugify(name)


# Backward-compat re-export — replay.py, tournament.py, usage.py, seed.py use this name.
_normalized_key = slugify


# ---------------------------------------------------------------------------
# Known-slug set (loaded once from data/pokemon.json)
# ---------------------------------------------------------------------------

_POKEMON_JSON = Path(__file__).parents[3] / "data" / "pokemon.json"
_SLUG_SET: frozenset[str] = frozenset()


def _build_slug_set() -> frozenset[str]:
    """Load once; subsequent calls return the cached frozenset."""
    global _SLUG_SET
    if _SLUG_SET:
        return _SLUG_SET
    if not _POKEMON_JSON.exists():  # graceful degradation in minimal envs
        warnings.warn(
            f"data/pokemon.json not found at {_POKEMON_JSON}; exact slug matching disabled.",
            UserWarning,
            stacklevel=2,
        )
        return frozenset()
    entries = json.loads(_POKEMON_JSON.read_text(encoding="utf-8"))
    _SLUG_SET = frozenset(slugify(e["name"]) for e in entries)
    return _SLUG_SET


# ---------------------------------------------------------------------------
# Form-override map
# ---------------------------------------------------------------------------

# Keys: slugify(raw_form_name) emitted by tournament/replay sources.
# Values: canonical slug that IS present in data/pokemon.json.
#
# Two categories:
#   Short-form defaults — source omits the form qualifier entirely, e.g. "Urshifu"
#                         when only one form is in pokemon.json.
#   Battle-only forms   — form exists only mid-battle; team sheets use the base form.
#
# Entries where the ALTERNATE form (Indeedee-F, Urshifu-RS) genuinely maps to a
# DIFFERENT competitive Pokémon that is missing from pokemon.json are intentionally
# absent — the normalizer returns "unresolved" so the gap is visible in review logs
# rather than silently recorded as the wrong species.
#
# ponytail: add new entries here only when (a) the target slug exists in pokemon.json
# AND (b) collapsing to that slug is analytically correct. The aliases.ts corpus in
# seed.py is the upgrade path for forms that warrant their own canonical_species row.
FORM_OVERRIDES: dict[str, str] = {
    # ---- Short-form / default-form (bare name = the one form in pokemon.json) ----
    "urshifu":         "urshifusinglestrike",   # Urshifu Single Strike
    "mimikyu":         "mimikyudisguised",       # Mimikyu Disguised
    "zygarde":         "zygarde50",              # Zygarde 50%
    "indeedee":        "indeedeemale",           # Indeedee Male (Female not yet seeded)
    "basculin":        "basculinredstriped",     # Basculin Red Striped
    "aegislash":       "aegislashshield",        # Aegislash Shield
    "wishiwashi":      "wishiwashisolo",         # Wishiwashi Solo
    "minior":          "miniorredmeteor",        # Minior (form-colour is cosmetic)
    "morpeko":         "morpekofullbelly",       # Morpeko Full Belly
    "oricorio":        "oricoriobaile",          # Oricorio Baile (default)

    # ---- Battle-only forms (same team slot, form changes in-battle) ----
    "mimikyubusted":   "mimikyudisguised",       # disguise breaks in battle
    "zygardecomplete": "zygarde50",              # Power Construct: 100% only triggers in battle
    "zygarde10":       "zygarde50",              # 10% forme (same mon, different speed tier)
    "wishiwashischool":"wishiwashisolo",          # school form only active in battle
    "aegislashblade":  "aegislashshield",        # blade stance in battle
    "morpekohungry":   "morpekofullbelly",       # Hunger Switch triggers mid-turn
    "morpekohangry":   "morpekofullbelly",       # alternate 'Hangry' spelling
}

# Validate at import: warn (don't raise) if a value slug is no longer in pokemon.json.
# This fires on first import after a pokemon.json update removes or renames a species.
def _validate_overrides(slug_set: frozenset[str]) -> None:
    if not slug_set:
        return
    for key, target in FORM_OVERRIDES.items():
        if target not in slug_set:
            warnings.warn(
                f"FORM_OVERRIDES[{key!r}] = {target!r} is not a known species slug. "
                "Update FORM_OVERRIDES or data/pokemon.json.",
                UserWarning,
                stacklevel=2,
            )


# ---------------------------------------------------------------------------
# Fuzzy match
# ---------------------------------------------------------------------------

FUZZY_CUTOFF = 0.85  # ponytail: calibrated on Pokémon name set; tune down only if aliases are sparse


def best_species_match(
    key: str,
    candidates: Iterable[str] | None = None,
    *,
    cutoff: float = FUZZY_CUTOFF,
) -> tuple[str | None, float]:
    """
    Return ``(best_slug, ratio)`` for the closest candidate above *cutoff*, or
    ``(None, 0.0)`` if nothing clears the threshold.

    Uses ``difflib.get_close_matches`` (stdlib, O(n)) then ``SequenceMatcher.ratio()``
    for the exact score. Acceptable for ≤ 1 500 candidates (current pokemon.json has 1 025).

    Args:
        key: already-slugified query string.
        candidates: slug set to search; defaults to the pokemon.json slug set.
        cutoff: minimum SequenceMatcher ratio to accept (default 0.85).
    """
    if candidates is None:
        candidates = _build_slug_set()
    # get_close_matches iterates any iterable; frozenset is fine.
    close = get_close_matches(key, candidates, n=1, cutoff=cutoff)
    if not close:
        return None, 0.0
    match = close[0]
    ratio = SequenceMatcher(None, key, match).ratio()
    return match, ratio


# ---------------------------------------------------------------------------
# Resolution result
# ---------------------------------------------------------------------------

Method = Literal["exact", "form_override", "fuzzy", "unresolved"]


@dataclass(frozen=True)
class SpeciesMatch:
    """
    Result of ``canonicalize_species()``.

    Attributes:
        raw_name:       Original string exactly as received from the data source.
        canonical_slug: Best offline guess at the species slug. ``None`` when unresolved.
                        Pass as ``normalized_key`` to ``repositories.resolve_species()``.
        confidence:     1.0 for exact/form_override; 0.85–0.99 for fuzzy; 0.0 for unresolved.
        method:         Resolution path taken. Use for triage bucketing (see alias-review doc).
    """
    raw_name: str
    canonical_slug: str | None
    confidence: float
    method: Method


# ---------------------------------------------------------------------------
# Core resolution
# ---------------------------------------------------------------------------

def canonicalize_species(
    raw: str,
    *,
    extra_overrides: dict[str, str] | None = None,
    fuzzy_cutoff: float = FUZZY_CUTOFF,
) -> SpeciesMatch:
    """
    Resolve a raw species name to a canonical slug (offline, no DB).

    Resolution steps (see module docstring for full explanation):
      1. Exact slug match against the known-slug set.
      2. Form override (FORM_OVERRIDES + optional extra_overrides).
      3. Base-form strip — strip the last hyphen segment, retry 1–2.
      4. Fuzzy match with SequenceMatcher ≥ fuzzy_cutoff.
      5. Unresolved — canonical_slug=None, confidence=0.0.

    Args:
        raw:             Species name as emitted by the data source.
        extra_overrides: Caller-supplied form mappings merged over FORM_OVERRIDES.
                         Useful for source-specific aliases not worth adding globally.
        fuzzy_cutoff:    Override the default FUZZY_CUTOFF for this call.

    Returns:
        SpeciesMatch with raw_name always set to the original *raw* string.
    """
    slug_set = _build_slug_set()
    overrides = FORM_OVERRIDES if not extra_overrides else {**FORM_OVERRIDES, **extra_overrides}
    key = slugify(raw)

    # Step 1: exact slug
    if key in slug_set:
        return SpeciesMatch(raw, key, 1.0, "exact")

    # Step 2: form override
    if key in overrides:
        return SpeciesMatch(raw, overrides[key], 1.0, "form_override")

    # Step 3: base-form strip (handles e.g. "Landorus-Therian" if base "Landorus" exists,
    #         or a source appending an unexpected suffix like "-Mega")
    if "-" in raw:
        base_key = slugify(raw.rsplit("-", 1)[0])
        if base_key != key:
            if base_key in slug_set:
                return SpeciesMatch(raw, base_key, 0.97, "exact")
            if base_key in overrides:
                return SpeciesMatch(raw, overrides[base_key], 0.97, "form_override")

    # Step 4: fuzzy
    match, ratio = best_species_match(key, slug_set, cutoff=fuzzy_cutoff)
    if match:
        return SpeciesMatch(raw, match, ratio, "fuzzy")

    return SpeciesMatch(raw, None, 0.0, "unresolved")


# ---------------------------------------------------------------------------
# Normalizer helpers (consumed by tournament.py / replay.py wiring, follow-up task)
# ---------------------------------------------------------------------------

def normalize_team_member(
    mon: dict,
    *,
    extra_overrides: dict[str, str] | None = None,
) -> dict:
    """
    Normalize a Limitless decklist entry (``mon`` dict) into a standardised dict.

    Reads ``mon["id"]`` (Showdown internal ID) preferentially over ``mon["name"]``.
    Returns a dict with:
        ``raw_name``       — original display name from the source.
        ``canonical_slug`` — resolved slug (or None if unresolved).
        ``confidence``     — 0.0–1.0; <1.0 entries should be reviewed.
        ``method``         — resolution path ("exact"/"form_override"/"fuzzy"/"unresolved").
        ``item``           — forwarded from mon, may be None.
        ``ability``        — forwarded from mon, may be None.
        ``tera_type``      — forwarded from mon["tera"], may be None.
        ``moves``          — forwarded from mon["attacks"] as list, may be empty.

    Does not perform any DB lookup.
    """
    # Limitless "id" is the Showdown slug (no hyphens); "name" is the display name.
    source_id = mon.get("id") or ""
    display = mon.get("name") or source_id
    # Prefer id for resolution; fall back to display name.
    resolve_from = source_id if source_id else display
    match = canonicalize_species(resolve_from, extra_overrides=extra_overrides)

    return {
        "raw_name": display,
        "canonical_slug": match.canonical_slug,
        "confidence": match.confidence,
        "method": match.method,
        "item": mon.get("item"),
        "ability": mon.get("ability"),
        "tera_type": mon.get("tera"),
        "moves": mon.get("attacks") or [],
    }


def normalize_replay_pokemon(
    species: str,
    *,
    extra_overrides: dict[str, str] | None = None,
) -> dict:
    """
    Normalize a Showdown species string from a replay log.

    Returns a dict with ``raw_name``, ``canonical_slug``, ``confidence``, ``method``.
    No build fields (replay logs carry species + tera_type but not items/EVs/etc.).

    Does not perform any DB lookup.
    """
    match = canonicalize_species(species, extra_overrides=extra_overrides)
    return {
        "raw_name": species,
        "canonical_slug": match.canonical_slug,
        "confidence": match.confidence,
        "method": match.method,
    }


# ---------------------------------------------------------------------------
# Module-level initialisation
# ---------------------------------------------------------------------------
# Build and validate on first import so any pokemon.json gaps appear early in the
# process, not mid-ingest. Using a private call avoids re-validating on every lookup.
def _init() -> None:
    slugs = _build_slug_set()
    _validate_overrides(slugs)


_init()


# ---------------------------------------------------------------------------
# Smoke test  (ponytail: one runnable check that fails if the logic breaks)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    cases = [
        ("Urshifu",             "urshifusinglestrike", "form_override"),
        ("Urshifu-Rapid-Strike", None,                 "unresolved"),  # RS not in pokemon.json — seed it
        ("Mimikyu-Busted",      "mimikyudisguised",    "form_override"),
        ("Zygarde-Complete",    "zygarde50",           "form_override"),
        ("Indeedee",            "indeedeemale",        "form_override"),
        ("Basculin",            "basculinredstriped",  "form_override"),
        ("Iron Hands",          "ironhands",           "exact"),
        ("Iron Hads",           "ironhands",           "fuzzy"),
        ("Notamon",             None,                  "unresolved"),
    ]
    print(f"{'raw':<28} {'slug':<26} {'conf':>5}  {'method'}")
    print("-" * 75)
    ok = True
    for raw, expected_slug, expected_method in cases:
        m = canonicalize_species(raw)
        status = "OK" if (m.canonical_slug == expected_slug and m.method == expected_method) else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"{status:<4} {raw:<26} {str(m.canonical_slug):<26} {m.confidence:>5.2f}  {m.method}")
    raise SystemExit(0 if ok else 1)
