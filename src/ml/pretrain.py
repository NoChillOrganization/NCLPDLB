"""
Behavioral Cloning Pre-Training — converts parsed Showdown replays into
(obs, action) pairs and trains a BC policy that warm-starts PPO.

Architecture
------------
  Replay JSON files
      ↓  parse_replay_dir()
  list[BattleRecord]
      ↓  ActionResolver.resolve()
  list[(obs: np.ndarray, action: int)]
      ↓  BC (imitation library)
  actor weights  →  bc_actor.pt
      ↓  PPO.policy.load_state_dict(..., strict=False)
  PPO fine-tune

Action space (gen9 singles, 26 actions):
  0-5   → switch to team slot 0-5
  6-9   → move 0-3 (no gimmick)
  22-25 → move 0-3 + terastallize
  (mega/z-move/dynamax not mapped — treated as unmappable)

Usage
-----
  python -m src.ml.pretrain data/replays/gen9ou \
      --format gen9ou --output bc_actor.pt

Requires: pip install imitation stable-baselines3 torch
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from src.ml.replay_parser import BattleRecord, TurnSnapshot

log = logging.getLogger(__name__)

# ── Action-mapping gap thresholds ─────────────────────────────────────────────

WARN_THRESHOLD  = 0.05   # 5 %  — log warning
ABORT_THRESHOLD = 0.15   # 15 % — raise RuntimeError unless force=True

# String status IDs matching battle_env's Status enum values
_STATUS_STR_IDS: dict[str, int] = {
    "brn": 1, "par": 2, "slp": 3, "frz": 4, "psn": 5, "tox": 6,
}

# Boost stats in the same order as build_observation() in battle_env.py
_BOOST_STATS = ["atk", "def", "spa", "spd", "spe", "accuracy"]


# ── Gap tracking ──────────────────────────────────────────────────────────────

def check_mapping_gap(unmappable: int, total: int, force: bool = False) -> float:
    """
    Validate action-mapping completeness; warn or abort on excessive gaps.

    Parameters
    ----------
    unmappable : int
        Number of turns whose move name could not be mapped to an action index.
    total : int
        Total number of turns processed.
    force : bool
        If True, downgrade an abort-threshold breach to a warning (research mode).

    Returns
    -------
    float
        The gap fraction (unmappable / total).
    """
    gap = unmappable / total if total > 0 else 0.0

    if gap > ABORT_THRESHOLD:
        msg = (
            f"Action mapping gap {gap:.1%} exceeds abort threshold "
            f"{ABORT_THRESHOLD:.0%}. "
            "Use --force to override for research runs."
        )
        if force:
            log.warning(msg)
        else:
            raise RuntimeError(msg)
    elif gap > WARN_THRESHOLD:
        log.warning(
            "Action mapping gap %.1f%% exceeds warn threshold %.0f%%.",
            gap * 100,
            WARN_THRESHOLD * 100,
        )

    return gap


# ── Observation builder (no poke-env required) ────────────────────────────────

def build_obs_from_snapshot(
    snapshot: "TurnSnapshot",
    player: str = "p1",
    p1_team: list[str] | None = None,
    p2_team: list[str] | None = None,
) -> np.ndarray:
    """
    Build a float32 observation vector from a TurnSnapshot without live poke-env objects.

    Mirrors build_observation() from battle_env.py using only data available in
    a parsed replay.  Approximations:
    - Move features (bp, accuracy, type, priority) are zero — moveset metadata
      is not present in replay logs.
    - Benched team HP defaults to 1.0 (unknown).
    - Weather, terrain, and trick room default to 0 (parser does not track field).

    Parameters
    ----------
    snapshot : TurnSnapshot
        Parsed turn snapshot from replay_parser.
    player : str
        Which side to build the obs for ("p1" or "p2").
    p1_team : list[str] | None
        Ordered species list for p1 (team preview or switch-in order).
    p2_team : list[str] | None
        Ordered species list for p2.

    Returns
    -------
    np.ndarray
        float32 array of shape (OBS_DIM,).
    """
    from src.ml.battle_env import BOOST_DIM, MOVE_FEATS, N_MOVES, OBS_DIM, TEAM_SIZE

    obs = np.zeros(OBS_DIM, dtype=np.float32)
    idx = 0

    opp = "p2" if player == "p1" else "p1"
    my_slot  = f"{player}a"
    opp_slot = f"{opp}a"
    my_active  = snapshot.p1_active if player == "p1" else snapshot.p2_active
    opp_active = snapshot.p2_active if player == "p1" else snapshot.p1_active
    my_team_list  = (p1_team or []) if player == "p1" else (p2_team or [])
    opp_team_list = (p2_team or []) if player == "p1" else (p1_team or [])

    # Derive HP, status, boosts from events within this turn
    hp_by_slot: dict[str, float]           = {}
    status_by_slot: dict[str, int]         = {}
    boosts_by_slot: dict[str, dict[str, int]] = {}

    for event in snapshot.events:
        slot = event.slot
        if not slot:
            continue
        if event.kind in ("damage", "heal", "switch", "faint") and event.hp_after >= 0:
            hp_by_slot[slot] = event.hp_after
        elif event.kind == "status":
            status_by_slot[slot] = _STATUS_STR_IDS.get(event.detail, 0)
        elif event.kind == "boost" and ":" in event.detail:
            stat, val_str = event.detail.split(":", 1)
            try:
                delta = int(val_str)
            except ValueError:
                continue
            slot_boosts = boosts_by_slot.setdefault(slot, {})
            slot_boosts[stat] = max(-6, min(6, slot_boosts.get(stat, 0) + delta))

    # ── Active Pokémon (29 dims) ───────────────────────────────────
    # Layout: species(1) + hp(1) + N_MOVES*MOVE_FEATS(20) + status(1) + boosts(6)
    if my_active:
        obs[idx] = hash(my_active) % 10000 / 10000.0
        idx += 1
        obs[idx] = hp_by_slot.get(my_slot, 1.0)
        idx += 1
        # Move features: zero-filled (no moveset metadata in replay logs)
        idx += N_MOVES * MOVE_FEATS
        obs[idx] = status_by_slot.get(my_slot, 0) / 6.0
        idx += 1
        boosts = boosts_by_slot.get(my_slot, {})
        for stat in _BOOST_STATS:
            obs[idx] = (max(-6, min(6, boosts.get(stat, 0))) + 6) / 12.0
            idx += 1
    else:
        idx += 29

    # ── Opponent active (3 dims) ───────────────────────────────────
    if opp_active:
        obs[idx] = hash(opp_active) % 10000 / 10000.0
        idx += 1
        obs[idx] = hp_by_slot.get(opp_slot, 1.0)
        idx += 1
        obs[idx] = status_by_slot.get(opp_slot, 0) / 6.0
        idx += 1
    else:
        idx += 3

    # ── My team HP (6 dims) ────────────────────────────────────────
    for i in range(TEAM_SIZE):
        if i < len(my_team_list) and my_team_list[i] == my_active:
            obs[idx] = hp_by_slot.get(my_slot, 1.0)
        else:
            obs[idx] = 1.0  # benched HP unknown — assume full
        idx += 1

    # ── Opponent team HP (6 dims) ──────────────────────────────────
    for i in range(TEAM_SIZE):
        if i < len(opp_team_list) and opp_team_list[i] == opp_active:
            obs[idx] = hp_by_slot.get(opp_slot, 1.0)
        else:
            obs[idx] = 1.0
        idx += 1

    # ── Field (4 dims) ─────────────────────────────────────────────
    obs[idx] = 0.0  # weather  (parser does not track)
    idx += 1
    obs[idx] = 0.0  # terrain  (parser does not track)
    idx += 1
    obs[idx] = 0.0  # trick room (parser does not track)
    idx += 1
    obs[idx] = min(snapshot.turn_number, 50) / 50.0
    idx += 1

    assert idx == OBS_DIM, f"Obs dim mismatch: {idx} != {OBS_DIM}"
    return obs


# ── Action resolver ───────────────────────────────────────────────────────────

class ActionResolver:
    """
    Maps parsed BattleRecord turns into (obs, action_idx) pairs for BC training.

    Move-slot indices are discovered incrementally — the first move seen for a
    species gets slot 0, the second slot 1, etc.  A fifth distinct move triggers
    an unmappable count (Transform, Impersonator, mid-battle forme changes).

    Switch actions use the team's team-preview (or first-seen) order.
    Tera is detected by a "tera" event for the player's slot earlier in the same
    turn than the "move" event.
    """

    def __init__(self, player: str = "p1") -> None:
        self._player   = player
        self._slot     = f"{player}a"
        # Per-species discovered moveset, ordered by first appearance
        self._movesets: dict[str, list[str]] = {}
        self._unmappable = 0
        self._total      = 0

    @property
    def unmappable(self) -> int:
        """Number of turns that could not be mapped to an action index."""
        return self._unmappable

    @property
    def total(self) -> int:
        """Total number of turns processed."""
        return self._total

    def resolve(self, record: "BattleRecord") -> list[tuple[np.ndarray, int]]:
        """
        Walk all turns in *record* and produce (obs, action_idx) pairs for
        the configured player's perspective.

        Parameters
        ----------
        record : BattleRecord
            Fully parsed battle from replay_parser.parse_replay_json / parse_replay_file.

        Returns
        -------
        list[tuple[np.ndarray, int]]
            (obs, action_index) pairs, one per mappable turn.
        """
        p1_team = list(record.p1_team)
        p2_team = list(record.p2_team)
        my_team = p1_team if self._player == "p1" else p2_team

        pairs: list[tuple[np.ndarray, int]] = []
        for snap in record.turns:
            obs    = build_obs_from_snapshot(snap, player=self._player,
                                             p1_team=p1_team, p2_team=p2_team)
            action = self._action_for_turn(snap, my_team)
            self._total += 1
            if action is None:
                self._unmappable += 1
            else:
                pairs.append((obs, action))
        return pairs

    def _action_for_turn(
        self, snap: "TurnSnapshot", my_team: list[str]
    ) -> int | None:
        """Return the action index the player took this turn, or None if unmappable."""
        active_species = snap.p1_active if self._player == "p1" else snap.p2_active

        # Check if tera happened for this slot before the move event
        tera_this_turn = False
        for event in snap.events:
            if event.slot != self._slot:
                continue
            if event.kind == "tera":
                tera_this_turn = True
            elif event.kind in ("move", "switch"):
                break  # stop scanning once we hit the action event

        # Find the first action event for this slot
        for event in snap.events:
            if event.slot != self._slot:
                continue
            if event.kind == "switch":
                species = event.detail
                if species in my_team:
                    return my_team.index(species)
                return None
            if event.kind == "move":
                return self._map_move(active_species, event.detail, tera_this_turn)

        return None  # no action found for this player this turn

    def _map_move(self, species: str, move_name: str, tera: bool) -> int | None:
        """
        Map a move name to its action index.

        Returns
        -------
        int | None
            6-9 (no gimmick), 22-25 (tera), or None if the 5th distinct move
            is seen for this species (unmappable).
        """
        moveset = self._movesets.setdefault(species, [])
        if move_name not in moveset:
            if len(moveset) >= 4:
                return None  # more than 4 moves — unmappable
            moveset.append(move_name)
        slot = moveset.index(move_name)
        return (22 + slot) if tera else (6 + slot)


# ── Full BC pipeline ──────────────────────────────────────────────────────────

def pretrain(
    replay_dir: Path,
    fmt: str,
    output_path: Path,
    force: bool = False,
    n_epochs: int = 10,
    batch_size: int = 64,
) -> None:
    """
    Full BC pre-training pipeline: parse → resolve → train → save actor weights.

    Requires: pip install imitation stable-baselines3 torch

    Parameters
    ----------
    replay_dir :  Directory of *.json replay files for the target format.
    fmt :         Format string (e.g. 'gen9ou') — informational only.
    output_path : Where to save the BC actor weights (.pt file).
    force :       If True, bypass the 15 % action-mapping gap abort.
    n_epochs :    Number of BC training epochs.
    batch_size :  Mini-batch size for BC training.
    """
    try:
        import torch
        from imitation.algorithms.bc import BC
        from imitation.data.types import Transitions
        from stable_baselines3 import PPO
    except ImportError as exc:
        raise ImportError(
            "pretrain() requires additional packages: "
            "pip install imitation stable-baselines3 torch"
        ) from exc

    from gymnasium.spaces import Box, Discrete
    from src.ml.battle_env import N_ACTIONS_GEN9, OBS_DIM
    from src.ml.replay_parser import parse_replay_dir as _parse_dir

    replay_dir   = Path(replay_dir)
    output_path  = Path(output_path)

    log.info("[pretrain] Parsing replays in %s ...", replay_dir)
    records = _parse_dir(replay_dir)
    if not records:
        raise ValueError(f"No replay JSON files found in {replay_dir}")
    log.info("[pretrain] Parsed %d replays", len(records))

    resolver: ActionResolver = ActionResolver(player="p1")
    all_pairs: list[tuple[np.ndarray, int]] = []
    for record in records:
        all_pairs.extend(resolver.resolve(record))

    check_mapping_gap(resolver.unmappable, resolver.total, force=force)
    log.info(
        "[pretrain] %d (obs, action) pairs from %d turns (%d unmappable, %.1f%% gap)",
        len(all_pairs), resolver.total, resolver.unmappable,
        resolver.unmappable / resolver.total * 100 if resolver.total else 0.0,
    )

    if not all_pairs:
        raise ValueError(
            "No mappable (obs, action) pairs found — verify replay format and player slot."
        )

    obs_arr  = np.stack([p[0] for p in all_pairs]).astype(np.float32)
    act_arr  = np.array([p[1] for p in all_pairs], dtype=np.int64)
    # Imitation Transitions requires next_obs, dones, infos — use dummies
    next_obs = np.zeros_like(obs_arr)
    dones    = np.zeros(len(obs_arr), dtype=bool)
    infos    = np.array([{}] * len(obs_arr))

    obs_space = Box(low=0.0, high=1.0, shape=(OBS_DIM,), dtype=np.float32)
    act_space = Discrete(N_ACTIONS_GEN9)

    transitions = Transitions(
        obs=obs_arr, acts=act_arr, next_obs=next_obs, dones=dones, infos=infos,
    )

    # Minimal dummy env so PPO can build the policy network
    from gymnasium import Env as _Env
    class _DummyEnv(_Env):
        observation_space = obs_space
        action_space      = act_space
        def reset(self, **_kw):  return np.zeros(OBS_DIM, dtype=np.float32), {}
        def step(self, _a):      return np.zeros(OBS_DIM, dtype=np.float32), 0.0, True, False, {}

    ppo = PPO("MlpPolicy", _DummyEnv())
    bc_trainer = BC(
        observation_space=obs_space,
        action_space=act_space,
        demonstrations=transitions,
        policy=ppo.policy,
        rng=np.random.default_rng(42),
        batch_size=batch_size,
    )

    log.info("[pretrain] Training BC for %d epoch(s) ...", n_epochs)
    bc_trainer.train(n_epochs=n_epochs)

    # Save actor-only weights; exclude value head so PPO can load with strict=False
    actor_weights = {
        k: v for k, v in ppo.policy.state_dict().items()
        if not k.startswith("value_net") and not k.startswith("mlp_extractor.value_net")
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(actor_weights, output_path)
    log.info("[pretrain] Saved BC actor weights → %s", output_path)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser(
        description="BC pre-train a PPO policy from Showdown replay JSON files"
    )
    ap.add_argument("replay_dir", type=Path,
                    help="Directory of replay JSON files (e.g. data/replays/gen9ou)")
    ap.add_argument("--format",     required=True,
                    help="Format string (e.g. gen9ou)")
    ap.add_argument("--output",     type=Path, default=Path("bc_actor.pt"),
                    help="Output path for BC actor weights (default: bc_actor.pt)")
    ap.add_argument("--epochs",     type=int,  default=10,
                    help="BC training epochs (default: 10)")
    ap.add_argument("--batch-size", type=int,  default=64,
                    help="BC mini-batch size (default: 64)")
    ap.add_argument("--force",      action="store_true",
                    help="Bypass 15%% action-mapping gap abort for research runs")
    args = ap.parse_args()

    try:
        pretrain(
            replay_dir=args.replay_dir,
            fmt=args.format,
            output_path=args.output,
            force=args.force,
            n_epochs=args.epochs,
            batch_size=args.batch_size,
        )
    except (ValueError, RuntimeError) as exc:
        log.error("%s", exc)
        sys.exit(1)
