"""
Unit tests for AnalyticsService — type coverage, weaknesses, archetypes.
"""
from unittest.mock import AsyncMock, MagicMock

from src.data.models import Pokemon, PokemonStats
from src.services.analytics_service import AnalyticsService, get_type_effectiveness


def make_pokemon(name: str, types: list[str], atk=80, spa=80, def_=80, spd=80, spe=80, hp=80,
                 is_legendary=False, is_mythical=False) -> Pokemon:
    return Pokemon(
        national_dex=1, name=name, types=types,
        base_stats=PokemonStats(hp=hp, atk=atk, def_=def_, spa=spa, spd=spd, spe=spe),
        generation=1, is_legendary=is_legendary, is_mythical=is_mythical,
    )


# ── Type Effectiveness ────────────────────────────────────────

def test_fire_vs_grass_is_super_effective():
    assert get_type_effectiveness("fire", ["grass"]) == 2.0

def test_water_vs_fire_is_super_effective():
    assert get_type_effectiveness("water", ["fire"]) == 2.0

def test_normal_vs_ghost_is_immune():
    assert get_type_effectiveness("normal", ["ghost"]) == 0.0

def test_electric_vs_ground_is_immune():
    assert get_type_effectiveness("electric", ["ground"]) == 0.0

def test_fire_vs_water_grass_double_resistance():
    # Fire vs Water/Grass: 0.5 * 2 = 1.0
    eff = get_type_effectiveness("fire", ["water", "grass"])
    assert eff == 1.0

def test_fighting_vs_normal_ghost():
    # Normal takes 2x, Ghost takes 0x → combined 0
    assert get_type_effectiveness("fighting", ["normal", "ghost"]) == 0.0


# ── Coverage Analysis ─────────────────────────────────────────

def test_coverage_identifies_types():
    svc = AnalyticsService()
    team = [
        make_pokemon("Charizard", ["fire", "flying"]),
        make_pokemon("Blastoise", ["water"]),
        make_pokemon("Venusaur", ["grass", "poison"]),
    ]
    report = svc.analyze_pokemon_list(team)
    assert "fire" in report.covered_types
    assert "water" in report.covered_types
    assert "grass" in report.covered_types


def test_weakness_counts_multiple_weak_pokemon():
    svc = AnalyticsService()
    # 3 fire types all weak to water
    team = [
        make_pokemon("A", ["fire"]),
        make_pokemon("B", ["fire"]),
        make_pokemon("C", ["fire"]),
    ]
    report = svc.analyze_pokemon_list(team)
    assert report.weak_to.get("water", 0) == 3


def test_no_weakness_with_diverse_team():
    svc = AnalyticsService()
    team = [
        make_pokemon("Steel", ["steel"]),
        make_pokemon("Dragon", ["dragon"]),
        make_pokemon("Water", ["water"]),
        make_pokemon("Ground", ["ground"]),
        make_pokemon("Dark", ["dark"]),
        make_pokemon("Electric", ["electric"]),
    ]
    report = svc.analyze_pokemon_list(team)
    # No type should hit 6 (no full sweep)
    max_weak = max(report.weak_to.values()) if report.weak_to else 0
    assert max_weak < 5


# ── Archetype Detection ───────────────────────────────────────

def test_trick_room_archetype():
    svc = AnalyticsService()
    team = [make_pokemon(f"Slow{i}", ["psychic"], spe=20) for i in range(6)]
    report = svc.analyze_pokemon_list(team)
    assert report.archetype == "Trick Room"


def test_rain_archetype():
    svc = AnalyticsService()
    team = [make_pokemon(f"Water{i}", ["water"]) for i in range(3)]
    team += [make_pokemon("Other", ["normal"])]
    report = svc.analyze_pokemon_list(team)
    assert "Rain" in report.archetype or "Water" in report.archetype


def test_hyper_offense_archetype():
    svc = AnalyticsService()
    team = [make_pokemon(f"Sweeper{i}", ["dragon"], atk=130, spa=130, spe=120) for i in range(4)]
    report = svc.analyze_pokemon_list(team)
    assert "Hyper Offense" in report.archetype or report.threat_score > 80


# ── Speed Tiers ───────────────────────────────────────────────

def test_speed_tiers_sorted_descending():
    svc = AnalyticsService()
    team = [
        make_pokemon("Fast", ["normal"], spe=130),
        make_pokemon("Medium", ["normal"], spe=90),
        make_pokemon("Slow", ["normal"], spe=40),
    ]
    report = svc.analyze_pokemon_list(team)
    speeds = [int(line.split(":")[1].split()[0]) for line in report.speed_tiers[:3]]
    assert speeds == sorted(speeds, reverse=True)


# ── Threat Score ──────────────────────────────────────────────

def test_high_bst_gives_high_threat_score():
    svc = AnalyticsService()
    team = [make_pokemon(f"Legend{i}", ["dragon"], atk=150, spa=150, spe=130, hp=100, def_=120, spd=120) for i in range(4)]
    report = svc.analyze_pokemon_list(team)
    assert report.threat_score > 80


def test_empty_team_returns_zero_threat():
    svc = AnalyticsService()
    report = svc.analyze_pokemon_list([])
    assert report.threat_score == 0


# ── Missing archetype branches ────────────────────────────────

def test_fire_core_archetype():
    svc = AnalyticsService()
    team = [make_pokemon(f"Fire{i}", ["fire"], spe=80) for i in range(3)]
    report = svc.analyze_pokemon_list(team)
    assert "Sun" in report.archetype or "Fire" in report.archetype


def test_vgc_restricted_archetype():
    svc = AnalyticsService()
    team = [
        make_pokemon(f"Legend{i}", ["dragon"], spe=80, is_legendary=True)
        for i in range(3)
    ]
    report = svc.analyze_pokemon_list(team)
    assert report.archetype == "VGC Restricted"


def test_stall_archetype():
    svc = AnalyticsService()
    # avg BST < 450 triggers Stall; use spe=60 to avoid Trick Room (avg_speed < 50)
    team = [make_pokemon(f"Weak{i}", ["normal"], atk=30, spa=30, spe=60, def_=50, spd=50, hp=50) for i in range(4)]
    report = svc.analyze_pokemon_list(team)
    assert "Stall" in report.archetype or "Bulky" in report.archetype


def test_balance_archetype():
    svc = AnalyticsService()
    # avg BST between 450 and 530, no other condition triggered, speed > 50
    team = [make_pokemon(f"Bal{i}", ["normal"], atk=80, spa=70, spe=70, def_=80, spd=80, hp=85) for i in range(4)]
    report = svc.analyze_pokemon_list(team)
    assert report.archetype == "Balance"


# ── Mixed role distribution ────────────────────────────────────

def test_wall_role_assigned():
    """Pokemon with def_ > 90 or spd > 90 (but not attacker) gets Wall role."""
    svc = AnalyticsService()
    team = [make_pokemon("Blissey", ["normal"], atk=30, spa=30, def_=50, spd=135)]
    report = svc.analyze_pokemon_list(team)
    assert report.role_distribution.get("Wall", 0) >= 1


def test_mixed_role_assigned():
    svc = AnalyticsService()
    # Stats that don't trigger Attacker (>100) or Wall (>90 def/spd)
    team = [make_pokemon("Mixed", ["normal"], atk=70, spa=70, def_=70, spd=70)]
    report = svc.analyze_pokemon_list(team)
    assert report.role_distribution.get("Mixed", 0) >= 1


# ── analyze_team (calls TeamService) ──────────────────────────

async def test_analyze_team_with_roster():
    svc = AnalyticsService()
    garchomp = make_pokemon("Garchomp", ["dragon", "ground"])
    mock_roster = MagicMock()
    mock_roster.pokemon = [garchomp]

    svc.team_service.get_team = AsyncMock(return_value=mock_roster)
    report = await svc.analyze_team("guild1", "p1")
    assert report.threat_score >= 0


async def test_analyze_team_no_roster():
    svc = AnalyticsService()
    svc.team_service.get_team = AsyncMock(return_value=None)
    report = await svc.analyze_team("guild1", "p1")
    assert report.archetype == "Unknown"
