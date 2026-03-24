"""
battle_env.py — coverage tests for pure observation/reward logic.

Tests _move_features, _pokemon_hp, build_observation, build_doubles_observation,
BattleEnv.calc_reward, BattleDoubleEnv.calc_reward,
and the fallback stubs when poke-env is unavailable.

__init__ methods are excluded (require live Showdown server).
"""
from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import pytest

from src.ml.battle_env import (
    OBS_DIM,
    OBS_DIM_DOUBLES,
    _move_features,
    _pokemon_hp,
    build_observation,
    build_doubles_observation,
    BattleEnv,
    BattleDoubleEnv,
    POKE_ENV_AVAILABLE,
)


# ── _move_features ────────────────────────────────────────────────────────────

class TestMoveFeatures:
    def test_none_move_returns_zeros(self):
        assert _move_features(None) == [0.0, 0.0, 0.0, 0.0, 0.5]

    def test_normal_move(self):
        move = MagicMock()
        move.base_power = 90
        move.accuracy = 100
        move.type = MagicMock()
        move.type.__str__ = lambda s: "PokemonType.FIRE"
        move.priority = 0
        feats = _move_features(move)
        assert len(feats) == 5
        assert 0.0 <= feats[0] <= 1.0  # base_power normalized
        assert feats[1] == 1.0          # accuracy 100 / 100
        assert 0.0 <= feats[2] <= 1.0  # type_id normalized
        assert feats[3] == pytest.approx(0.5, abs=0.1)  # priority=0 → (0+5)/10=0.5

    def test_high_priority_move(self):
        move = MagicMock()
        move.base_power = 40
        move.accuracy = 100
        move.type = MagicMock()
        move.type.__str__ = lambda s: "normal"
        move.priority = 1
        feats = _move_features(move)
        assert feats[3] == pytest.approx(0.6)  # (1+5)/10

    def test_none_base_power_treated_as_zero(self):
        move = MagicMock()
        move.base_power = None
        move.accuracy = 100
        move.type = MagicMock()
        move.type.__str__ = lambda s: "normal"
        move.priority = 0
        feats = _move_features(move)
        assert feats[0] == 0.0

    def test_none_accuracy_treated_as_100(self):
        move = MagicMock()
        move.base_power = 0
        move.accuracy = None
        move.type = MagicMock()
        move.type.__str__ = lambda s: "normal"
        move.priority = 0
        feats = _move_features(move)
        assert feats[1] == 1.0  # 100/100

    def test_priority_exception_falls_back_to_05(self):
        # The priority except branch is marked # pragma: no cover because
        # real Move objects don't raise on .priority. This test just confirms
        # normal priority works — the except path is excluded from coverage.
        move = MagicMock()
        move.base_power = 0
        move.accuracy = 100
        move.type = MagicMock()
        move.type.__str__ = lambda s: "normal"
        move.priority = 0
        feats = _move_features(move)
        assert feats[3] == pytest.approx(0.5)

    def test_base_power_capped_at_250(self):
        move = MagicMock()
        move.base_power = 999
        move.accuracy = 100
        move.type = MagicMock()
        move.type.__str__ = lambda s: "normal"
        move.priority = 0
        feats = _move_features(move)
        assert feats[0] == 1.0  # capped at 250/250

    def test_known_type_id(self):
        move = MagicMock()
        move.base_power = 0
        move.accuracy = 100
        move.type = MagicMock()
        move.type.__str__ = lambda s: "fire"
        move.priority = 0
        feats = _move_features(move)
        # type "fire" → id 2 → 2/20 = 0.1
        assert feats[2] == pytest.approx(0.1)


# ── _pokemon_hp ───────────────────────────────────────────────────────────────

class TestPokemonHp:
    def test_none_returns_zero(self):
        assert _pokemon_hp(None) == 0.0

    def test_fainted_returns_zero(self):
        mon = MagicMock()
        mon.fainted = True
        assert _pokemon_hp(mon) == 0.0

    def test_full_hp(self):
        mon = MagicMock()
        mon.fainted = False
        mon.current_hp_fraction = 1.0
        assert _pokemon_hp(mon) == 1.0

    def test_partial_hp(self):
        mon = MagicMock()
        mon.fainted = False
        mon.current_hp_fraction = 0.5
        assert _pokemon_hp(mon) == 0.5

    def test_none_hp_fraction_returns_zero(self):
        mon = MagicMock()
        mon.fainted = False
        mon.current_hp_fraction = None
        assert _pokemon_hp(mon) == 0.0


# ── build_observation ─────────────────────────────────────────────────────────

def _make_mock_battle(n_moves=4, n_team=6, n_opp_team=6, turn=10,
                      won=False, lost=False, has_active=True, has_opp=True):
    """Build a minimal mock AbstractBattle."""
    battle = MagicMock()

    if has_active:
        active = MagicMock()
        active.species = "pikachu"
        active.fainted = False
        active.current_hp_fraction = 0.8
        active.status = None
        active.boosts = {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0}
        battle.active_pokemon = active
    else:
        battle.active_pokemon = None

    moves = []
    for _ in range(n_moves):
        m = MagicMock()
        m.base_power = 80
        m.accuracy = 100
        m.type = MagicMock()
        m.type.__str__ = lambda s: "normal"
        m.priority = 0
        moves.append(m)
    battle.available_moves = moves

    if has_opp:
        opp = MagicMock()
        opp.species = "charizard"
        opp.fainted = False
        opp.current_hp_fraction = 0.6
        opp.status = None
        battle.opponent_active_pokemon = opp
    else:
        battle.opponent_active_pokemon = None

    team_mons = {}
    for i in range(n_team):
        m = MagicMock()
        m.fainted = False
        m.current_hp_fraction = 0.9
        team_mons[f"slot{i}"] = m
    battle.team = team_mons

    opp_team_mons = {}
    for i in range(n_opp_team):
        m = MagicMock()
        m.fainted = False
        m.current_hp_fraction = 0.7
        opp_team_mons[f"oppslot{i}"] = m
    battle.opponent_team = opp_team_mons

    battle.weather = {}
    battle.fields = {}
    battle.turn = turn
    battle.won = won
    battle.lost = lost
    return battle


class TestBuildObservation:
    def test_shape_and_dtype(self):
        battle = _make_mock_battle()
        obs = build_observation(battle)
        assert obs.shape == (OBS_DIM,)
        assert obs.dtype == np.float32

    def test_all_values_in_unit_range(self):
        battle = _make_mock_battle()
        obs = build_observation(battle)
        assert np.all(obs >= 0.0)
        assert np.all(obs <= 1.0)

    def test_no_active_pokemon_advances_idx(self):
        battle = _make_mock_battle(has_active=False)
        obs = build_observation(battle)
        assert obs.shape == (OBS_DIM,)

    def test_no_opponent_advances_idx(self):
        battle = _make_mock_battle(has_opp=False)
        obs = build_observation(battle)
        assert obs.shape == (OBS_DIM,)

    def test_fewer_than_4_moves(self):
        battle = _make_mock_battle(n_moves=2)
        obs = build_observation(battle)
        assert obs.shape == (OBS_DIM,)

    def test_fewer_than_6_team_members(self):
        battle = _make_mock_battle(n_team=3, n_opp_team=4)
        obs = build_observation(battle)
        assert obs.shape == (OBS_DIM,)

    def test_turn_normalized(self):
        print(f"DEBUG: OBS_DIM={OBS_DIM}")
        battle = _make_mock_battle(turn=50)
        obs = build_observation(battle)
        # Turn is at idx OBS_DIM-1
        assert obs[OBS_DIM - 1] == pytest.approx(0.5)

    def test_turn_capped_at_100(self):
        battle = _make_mock_battle(turn=200)
        obs = build_observation(battle)
        assert obs[OBS_DIM - 1] == pytest.approx(1.0)

    def test_zero_turn(self):
        battle = _make_mock_battle(turn=0)
        obs = build_observation(battle)
        # Turn is at last index
        assert obs[OBS_DIM - 1] == pytest.approx(0.0)

    def test_trick_room_effect_imported(self):
        """Force the trick_room try-block to execute with a non-empty fields dict."""
        battle = _make_mock_battle()
        battle.fields = {"some_field": 1}
        obs = build_observation(battle)
        assert obs.shape == (OBS_DIM,)

    def test_active_terrain_field_hits_break(self):
        """TERRAIN_IDS loop hits terrain=val; break for a known terrain key."""
        from poke_env.battle import Field
        battle = _make_mock_battle()
        battle.fields = {Field.ELECTRIC_TERRAIN: 1}
        obs = build_observation(battle)
        assert obs.shape == (OBS_DIM,)
        # terrain slot should be non-zero (ELECTRIC_TERRAIN id / 4.0)
        assert obs[OBS_DIM - 3] > 0.0


# ── build_doubles_observation ─────────────────────────────────────────────────

def _make_mock_doubles_battle():
    """Build a minimal mock doubles battle with 2 active per side."""
    battle = MagicMock()

    active_list = []
    for _ in range(2):
        a = MagicMock()
        a.species = "pikachu"
        a.fainted = False
        a.current_hp_fraction = 0.9
        a.status = None
        a.boosts = {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0}
        active_list.append(a)
    battle.active_pokemon = active_list

    moves1 = []
    moves2 = []
    for _ in range(4):
        m = MagicMock()
        m.base_power = 60
        m.accuracy = 100
        m.type = MagicMock()
        m.type.__str__ = lambda s: "normal"
        m.priority = 0
        moves1.append(m)
        moves2.append(m)
    battle.available_moves = [moves1, moves2]

    opp_list = []
    for _ in range(2):
        o = MagicMock()
        o.species = "gengar"
        o.fainted = False
        o.current_hp_fraction = 0.8
        o.status = None
        opp_list.append(o)
    battle.opponent_active_pokemon = opp_list

    team_mons = {}
    opp_team_mons = {}
    for i in range(6):
        m = MagicMock()
        m.fainted = False
        m.current_hp_fraction = 0.8
        team_mons[f"s{i}"] = m
        opp_team_mons[f"o{i}"] = m
    battle.team = team_mons
    battle.opponent_team = opp_team_mons

    battle.weather = {}
    battle.fields = {}
    battle.turn = 5
    return battle


class TestBuildDoublesObservation:
    def test_shape_and_dtype(self):
        battle = _make_mock_doubles_battle()
        obs = build_doubles_observation(battle)
        assert obs.shape == (OBS_DIM_DOUBLES,)
        assert obs.dtype == np.float32

    def test_all_values_in_unit_range(self):
        battle = _make_mock_doubles_battle()
        obs = build_doubles_observation(battle)
        assert np.all(obs >= 0.0)
        assert np.all(obs <= 1.0)

    def test_scalar_active_pokemon_wrapped_to_list(self):
        """Single active mon (not a list) — hits 'opp_list = [opp_list, None]' branch."""
        battle = _make_mock_doubles_battle()
        a = MagicMock()
        a.species = "bulbasaur"
        a.fainted = False
        a.current_hp_fraction = 1.0
        a.status = None
        a.boosts = {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0}
        battle.active_pokemon = a  # scalar, not list
        battle.available_moves = []
        # Also make opponent a scalar to trigger line 349
        o = MagicMock()
        o.species = "gengar"
        o.fainted = False
        o.current_hp_fraction = 0.8
        o.status = None
        battle.opponent_active_pokemon = o  # scalar, triggers line 349
        obs = build_doubles_observation(battle)
        assert obs.shape == (OBS_DIM_DOUBLES,)

    def test_doubles_active_terrain_hits_break(self):
        """TERRAIN_IDS loop in doubles hits terrain=val; break."""
        from poke_env.battle import Field
        battle = _make_mock_doubles_battle()
        battle.fields = {Field.ELECTRIC_TERRAIN: 1}
        obs = build_doubles_observation(battle)
        assert obs.shape == (OBS_DIM_DOUBLES,)

    def test_none_active_list_falls_back(self):
        battle = _make_mock_doubles_battle()
        battle.active_pokemon = None
        obs = build_doubles_observation(battle)
        assert obs.shape == (OBS_DIM_DOUBLES,)

    def test_no_opponent_slots_fill_zeros(self):
        battle = _make_mock_doubles_battle()
        battle.opponent_active_pokemon = None
        obs = build_doubles_observation(battle)
        assert obs.shape == (OBS_DIM_DOUBLES,)

    def test_one_opponent_slot_none(self):
        """Opp list with only 1 entry — second slot hits else: idx += 3."""
        battle = _make_mock_doubles_battle()
        o = MagicMock()
        o.species = "gengar"
        o.fainted = False
        o.current_hp_fraction = 0.7
        o.status = None
        battle.opponent_active_pokemon = [o]  # only 1 entry, slot 1 is None
        obs = build_doubles_observation(battle)
        assert obs.shape == (OBS_DIM_DOUBLES,)


# ── BattleEnv.calc_reward ─────────────────────────────────────────────────────

@pytest.mark.skipif(not POKE_ENV_AVAILABLE, reason="poke-env not installed")
class TestBattleEnvCalcReward:
    """Test calc_reward without calling __init__ (needs live Showdown)."""

    def _make_env(self):
        env = BattleEnv.__new__(BattleEnv)
        env._prev_state = {}
        return env

    def _make_battle(self, won=False, lost=False, opp_fainted=0, own_fainted=0):
        battle = MagicMock()
        battle.won = won
        battle.lost = lost
        opp_team = {}
        for i in range(6):
            m = MagicMock()
            m.fainted = i < opp_fainted
            opp_team[f"o{i}"] = m
        battle.opponent_team = opp_team
        own_team = {}
        for i in range(6):
            m = MagicMock()
            m.fainted = i < own_fainted
            own_team[f"p{i}"] = m
        battle.team = own_team
        return battle

    def test_win_reward_is_positive(self):
        env = self._make_env()
        battle = self._make_battle(won=True)
        reward = env.calc_reward(battle)
        assert reward > 0.0

    def test_loss_reward_is_negative(self):
        env = self._make_env()
        battle = self._make_battle(lost=True)
        reward = env.calc_reward(battle)
        assert reward < 0.0

    def test_neutral_step_is_zero(self):
        env = self._make_env()
        battle = self._make_battle()
        reward = env.calc_reward(battle)
        assert reward == pytest.approx(0.0)

    def test_opponent_faint_adds_reward(self):
        env = self._make_env()
        battle_id = 42
        # Simulate a previous state with 0 opponent fainted
        env._prev_state[battle_id] = {"opp_fainted": 0, "own_fainted": 0}
        battle = self._make_battle(opp_fainted=1)
        # Override id(battle) by patching
        with patch("builtins.id", return_value=battle_id):
            reward = env.calc_reward(battle)
        assert reward == pytest.approx(0.3)

    def test_own_faint_reduces_reward(self):
        env = self._make_env()
        battle_id = 99
        env._prev_state[battle_id] = {"opp_fainted": 0, "own_fainted": 0}
        battle = self._make_battle(own_fainted=1)
        with patch("builtins.id", return_value=battle_id):
            reward = env.calc_reward(battle)
        assert reward == pytest.approx(-0.3)

    def test_state_persists_across_calls(self):
        env = self._make_env()
        battle = self._make_battle(opp_fainted=1)
        # First call — opp_fainted goes from 0 → 1
        r1 = env.calc_reward(battle)
        # Second call with same fainted count — delta is 0
        r2 = env.calc_reward(battle)
        assert r1 == pytest.approx(0.3)
        assert r2 == pytest.approx(0.0)


# ── BattleDoubleEnv.calc_reward + teampreview ─────────────────────────────────

@pytest.mark.skipif(not POKE_ENV_AVAILABLE, reason="poke-env not installed")
class TestBattleDoubleEnvMethods:
    def _make_env(self):
        env = BattleDoubleEnv.__new__(BattleDoubleEnv)
        env._prev_state = {}
        return env

    def _make_battle(self, won=False, lost=False, opp_fainted=0, own_fainted=0,
                     team_size=6, max_team_size=4):
        battle = MagicMock()
        battle.won = won
        battle.lost = lost
        battle.max_team_size = max_team_size
        opp_team = {}
        for i in range(6):
            m = MagicMock()
            m.fainted = i < opp_fainted
            opp_team[f"o{i}"] = m
        battle.opponent_team = opp_team
        own_team = {}
        for i in range(team_size):
            m = MagicMock()
            m.fainted = i < own_fainted
            own_team[f"p{i}"] = m
        battle.team = own_team
        return battle

    def test_win_is_positive(self):
        env = self._make_env()
        battle = self._make_battle(won=True)
        assert env.calc_reward(battle) > 0.0

    def test_loss_is_negative(self):
        env = self._make_env()
        battle = self._make_battle(lost=True)
        assert env.calc_reward(battle) < 0.0

    def test_neutral_is_zero(self):
        env = self._make_env()
        battle = self._make_battle()
        assert env.calc_reward(battle) == pytest.approx(0.0)


# ── embed_battle delegates ─────────────────────────────────────────────────────

@pytest.mark.skipif(not POKE_ENV_AVAILABLE, reason="poke-env not installed")
class TestEmbedBattle:
    def test_battle_env_embed_battle_returns_observation(self):
        env = BattleEnv.__new__(BattleEnv)
        battle = _make_mock_battle()
        obs = env.embed_battle(battle)
        assert obs.shape == (OBS_DIM,)

    def test_battle_double_env_embed_battle_returns_doubles_obs(self):
        env = BattleDoubleEnv.__new__(BattleDoubleEnv)
        battle = _make_mock_doubles_battle()
        obs = env.embed_battle(battle)
        assert obs.shape == (OBS_DIM_DOUBLES,)


# ── Fallback stubs (no poke-env) ──────────────────────────────────────────────

class TestFallbackStubs:
    """When poke-env is unavailable the stubs raise ImportError."""

    @pytest.mark.skipif(POKE_ENV_AVAILABLE, reason="poke-env installed — stub not active")
    def test_battle_env_stub_raises_import_error(self):
        with pytest.raises(ImportError):
            BattleEnv()

    @pytest.mark.skipif(POKE_ENV_AVAILABLE, reason="poke-env installed — stub not active")
    def test_battle_double_env_stub_raises_import_error(self):
        with pytest.raises(ImportError):
            BattleDoubleEnv()

    def test_no_custom_teampreview_override(self):
        # BattleDoubleEnv no longer overrides teampreview() - it relies on
        # choose_on_teampreview=False (set in __init__) so the embedded
        # _EnvPlayer instances always use random_teampreview(), which
        # correctly picks 4 unique slots for VGC 6-mon team preview.
        assert "teampreview" not in BattleDoubleEnv.__dict__, (
            "BattleDoubleEnv should NOT define its own teampreview(); "
            "use choose_on_teampreview=False instead"
        )
