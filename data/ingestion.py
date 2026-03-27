"""
data/ingestion.py — Offline Replay Ingestion

Converts scraped Showdown replay JSON files (stored by data_pipeline.py) into
the OBS_DIM=48 transition format consumed by ReplayBuffer, so the self-play
training loop can be pre-seeded with real competitive game data.

The key bridge this module provides:

  Offline replay pipeline  →  Real-time RL observation space
  (STATE_FEATURE_DIM=19)       (OBS_DIM=48, battle_env.py)

Observation vector layout (48 dims, mirrors battle_env.py):
  [0]      active species ID (normalised from vocabulary)
  [1]      active hp_pct
  [2-21]   4 moves × 5 features — zero-padded (unavailable in replays)
  [22]     active status ID (normalised)
  [23-28]  stat boosts × 6 — zero-padded
  [29]     opponent active species ID
  [30]     opponent hp_pct
  [31]     opponent status ID
  [32-37]  own team hp_pct (6 slots)
  [38-43]  opponent team hp_pct (6 slots)
  [44]     weather ID (normalised)
  [45]     terrain ID (normalised)
  [46]     trick_room flag
  [47]     turn / 50 (normalised)

Action inference from replay events (maps to the 26-action space):
  switch → slot 0-5 in team list
  move   → 6 (slot 0, no gimmick) — exact move slot unknown from replay
  tera   → 22 (slot 0 + terastallise offset)

Usage:
    from data.ingestion import ReplayIngester
    from src.ml.trainer import ReplayBuffer

    buffer   = ReplayBuffer(capacity=50_000)
    ingester = ReplayIngester()
    n = ingester.ingest_into_buffer(buffer, formats=["gen9ou"], max_battles=500)
    print(f"Seeded buffer with {n} transitions from replays")

Standalone (seeds buffer and prints stats):
    python data/ingestion.py --formats gen9ou --max-battles 500
"""
from __future__ import annotations

import argparse
import json
import logging
import random
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent
_REPLAYS_DIR  = _PROJECT_ROOT / "data" / "replays"
_VOCAB_DIR    = _PROJECT_ROOT / "data" / "ml" / "vocab"

# ---------------------------------------------------------------------------
# Observation constants (must stay in sync with battle_env.OBS_DIM = 48)
# ---------------------------------------------------------------------------

OBS_DIM = 48

_I_ACT_SPECIES = 0
_I_ACT_HP      = 1
_I_MOVES       = slice(2, 22)    # 4 moves × 5 feats — zero-padded from replays
_I_STATUS      = 22
_I_BOOSTS      = slice(23, 29)   # 6 boosts — zero-padded from replays
_I_OPP_SPECIES = 29
_I_OPP_HP      = 30
_I_OPP_STATUS  = 31
_I_MY_TEAM_HP  = slice(32, 38)
_I_OPP_TEAM_HP = slice(38, 44)
_I_WEATHER     = 44
_I_TERRAIN     = 45
_I_TRICK_ROOM  = 46
_I_TURN_NORM   = 47

# Action space indices (matches battle_env.py)
_ACTION_SWITCH_BASE = 0     # +slot_index → 0-5
_ACTION_MOVE_BASE   = 6     # +move_slot  → 6-9
_ACTION_TERA_BASE   = 22    # +move_slot  → 22-25

# Normalisation denominators
_MAX_STATUS_ID  = 6.0
_MAX_WEATHER_ID = 10.0
_MAX_TERRAIN_ID = 4.0

_STATUS_IDS: dict[str, float] = {
    "brn": 1 / _MAX_STATUS_ID, "par": 2 / _MAX_STATUS_ID,
    "slp": 3 / _MAX_STATUS_ID, "frz": 4 / _MAX_STATUS_ID,
    "psn": 5 / _MAX_STATUS_ID, "tox": 6 / _MAX_STATUS_ID,
}

_WEATHER_IDS: dict[str, float] = {
    "sunnyday": 1 / _MAX_WEATHER_ID, "desolateland": 1 / _MAX_WEATHER_ID,
    "raindance": 2 / _MAX_WEATHER_ID, "primordialsea": 2 / _MAX_WEATHER_ID,
    "sandstorm": 3 / _MAX_WEATHER_ID,
    "hail": 4 / _MAX_WEATHER_ID, "snow": 4 / _MAX_WEATHER_ID,
}

_TERRAIN_IDS: dict[str, float] = {
    "electricterrain": 1 / _MAX_TERRAIN_ID, "grassyterrain": 2 / _MAX_TERRAIN_ID,
    "mistyterrain": 3 / _MAX_TERRAIN_ID, "psychicterrain": 4 / _MAX_TERRAIN_ID,
}


# ---------------------------------------------------------------------------
# Vocabulary loading
# ---------------------------------------------------------------------------

def _load_species_vocab(vocab_dir: Path) -> dict[str, float]:
    """
    Load species-name → normalised-ID mapping from the FeatureExtractor vocab.

    Returns an empty dict if the vocab hasn't been built yet (replay pipeline
    hasn't been run).  Callers should treat missing IDs as 0.0 (UNKNOWN).
    """
    for candidate in ("species_vocab.json", "vocab.json"):
        p = vocab_dir / candidate
        if not p.exists():
            continue
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            token2id: dict[str, int] = raw.get("token2id", raw)
            if not token2id:
                continue
            max_id = max(token2id.values()) or 1
            return {k: v / max_id for k, v in token2id.items()}
        except Exception as exc:
            log.warning("Failed to load vocab from %s: %s", p, exc)
    return {}


# ---------------------------------------------------------------------------
# Per-battle state tracker
# ---------------------------------------------------------------------------

class _BattleState:
    """
    Tracks mutable state (HP, status, field) across turns for one BattleRecord.

    Rather than replaying the full simulator, we approximate state by:
    - tracking each named Pokemon's HP percentage from damage/heal/faint events
    - tracking active-slot status conditions
    - tracking global field conditions (weather, terrain, trick room)
    """

    def __init__(self, p1_team: list[str], p2_team: list[str]) -> None:
        # Pad/trim both rosters to exactly 6 slots
        def _pad(t: list[str]) -> list[str]:
            return (list(t) + [""] * 6)[:6]

        self.p1_team = _pad(p1_team)
        self.p2_team = _pad(p2_team)

        # HP per species name; defaults to 1.0 (full health)
        self._species_hp: dict[str, float] = {}

        # Status per active slot ("p1a", "p2a")
        self._slot_status: dict[str, str] = {}

        # Field
        self.weather    = 0.0
        self.terrain    = 0.0
        self.trick_room = 0.0

    # ── Public accessors ──────────────────────────────────────────────

    def hp(self, species: str) -> float:
        return max(0.0, min(1.0, self._species_hp.get(species, 1.0)))

    def status(self, slot: str) -> float:
        return _STATUS_IDS.get(self._slot_status.get(slot, ""), 0.0)

    def team_hps(self, team: list[str]) -> list[float]:
        return [self.hp(s) if s else 0.0 for s in team]

    # ── State updates ─────────────────────────────────────────────────

    def apply_events(
        self,
        events: list[Any],
        active: dict[str, str],
    ) -> None:
        """
        Update tracked state from a turn's event list.

        ``active`` maps slot names ("p1a", "p2a") to current species names.
        """
        for evt in events:
            kind = evt.kind

            if kind in ("damage", "heal") and evt.hp_after >= 0.0:
                species = active.get(evt.slot, "")
                if species:
                    self._species_hp[species] = float(evt.hp_after)

            elif kind == "faint":
                species = active.get(evt.slot, "")
                if species:
                    self._species_hp[species] = 0.0

            elif kind == "status":
                self._slot_status[evt.slot] = evt.detail

            elif kind == "switch":
                # Carry over previous HP if available; new active species
                # gets its own entry on first damage event
                species = evt.detail
                active[evt.slot] = species   # update the shared active map
                # If we've never seen this Pokemon, it enters at full HP
                if species not in self._species_hp:
                    self._species_hp[species] = 1.0

            elif kind == "other":
                detail_lower = evt.detail.lower()
                if detail_lower in _WEATHER_IDS:
                    self.weather = _WEATHER_IDS[detail_lower]
                elif detail_lower in _TERRAIN_IDS:
                    self.terrain = _TERRAIN_IDS[detail_lower]
                elif "trickroom" in detail_lower:
                    self.trick_room = 1.0 - self.trick_room  # toggle

    # ── Observation builder ───────────────────────────────────────────

    def build_obs(
        self,
        p1_active: str,
        p2_active: str,
        turn_number: int,
        species_vocab: dict[str, float],
    ) -> np.ndarray:
        """
        Build an OBS_DIM=48 observation from p1's perspective.

        Fields unavailable from replays (move power, type, boosts) are
        zero-padded; the resulting vector is compatible with BattleTransformer
        input but will be weaker than real-time observations.
        """
        obs = np.zeros(OBS_DIM, dtype=np.float32)

        # ── Own active Pokemon ──────────────────────────────────────────
        obs[_I_ACT_SPECIES] = species_vocab.get(p1_active, 0.0)
        obs[_I_ACT_HP]      = self.hp(p1_active)
        # obs[2:22] — move features — stay zero
        obs[_I_STATUS]      = self.status("p1a")
        # obs[23:29] — boosts — stay zero

        # ── Opponent active Pokemon ──────────────────────────────────────
        obs[_I_OPP_SPECIES] = species_vocab.get(p2_active, 0.0)
        obs[_I_OPP_HP]      = self.hp(p2_active)
        obs[_I_OPP_STATUS]  = self.status("p2a")

        # ── Team HP arrays ───────────────────────────────────────────────
        obs[_I_MY_TEAM_HP]  = self.team_hps(self.p1_team)
        obs[_I_OPP_TEAM_HP] = self.team_hps(self.p2_team)

        # ── Field ────────────────────────────────────────────────────────
        obs[_I_WEATHER]    = self.weather
        obs[_I_TERRAIN]    = self.terrain
        obs[_I_TRICK_ROOM] = self.trick_room
        obs[_I_TURN_NORM]  = min(turn_number / 50.0, 1.0)

        return obs


# ---------------------------------------------------------------------------
# Action inference
# ---------------------------------------------------------------------------

def _infer_action(events: list[Any], perspective: str, team: list[str]) -> int:
    """
    Infer the action taken by `perspective` ("p1" or "p2") from a turn's events.

    Returns an integer action index (0-25) that maps to the RL action space:
      0-5   switch to team slot
      6-9   use move (no gimmick)
      22-25 use move + terastallise

    Defaults to action 6 (first move, no gimmick) when nothing more specific
    can be determined.
    """
    active_slot = f"{perspective}a"
    has_tera    = False

    for evt in events:
        # Detect terastallise flag on this turn for perspective player
        if evt.kind == "tera" and evt.slot.startswith(perspective):
            has_tera = True

    for evt in events:
        if not evt.slot.startswith(perspective):
            continue

        if evt.kind == "switch":
            species = evt.detail
            try:
                slot_idx = team.index(species)
            except ValueError:
                slot_idx = 0
            return _ACTION_SWITCH_BASE + min(slot_idx, 5)

        if evt.kind == "move":
            base = _ACTION_TERA_BASE if has_tera else _ACTION_MOVE_BASE
            return base  # slot 0 — exact move slot unknown from replay

    # No decisive event found; default to first move
    return _ACTION_MOVE_BASE


def _one_hot_action(action: int, n_actions: int = 26) -> np.ndarray:
    """Return a one-hot action probability vector for supervised learning."""
    probs = np.zeros(n_actions, dtype=np.float32)
    probs[action] = 1.0
    return probs


# ---------------------------------------------------------------------------
# Replay-to-transitions converter
# ---------------------------------------------------------------------------

def record_to_transitions(
    record: Any,
    species_vocab: dict[str, float],
    perspective: str = "winner",
) -> tuple[list[np.ndarray], list[int], list[np.ndarray], float]:
    """
    Convert a single BattleRecord into lists of (obs, action, action_probs)
    tuples plus a scalar terminal reward, ready for ReplayBuffer.add_game().

    Parameters
    ----------
    record:
        A BattleRecord from replay_parser.
    species_vocab:
        Species-name → normalised-ID mapping from _load_species_vocab().
    perspective:
        "p1"     — always extract p1's actions (may include losses)
        "p2"     — always extract p2's actions
        "winner" — extract winner's actions only (skips ties/unknown)

    Returns
    -------
    (observations, actions, action_probs_list, reward)
    Empty lists with reward=0.0 for battles that should be skipped.
    """
    winner = record.winner   # "p1" | "p2" | "tie" | "unknown"

    if perspective == "winner":
        if winner not in ("p1", "p2"):
            return [], [], [], 0.0
        player = winner
    elif perspective in ("p1", "p2"):
        player = perspective
    else:
        raise ValueError(f"perspective must be 'p1', 'p2', or 'winner'; got {perspective!r}")

    # Terminal reward: +1 if this player won, -1 if lost, 0 if tie
    if winner == player:
        reward = 1.0
    elif winner in ("p1", "p2"):
        reward = -1.0
    else:
        reward = 0.0

    p1_team = list(record.p1_team)
    p2_team = list(record.p2_team)
    team    = p1_team if player == "p1" else p2_team

    state = _BattleState(p1_team, p2_team)

    observations:      list[np.ndarray] = []
    actions:           list[int]        = []
    action_probs_list: list[np.ndarray] = []

    # Active species tracker shared with _BattleState.apply_events()
    active: dict[str, str] = {
        "p1a": p1_team[0] if p1_team else "",
        "p2a": p2_team[0] if p2_team else "",
    }

    for turn in record.turns:
        p1_active = turn.p1_active or active.get("p1a", "")
        p2_active = turn.p2_active or active.get("p2a", "")

        # Build observation BEFORE applying this turn's events (pre-decision state)
        if player == "p1":
            obs = state.build_obs(p1_active, p2_active, turn.turn_number, species_vocab)
        else:
            # Flip perspective: my active is p2_active, opponent is p1_active
            obs = state.build_obs(p2_active, p1_active, turn.turn_number, species_vocab)
            # Swap team HP halves in the observation
            my_hp  = obs[_I_MY_TEAM_HP].copy()
            opp_hp = obs[_I_OPP_TEAM_HP].copy()
            obs[_I_MY_TEAM_HP]  = opp_hp
            obs[_I_OPP_TEAM_HP] = my_hp

        # Infer the action this player took in this turn
        action = _infer_action(turn.events, player, team)

        # Apply events to update state for subsequent turns
        state.apply_events(turn.events, active)

        observations.append(obs)
        actions.append(action)
        action_probs_list.append(_one_hot_action(action))

    return observations, actions, action_probs_list, reward


# ---------------------------------------------------------------------------
# Main ingester class
# ---------------------------------------------------------------------------

class ReplayIngester:
    """
    Loads scraped replay JSON files and converts them into ReplayBuffer
    transitions for pre-training the BattleTransformer before self-play starts.

    Parameters
    ----------
    replays_dir:
        Root directory that contains per-format sub-directories of replay
        JSON files.  Defaults to ``data/replays/``.
    vocab_dir:
        Directory containing ``species_vocab.json`` produced by
        ``data_pipeline.py``.  Defaults to ``data/ml/vocab/``.
    """

    def __init__(
        self,
        replays_dir: Path | str | None = None,
        vocab_dir: Path | str | None   = None,
    ) -> None:
        self._replays_dir    = Path(replays_dir) if replays_dir else _REPLAYS_DIR
        self._vocab_dir      = Path(vocab_dir)   if vocab_dir   else _VOCAB_DIR
        self._species_vocab: dict[str, float] | None = None

    # ── Lazy vocab loading ────────────────────────────────────────────

    def _get_vocab(self) -> dict[str, float]:
        if self._species_vocab is None:
            self._species_vocab = _load_species_vocab(self._vocab_dir)
            log.info(
                "Species vocab loaded: %d entries from %s",
                len(self._species_vocab),
                self._vocab_dir,
            )
        return self._species_vocab

    # ── Public API ────────────────────────────────────────────────────

    def list_available_formats(self) -> list[str]:
        """Return format names that have at least one replay JSON file."""
        if not self._replays_dir.exists():
            return []
        return sorted(
            d.name
            for d in self._replays_dir.iterdir()
            if d.is_dir() and any(d.glob("*.json"))
        )

    def count_replays(self, fmt: str) -> int:
        """Return the number of replay JSON files available for a format."""
        replay_dir = self._replays_dir / fmt
        if not replay_dir.exists():
            return 0
        return len(list(replay_dir.glob("*.json")))

    def ingest_into_buffer(
        self,
        buffer: Any,
        formats: list[str] | None = None,
        max_battles: int          = 1000,
        min_rating: int           = 0,
        perspective: str          = "winner",
        shuffle: bool             = True,
    ) -> int:
        """
        Load replay files, convert to transitions, and push into ``buffer``.

        Parameters
        ----------
        buffer:
            A ReplayBuffer instance (src.ml.trainer.ReplayBuffer).
        formats:
            List of format IDs to load (e.g. ``["gen9ou", "gen9vgc2024regh"]``).
            Defaults to all available formats.
        max_battles:
            Maximum number of replays to ingest across all formats.
        min_rating:
            Skip replays below this rating threshold.
        perspective:
            Which player's moves to learn from: "winner", "p1", or "p2".
        shuffle:
            Shuffle the replay file order before selecting up to max_battles.

        Returns
        -------
        Total number of transitions added to the buffer.
        """
        from src.ml.replay_parser import parse_replay_json

        if formats is None:
            formats = self.list_available_formats()

        if not formats:
            log.warning("No replay formats available in %s", self._replays_dir)
            return 0

        vocab = self._get_vocab()

        # Collect all available replay paths across requested formats
        replay_paths: list[Path] = []
        for fmt in formats:
            fmt_dir = self._replays_dir / fmt
            if fmt_dir.exists():
                replay_paths.extend(fmt_dir.glob("*.json"))

        if not replay_paths:
            log.warning("No replay JSON files found for formats: %s", formats)
            return 0

        if shuffle:
            random.shuffle(replay_paths)

        replay_paths = replay_paths[:max_battles]
        log.info(
            "Ingesting up to %d replays from %d format(s) (perspective=%s)",
            len(replay_paths), len(formats), perspective,
        )

        total_transitions = 0
        skipped           = 0

        for path in replay_paths:
            try:
                raw    = json.loads(path.read_text(encoding="utf-8"))
                record = parse_replay_json(raw)
            except Exception as exc:
                log.debug("Failed to parse %s: %s", path.name, exc)
                skipped += 1
                continue

            if min_rating and record.rating < min_rating:
                skipped += 1
                continue

            obs_list, act_list, probs_list, reward = record_to_transitions(
                record, vocab, perspective=perspective
            )

            if not obs_list:
                skipped += 1
                continue

            buffer.add_game(obs_list, act_list, probs_list, reward)
            total_transitions += len(obs_list)

        log.info(
            "Ingestion complete: %d transitions from %d battles (%d skipped)",
            total_transitions, len(replay_paths) - skipped, skipped,
        )
        return total_transitions

    def ingest_to_arrays(
        self,
        formats: list[str] | None = None,
        max_battles: int           = 1000,
        min_rating: int            = 0,
        perspective: str           = "winner",
        shuffle: bool              = True,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Load replays and return raw numpy arrays (obs, actions) without
        requiring a ReplayBuffer.  Useful for offline supervised training.

        Returns
        -------
        obs     : float32 array of shape (N, OBS_DIM)
        actions : int64   array of shape (N,)
        """
        from src.ml.replay_parser import parse_replay_json

        if formats is None:
            formats = self.list_available_formats()

        vocab = self._get_vocab()

        replay_paths: list[Path] = []
        for fmt in (formats or []):
            fmt_dir = self._replays_dir / fmt
            if fmt_dir.exists():
                replay_paths.extend(fmt_dir.glob("*.json"))

        if shuffle:
            random.shuffle(replay_paths)
        replay_paths = replay_paths[:max_battles]

        all_obs:  list[np.ndarray] = []
        all_acts: list[int]        = []

        for path in replay_paths:
            try:
                raw    = json.loads(path.read_text(encoding="utf-8"))
                record = parse_replay_json(raw)
            except Exception:
                continue

            if min_rating and record.rating < min_rating:
                continue

            obs_list, act_list, _, _ = record_to_transitions(
                record, vocab, perspective=perspective
            )
            all_obs.extend(obs_list)
            all_acts.extend(act_list)

        if not all_obs:
            return np.empty((0, OBS_DIM), dtype=np.float32), np.empty(0, dtype=np.int64)

        return (
            np.stack(all_obs,  axis=0).astype(np.float32),
            np.array(all_acts, dtype=np.int64),
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="data.ingestion",
        description=(
            "Ingest scraped Showdown replays into the ReplayBuffer "
            "for pre-training BattleTransformer."
        ),
    )
    parser.add_argument(
        "--formats", nargs="+", default=None, metavar="FORMAT",
        help="Format IDs to load (default: all available).",
    )
    parser.add_argument(
        "--max-battles", type=int, default=500, dest="max_battles",
        help="Maximum replays to ingest (default: 500).",
    )
    parser.add_argument(
        "--min-rating", type=int, default=0, dest="min_rating",
        help="Skip replays below this rating (default: 0).",
    )
    parser.add_argument(
        "--perspective", default="winner",
        choices=["winner", "p1", "p2"],
        help="Whose moves to learn from (default: winner).",
    )
    parser.add_argument(
        "--buffer-size", type=int, default=50_000, dest="buffer_size",
        help="ReplayBuffer capacity (default: 50000).",
    )
    return parser


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    args = _build_parser().parse_args()

    try:
        from src.ml.trainer import ReplayBuffer
        buffer = ReplayBuffer(capacity=args.buffer_size)
    except ImportError:
        log.warning(
            "src.ml.trainer not importable (missing PyTorch?). "
            "Running ingest_to_arrays() instead."
        )
        buffer = None

    ingester = ReplayIngester()

    available = ingester.list_available_formats()
    if not available:
        print("No replays found. Run data_pipeline.py first to scrape replays.")
    else:
        print(f"Available formats: {available}")

    if buffer is not None:
        n = ingester.ingest_into_buffer(
            buffer,
            formats=args.formats,
            max_battles=args.max_battles,
            min_rating=args.min_rating,
            perspective=args.perspective,
        )
        print(f"\nSeeded ReplayBuffer with {n} transitions (buffer size: {len(buffer)})")
    else:
        obs, acts = ingester.ingest_to_arrays(
            formats=args.formats,
            max_battles=args.max_battles,
            min_rating=args.min_rating,
            perspective=args.perspective,
        )
        print(f"\nLoaded {len(obs)} transitions: obs={obs.shape}, acts={acts.shape}")
