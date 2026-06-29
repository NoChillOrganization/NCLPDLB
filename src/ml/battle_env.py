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
  STAB flags:  4 floats at [48..51], one per move slot (1.0 if move type ∈ active types)
  Speed tier:  1 float  at [52], 0.0=slower / 0.5=unknown / 1.0=faster (base stats)
  Total dims:  OBS_DIM = 78 — see MOVE_TYPE_EFF_OBS_IDXS for type_eff slot indices

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

import hashlib
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


def _stable_species_id(species: Any) -> float:
    """Stable, cross-process species float in [0,1] using MD5 (not hash())."""
    digest = hashlib.md5(str(species or "").encode()).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF


def _sort_team_dict(battle: Any) -> None:
    """Sort battle.team and battle.opponent_team alphabetically by species in-place.

    Ensures that action slot i always refers to the alphabetically i-th team member,
    matching the sorted ordering used by ActionResolver in pretrain.py (Branch 1/2 fix).
    Called by BattleEnv.embed_battle() so poke-env's action_to_order sees the same order.
    """
    for attr in ("team", "opponent_team"):
        team_dict = getattr(battle, attr, None)
        if not team_dict:
            continue
        try:
            items = sorted(
                team_dict.items(),
                key=lambda kv: str(getattr(kv[1], "species", None) or kv[0]),
            )
            team_dict.clear()
            team_dict.update(items)
        except Exception:
            pass


# ── Observation constants ─────────────────────────────────────────────────────
OBS_DIM = 78
TEAM_SIZE = 6
OBS_DIM_DOUBLES = 140
N_MOVES = 4
MOVE_FEATS = 5  # base_power, accuracy, type_id, priority, effectiveness
STATUS_DIM = 1
BOOST_DIM = 6
FIELD_DIM = 4

# Active mon:    [species_id, hp, 4×(5-feats), status, 6×boosts] = 2 + 20 + 1 + 6 = 29
# Opp active:    [species_id, hp, status]     = 3
# My team HP:    6
# Opp team HP:   6
# Field:         4  (weather, terrain, trick_room, turn)
# STAB flags:    4  ([48..51], one per move slot)
# Speed tier:    1  ([52], base-stat relative speed)
# Ability buckets: 14  ([53..66], own 8 + opp 6)
# Item buckets:   11  ([67..77], own 7 + opp 4)
OBS_DIM = 29 + 3 + 6 + 6 + 4 + 4 + 1 + 14 + 11  # = 78

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
    "normal": 1,
    "fire": 2,
    "water": 3,
    "electric": 4,
    "grass": 5,
    "ice": 6,
    "fighting": 7,
    "poison": 8,
    "ground": 9,
    "flying": 10,
    "psychic": 11,
    "bug": 12,
    "rock": 13,
    "ghost": 14,
    "dragon": 15,
    "dark": 16,
    "steel": 17,
    "fairy": 18,
    "stellar": 19,
}

STATUS_IDS: dict[Any, int] = {None: 0}
try:
    STATUS_IDS.update(
        {
            Status.BRN: 1,
            Status.PAR: 2,
            Status.SLP: 3,
            Status.FRZ: 4,
            Status.PSN: 5,
            Status.TOX: 6,
        }
    )
except Exception:  # pragma: no cover
    pass

WEATHER_IDS: dict[Any, int] = {None: 0}
TERRAIN_IDS: dict[Any, int] = {None: 0}
try:
    WEATHER_IDS.update(
        {
            Weather.SUNNYDAY: 1,
            Weather.RAINDANCE: 2,
            Weather.SANDSTORM: 3,
            Weather.SNOW: 4,
            Weather.HAIL: 5,
        }
    )
    TERRAIN_IDS.update(
        {
            Field.ELECTRIC_TERRAIN: 1,
            Field.GRASSY_TERRAIN: 2,
            Field.MISTY_TERRAIN: 3,
            Field.PSYCHIC_TERRAIN: 4,
        }
    )
except Exception:  # pragma: no cover
    pass


# ── Ability / item effect maps (ISS-008) ─────────────────────────────────────

SPEED_BOOST_ABILITIES = frozenset(
    {
        "speedboost",
        "swiftswim",
        "chlorophyll",
        "sandrush",
        "slushrush",
        "surgesurfer",
    }
)
ATK_BOOST_ABILITIES = frozenset(
    {
        "hugepower",
        "purepower",
        "guts",
        "hustle",
        "gorillatactics",
    }
)
REGEN_ABILITIES = frozenset({"regenerator", "naturalcure", "shedskin"})
PRIORITY_ABILITIES = frozenset({"prankster", "triage", "galewings"})
CONTACT_PUNISH_ABILITIES = frozenset(
    {
        "roughskin",
        "ironbarbs",
        "flamebody",
        "static",
        "poisonpoint",
        "effectspore",
    }
)
CONDITIONAL_BOOST_ABILITIES = frozenset({"unburden", "moxie", "beastboost"})

# Intimidate → -1.0 (atk drop on opponent); Dauntless Shield / Intrepid Sword → +1.0
ENTRY_EFFECT_ABILITIES: dict[str, float] = {
    "intimidate": -1.0,
    "dauntlessshield": 1.0,
    "intrepidsword": 1.0,
}

# Absorption ability → absorbed type name (feeds into TYPE_IDS for the slot value)
ABSORB_TYPE_ABILITIES: dict[str, str] = {
    "voltabsorb": "electric",
    "motordrive": "electric",
    "lightningrod": "electric",
    "waterabsorb": "water",
    "stormdrain": "water",
    "flashfire": "fire",
    "sapsipper": "grass",
}

CHOICE_ITEMS: dict[str, float] = {
    "choiceband": 0.33,
    "choicespecs": 0.67,
    "choicescarf": 1.0,
}
HEAL_ITEMS: dict[str, float] = {
    "leftovers": 0.0625,
    "blacksludge": 0.0625,
}
SPEED_ITEMS: dict[str, float] = {
    "choicescarf": 1.5,
    "ironball": 0.5,
    "laggingtail": 0.5,
}
SASH_ITEMS = frozenset({"focussash"})
OFFENCE_ITEMS: dict[str, float] = {
    "lifeorb": 1.0,
    "expertbelt": 0.5,
}
STATUS_ITEMS: dict[str, float] = {
    "lumberry": 1.0,
    "flameorb": -1.0,
    "toxicorb": -1.0,
}
DEFENSIVE_ITEMS = frozenset({"eviolite", "assaultvest", "rockyhelmet"})

# ── Observation builder ───────────────────────────────────────────────────────


def _move_features(move: "Move | None", target: "Pokemon | None" = None) -> list[float]:
    """Extract 5-float feature vector for one move slot."""
    if move is None:
        return [0.0, 0.0, 0.0, 0.0, 0.5]

    bp = min(getattr(move, "base_power", 0) or 0, 250) / 250.0
    acc = (getattr(move, "accuracy", 100) or 100) / 100.0
    type_id = (
        TYPE_IDS.get(str(getattr(move, "type", "")).lower().split(".")[-1], 0) / 20.0
    )

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


def _stab_flag(move: "Move | None", mon: "Pokemon | None") -> float:
    """1.0 if move shares a type with mon (STAB), 0.0 otherwise."""
    if move is None or mon is None:
        return 0.0
    try:
        move_type = str(getattr(move, "type", "")).lower().split(".")[-1]
        mon_types = [
            str(t).lower().split(".")[-1] for t in (getattr(mon, "types", None) or [])
        ]
    except Exception:
        return 0.0
    return 1.0 if move_type in mon_types else 0.0


def _speed_tier(active: "Pokemon | None", opp: "Pokemon | None") -> float:
    """Base-stat speed comparison: 1.0=faster, 0.5=unknown/equal, 0.0=slower."""
    if active is None or opp is None:
        return 0.5
    try:
        my_spe = int(getattr(active, "base_stats", {}).get("spe", 0) or 0)
        opp_spe = int(getattr(opp, "base_stats", {}).get("spe", 0) or 0)
    except (TypeError, ValueError):
        return 0.5
    if my_spe > opp_spe:
        return 1.0
    if my_spe < opp_spe:
        return 0.0
    return 0.5


def _norm(s: Any) -> str:
    """Normalize ability/item string to lowercase, no spaces or hyphens."""
    return str(s or "").lower().replace(" ", "").replace("-", "")


def _ability_buckets(ability: Any, *, is_own: bool) -> list[float]:
    """
    Convert an ability string to effect-bucket floats.
    Own (is_own=True):  8 floats [speed_boost, atk_boost, regen, priority,
                                    absorb_type_id, entry_effect, contact_punish, conditional]
    Opp (is_own=False): 6 floats [speed_boost, atk_boost, regen, priority,
                                    absorb_type_id, contact_punish]
    Unknown/None ability → all 0.0.
    """
    try:
        a = _norm(ability)
        absorb_type = ABSORB_TYPE_ABILITIES.get(a, "")
        absorb_val = TYPE_IDS.get(absorb_type, 0) / 20.0
        own_buckets = [
            1.0 if a in SPEED_BOOST_ABILITIES else 0.0,
            1.0 if a in ATK_BOOST_ABILITIES else 0.0,
            1.0 if a in REGEN_ABILITIES else 0.0,
            1.0 if a in PRIORITY_ABILITIES else 0.0,
            absorb_val,
            ENTRY_EFFECT_ABILITIES.get(a, 0.0),
            1.0 if a in CONTACT_PUNISH_ABILITIES else 0.0,
            1.0 if a in CONDITIONAL_BOOST_ABILITIES else 0.0,
        ]
        if is_own:
            return own_buckets
        # Opponent: omit entry_effect and conditional (less observable)
        return [
            own_buckets[0],
            own_buckets[1],
            own_buckets[2],
            own_buckets[3],
            own_buckets[4],
            own_buckets[6],
        ]
    except Exception:
        return [0.0] * (8 if is_own else 6)


def _item_buckets(item: Any, hp_frac: float, *, is_own: bool) -> list[float]:
    """
    Convert an item string + HP fraction to effect-bucket floats.
    Own (is_own=True):  7 floats [heal, choice, speed_mod, defensive, sash, offence, status]
    Opp (is_own=False): 4 floats [heal, choice, defensive, sash]
    Unknown/None/consumed item → all 0.0.
    """
    try:
        it = _norm(item)
        sash_val = 1.0 if (it in SASH_ITEMS and hp_frac >= 1.0) else 0.0
        own_buckets = [
            HEAL_ITEMS.get(it, 0.0),
            CHOICE_ITEMS.get(it, 0.0),
            SPEED_ITEMS.get(it, 1.0) if it in SPEED_ITEMS else 1.0,
            0.5 if it in DEFENSIVE_ITEMS else 0.0,
            sash_val,
            OFFENCE_ITEMS.get(it, 0.0),
            STATUS_ITEMS.get(it, 0.0),
        ]
        if is_own:
            return own_buckets
        # Opponent: heal, choice, defensive, sash (speed/offence/status less observable)
        return [own_buckets[0], own_buckets[1], own_buckets[3], own_buckets[4]]
    except Exception:
        return [0.0] * (7 if is_own else 4)


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
        obs[idx] = _stable_species_id(active.species)
        idx += 1
        obs[idx] = _pokemon_hp(active)
        idx += 1

        moves = list(battle.available_moves)
        opp_active = battle.opponent_active_pokemon
        for i in range(N_MOVES):
            move = moves[i] if i < len(moves) else None
            feats = _move_features(move, opp_active)
            obs[idx : idx + MOVE_FEATS] = feats
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

    # ── STAB flags [48..51] ────────────────────────────────────────
    stab_moves = (
        list(battle.available_moves) if hasattr(battle, "available_moves") else []
    )
    for i in range(N_MOVES):
        move = stab_moves[i] if i < len(stab_moves) else None
        obs[idx] = _stab_flag(move, active)
        idx += 1

    # ── Relative speed tier [52] ───────────────────────────────────
    obs[idx] = _speed_tier(active, opp)
    idx += 1

    # ── Ability buckets [53..66] ───────────────────────────────────
    active_ability = getattr(active, "ability", None)
    opp_ability = getattr(opp, "ability", None)
    for val in _ability_buckets(active_ability, is_own=True):  # 8 floats
        obs[idx] = val
        idx += 1
    for val in _ability_buckets(opp_ability, is_own=False):  # 6 floats
        obs[idx] = val
        idx += 1

    # ── Item buckets [67..77] ──────────────────────────────────────
    active_item = getattr(active, "item", None)
    opp_item = getattr(opp, "item", None)
    active_hp = _pokemon_hp(active)
    opp_hp = _pokemon_hp(opp)
    for val in _item_buckets(active_item, active_hp, is_own=True):  # 7 floats
        obs[idx] = val
        idx += 1
    for val in _item_buckets(opp_item, opp_hp, is_own=False):  # 4 floats
        obs[idx] = val
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
            # low=-1.0/high=2.0: covers intimidate/flameorb (-1.0) and choicescarf speed (1.5)
            obs_space = Box(low=-1.0, high=2.0, shape=(OBS_DIM,), dtype=np.float32)
            self.observation_spaces = {
                agent: obs_space for agent in self.possible_agents
            }
            # Track previous faint counts for shaped reward (keyed by battle_tag)
            self._prev_state: dict[str, dict[str, int]] = {}

        @property
        def action_space(self):
            if hasattr(self, "_sb3_action_space"):
                return self._sb3_action_space
            # Fallback during super().__init__() before _sb3_action_space is set
            return Discrete(N_ACTIONS_GEN9)

        @action_space.setter
        def action_space(self, space):
            self._sb3_action_space = space

        def order_to_action(
            self, order: Any, battle: Any, **kwargs: Any
        ) -> int:  # pragma: no cover
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
                # Note: self.observation_space is a method on the poke-env parent class,
                # not a property — use the concrete space we set in __init__ instead.
                obs_space = next(iter(self.observation_spaces.values()))
                obs = np.zeros(obs_space.shape, dtype=obs_space.dtype)
                return obs, 0.0, True, True, {}

        def embed_battle(self, battle: AbstractBattle) -> np.ndarray:
            _sort_team_dict(battle)
            return build_observation(battle)

        def calc_reward(self, battle: AbstractBattle) -> float:
            """
            Shaped reward per step:
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

    class BattleEnv:  # type: ignore
        observation_spaces = None
        action_spaces = None

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "poke-env is not properly installed. Run: pip install poke-env>=0.8.1"
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
                # Note: self.observation_space is a method on the poke-env parent class,
                # not a property — use the concrete space we set in __init__ instead.
                obs_space = next(iter(self.observation_spaces.values()))
                obs = np.zeros(obs_space.shape, dtype=obs_space.dtype)
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
                "poke-env is not properly installed. Run: pip install poke-env>=0.8.1"
            )
