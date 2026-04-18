"""Tests for src.ml.training_players — MaxBasePowerPlayer and SimpleHeuristicPlayer."""
import pytest
from unittest.mock import MagicMock, patch

import src.ml.training_players as _tp_mod
from src.ml.training_players import MaxBasePowerPlayer, SimpleHeuristicPlayer


# ── NCLP-007: stub raises ImportError on instantiation ───────────────────────

def test_stub_player_raises_on_instantiation_when_poke_env_missing(monkeypatch):
    """If poke_env is absent the module-level Player stub must raise immediately."""
    monkeypatch.setattr(_tp_mod, "_POKE_ENV_OK", False)

    # Import the stub class directly (the module already has it defined)
    original_poke_env_ok = _tp_mod._POKE_ENV_OK
    # When poke_env is truly not installed the Player in the module IS the stub.
    # We simulate that by temporarily replacing the class with the stub definition.
    import importlib, sys
    # Force reimport with poke_env hidden
    with patch.dict(sys.modules, {"poke_env": None, "poke_env.player": None}):
        # Remove cached module so reimport triggers the ImportError path
        sys.modules.pop("src.ml.training_players", None)
        import src.ml.training_players as fresh_mod
        if not fresh_mod._POKE_ENV_OK:
            with pytest.raises(ImportError, match="pip install poke-env"):
                fresh_mod.Player()
        # Restore
        sys.modules.pop("src.ml.training_players", None)


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
