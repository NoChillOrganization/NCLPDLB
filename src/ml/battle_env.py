"""
Battle Environment — poke-env Gymnasium wrapper for RL training.

Wraps a Gen 9 Singles battle as a Gymnasium environment so stable-baselines3
can train a PPO agent via self-play.

Observation space (float32 vector):
  Active mon:  species_id/10000, hp_pct, 4×(base_power/250, accuracy/100,
               type_id/20, priority/10, type_eff∈[-1,1]), status_id/6, 6×boost/12
  Opponent:    species_id/10000, hp_pct, status_id/6
  Team HP:     6×hp_pct for each side
  Field:       weather_id/5, terrain_id/4, trick_room (0/1), turn/50
  Total dims:  OBS_DIM = 48 — see MOVE_TYPE_EFF_OBS_IDXS for type_eff slot indices

Action space (Discrete — gen9 = 26):
  0-5   → switch to team slot 0-5
  6-9   → use move 0-3 (no gimmick)
  10-13 → move + mega evolve
  14-17 → move + z-move
  18-21 → move + dynamax
  22-25 → move + terastallize

Requires a local Pokemon Showdown server running on ws://localhost:8000.
See scripts/setup_showdown_server.md for setup instructions.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

try:
    from gymnasium.spaces import Box, Discrete, MultiDiscrete
except ImportError:  # pragma: no cover
    Box = None  # type: ignore
    Discrete = None  # type: ignore
    MultiDiscrete = None  # type: ignore

try:
    from poke_env.battle import AbstractBattle, Field, Move, Pokemon, Status, Weather
    from poke_env.environment.doubles_env import DoublesEnv
    from poke_env.environment.singles_env import SinglesEnv
    POKE_ENV_AVAILABLE = True
except ImportError:  # pragma: no cover
    POKE_ENV_AVAILABLE = False
    SinglesEnv = object  # type: ignore
    DoublesEnv = object  # type: ignore

log = logging.getLogger(__name__)

# ── Observation constants ─────────────────────────────────────────────────────
OBS_DIM = 48
TEAM_SIZE = 6
OBS_DIM_DOUBLES = 80
N_MOVES = 4
MOVE_FEATS = 5    # base_power, accuracy, type_id, priority, effectiveness
STATUS_DIM  = 1
BOOST_DIM   = 6
FIELD_DIM   = 4

# Active mon:    [species_id, hp, 4×(5-feats), status, 6×boosts] = 2 + 20 + 1 + 6 = 29
# Opp active:    [species_id, hp, status]     = 3
# My team HP:    6
# Opp team HP:   6
# Field:         4
OBS_DIM = 29 + 3 + 6 + 6 + 4   # = 48

# Obs-vector indices for the type-effectiveness feature, one per move slot.
# Active-mon layout: [species(1), hp(1), slot0…slot3(5 feats each), …]
# The eff feature is the last (5th) feature of each move slot.
# Slot 0 → idx 6, slot 1 → idx 11, slot 2 → idx 16, slot 3 → idx 21.
MOVE_TYPE_EFF_OBS_IDXS: list[int] = [
    2 + MOVE_FEATS * i + (MOVE_FEATS - 1) for i in range(N_MOVES)
]

# gen9 action space: 6 switches + 4 moves × (4 gimmicks + 1 none) = 26
N_ACTIONS_GEN9 = 26


# ── Type / status ID maps ─────────────────────────────────────────────────────

TYPE_IDS = {
    "normal": 1, "fire": 2, "water": 3, "electric": 4, "grass": 5,
    "ice": 6, "fighting": 7, "poison": 8, "ground": 9, "flying": 10,
    "psychic": 11, "bug": 12, "rock": 13, "ghost": 14, "dragon": 15,
    "dark": 16, "steel": 17, "fairy": 18, "stellar": 19,
}

STATUS_IDS: dict[Any, int] = {None: 0}
try:
    STATUS_IDS.update({
        Status.BRN: 1, Status.PAR: 2, Status.SLP: 3,
        Status.FRZ: 4, Status.PSN: 5, Status.TOX: 6,
    })
except Exception:  # pragma: no cover
    pass

WEATHER_IDS: dict[Any, int] = {None: 0}
TERRAIN_IDS: dict[Any, int] = {None: 0}
try:
    WEATHER_IDS.update({
        Weather.SUNNYDAY: 1, Weather.RAINDANCE: 2,
        Weather.SANDSTORM: 3, Weather.SNOW: 4,
        Weather.HAIL: 5,
    })
    TERRAIN_IDS.update({
        Field.ELECTRIC_TERRAIN: 1, Field.GRASSY_TERRAIN: 2,
        Field.MISTY_TERRAIN: 3, Field.PSYCHIC_TERRAIN: 4,
    })
except Exception:  # pragma: no cover
    pass


# ── Observation builder ───────────────────────────────────────────────────────

def _move_features(move: "Move | None", target: "Pokemon | None" = None) -> list[float]:
    """Extract 5-float feature vector for one move slot."""
    if move is None:
        return [0.0, 0.0, 0.0, 0.0, 0.5]
    
    bp = min(getattr(move, "base_power", 0) or 0, 250) / 250.0
    acc = (getattr(move, "accuracy", 100) or 100) / 100.0
    type_id = TYPE_IDS.get(str(getattr(move, "type", "")).lower().split(".")[-1], 0) / 20.0
    
    try:
        prio = (move.priority + 5) / 10.0
    except Exception:  # pragma: no cover
        prio = 0.5  # neutral priority
    
    eff = 0.5  # Neutral default
    if target and move:
        from src.ml.type_chart import get_type_effectiveness_float
        eff = get_type_effectiveness_float(move, target)
        
    return [bp, acc, type_id, prio, eff]


def _pokemon_hp(mon: "Pokemon | None") -> float:
    if mon is None or mon.fainted:
        return 0.0
    return getattr(mon, "current_hp_fraction", 1.0) or 0.0


def build_observation(battle: "AbstractBattle") -> np.ndarray:
    """
    Convert a poke-env AbstractBattle into a float32 observation vector of
    shape (OBS_DIM,).
    """
    obs = np.zeros(OBS_DIM, dtype=np.float32)
    idx = 0

    # ── Active Pokemon ─────────────────────────────────────────────
    active = battle.active_pokemon
    if active:
        obs[idx] = hash(active.species) % 10000 / 10000.0
        idx += 1
        obs[idx] = _pokemon_hp(active)
        idx += 1

        moves = list(battle.available_moves)
        opp_active = battle.opponent_active_pokemon
        for i in range(N_MOVES):
            move = moves[i] if i < len(moves) else None
            feats = _move_features(move, opp_active)
            obs[idx:idx + MOVE_FEATS] = feats
            idx += MOVE_FEATS

        obs[idx] = STATUS_IDS.get(getattr(active, "status", None), 0) / 6.0
        idx += 1

        boosts = getattr(active, "boosts", {})
        for stat in ["atk", "def", "spa", "spd", "spe", "accuracy"]:
            obs[idx] = (boosts.get(stat, 0) + 6) / 12.0
            idx += 1
    else:
        # Default empty active state
        idx += 29

    # ── Opponent active ────────────────────────────────────────────
    opp = battle.opponent_active_pokemon
    if opp:
        obs[idx] = hash(opp.species) % 10000 / 10000.0
        idx += 1
        obs[idx] = _pokemon_hp(opp)
        idx += 1
        obs[idx] = STATUS_IDS.get(getattr(opp, "status", None), 0) / 6.0
        idx += 1
    else:
        idx += 3

    # ── My team HP ─────────────────────────────────────────────────
    team = list(battle.team.values())
    for i in range(TEAM_SIZE):
        obs[idx] = _pokemon_hp(team[i]) if i < len(team) else 0.0
        idx += 1

    # ── Opponent team HP ───────────────────────────────────────────
    opp_team = list(battle.opponent_team.values())
    for i in range(TEAM_SIZE):
        obs[idx] = _pokemon_hp(opp_team[i]) if i < len(opp_team) else 1.0
        idx += 1

    # ── Field conditions ───────────────────────────────────────────
    # weather is Dict[Weather, int] in new poke-env — get first active key
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

    # Trick room: check fields dict for trick room effect
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

    # ── Final Dimension Verification ──────────────────────────────────
    assert idx == OBS_DIM, f"Observation dimension mismatch: {idx} != {OBS_DIM}"
    
    return obs


# ── RL Environment ────────────────────────────────────────────────────────────

if POKE_ENV_AVAILABLE:
    class BattleEnv(SinglesEnv):
        """
        poke-env + Gymnasium environment for PPO training.

        Inherits from SinglesEnv, overrides embed_battle and calc_reward.
        The observation_spaces dict is set in __init__ (required by poke-env).

        Use with SingleAgentWrapper for standard Gymnasium-compatible self-play:
            env = BattleEnv(battle_format="gen9randombattle", ...)
            wrapped = SingleAgentWrapper(env, opponent_player)
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
            # SinglesEnv.__init__ already populated self.action_spaces with
            # {username: Discrete(26)} — store a concrete copy for SB3.
            self._sb3_action_space = Discrete(N_ACTIONS_GEN9)
            # Override observation_spaces with our custom flat Box per agent
            # (poke-env's __setattr__ wraps these with action_mask).
            obs_space = Box(low=0.0, high=1.0, shape=(OBS_DIM,), dtype=np.float32)
            self.observation_spaces = {
                agent: obs_space for agent in self.possible_agents
            }
            # Track previous faint counts for shaped reward (keyed by id(battle))
            self._prev_state: dict[int, dict[str, int]] = {}

        @property
        def action_space(self):
            if hasattr(self, "_sb3_action_space"):
                return self._sb3_action_space
            # Fallback during super().__init__() before _sb3_action_space is set
            return Discrete(N_ACTIONS_GEN9)

        @action_space.setter
        def action_space(self, space):
            self._sb3_action_space = space

        def order_to_action(self, order: Any, battle: Any, **kwargs: Any) -> int:  # pragma: no cover
            # poke-env bug: two-turn moves (Dig, Fly, etc.) are "locked in" on
            # turn 2 and don't appear in battle.available_moves, causing
            # singles_env.order_to_action to raise ValueError recursively until
            # RecursionError. Fall back to action 0 (switch slot 0), which is
            # always legal in a 6-slot team and handled by strict=False training.
            try:
                return super().order_to_action(order, battle, **kwargs)
            except (ValueError, RecursionError) as exc:
                log.warning(
                    "[BattleEnv] order_to_action fallback (poke-env two-turn move bug): "
                    "%s — returning action 0",
                    exc,
                )
                return 0

        def step(self, action):
            """Guard against poke-env AssertionError when battle ends mid-rollout."""
            try:
                return super().step(action)
            except AssertionError:
                # Battle ended before SB3 could observe done=True.
                # Return a terminal step with zero reward so the rollout closes cleanly.
                obs = np.zeros(self.observation_space.shape, dtype=self.observation_space.dtype)
                return obs, 0.0, True, True, {}

        def embed_battle(self, battle: AbstractBattle) -> np.ndarray:
            return build_observation(battle)

        def calc_reward(self, battle: AbstractBattle) -> float:
            """
            Shaped reward per step:
              +1.0  win
              -1.0  loss
              +0.3  per opponent faint (delta since last step)
              -0.3  per own faint (delta since last step)
            """
            bid = id(battle)
            prev = self._prev_state.get(bid, {"opp_fainted": 0, "own_fainted": 0})

            curr_opp_fainted = sum(1 for p in battle.opponent_team.values() if p.fainted)
            curr_own_fainted = sum(1 for p in battle.team.values() if p.fainted)

            reward = 0.0
            if battle.won:
                reward += 1.0
            elif battle.lost:
                reward -= 1.0

            reward += 0.3 * (curr_opp_fainted - prev["opp_fainted"])
            reward -= 0.3 * (curr_own_fainted - prev["own_fainted"])

            self._prev_state[bid] = {
                "opp_fainted": curr_opp_fainted,
                "own_fainted": curr_own_fainted,
            }
            return reward

else:  # pragma: no cover
    class BattleEnv:  # type: ignore
        observation_spaces = None
        action_spaces = None

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "poke-env is not properly installed. "
                "Run: pip install poke-env>=0.8.1"
            )


# ── Doubles observation constants ─────────────────────────────────────────────

# Active mon 1: [species_id, hp, 4×(5-feats), status, 6×boosts] = 29
# Active mon 2: same = 29
# Opp active 1: [species_id, hp, status] = 3
# Opp active 2: same = 3
# My team HP:   6
# Opp team HP:  6
# Field:        4  (weather, terrain, trick_room, turn)
OBS_DIM_DOUBLES = 29 + 29 + 3 + 3 + 6 + 6 + 4   # = 80


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
            obs[idx] = hash(active.species) % 10000 / 10000.0
            idx += 1
            obs[idx] = _pokemon_hp(active)
            idx += 1
            moves = list(getattr(battle, "available_moves", [[]])[slot]
                         if slot < len(getattr(battle, "available_moves", []))
                         else [])
            for i in range(N_MOVES):
                move = moves[i] if i < len(moves) else None
                obs[idx:idx + MOVE_FEATS] = _move_features(move)
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
            obs[idx] = hash(opp.species) % 10000 / 10000.0
            idx += 1
            obs[idx] = _pokemon_hp(opp)
            idx += 1
            obs[idx] = STATUS_IDS.get(getattr(opp, "status", None), 0) / 6.0
            idx += 1
        else:
            idx += 3

    # ── My team HP ─────────────────────────────────────────────────
    team = list(battle.team.values())
    for i in range(TEAM_SIZE):
        obs[idx] = _pokemon_hp(team[i]) if i < len(team) else 0.0
        idx += 1

    # ── Opponent team HP ───────────────────────────────────────────
    opp_team = list(battle.opponent_team.values())
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

    # ── Final Dimension Verification ──────────────────────────────────
    assert idx == OBS_DIM_DOUBLES, f"Doubles observation dimension mismatch: {idx} != {OBS_DIM_DOUBLES}"
    
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
            obs_space = Box(low=0.0, high=1.0, shape=(OBS_DIM_DOUBLES,), dtype=np.float32)
            self.observation_spaces = {
                agent: obs_space for agent in self.possible_agents
            }
            self._prev_state: dict[int, dict[str, int]] = {}

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
                # Battle ended before SB3 could observe done=True.
                # Return a terminal step with zero reward so the rollout closes cleanly.
                obs = np.zeros(self.observation_space.shape, dtype=self.observation_space.dtype)
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
            bid = id(battle)
            prev = self._prev_state.get(bid, {"opp_fainted": 0, "own_fainted": 0})

            curr_opp_fainted = sum(1 for p in battle.opponent_team.values() if p.fainted)
            curr_own_fainted = sum(1 for p in battle.team.values() if p.fainted)

            reward = 0.0
            if battle.won:
                reward += 1.0
            elif battle.lost:
                reward -= 1.0

            reward += 0.3 * (curr_opp_fainted - prev["opp_fainted"])
            reward -= 0.3 * (curr_own_fainted - prev["own_fainted"])

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
                "poke-env is not properly installed. "
                "Run: pip install poke-env>=0.8.1"
            )
