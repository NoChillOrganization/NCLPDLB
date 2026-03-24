"""Tests for src.ml.training_players — MaxBasePowerPlayer and SimpleHeuristicPlayer."""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.ml.training_players import MaxBasePowerPlayer, SimpleHeuristicPlayer


def _make_player(cls):
    """Instantiate a player class without poke_env's Player.__init__ setup."""
    with patch.object(cls.__bases__[0], '__init__', return_value=None):
        obj = cls.__new__(cls)
        return obj


def _move(base_power: int, name: str = "move") -> MagicMock:
    m = MagicMock()
    m.base_power = base_power
    m.id = name
    return m


# ── MaxBasePowerPlayer ────────────────────────────────────────────────────────

class TestMaxBasePowerPlayer:
    def test_selects_highest_base_power(self):
        player = _make_player(MaxBasePowerPlayer)
        player.create_order = MagicMock(return_value="order")

        battle = MagicMock()
        low = _move(50, "tackle")
        high = _move(120, "earthquake")
        battle.available_moves = [low, high]

        result = player.choose_move(battle)

        player.create_order.assert_called_once_with(high)
        assert result == "order"

    def test_tie_picks_from_best_moves(self):
        player = _make_player(MaxBasePowerPlayer)
        player.create_order = MagicMock(return_value="order")

        m1 = _move(90, "surf")
        m2 = _move(90, "hydro_pump")
        battle = MagicMock()
        battle.available_moves = [m1, m2]

        player.choose_move(battle)

        # Should pick one of the two tied moves
        called_with = player.create_order.call_args[0][0]
        assert called_with in (m1, m2)

    def test_fallback_to_random_when_no_moves(self):
        player = _make_player(MaxBasePowerPlayer)
        player.choose_random_move = MagicMock(return_value="random_order")

        battle = MagicMock()
        battle.available_moves = []

        result = player.choose_move(battle)

        player.choose_random_move.assert_called_once_with(battle)
        assert result == "random_order"


# ── SimpleHeuristicPlayer ─────────────────────────────────────────────────────

class TestSimpleHeuristicPlayer:
    def test_selects_highest_scored_move(self):
        player = _make_player(SimpleHeuristicPlayer)
        player.create_order = MagicMock(return_value="order")

        battle = MagicMock()
        m_weak = MagicMock(base_power=80)
        m_effective = MagicMock(base_power=80)

        opp = MagicMock()
        opp.damage_multiplier.side_effect = lambda m: 1.0 if m is m_weak else 2.0
        battle.opponent_active_pokemon = opp
        battle.available_moves = [m_weak, m_effective]

        result = player.choose_move(battle)

        player.create_order.assert_called_once_with(m_effective)
        assert result == "order"

    def test_fallback_to_random_when_no_moves(self):
        player = _make_player(SimpleHeuristicPlayer)
        player.choose_random_move = MagicMock(return_value="random_order")

        battle = MagicMock()
        battle.available_moves = []

        result = player.choose_move(battle)

        player.choose_random_move.assert_called_once_with(battle)
        assert result == "random_order"
