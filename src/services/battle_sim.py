"""
Battle Simulation Service — Damage calc, team comparison, Showdown replay parsing.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp

from src.data.models import Pokemon
from src.data.sheets import sheets
from src.services.analytics_service import AnalyticsService, get_type_effectiveness
from src.services.team_service import TeamService

log = logging.getLogger(__name__)


@dataclass
class TeamCompareResult:
    advantage_summary: str
    p1_threats: str
    p2_threats: str
    type_summary: str
    p1_score: float
    p2_score: float


@dataclass
class ReplayParseResult:
    success: bool
    winner_name: str = ""
    p1_team: list[str] = None
    p2_team: list[str] = None
    turns: int = 0
    p1_name: str = ""
    p2_name: str = ""
    error: str = ""

    def __post_init__(self):
        if self.p1_team is None:
            self.p1_team = []
        if self.p2_team is None:
            self.p2_team = []


class BattleSimService:
    def __init__(self) -> None:
        self.analytics = AnalyticsService()

    # ── Team Comparison ───────────────────────────────────────
    async def compare_teams(
        self,
        guild_id: str,
        player1_id: str,
        player2_id: str,
    ) -> TeamCompareResult:
        ts = TeamService()
        r1 = await ts.get_team(guild_id, player1_id)
        r2 = await ts.get_team(guild_id, player2_id)

        if not r1 or not r2:
            return TeamCompareResult(
                advantage_summary="Could not load one or both teams.",
                p1_threats="N/A", p2_threats="N/A",
                type_summary="N/A", p1_score=0, p2_score=0,
            )

        # Find which of p1's pokemon threaten p2's team
        p1_threats = self._find_threats(r1.pokemon, r2.pokemon)
        p2_threats = self._find_threats(r2.pokemon, r1.pokemon)

        p1_score = self._team_matchup_score(r1.pokemon, r2.pokemon)
        p2_score = self._team_matchup_score(r2.pokemon, r1.pokemon)

        if p1_score > p2_score + 5:
            advantage = f"Player 1 has the advantage ({p1_score:.0f} vs {p2_score:.0f})"
        elif p2_score > p1_score + 5:
            advantage = f"Player 2 has the advantage ({p2_score:.0f} vs {p1_score:.0f})"
        else:
            advantage = f"Roughly even matchup ({p1_score:.0f} vs {p2_score:.0f})"

        type_adv = self._type_advantage_summary(r1.pokemon, r2.pokemon)

        return TeamCompareResult(
            advantage_summary=advantage,
            p1_threats=", ".join(p1_threats[:5]) or "None identified",
            p2_threats=", ".join(p2_threats[:5]) or "None identified",
            type_summary=type_adv,
            p1_score=p1_score,
            p2_score=p2_score,
        )

    def _find_threats(self, attackers: list[Pokemon], defenders: list[Pokemon]) -> list[str]:
        """Find attackers that have a type advantage over 2+ defenders."""
        threats = []
        for atk in attackers:
            targets = 0
            for dfn in defenders:
                for atk_type in atk.types:
                    if get_type_effectiveness(atk_type, dfn.types) >= 2.0:
                        targets += 1
                        break
            if targets >= 2:
                threats.append(f"{atk.name} ({atk.type_string})")
        return threats

    def _team_matchup_score(self, team_a: list[Pokemon], team_b: list[Pokemon]) -> float:
        """Heuristic score for team_a vs team_b (higher = better for team_a)."""
        score = 0.0
        for a in team_a:
            for b in team_b:
                for a_type in a.types:
                    eff = get_type_effectiveness(a_type, b.types)
                    score += eff
                # Speed advantage adds small bonus
                if a.base_stats.spe > b.base_stats.spe:
                    score += 0.5
        return score

    def _type_advantage_summary(self, p1: list[Pokemon], p2: list[Pokemon]) -> str:
        p1_types = set(t for m in p1 for t in m.types)
        p2_types = set(t for m in p2 for t in m.types)
        p1_wins = [t for t in p1_types if any(get_type_effectiveness(t, list(p2_types)) > 1 for _ in [1])]
        return f"P1 type advantages: {', '.join(p1_wins[:4]) or 'Few'}"

    # ── Showdown Replay Parser ────────────────────────────────
    async def parse_replay(
        self,
        guild_id: str,
        player_id: str,
        replay_url: str,
    ) -> ReplayParseResult:
        """
        Fetch and parse a Pokemon Showdown replay.
        Replay JSON is at <url>.json — e.g. replay.pokemonshowdown.com/gen9ou-1234.json
        """
        json_url = replay_url.rstrip("/") + ".json"
        if not json_url.startswith("https"):
            json_url = "https://" + json_url.lstrip("/")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(json_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return ReplayParseResult(
                            success=False,
                            error=f"Could not fetch replay (HTTP {resp.status}). Check the URL."
                        )
                    data = await resp.json(content_type=None)
        except aiohttp.ClientError as e:
            return ReplayParseResult(success=False, error=f"Network error: {e}")

        try:
            result = self._parse_replay_data(data)
        except Exception as e:
            log.error(f"Replay parse error: {e}", exc_info=True)
            return ReplayParseResult(success=False, error=f"Parse error: {e}")

        # Save to Google Sheets
        sheets.save_replay({
            "replay_id": str(uuid.uuid4())[:8],
            "match_id": "",  # Will be linked if match exists
            "url": replay_url,
            "winner": result.winner_name,
            "p1_team": result.p1_team,
            "p2_team": result.p2_team,
            "turns": result.turns,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return result

    def _parse_replay_data(self, data: dict) -> ReplayParseResult:
        """
        Parse Showdown replay JSON.
        The 'log' field contains the battle log with player names, teams, and result.
        Format: https://github.com/smogon/pokemon-showdown/blob/master/sim/dex-data.ts
        """
        log_text: str = data.get("log", "")
        lines = log_text.split("\n")

        p1_name = data.get("p1", "Player 1")
        p2_name = data.get("p2", "Player 2")
        p1_team: list[str] = []
        p2_team: list[str] = []
        winner_name = ""
        turns = 0

        for line in lines:
            # Track Pokemon used: |poke|p1|Garchomp, L50
            if line.startswith("|poke|p1|"):
                parts = line.split("|")
                if len(parts) > 3:
                    mon = parts[3].split(",")[0].strip()
                    if mon and mon not in p1_team:
                        p1_team.append(mon)
            elif line.startswith("|poke|p2|"):
                parts = line.split("|")
                if len(parts) > 3:
                    mon = parts[3].split(",")[0].strip()
                    if mon and mon not in p2_team:
                        p2_team.append(mon)
            # Track turns
            elif line.startswith("|turn|"):
                try:
                    turns = int(line.split("|")[2])
                except (IndexError, ValueError):
                    pass
            # Track winner: |win|PlayerName
            elif line.startswith("|win|"):
                parts = line.split("|")
                if len(parts) > 2:
                    winner_name = parts[2].strip()

        return ReplayParseResult(
            success=True,
            winner_name=winner_name or "Unknown",
            p1_name=p1_name,
            p2_name=p2_name,
            p1_team=p1_team,
            p2_team=p2_team,
            turns=turns,
        )
