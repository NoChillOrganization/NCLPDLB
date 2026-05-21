"""
RotatingTeambuilder — cycles through a pool of teams during RL training.

Each call to yield_team() returns the next team in the pool (round-robin),
giving the agent varied opponents across training episodes.

Usage
─────
  from src.ml.teambuilder import RotatingTeambuilder
  from src.ml.teams import FORMAT_TEAMS

  tb = RotatingTeambuilder(FORMAT_TEAMS["gen9ou"])
  env = BattleEnv(battle_format="gen9ou", team=tb, ...)
"""
from __future__ import annotations

from poke_env.teambuilder.teambuilder import Teambuilder


class RotatingTeambuilder(Teambuilder):
    """
    Cycles through a list of Showdown export-format team strings.

    Converts each string to poke-env packed format on first use and caches them.
    Teams rotate round-robin so every episode uses a different team composition.
    """

    def __init__(self, teams: list[str]) -> None:
        if not teams:
            raise ValueError("RotatingTeambuilder requires at least one team string.")
        self._packed: list[str] = [
            self.join_team(self.parse_showdown_team(t)) for t in teams
        ]
        self._idx: int = 0

    def yield_team(self) -> str:
        team = self._packed[self._idx % len(self._packed)]
        self._idx += 1
        return team

    def __len__(self) -> int:
        return len(self._packed)
