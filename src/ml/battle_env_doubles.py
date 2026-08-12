"""
Doubles Battle Environment — poke-env Gymnasium wrapper for VGC/doubles RL training.

Extracted from battle_env.py (which had grown past the project's 800-line
guideline): the singles-format observation builder and BattleEnv stay in
battle_env.py; this module holds the doubles-format equivalents. Shared
feature-extraction helpers (_move_features, _pokemon_hp, etc.) stay in
battle_env.py and are imported from there.

See battle_env.py's module docstring for the overall observation/action
space design this mirrors for 2v2 doubles battles.
"""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    from gymnasium.spaces import Box, Discrete
except ImportError:  # pragma: no cover
    Box = None  # type: ignore
    Discrete = None  # type: ignore

try:
    from poke_env.environment.doubles_env import DoublesEnv
except ImportError:  # pragma: no cover
    DoublesEnv = object  # type: ignore

from src.ml.battle_env import (
    MOVE_FEATS,
    N_MOVES,
    POKE_ENV_AVAILABLE,
    STATUS_IDS,
    TEAM_SIZE,
    TERRAIN_IDS,
    WEATHER_IDS,
    _ability_buckets,
    _item_buckets,
    _move_features,
    _pokemon_hp,
    _speed_tier,
    _stab_flag,
    _stable_species_id,
)


# ── Doubles observation constants ─────────────────────────────────────────────

# Active mon 1: [species_id, hp, 4×(5-feats), status, 6×boosts] = 29
# Active mon 2: same = 29
# Opp active 1: [species_id, hp, status] = 3
# Opp active 2: same = 3
# My team HP:   6
# Opp team HP:  6
# Field:        4  (weather, terrain, trick_room, turn)
# STAB+speed 1: 5   (4 STAB flags + 1 speed tier for active mon 1)
# STAB+speed 2: 5   (4 STAB flags + 1 speed tier for active mon 2)
# Abil+item 1: 15   (own ability 8 + own item 7)
# Abil+item 2: 15   (own ability 8 + own item 7)
# Opp abil 1:  10   (opp ability 6 + opp item 4)
# Opp abil 2:  10   (opp ability 6 + opp item 4)
OBS_DIM_DOUBLES = 29 + 29 + 3 + 3 + 6 + 6 + 4 + 5 + 5 + 15 + 15 + 10 + 10  # = 140


def build_doubles_observation(battle: Any) -> np.ndarray:
    """
    Convert a poke-env DoubleBattle into a float32 observation vector of
    shape (OBS_DIM_DOUBLES,).
    """
    obs = np.zeros(OBS_DIM_DOUBLES, dtype=np.float32)
    idx = 0

    # ── Two active Pokémon on our side ─────────────────────────────
    active_list = getattr(battle, "active_pokemon", [None, None]) or [None, None]
    if not isinstance(active_list, (list, tuple)):
        active_list = [active_list, None]

    for slot in range(2):
        active = active_list[slot] if slot < len(active_list) else None
        if active:
            obs[idx] = _stable_species_id(active.species)
            idx += 1
            obs[idx] = _pokemon_hp(active)
            idx += 1
            moves = list(
                getattr(battle, "available_moves", [[]])[slot]
                if slot < len(getattr(battle, "available_moves", []))
                else []
            )
            for i in range(N_MOVES):
                move = moves[i] if i < len(moves) else None
                obs[idx : idx + MOVE_FEATS] = _move_features(move)
                idx += MOVE_FEATS
            obs[idx] = STATUS_IDS.get(getattr(active, "status", None), 0) / 6.0
            idx += 1
            boosts = getattr(active, "boosts", {})
            for stat in ["atk", "def", "spa", "spd", "spe", "accuracy"]:
                obs[idx] = (boosts.get(stat, 0) + 6) / 12.0
                idx += 1
        else:
            idx += 29

    # ── Two opponent active Pokémon ────────────────────────────────
    opp_list = getattr(battle, "opponent_active_pokemon", [None, None]) or [None, None]
    if not isinstance(opp_list, (list, tuple)):
        opp_list = [opp_list, None]

    for slot in range(2):
        opp = opp_list[slot] if slot < len(opp_list) else None
        if opp:
            obs[idx] = _stable_species_id(opp.species)
            idx += 1
            obs[idx] = _pokemon_hp(opp)
            idx += 1
            obs[idx] = STATUS_IDS.get(getattr(opp, "status", None), 0) / 6.0
            idx += 1
        else:
            idx += 3

    # ── My team HP ─────────────────────────────────────────────────
    team = sorted(
        battle.team.values(), key=lambda p: str(getattr(p, "species", "") or "")
    )
    for i in range(TEAM_SIZE):
        obs[idx] = _pokemon_hp(team[i]) if i < len(team) else 0.0
        idx += 1

    # ── Opponent team HP ───────────────────────────────────────────
    opp_team = sorted(
        battle.opponent_team.values(),
        key=lambda p: str(getattr(p, "species", "") or ""),
    )
    for i in range(TEAM_SIZE):
        obs[idx] = _pokemon_hp(opp_team[i]) if i < len(opp_team) else 1.0
        idx += 1

    # ── Field conditions ───────────────────────────────────────────
    weather_dict = getattr(battle, "weather", {}) or {}
    active_weather = next(iter(weather_dict), None)
    obs[idx] = WEATHER_IDS.get(active_weather, 0) / 5.0
    idx += 1

    fields = getattr(battle, "fields", {}) or {}
    terrain = 0
    for fld, val in TERRAIN_IDS.items():
        if fld and fld in fields:
            terrain = val
            break
    obs[idx] = terrain / 4.0
    idx += 1

    trick_room = 0.0
    try:
        from poke_env.battle import Effect

        trick_room = float(Effect.TRICK_ROOM in fields)
    except Exception:  # pragma: no cover
        pass
    obs[idx] = trick_room
    idx += 1

    obs[idx] = min(getattr(battle, "turn", 0), 50) / 50.0
    idx += 1

    # ── STAB flags + speed tier per active slot ────────────────────
    opp_list_full = getattr(battle, "opponent_active_pokemon", [None, None]) or [
        None,
        None,
    ]
    if not isinstance(opp_list_full, (list, tuple)):
        opp_list_full = [opp_list_full, None]
    for slot in range(2):
        slot_active = active_list[slot] if slot < len(active_list) else None
        slot_opp = opp_list_full[slot] if slot < len(opp_list_full) else None
        slot_moves = list(
            getattr(battle, "available_moves", [[]])[slot]
            if slot < len(getattr(battle, "available_moves", []))
            else []
        )
        for i in range(N_MOVES):
            move = slot_moves[i] if i < len(slot_moves) else None
            obs[idx] = _stab_flag(move, slot_active)
            idx += 1
        obs[idx] = _speed_tier(slot_active, slot_opp)
        idx += 1

    # ── Ability + item buckets per active slot ─────────────────────
    for slot in range(2):
        slot_active = active_list[slot] if slot < len(active_list) else None
        slot_opp = opp_list_full[slot] if slot < len(opp_list_full) else None
        slot_hp = _pokemon_hp(slot_active)
        slot_opp_hp = _pokemon_hp(slot_opp)
        for val in _ability_buckets(
            getattr(slot_active, "ability", None), is_own=True
        ):  # 8
            obs[idx] = val
            idx += 1
        for val in _item_buckets(
            getattr(slot_active, "item", None), slot_hp, is_own=True
        ):  # 7
            obs[idx] = val
            idx += 1
        for val in _ability_buckets(
            getattr(slot_opp, "ability", None), is_own=False
        ):  # 6
            obs[idx] = val
            idx += 1
        for val in _item_buckets(
            getattr(slot_opp, "item", None), slot_opp_hp, is_own=False
        ):  # 4
            obs[idx] = val
            idx += 1

    # ── Final Dimension Verification ──────────────────────────────────
    assert idx == OBS_DIM_DOUBLES, (
        f"Doubles observation dimension mismatch: {idx} != {OBS_DIM_DOUBLES}"
    )

    return obs


# ── Doubles RL Environment ────────────────────────────────────────────────────

if POKE_ENV_AVAILABLE:

    class BattleDoubleEnv(DoublesEnv):
        """
        poke-env + Gymnasium environment for PPO training on doubles formats.

        Inherits from DoublesEnv, overrides embed_battle and calc_reward.
        The observation_spaces dict is set in __init__ (required by poke-env).
        Action space is MultiDiscrete set by DoublesEnv parent.
        """

        def __init__(self, **kwargs: Any) -> None:  # pragma: no cover
            # Force choose_on_teampreview=False so embedded _EnvPlayer
            # instances use random_teampreview() for all formats.
            # The choose_on_teampreview=True path (DoublesEnv default)
            # calls _choose_move() twice for VGC leads, but an untrained
            # PPO model can output duplicate slot indices causing Showdown
            # PS_ERROR "slot N can only switch in once" -> battle hangs.
            # random_teampreview() always picks 4 unique slots correctly.
            kwargs.setdefault("choose_on_teampreview", False)
            super().__init__(**kwargs)
            # poke-env defines action_space as a method (takes agent name),
            # but SB3 expects a gymnasium.spaces object via a property.
            # DoublesEnv.__init__ already populated self.action_spaces —
            # grab the first agent's concrete space for SB3.
            first_agent = next(iter(self.action_spaces))
            self._sb3_action_space = self.action_spaces[first_agent]
            # Override observation_spaces with our custom flat Box per agent
            # (poke-env's __setattr__ wraps these with action_mask).
            # low=-1.0/high=2.0: covers intimidate/flameorb (-1.0) and choicescarf speed (1.5)
            obs_space = Box(
                low=-1.0, high=2.0, shape=(OBS_DIM_DOUBLES,), dtype=np.float32
            )
            self.observation_spaces = {
                agent: obs_space for agent in self.possible_agents
            }
            self._prev_state: dict[str, dict[str, int]] = {}

        @property
        def action_space(self):
            if hasattr(self, "_sb3_action_space"):
                return self._sb3_action_space
            # Fallback during super().__init__() — DoublesEnv will set
            # action_spaces before we can read it, so use a safe default.
            return Discrete(1)

        @action_space.setter
        def action_space(self, space):
            self._sb3_action_space = space

        def step(self, action):
            """Guard against poke-env AssertionError when battle ends mid-rollout."""
            try:
                return super().step(action)
            except AssertionError:
                # Only silence the known "battle ended before SB3 observed done=True" case.
                # For any other assertion failure, re-raise so it surfaces and can be fixed.
                # (If battles dict is missing or empty the battle already cleaned up — swallow.)
                battles = (
                    list(self.battles.values()) if hasattr(self, "battles") else []
                )
                if battles and not any(b.finished for b in battles):
                    raise
                # Battle ended before SB3 could observe done=True.
                # Return a terminal step with zero reward so the rollout closes cleanly.
                # poke-env 0.15+ wraps observation_spaces in a Dict{action_mask, observation},
                # whose .shape is None; build the flat terminal obs from the known embed dim
                # instead (matches build_observation's output exactly).
                obs = np.zeros(OBS_DIM_DOUBLES, dtype=np.float32)
                return obs, 0.0, True, True, {}

        def embed_battle(self, battle: Any) -> np.ndarray:
            return build_doubles_observation(battle)

        def calc_reward(self, battle: Any) -> float:
            """
            Shaped reward per step (same structure as singles):
              +1.0  win
              -1.0  loss
              +0.3  per opponent faint (delta since last step)
              -0.3  per own faint (delta since last step)
            """
            bid = getattr(battle, "battle_tag", id(battle))
            prev = self._prev_state.get(bid, {"opp_fainted": 0, "own_fainted": 0})

            curr_opp_fainted = sum(
                1 for p in battle.opponent_team.values() if p.fainted
            )
            curr_own_fainted = sum(1 for p in battle.team.values() if p.fainted)

            reward = 0.0
            if battle.won:
                reward += 1.0
            elif battle.lost:
                reward -= 1.0

            reward += 0.3 * (curr_opp_fainted - prev["opp_fainted"])
            reward -= 0.3 * (curr_own_fainted - prev["own_fainted"])

            if battle.finished:
                self._prev_state.pop(bid, None)
            else:
                self._prev_state[bid] = {
                    "opp_fainted": curr_opp_fainted,
                    "own_fainted": curr_own_fainted,
                }
            return reward

else:  # pragma: no cover

    class BattleDoubleEnv:  # type: ignore
        observation_spaces = None
        action_spaces = None

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "poke-env is not properly installed. Run: pip install poke-env>=0.15.0"
            )
