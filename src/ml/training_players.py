"""
Implementation of simple rule-based players for curriculum training.

Stub pattern
------------
When ``poke_env`` is not installed, a minimal ``Player`` stub is defined so
that this module can be *imported* in environments without poke-env (e.g. CI
without the ML extras).  The stub defers the ``ImportError`` to instantiation
time so that import-level checks (``hasattr``, ``isinstance``) still work,
but any attempt to actually create a player fails loudly with a clear install
instruction.
"""
from __future__ import annotations

import logging
from typing import Any

import random
try:
    from poke_env.player import Player
    _POKE_ENV_OK = True
except ImportError:  # pragma: no cover
    _POKE_ENV_OK = False

    class Player:  # type: ignore
        """Stub — raises ImportError on instantiation if poke_env is missing."""
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise ImportError(
                "poke_env is not installed. Run: pip install poke-env>=0.8.1"
            )

        def choose_random_move(self, battle: object) -> object:
            raise ImportError("poke_env is not installed")

        def create_order(self, move: object) -> object:
            raise ImportError("poke_env is not installed")

log = logging.getLogger(__name__)

class MaxBasePowerPlayer(Player):
    """
    Curriculum opponent that selects the move with the highest base power.
    If multiple moves have the same base power, it picks one randomly among them.
    If no moves are available, it defaults to a random move or switch.
    """

    def choose_move(self, battle: Any) -> Any:
        # 1. Prioritize moves with highest base power
        if battle.available_moves:
            # Calculate max base power
            max_power = max(m.base_power for m in battle.available_moves)
            
            # Get all moves with that power (to break ties randomly)
            best_moves = [m for m in battle.available_moves if m.base_power == max_power]
            
            # Select one at random from the best
            chosen_move = random.choice(best_moves)
            return self.create_order(chosen_move)

        # 2. Fallback to random (switches, etc.)
        return self.choose_random_move(battle)

class SimpleHeuristicPlayer(Player):
    """
    Intermediate curriculum opponent that uses type effectiveness and base power.
    """
    def choose_move(self, battle: Any) -> Any:
        if battle.available_moves:
            # Score moves: base_power * type_effectiveness
            scores = []
            for move in battle.available_moves:
                effectiveness = battle.opponent_active_pokemon.damage_multiplier(move)
                score = move.base_power * effectiveness
                scores.append((move, score))
            
            # Pick move with highest score
            best_move = max(scores, key=lambda x: x[1])[0]
            return self.create_order(best_move)
            
        return self.choose_random_move(battle)
