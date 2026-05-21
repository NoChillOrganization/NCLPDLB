"""
Analytics Service — Team coverage, weaknesses, speed tiers, archetypes.
Based on Smogon OU + VGC competitive data.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.data.models import Pokemon
from src.services.team_service import TeamService

log = logging.getLogger(__name__)

# Gen 1-9 type effectiveness chart
# effectiveness[attacking_type][defending_type] -> multiplier
TYPE_CHART: dict[str, dict[str, float]] = {
    "normal":   {"rock": 0.5, "ghost": 0, "steel": 0.5},
    "fire":     {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 2, "bug": 2, "rock": 0.5, "dragon": 0.5, "steel": 2},
    "water":    {"fire": 2, "water": 0.5, "grass": 0.5, "ground": 2, "rock": 2, "dragon": 0.5},
    "electric": {"water": 2, "electric": 0.5, "grass": 0.5, "ground": 0, "flying": 2, "dragon": 0.5},
    "grass":    {"fire": 0.5, "water": 2, "grass": 0.5, "poison": 0.5, "ground": 2, "flying": 0.5, "bug": 0.5, "rock": 2, "dragon": 0.5, "steel": 0.5},
    "ice":      {"water": 0.5, "grass": 2, "ice": 0.5, "ground": 2, "flying": 2, "dragon": 2, "steel": 0.5},
    "fighting": {"normal": 2, "ice": 2, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5, "rock": 2, "ghost": 0, "dark": 2, "steel": 2, "fairy": 0.5},
    "poison":   {"grass": 2, "poison": 0.5, "ground": 0.5, "rock": 0.5, "ghost": 0.5, "steel": 0, "fairy": 2},
    "ground":   {"fire": 2, "electric": 2, "grass": 0.5, "poison": 2, "flying": 0, "bug": 0.5, "rock": 2, "steel": 2},
    "flying":   {"electric": 0.5, "grass": 2, "fighting": 2, "bug": 2, "rock": 0.5, "steel": 0.5},
    "psychic":  {"fighting": 2, "poison": 2, "psychic": 0.5, "dark": 0, "steel": 0.5},
    "bug":      {"fire": 0.5, "grass": 2, "fighting": 0.5, "flying": 0.5, "psychic": 2, "ghost": 0.5, "dark": 2, "steel": 0.5, "fairy": 0.5},
    "rock":     {"fire": 2, "ice": 2, "fighting": 0.5, "ground": 0.5, "flying": 2, "bug": 2, "steel": 0.5},
    "ghost":    {"normal": 0, "psychic": 2, "ghost": 2, "dark": 0.5},
    "dragon":   {"dragon": 2, "steel": 0.5, "fairy": 0},
    "dark":     {"fighting": 0.5, "psychic": 2, "ghost": 2, "dark": 0.5, "fairy": 0.5},
    "steel":    {"fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2, "rock": 2, "steel": 0.5, "fairy": 2},
    "fairy":    {"fire": 0.5, "fighting": 2, "poison": 0.5, "dragon": 2, "dark": 2, "steel": 0.5},
}

ALL_TYPES = list(TYPE_CHART.keys())

# Common team archetypes based on type/role composition
ARCHETYPES = {
    "Hyper Offense": {"criteria": "3+ sweepers, avg_bst > 530, low bulk"},
    "Stall":         {"criteria": "3+ walls, high bulk, recovery moves"},
    "Balance":       {"criteria": "mixed offense/defense"},
    "Rain":          {"criteria": "water type + swift swim or drizzle"},
    "Sun":           {"criteria": "fire type + chlorophyll or drought"},
    "Sand":          {"criteria": "rock/ground/steel + sand rush"},
    "Trick Room":    {"criteria": "low speed + slow pokemon"},
    "VGC Restricted":{"criteria": "legendary + restricted combo"},
}


@dataclass
class TeamAnalysisReport:
    coverage_summary: str
    weakness_summary: str
    speed_summary: str
    archetype: str
    threat_score: int
    covered_types: list[str]
    weak_to: dict[str, int]   # type -> number of pokemon weak to it
    resists: dict[str, int]   # type -> number of pokemon resisting it
    speed_tiers: list[str]
    role_distribution: dict[str, int]


def get_type_effectiveness(atk_type: str, def_types: list[str]) -> float:
    """Calculate combined type effectiveness for an attack."""
    mult = 1.0
    chart = TYPE_CHART.get(atk_type.lower(), {})
    for def_type in def_types:
        mult *= chart.get(def_type.lower(), 1.0)
    return mult


class AnalyticsService:
    def __init__(self) -> None:
        self.team_service = TeamService()

    async def analyze_team(self, guild_id: str, player_id: str) -> TeamAnalysisReport:
        roster = await self.team_service.get_team(guild_id, player_id)
        if not roster or not roster.pokemon:
            return TeamAnalysisReport(
                coverage_summary="No team found.",
                weakness_summary="N/A",
                speed_summary="N/A",
                archetype="Unknown",
                threat_score=0,
                covered_types=[],
                weak_to={},
                resists={},
                speed_tiers=[],
                role_distribution={},
            )
        return self._compute_analysis(roster.pokemon)

    def analyze_pokemon_list(self, pokemon_list: list[Pokemon]) -> TeamAnalysisReport:
        return self._compute_analysis(pokemon_list)

    def _compute_analysis(self, team: list[Pokemon]) -> TeamAnalysisReport:
        weak_to: dict[str, int] = {t: 0 for t in ALL_TYPES}
        resists: dict[str, int] = {t: 0 for t in ALL_TYPES}
        covered_types: set[str] = set()

        for mon in team:
            # Offensive coverage
            for t in mon.types:
                covered_types.add(t.lower())

            # Defensive profile
            for atk_type in ALL_TYPES:
                eff = get_type_effectiveness(atk_type, mon.types)
                if eff > 1.0:
                    weak_to[atk_type] += 1
                elif eff < 1.0:
                    resists[atk_type] += 1

        # Coverage summary
        uncovered = [t.title() for t in ALL_TYPES if t not in covered_types]
        coverage_txt = (
            f"Covers: {', '.join(t.title() for t in sorted(covered_types))}\n"
            f"Missing: {', '.join(uncovered) or 'None'}"
        )

        # Weakness summary (types where 2+ Pokemon are weak)
        serious_weaknesses = {t: n for t, n in weak_to.items() if n >= 2}
        weakness_txt = (
            ", ".join(f"{t.title()} ×{n}" for t, n in sorted(serious_weaknesses.items(), key=lambda x: -x[1]))
            or "No major weaknesses!"
        )

        # Speed tiers
        speed_lines = [f"{mon.name}: {mon.base_stats.spe} ({mon.speed_tier})" for mon in sorted(team, key=lambda m: -m.base_stats.spe)]

        # Archetype detection
        archetype = self._detect_archetype(team)

        # Threat score (BST-based heuristic)
        avg_bst = sum(m.base_stats.total for m in team) / max(len(team), 1)
        threat_score = min(100, int(avg_bst / 6))

        # Role distribution
        roles: dict[str, int] = {"Attacker": 0, "Wall": 0, "Support": 0, "Mixed": 0}
        for mon in team:
            if mon.base_stats.atk > 100 or mon.base_stats.spa > 100:
                roles["Attacker"] += 1
            elif mon.base_stats.def_ > 90 or mon.base_stats.spd > 90:
                roles["Wall"] += 1
            else:
                roles["Mixed"] += 1

        return TeamAnalysisReport(
            coverage_summary=coverage_txt,
            weakness_summary=weakness_txt,
            speed_summary="\n".join(speed_lines[:6]),
            archetype=archetype,
            threat_score=threat_score,
            covered_types=sorted(covered_types),
            weak_to={k: v for k, v in weak_to.items() if v > 0},
            resists={k: v for k, v in resists.items() if v > 0},
            speed_tiers=speed_lines,
            role_distribution=roles,
        )

    def _detect_archetype(self, team: list[Pokemon]) -> str:
        speeds = [m.base_stats.spe for m in team]
        avg_speed = sum(speeds) / max(len(team), 1)
        water_count = sum(1 for m in team if "water" in m.types)
        fire_count = sum(1 for m in team if "fire" in m.types)
        legendary_count = sum(1 for m in team if m.is_legendary or m.is_mythical)

        if avg_speed < 50:
            return "Trick Room"
        if water_count >= 2:
            return "Rain / Water Spam"
        if fire_count >= 2:
            return "Sun / Fire Core"
        if legendary_count >= 2:
            return "VGC Restricted"
        avg_bst = sum(m.base_stats.total for m in team) / max(len(team), 1)
        if avg_bst > 530:
            return "Hyper Offense"
        if avg_bst < 450:
            return "Stall / Bulky"
        return "Balance"
