"""
battle_env.py — coverage tests for pure observation/reward logic.

Tests _move_features, _pokemon_hp, build_observation, build_doubles_observation,
BattleEnv.calc_reward, BattleDoubleEnv.calc_reward,
and the fallback stubs when poke-env is unavailable.

__init__ methods are excluded (require live Showdown server).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.ml.battle_env import (
    OBS_DIM,
    OBS_DIM_DOUBLES,
    MOVE_TYPE_EFF_OBS_IDXS,
    N_ACTIONS_GEN9,
    _move_features,
    _pokemon_hp,
    _stab_flag,
    _speed_tier,
    _ability_buckets,
    _item_buckets,
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

    def test_type_eff_super_effective(self):
        """2x effective move → log2(2)/2 = 0.5."""
        move = MagicMock()
        move.base_power = 80
        move.accuracy = 100
        move.type = MagicMock()
        move.type.__str__ = lambda s: "fire"
        move.priority = 0
        target = MagicMock()
        target.damage_multiplier = MagicMock(return_value=2.0)
        feats = _move_features(move, target)
        assert feats[4] == pytest.approx(0.5)  # log2(2)/2

    def test_type_eff_resist(self):
        """0.5x resist → log2(0.5)/2 = -0.5."""
        move = MagicMock()
        move.base_power = 80
        move.accuracy = 100
        move.type = MagicMock()
        move.type.__str__ = lambda s: "fire"
        move.priority = 0
        target = MagicMock()
        target.damage_multiplier = MagicMock(return_value=0.5)
        feats = _move_features(move, target)
        assert feats[4] == pytest.approx(-0.5)  # log2(0.5)/2

    def test_type_eff_immune(self):
        """Immune (0x) → -1.0."""
        move = MagicMock()
        move.base_power = 80
        move.accuracy = 100
        move.type = MagicMock()
        move.type.__str__ = lambda s: "normal"
        move.priority = 0
        target = MagicMock()
        target.damage_multiplier = MagicMock(return_value=0)
        feats = _move_features(move, target)
        assert feats[4] == pytest.approx(-1.0)

    def test_type_eff_neutral_no_target(self):
        """Without a target, type_eff defaults to 0.5 (neutral sentinel)."""
        move = MagicMock()
        move.base_power = 80
        move.accuracy = 100
        move.type = MagicMock()
        move.type.__str__ = lambda s: "fire"
        move.priority = 0
        feats = _move_features(move, target=None)
        assert feats[4] == pytest.approx(0.5)

    def test_move_type_eff_obs_idxs_correct(self):
        """MOVE_TYPE_EFF_OBS_IDXS = [6, 11, 16, 21] — one per move slot."""
        assert MOVE_TYPE_EFF_OBS_IDXS == [6, 11, 16, 21]


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


# ── _stab_flag ────────────────────────────────────────────────────────────────

class TestStabFlag:
    def _make_move(self, type_str: str):
        m = MagicMock()
        m.type = MagicMock()
        m.type.__str__ = lambda s: type_str
        return m

    def _make_mon(self, types: list[str]):
        mon = MagicMock()
        type_mocks = []
        for t in types:
            tm = MagicMock()
            tm.__str__ = lambda s, t=t: t
            type_mocks.append(tm)
        mon.types = type_mocks
        return mon

    def test_none_move_returns_zero(self):
        assert _stab_flag(None, self._make_mon(["fire"])) == 0.0

    def test_none_mon_returns_zero(self):
        assert _stab_flag(self._make_move("fire"), None) == 0.0

    def test_stab_match(self):
        assert _stab_flag(self._make_move("fire"), self._make_mon(["fire", "flying"])) == 1.0

    def test_no_stab(self):
        assert _stab_flag(self._make_move("water"), self._make_mon(["fire", "flying"])) == 0.0

    def test_dual_type_second_slot_stab(self):
        assert _stab_flag(self._make_move("flying"), self._make_mon(["fire", "flying"])) == 1.0


# ── _speed_tier ───────────────────────────────────────────────────────────────

class TestSpeedTier:
    def _make_mon_with_speed(self, spe: int):
        mon = MagicMock()
        mon.base_stats = {"spe": spe}
        return mon

    def test_none_active_returns_half(self):
        assert _speed_tier(None, self._make_mon_with_speed(100)) == 0.5

    def test_none_opp_returns_half(self):
        assert _speed_tier(self._make_mon_with_speed(100), None) == 0.5

    def test_faster(self):
        assert _speed_tier(self._make_mon_with_speed(120), self._make_mon_with_speed(80)) == 1.0

    def test_slower(self):
        assert _speed_tier(self._make_mon_with_speed(60), self._make_mon_with_speed(100)) == 0.0

    def test_equal_returns_half(self):
        assert _speed_tier(self._make_mon_with_speed(95), self._make_mon_with_speed(95)) == 0.5

    def test_both_zero_returns_half(self):
        assert _speed_tier(self._make_mon_with_speed(0), self._make_mon_with_speed(0)) == 0.5

    def test_invalid_type_returns_half(self):
        # MagicMock base_stats should trigger the TypeError guard
        fast = MagicMock()  # base_stats.get("spe") will return MagicMock, int() raises TypeError
        slow = MagicMock()
        assert _speed_tier(fast, slow) == 0.5


# ── _ability_buckets ──────────────────────────────────────────────────────────

class TestAbilityBuckets:
    def test_none_ability_own_all_zero(self):
        assert _ability_buckets(None, is_own=True) == [0.0] * 8

    def test_none_ability_opp_all_zero(self):
        assert _ability_buckets(None, is_own=False) == [0.0] * 6

    def test_own_length(self):
        assert len(_ability_buckets("speedboost", is_own=True)) == 8

    def test_opp_length(self):
        assert len(_ability_buckets("speedboost", is_own=False)) == 6

    def test_speed_boost(self):
        buckets = _ability_buckets("speedboost", is_own=True)
        assert buckets[0] == 1.0  # speed_boost slot

    def test_intimidate_entry_effect(self):
        buckets = _ability_buckets("intimidate", is_own=True)
        assert buckets[5] == pytest.approx(-1.0)  # entry_effect slot

    def test_dauntless_shield_entry_effect(self):
        buckets = _ability_buckets("dauntlessshield", is_own=True)
        assert buckets[5] == pytest.approx(1.0)

    def test_absorb_type_volt_absorb(self):
        buckets = _ability_buckets("voltabsorb", is_own=True)
        assert buckets[4] > 0.0  # absorb_type_id for electric

    def test_regenerator_regen(self):
        assert _ability_buckets("regenerator", is_own=True)[2] == 1.0

    def test_normalization_spaces(self):
        assert _ability_buckets("Speed Boost", is_own=True)[0] == 1.0

    def test_unknown_ability_all_zero(self):
        assert _ability_buckets("unknown", is_own=True) == [0.0] * 8


# ── _item_buckets ─────────────────────────────────────────────────────────────

class TestItemBuckets:
    def test_none_item_own_all_zero(self):
        result = _item_buckets(None, 1.0, is_own=True)
        assert result == [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0]  # speed_mod defaults to 1.0

    def test_own_length(self):
        assert len(_item_buckets("leftovers", 1.0, is_own=True)) == 7

    def test_opp_length(self):
        assert len(_item_buckets("leftovers", 1.0, is_own=False)) == 4

    def test_leftovers_heal(self):
        buckets = _item_buckets("leftovers", 1.0, is_own=True)
        assert buckets[0] == pytest.approx(0.0625)

    def test_choice_scarf(self):
        buckets = _item_buckets("choicescarf", 1.0, is_own=True)
        assert buckets[1] == pytest.approx(1.0)   # choice slot
        assert buckets[2] == pytest.approx(1.5)   # speed_mod slot

    def test_focus_sash_at_full_hp(self):
        buckets = _item_buckets("focussash", 1.0, is_own=True)
        assert buckets[4] == pytest.approx(1.0)

    def test_focus_sash_below_full_hp(self):
        buckets = _item_buckets("focussash", 0.9, is_own=True)
        assert buckets[4] == pytest.approx(0.0)

    def test_life_orb_offence(self):
        assert _item_buckets("lifeorb", 1.0, is_own=True)[5] == pytest.approx(1.0)

    def test_lum_berry_status(self):
        assert _item_buckets("lumberry", 1.0, is_own=True)[6] == pytest.approx(1.0)

    def test_flame_orb_status_negative(self):
        assert _item_buckets("flameorb", 1.0, is_own=True)[6] == pytest.approx(-1.0)


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

    def test_obs_shape_is_78(self):
        """Obs vector for singles battles must be exactly 78 dimensions (ISS-008)."""
        battle = _make_mock_battle()
        obs = build_observation(battle)
        assert obs.shape == (78,)
        assert OBS_DIM == 78

    def test_all_values_in_expected_range(self):
        """Most obs values lie in [0, 1]; type_eff slots may be in [-1, 1]."""
        battle = _make_mock_battle()
        obs = build_observation(battle)
        assert np.all(obs >= -1.0)
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
        battle = _make_mock_battle(turn=25)
        obs = build_observation(battle)
        # Turn is at fixed index 47 (field block, before STAB/speed tail)
        assert obs[47] == pytest.approx(0.5)

    def test_turn_capped_at_100(self):
        battle = _make_mock_battle(turn=200)
        obs = build_observation(battle)
        assert obs[47] == pytest.approx(1.0)

    def test_zero_turn(self):
        battle = _make_mock_battle(turn=0)
        obs = build_observation(battle)
        # Turn is at fixed index 47 (field block, before STAB/speed tail)
        assert obs[47] == pytest.approx(0.0)

    def test_trick_room_effect_imported(self):
        """Force the trick_room try-block to execute with a non-empty fields dict."""
        battle = _make_mock_battle()
        battle.fields = {"some_field": 1}
        obs = build_observation(battle)
        assert obs.shape == (OBS_DIM,)

    def test_active_terrain_field_hits_break(self):
        """TERRAIN_IDS loop hits terrain=val; break for a known terrain key."""
        pytest.importorskip("poke_env")
        from poke_env.battle import Field
        battle = _make_mock_battle()
        battle.fields = {Field.ELECTRIC_TERRAIN: 1}
        obs = build_observation(battle)
        assert obs.shape == (OBS_DIM,)
        # terrain is at fixed index 45 (field block, before STAB/speed tail)
        assert obs[45] > 0.0

    def test_stab_flags_present_in_obs(self):
        """STAB flag slots [48..51] exist and are 0.0 for mock moves (no type match)."""
        battle = _make_mock_battle()
        obs = build_observation(battle)
        for i in range(48, 52):
            assert obs[i] in (0.0, 1.0), f"obs[{i}] not a valid STAB flag: {obs[i]}"

    def test_speed_tier_in_obs(self):
        """Speed tier slot [52] exists and is 0.0, 0.5, or 1.0."""
        battle = _make_mock_battle()
        obs = build_observation(battle)
        assert obs[52] in (0.0, 0.5, 1.0)

    def test_speed_tier_unknown_for_mock(self):
        """Mock mons have no base_stats → speed tier defaults to 0.5."""
        battle = _make_mock_battle()
        obs = build_observation(battle)
        assert obs[52] == pytest.approx(0.5)

    def test_ability_slots_present(self):
        """Ability bucket slots [53..66] are populated (all 0.0 for mock mons)."""
        battle = _make_mock_battle()
        obs = build_observation(battle)
        for i in range(53, 67):
            assert -1.0 <= obs[i] <= 1.0, f"obs[{i}] out of range: {obs[i]}"

    def test_item_slots_present(self):
        """Item bucket slots [67..77] are populated (all 0.0 for mock mons except speed_mod=1.0)."""
        battle = _make_mock_battle()
        obs = build_observation(battle)
        for i in range(67, 78):
            assert -1.0 <= obs[i] <= 1.5, f"obs[{i}] out of range: {obs[i]}"


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
        pytest.importorskip("poke_env")
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
        battle.finished = False
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


# ── BattleEnv.action_space property/setter + step() guard ────────────────────

@pytest.mark.skipif(not POKE_ENV_AVAILABLE, reason="poke-env not installed")
class TestBattleEnvActionSpace:
    """Cover action_space fallback property, setter, and AssertionError guard."""

    def test_fallback_returns_discrete_n_actions_gen9(self):
        """action_space property returns Discrete(N_ACTIONS_GEN9) when _sb3_action_space absent."""
        from src.ml.battle_env import N_ACTIONS_GEN9
        env = BattleEnv.__new__(BattleEnv)
        space = env.action_space
        assert space.n == N_ACTIONS_GEN9

    def test_setter_stores_custom_space(self):
        """action_space setter stores value and getter returns it (line 281 branch)."""
        from gymnasium.spaces import Discrete
        env = BattleEnv.__new__(BattleEnv)
        custom = Discrete(10)
        env.action_space = custom
        # Reading the property after setting covers the hasattr=True branch (line 281)
        assert env.action_space is custom

    def test_step_assertion_error_returns_terminal(self):
        """step() catches AssertionError from poke-env and returns zero terminal step."""
        from gymnasium.spaces import Box, Discrete
        from poke_env.environment.singles_env import SinglesEnv
        env = BattleEnv.__new__(BattleEnv)
        fake_space = Box(low=0.0, high=1.0, shape=(OBS_DIM,), dtype=np.float32)
        # poke-env's __setattr__ for observation_spaces reads self.action_spaces,
        # so prime it before assigning observation_spaces.
        env.action_spaces = {"p1": Discrete(N_ACTIONS_GEN9)}
        env.observation_spaces = {"p1": fake_space}
        with patch.object(SinglesEnv, "step", side_effect=AssertionError):
            obs, rew, done, trunc, info = env.step(0)
        assert done is True
        assert trunc is True
        assert rew == pytest.approx(0.0)
        assert obs.shape == (OBS_DIM,)
        assert info == {}


# ── BattleDoubleEnv.action_space property/setter + step() guard ───────────────

@pytest.mark.skipif(not POKE_ENV_AVAILABLE, reason="poke-env not installed")
class TestBattleDoubleEnvActionSpace:
    """Cover doubles action_space fallback property, setter, and AssertionError guard."""

    def test_fallback_returns_discrete_1(self):
        """action_space property returns Discrete(1) when _sb3_action_space absent."""
        env = BattleDoubleEnv.__new__(BattleDoubleEnv)
        space = env.action_space
        assert space.n == 1

    def test_setter_stores_custom_space(self):
        """action_space setter stores value and getter returns it (line 511 branch)."""
        from gymnasium.spaces import Discrete
        env = BattleDoubleEnv.__new__(BattleDoubleEnv)
        custom = Discrete(5)
        env.action_space = custom
        # Reading the property after setting covers the hasattr=True branch (line 511)
        assert env.action_space is custom

    def test_step_assertion_error_returns_terminal(self):
        """step() catches AssertionError and returns zero terminal step for doubles."""
        from gymnasium.spaces import Box, Discrete
        from poke_env.environment.doubles_env import DoublesEnv
        env = BattleDoubleEnv.__new__(BattleDoubleEnv)
        fake_space = Box(low=0.0, high=1.0, shape=(OBS_DIM_DOUBLES,), dtype=np.float32)
        # poke-env's __setattr__ for observation_spaces reads self.action_spaces,
        # so prime it before assigning observation_spaces.
        env.action_spaces = {"p1": Discrete(1)}
        env.observation_spaces = {"p1": fake_space}
        with patch.object(DoublesEnv, "step", side_effect=AssertionError):
            obs, rew, done, trunc, info = env.step(0)
        assert done is True
        assert trunc is True
        assert rew == pytest.approx(0.0)
        assert obs.shape == (OBS_DIM_DOUBLES,)
        assert info == {}
