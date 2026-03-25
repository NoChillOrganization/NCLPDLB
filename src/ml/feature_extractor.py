"""
Feature Extractor — converts BattleRecord objects into numpy arrays for ML models.

Two feature spaces are produced:

  1. TEAM features (one row per battle)
     Used for: matchup prediction (who wins given two full rosters?)
     Shape: (n_battles, TEAM_FEATURE_DIM)

  2. STATE features (one row per turn)
     Used for: battle policy learning (what's the best move right now?)
     Shape: (n_turns, STATE_FEATURE_DIM)

Both feature spaces use integer Pokemon IDs from a vocabulary that is built
the first time you call build_vocabulary() and then saved to disk so it stays
consistent across training runs.

Usage:
    from src.ml.feature_extractor import FeatureExtractor, build_dataset

    extractor = FeatureExtractor.load_or_create("data/ml/vocab.json")
    X, y = extractor.team_features(records)   # matchup model training data
    # X shape: (n_battles, TEAM_FEATURE_DIM)
    # y shape: (n_battles,)  — 1 if p1 won, 0 if p2 won
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np
from src.ml.type_chart import get_type_effectiveness_float

if TYPE_CHECKING:
    from poke_env.battle import AbstractBattle
    from src.ml.replay_parser import BattleRecord

log = logging.getLogger(__name__)

# ── Vocabulary constants ──────────────────────────────────────────────────────

UNKNOWN_ID  = 0     # reserved for species not seen in training
TEAM_SIZE   = 6     # Pokemon per team in team preview

# ── Feature dimensions ────────────────────────────────────────────────────────

# Team feature vector layout:
#   [p1_poke_0 ... p1_poke_5,  p2_poke_0 ... p2_poke_5]  — 12 species IDs
#   + type coverage flags, BST bins, tier bins (added when Smogon data available)
TEAM_FEATURE_DIM = TEAM_SIZE * 2   # minimum — extended below when data is available

# State feature vector layout (per turn): MATCHES BattleEnv.py build_observation()
#   Active mon:    [species_id, hp, 4×(5-feats), status, 6×boosts] = 2 + 20 + 1 + 6 = 29
#   Opp active:    [species_id, hp, status]     = 3
#   My team HP:    6
#   Opp team HP:   6
#   Field:         4
#   TOTAL:         48
STATE_FEATURE_DIM = 19


# ── Battle Observation Constants ──────────────────────────────────────────────

TYPE_IDS = {
    "normal": 1, "fire": 2, "water": 3, "electric": 4, "grass": 5, "ice": 6,
    "fighting": 7, "poison": 8, "ground": 9, "flying": 10, "psychic": 11,
    "bug": 12, "rock": 13, "ghost": 14, "dragon": 15, "dark": 16, "steel": 17, "fairy": 18
}

STATUS_IDS = {
    "brn": 1, "par": 2, "slp": 3, "frz": 4, "psn": 5, "tox": 6
}

WEATHER_IDS = {
    "sunnyday": 1, "desolateland": 1, "raindance": 2, "primordialsea": 2,
    "sandstorm": 3, "hail": 4, "snow": 4
}

TERRAIN_IDS = {
    "electricterrain": 1, "grassyterrain": 2, "mistyterrain": 3, "psychicterrain": 4
}


# ── Vocabulary ────────────────────────────────────────────────────────────────

class Vocabulary:
    """
    Maps string tokens (Pokemon species, move names) to integer IDs.
    ID 0 is always UNKNOWN.
    """

    def __init__(self) -> None:
        self._token2id: dict[str, int] = {"<UNK>": UNKNOWN_ID}
        self._id2token: list[str]      = ["<UNK>"]

    def __len__(self) -> int:
        return len(self._token2id)

    def add(self, token: str) -> int:
        token = _normalize(token)
        if token not in self._token2id:
            idx = len(self._token2id)
            self._token2id[token] = idx
            self._id2token.append(token)
        return self._token2id[token]

    def get(self, token: str) -> int:
        return self._token2id.get(_normalize(token), UNKNOWN_ID)

    def token(self, idx: int) -> str:
        return self._id2token[idx] if 0 <= idx < len(self._id2token) else "<UNK>"

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"token2id": self._token2id}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "Vocabulary":
        data = json.loads(path.read_text(encoding="utf-8"))
        vocab = cls()
        vocab._token2id = data["token2id"]
        vocab._id2token = [""] * len(vocab._token2id)
        for token, idx in vocab._token2id.items():
            if idx < len(vocab._id2token):
                vocab._id2token[idx] = token
        return vocab


def _normalize(name: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return " ".join(name.lower().strip().split())


# ── Feature Extractor ─────────────────────────────────────────────────────────

class FeatureExtractor:
    """
    Converts BattleRecord objects into numpy feature arrays.

    The vocabulary is built lazily from the first batch of records seen.
    Call save() after building to persist the vocabulary for future runs.
    """

    def __init__(self, vocab_path: Path | None = None) -> None:
        self.species_vocab = Vocabulary()
        self.move_vocab    = Vocabulary()
        self.vocab_path    = vocab_path
        self._frozen       = False   # once frozen, add() becomes a no-op

    # ── Vocabulary management ──────────────────────────────────────

    def freeze(self) -> None:
        """Lock the vocabulary — new tokens become UNKNOWN. Call before inference."""
        self._frozen = True

    def _add_species(self, name: str) -> int:
        if self._frozen:
            return self.species_vocab.get(name)
        return self.species_vocab.add(name)

    def _add_move(self, name: str) -> int:
        if self._frozen:
            return self.move_vocab.get(name)
        return self.move_vocab.add(name)

    def build_vocab_from_records(self, records: list["BattleRecord"]) -> None:
        """Scan records and populate the species + move vocabularies."""
        for rec in records:
            for species in rec.p1_team + rec.p2_team:
                self._add_species(species)
            for turn in rec.turns:
                for evt in turn.events:
                    if evt.kind == "move":
                        self._add_move(evt.detail)
        log.info(
            f"Vocabulary built: {len(self.species_vocab)} species, "
            f"{len(self.move_vocab)} moves"
        )

    def save(self, base_dir: Path | None = None) -> None:
        base = base_dir or (self.vocab_path.parent if self.vocab_path else Path("data/ml"))
        self.species_vocab.save(base / "species_vocab.json")
        self.move_vocab.save(base / "move_vocab.json")
        log.info(f"Vocabularies saved to {base}")

    @classmethod
    def load(cls, base_dir: Path) -> "FeatureExtractor":
        ext = cls()
        ext.species_vocab = Vocabulary.load(base_dir / "species_vocab.json")
        ext.move_vocab    = Vocabulary.load(base_dir / "move_vocab.json")
        ext._frozen = True
        log.info(
            f"Loaded vocabularies: {len(ext.species_vocab)} species, "
            f"{len(ext.move_vocab)} moves"
        )
        return ext

    @classmethod
    def load_or_create(cls, base_dir: Path) -> "FeatureExtractor":
        """Load existing vocabularies if present, else return a fresh extractor."""
        species_path = base_dir / "species_vocab.json"
        move_path    = base_dir / "move_vocab.json"
        if species_path.exists() and move_path.exists():
            return cls.load(base_dir)
        log.info("No existing vocabulary found — creating fresh extractor")
        return cls(vocab_path=base_dir / "species_vocab.json")

    # ── Team feature extraction ────────────────────────────────────

    def _team_vector(self, team: list[str]) -> np.ndarray:
        """
        Convert a list of species names to a fixed-size ID vector.
        Pads with UNKNOWN_ID if team has fewer than TEAM_SIZE members.
        Truncates if more.
        """
        ids = [self._add_species(s) for s in team[:TEAM_SIZE]]
        while len(ids) < TEAM_SIZE:
            ids.append(UNKNOWN_ID)
        return np.array(ids, dtype=np.int32)

    def team_features(
        self,
        records: list["BattleRecord"],
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Build team-level feature matrix and label vector for matchup prediction.

        Returns:
            X: shape (n, TEAM_SIZE*2) — p1_team_ids + p2_team_ids concatenated
            y: shape (n,)             — 1 if p1 won, 0 if p2 won
                                        Ties and unknowns are excluded.
        """
        rows, labels = [], []
        for rec in records:
            if rec.winner not in ("p1", "p2"):
                continue
            p1_vec = self._team_vector(rec.p1_team)
            p2_vec = self._team_vector(rec.p2_team)
            rows.append(np.concatenate([p1_vec, p2_vec]))
            labels.append(1 if rec.winner == "p1" else 0)

        if not rows:
            return np.empty((0, TEAM_SIZE * 2), dtype=np.int32), np.empty((0,), dtype=np.int8)

        X = np.stack(rows).astype(np.int32)
        y = np.array(labels, dtype=np.int8)
        return X, y

    # ── State feature extraction (Online/RL) ──────────────────────

    def extract_features(self, battle: "AbstractBattle") -> np.ndarray:
        """
        Extracts 48 features from a live battle state.
        This must EXACTLY match BattleEnv.build_observation() logic.
        """
        active = battle.active_pokemon
        opp_active = battle.opponent_active_pokemon

        # 1. Active mon features (2 + 20 + 1 + 6 = 29)
        # Species (1)
        active_id = self._species_to_id_normalized(active.species if active else None)
        # HP (1)
        active_hp = active.current_hp_fraction if active else 0.0
        
        # Moves (4 slots × 5 features = 20)
        move_feats = []
        moves = list(active.moves.values()) if active else []
        for i in range(4):
            if i < len(moves):
                m = moves[i]
                eff = get_type_effectiveness_float(m, opp_active) if opp_active else 0.5
                move_feats.extend([
                    (m.base_power / 250.0),
                    (m.accuracy if m.accuracy is not True else 1.0),
                    (TYPE_IDS.get(m.type.name.lower(), 0) / 18.0),
                    ((m.priority + 1) / 5.0),
                    eff
                ])
            else:
                move_feats.extend([0.0] * 5)
        
        # Status (1)
        status_id = 0.0
        if active and active.status:
            status_id = STATUS_IDS.get(active.status.name.lower(), 0) / 6.0
            
        # Boosts (6)
        boost_list = ["atk", "def", "spa", "spd", "spe", "accuracy"]
        boosts = [((active.boosts.get(b, 0) + 6) / 12.0) if active else 0.5 for b in boost_list]

        # 2. Opponent active (3)
        opp_id = self._species_to_id_normalized(opp_active.species if opp_active else None)
        opp_hp = opp_active.current_hp_fraction if opp_active else 0.0
        opp_status = 0.0
        if opp_active and opp_active.status:
            opp_status = STATUS_IDS.get(opp_active.status.name.lower(), 0) / 6.0

        # 3. Team HP (6 + 6 = 12)
        my_team_hp = [p.current_hp_fraction for p in battle.team.values()]
        while len(my_team_hp) < 6:
            my_team_hp.append(0.0)

        opp_team_hp = [p.current_hp_fraction for p in battle.opponent_team.values()]
        while len(opp_team_hp) < 6:
            opp_team_hp.append(0.0)

        # 4. Field (4)
        weather_id = 0.0
        if battle.weather:
            weather_id = WEATHER_IDS.get(list(battle.weather.keys())[0].name.lower(), 0) / 4.0
        
        terrain_id = 0.0
        if battle.fields:
            # Check for terrain in fields
            for f in battle.fields:
                if f.name.lower() in TERRAIN_IDS:
                    terrain_id = TERRAIN_IDS[f.name.lower()] / 4.0
                    break
        
        trick_room = 1.0 if "trickroom" in [f.name.lower() for f in (battle.fields.keys() if hasattr(battle.fields, "keys") else [])] else 0.0
        turn_norm = min(battle.turn / 100.0, 1.0)

        # Assemble
        feature = np.array(
            [active_id, active_hp] + move_feats + [status_id] + boosts +
            [opp_id, opp_hp, opp_status] +
            my_team_hp[:6] + opp_team_hp[:6] +
            [weather_id, terrain_id, trick_room, turn_norm],
            dtype=np.float32
        )
        return feature

    def _species_to_id_normalized(self, species_name: Optional[str]) -> float:
        """Normalized species ID for the feature vector."""
        if not species_name:
            return 0.0
        # Use simple hash like in BattleEnv.py for stability without vocab if needed
        # But we have a vocab, so let's use it!
        # Wait, BattleEnv.py used: hash(species) % 10000 / 10000.0
        # If I want to be 100% compatible with the RL training in BattleEnv, I should use the SAME hash.
        return (hash(species_name) % 10000) / 10000.0

    # ── State feature extraction (Replays/Offline) ─────────────────

    def state_features(
        self,
        records: list["BattleRecord"],
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Build turn-level state feature matrix for battle policy learning.

        Each row represents a single turn's state + the action taken.
        Label is 1 if the player whose turn it is eventually won the game.

        Returns:
            X: shape (n_turns, STATE_FEATURE_DIM)
            y: shape (n_turns,)  — 1 if the acting player won
        """
        rows, labels = [], []

        for rec in records:
            if rec.winner not in ("p1", "p2"):
                continue

            # Track HP for each slot across turns
            hp: dict[str, float] = {}           # slot → latest hp_pct
            last_move: dict[str, int] = {}       # "p1"/"p2" → last move id
            fainted: dict[str, int] = {"p1": 0, "p2": 0}

            for turn in rec.turns:
                # Update HP and move tracking from events
                for evt in turn.events:
                    if evt.hp_after >= 0:
                        hp[evt.slot] = evt.hp_after
                    if evt.kind == "faint":
                        hp[evt.slot] = 0.0
                        player = evt.slot[:2]
                        fainted[player] = fainted.get(player, 0) + 1
                    if evt.kind == "move":
                        player = evt.slot[:2]
                        last_move[player] = self._add_move(evt.detail)

                # Build state vector at the END of this turn
                p1_active_id = self._add_species(turn.p1_active)
                p2_active_id = self._add_species(turn.p2_active)

                # HP for all 6 slots per player
                p1_hps = [hp.get(f"p1{chr(ord('a')+i)}", 1.0) for i in range(TEAM_SIZE)]
                p2_hps = [hp.get(f"p2{chr(ord('a')+i)}", 1.0) for i in range(TEAM_SIZE)]

                turn_norm = min(turn.turn_number / 50.0, 1.0)

                feature = np.array(
                    [p1_active_id, p2_active_id]
                    + p1_hps + p2_hps
                    + [fainted["p1"], fainted["p2"]]
                    + [turn_norm]
                    + [last_move.get("p1", UNKNOWN_ID), last_move.get("p2", UNKNOWN_ID)],
                    dtype=np.float32,
                )
                rows.append(feature)
                # Label: did p1 win?
                labels.append(1 if rec.winner == "p1" else 0)

        if not rows:
            return (
                np.empty((0, STATE_FEATURE_DIM), dtype=np.float32),
                np.empty((0,), dtype=np.int8),
            )

        X = np.stack(rows).astype(np.float32)
        y = np.array(labels, dtype=np.int8)
        return X, y


# ── Dataset builder ───────────────────────────────────────────────────────────

def build_dataset(
    replay_dir: Path,
    output_dir: Path,
    max_replays: int = 0,
    min_rating: int = 0,
) -> dict[str, np.ndarray]:
    """
    High-level helper: parse all replays in a directory, build both feature
    matrices, and save them as .npy files.

    Args:
        replay_dir:  Directory containing replay JSON files.
        output_dir:  Where to save vocabulary and .npy arrays.
        max_replays: Cap on how many replays to process (0 = all).
        min_rating:  Skip replays below this rating.

    Returns:
        Dict with keys: X_team, y_team, X_state, y_state
    """
    from src.ml.replay_parser import parse_replay_dir

    output_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"Parsing replays from {replay_dir} ...")
    records = parse_replay_dir(replay_dir, max_count=max_replays)

    if min_rating:
        records = [r for r in records if r.rating >= min_rating]
    log.info(f"  {len(records)} records after rating filter (min={min_rating})")

    extractor = FeatureExtractor.load_or_create(output_dir)
    extractor.build_vocab_from_records(records)
    extractor.save(output_dir)

    log.info("Extracting team features ...")
    X_team, y_team = extractor.team_features(records)
    log.info(f"  Team dataset: {X_team.shape}  labels: {y_team.shape}")

    log.info("Extracting state features ...")
    X_state, y_state = extractor.state_features(records)
    log.info(f"  State dataset: {X_state.shape}  labels: {y_state.shape}")

    np.save(output_dir / "X_team.npy",  X_team)
    np.save(output_dir / "y_team.npy",  y_team)
    np.save(output_dir / "X_state.npy", X_state)
    np.save(output_dir / "y_state.npy", y_state)
    log.info(f"Saved datasets to {output_dir}")

    return {"X_team": X_team, "y_team": y_team, "X_state": X_state, "y_state": y_state}


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser(description="Build ML feature datasets from replays")
    ap.add_argument("--replay-dir",  required=True, help="Directory of replay JSON files")
    ap.add_argument("--output-dir",  default="data/ml", help="Where to save features")
    ap.add_argument("--max-replays", type=int, default=0)
    ap.add_argument("--min-rating",  type=int, default=0)
    args = ap.parse_args()

    datasets = build_dataset(
        replay_dir  = Path(args.replay_dir),
        output_dir  = Path(args.output_dir),
        max_replays = args.max_replays,
        min_rating  = args.min_rating,
    )
    print("\nDataset summary:")
    for key, arr in datasets.items():
        print(f"  {key}: shape={arr.shape}  dtype={arr.dtype}")
