"""Unit tests for src.platform.normalize.species — pure, no DB required."""

import pytest
from src.platform.normalize.species import (
    FORM_OVERRIDES,
    FUZZY_CUTOFF,
    _build_slug_set,
    best_species_match,
    canonicalize_species,
    normalize_replay_pokemon,
    normalize_team_member,
    slugify,
    norm,
)


# ---------------------------------------------------------------------------
# slugify / norm
# ---------------------------------------------------------------------------


def test_slugify_strips_hyphens_and_spaces():
    assert slugify("Urshifu-Rapid-Strike") == "urshifurapidstrike"
    assert slugify("Iron Hands") == "ironhands"
    assert slugify("Iron hands") == slugify("iron hands")


def test_slugify_parity_with_legacy():
    """Regression: same result as the old _normalized_key in replay.py."""
    from src.platform.normalize.replay import _normalized_key

    for name in [
        "Urshifu-Rapid-Strike",
        "Iron Hands",
        "Mimikyu-Busted",
        "Calyrex-Shadow",
    ]:
        assert slugify(name) == _normalized_key(name), f"mismatch for {name!r}"


def test_norm_equals_slugify():
    """norm is a public alias; must match slugify for all test cases."""
    for name in ["Urshifu", "Mimikyu-Busted", "Indeedee-F", "Basculin"]:
        assert norm(name) == slugify(name)


# ---------------------------------------------------------------------------
# FORM_OVERRIDES integrity
# ---------------------------------------------------------------------------


def test_form_overrides_values_are_known_slugs():
    """Every FORM_OVERRIDES value must exist in the pokemon.json slug set."""
    slug_set = _build_slug_set()
    bad = {k: v for k, v in FORM_OVERRIDES.items() if v not in slug_set}
    assert not bad, f"Stale FORM_OVERRIDES entries (value not in pokemon.json): {bad}"


# ---------------------------------------------------------------------------
# canonicalize_species — required forms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected_slug, expected_method",
    [
        # Short-form defaults
        ("Urshifu", "urshifusinglestrike", "form_override"),
        ("Mimikyu", "mimikyudisguised", "form_override"),
        ("Zygarde", "zygarde50", "form_override"),
        ("Indeedee", "indeedeemale", "form_override"),
        ("Basculin", "basculinredstriped", "form_override"),
        # Battle-only forms
        ("Mimikyu-Busted", "mimikyudisguised", "form_override"),
        ("Zygarde-Complete", "zygarde50", "form_override"),
        # Direct slugs already in pokemon.json
        ("Iron Hands", "ironhands", "exact"),
        ("Urshifu Single Strike", "urshifusinglestrike", "exact"),
        ("Mimikyu Disguised", "mimikyudisguised", "exact"),
    ],
)
def test_required_forms_resolve_confidently(raw, expected_slug, expected_method):
    m = canonicalize_species(raw)
    assert m.canonical_slug == expected_slug, f"{raw!r}: got {m.canonical_slug!r}"
    assert m.method == expected_method, f"{raw!r}: method={m.method!r}"
    assert m.confidence == 1.0


def test_urshifu_rapid_strike_unresolved():
    """Urshifu-RS is not in pokemon.json — must surface as unresolved for seed review."""
    m = canonicalize_species("Urshifu-Rapid-Strike")
    assert m.canonical_slug is None
    assert m.method == "unresolved"
    assert m.raw_name == "Urshifu-Rapid-Strike"  # raw name preserved


# ---------------------------------------------------------------------------
# canonicalize_species — fuzzy fallback
# ---------------------------------------------------------------------------


def test_fuzzy_typo_resolves_with_subunit_confidence():
    m = canonicalize_species("Iron Hads")
    assert m.canonical_slug == "ironhands"
    assert m.method == "fuzzy"
    assert FUZZY_CUTOFF <= m.confidence < 1.0


def test_fuzzy_confidence_below_cutoff_gives_unresolved():
    m = canonicalize_species("Notamon", fuzzy_cutoff=0.99)
    assert m.canonical_slug is None
    assert m.method == "unresolved"


# ---------------------------------------------------------------------------
# canonicalize_species — unresolved case
# ---------------------------------------------------------------------------


def test_unresolved_preserves_raw_name():
    m = canonicalize_species("Notamon")
    assert m.method == "unresolved"
    assert m.canonical_slug is None
    assert m.confidence == 0.0
    assert m.raw_name == "Notamon"


# ---------------------------------------------------------------------------
# canonicalize_species — extra_overrides
# ---------------------------------------------------------------------------


def test_extra_overrides_take_precedence():
    custom = {"fakeform": "ironhands"}
    m = canonicalize_species("FakeForm", extra_overrides=custom)
    assert m.canonical_slug == "ironhands"
    assert m.method == "form_override"


# ---------------------------------------------------------------------------
# best_species_match
# ---------------------------------------------------------------------------


def test_best_species_match_exact_returns_10():
    slug_set = _build_slug_set()
    match, ratio = best_species_match("ironhands", slug_set)
    assert match == "ironhands"
    assert ratio == 1.0


def test_best_species_match_near_miss():
    slug_set = _build_slug_set()
    match, ratio = best_species_match("ironhads", slug_set)
    assert match == "ironhands"
    assert FUZZY_CUTOFF <= ratio < 1.0


def test_best_species_match_garbage_returns_none():
    slug_set = _build_slug_set()
    match, ratio = best_species_match("xyznotamon", slug_set, cutoff=0.99)
    assert match is None
    assert ratio == 0.0


# ---------------------------------------------------------------------------
# normalize_team_member
# ---------------------------------------------------------------------------


def test_normalize_team_member_prefers_id():
    mon = {
        "id": "urshifu",
        "name": "Urshifu Single Strike",
        "item": "Choice Band",
        "ability": "Unseen Fist",
        "tera": "Water",
        "attacks": ["Close Combat", "Wicked Blow"],
    }
    result = normalize_team_member(mon)
    assert result["canonical_slug"] == "urshifusinglestrike"
    assert result["raw_name"] == "Urshifu Single Strike"  # display name preserved
    assert result["item"] == "Choice Band"
    assert result["ability"] == "Unseen Fist"
    assert result["tera_type"] == "Water"
    assert result["moves"] == ["Close Combat", "Wicked Blow"]


def test_normalize_team_member_falls_back_to_name():
    mon = {"name": "Iron Hands", "attacks": []}
    result = normalize_team_member(mon)
    assert result["canonical_slug"] == "ironhands"
    assert result["raw_name"] == "Iron Hands"


def test_normalize_team_member_battle_form_collapses():
    mon = {"id": "mimikyubusted", "name": "Mimikyu-Busted"}
    result = normalize_team_member(mon)
    assert result["canonical_slug"] == "mimikyudisguised"
    assert result["confidence"] == 1.0


# ---------------------------------------------------------------------------
# normalize_replay_pokemon
# ---------------------------------------------------------------------------


def test_normalize_replay_pokemon_exact():
    result = normalize_replay_pokemon("Urshifu Single Strike")
    assert result["canonical_slug"] == "urshifusinglestrike"
    assert result["method"] == "exact"
    assert result["raw_name"] == "Urshifu Single Strike"


def test_normalize_replay_pokemon_form_override():
    result = normalize_replay_pokemon("Mimikyu-Busted")
    assert result["canonical_slug"] == "mimikyudisguised"
    assert result["confidence"] == 1.0


def test_normalize_replay_pokemon_unresolved_preserves_raw():
    result = normalize_replay_pokemon("??Unknown??")
    assert result["canonical_slug"] is None
    assert result["raw_name"] == "??Unknown??"
    assert result["method"] == "unresolved"


# ---------------------------------------------------------------------------
# SpeciesMatch immutability
# ---------------------------------------------------------------------------


def test_species_match_is_frozen():
    m = canonicalize_species("Iron Hands")
    with pytest.raises((AttributeError, TypeError)):
        m.canonical_slug = "changed"  # type: ignore[misc]
