"""
Tests for src/ml/feature_extractor.py

Covers uncovered lines: 88, 99-106, 168-176, 184, 216, 249, 331
  - Vocabulary.token() out-of-bounds → "<UNK>"
  - Vocabulary.save() + Vocabulary.load() round-trip
  - FeatureExtractor.load() classmethod
  - FeatureExtractor.load_or_create() when files exist (line 184)
  - team_features() skipping ties/unknowns (line 216)
  - state_features() skipping ties/unknowns (line 249)
  - build_dataset() min_rating filter (line 331)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from src.ml.feature_extractor import (
    UNKNOWN_ID,
    TEAM_SIZE,
    STATE_FEATURE_DIM,
    FeatureExtractor,
    Vocabulary,
    build_dataset,
)
from src.ml.replay_parser import BattleRecord, TurnSnapshot, BattleEvent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_record(winner: str = "p1", rating: int = 1000) -> BattleRecord:
    return BattleRecord(
        replay_id="test-123",
        format="gen9ou",
        rating=rating,
        p1_name="Alice",
        p2_name="Bob",
        winner=winner,
        winner_name="Alice" if winner == "p1" else ("Bob" if winner == "p2" else ""),
        p1_team=["Garchomp", "Pikachu", "Charizard", "Blastoise", "Venusaur", "Mewtwo"],
        p2_team=["Dragonite", "Alakazam", "Snorlax", "Lapras", "Jolteon", "Vaporeon"],
        turns=[],
        total_turns=0,
    )


def _make_turn_record(winner: str = "p1") -> BattleRecord:
    """Record with one turn containing events for state_features tests."""
    evt = BattleEvent(kind="move", slot="p1a", detail="Earthquake", hp_after=-1.0)
    snap = TurnSnapshot(turn_number=1, events=[evt], p1_active="Garchomp", p2_active="Dragonite")
    rec = _make_record(winner=winner)
    rec.turns = [snap]
    return rec


# ── Vocabulary.token() ────────────────────────────────────────────────────────

class TestVocabularyToken:
    def test_in_bounds_returns_token(self):
        v = Vocabulary()
        v.add("Pikachu")
        assert v.token(1) == "pikachu"

    def test_zero_returns_unk(self):
        v = Vocabulary()
        assert v.token(0) == "<UNK>"

    def test_out_of_bounds_high_returns_unk(self):
        """Line 88: else branch when idx >= len."""
        v = Vocabulary()
        v.add("Pikachu")
        assert v.token(999) == "<UNK>"

    def test_negative_index_returns_unk(self):
        """Line 88: else branch when idx < 0."""
        v = Vocabulary()
        assert v.token(-1) == "<UNK>"

    def test_exact_boundary_returns_unk(self):
        v = Vocabulary()
        # len is 1 (just <UNK>); index 1 is out of bounds
        assert v.token(1) == "<UNK>"


# ── Vocabulary.save() + .load() round-trip ───────────────────────────────────

class TestVocabularySaveLoad:
    def test_load_restores_token2id(self, tmp_path):
        """Lines 99-106: Vocabulary.load() classmethod."""
        v = Vocabulary()
        v.add("Pikachu")
        v.add("Charmander")
        path = tmp_path / "vocab.json"
        v.save(path)

        loaded = Vocabulary.load(path)
        assert loaded.get("Pikachu") == v.get("Pikachu")
        assert loaded.get("Charmander") == v.get("Charmander")

    def test_load_unknown_returns_zero(self, tmp_path):
        v = Vocabulary()
        v.add("Pikachu")
        path = tmp_path / "vocab.json"
        v.save(path)

        loaded = Vocabulary.load(path)
        assert loaded.get("Mewtwo") == UNKNOWN_ID

    def test_load_len_matches(self, tmp_path):
        v = Vocabulary()
        for name in ["Pikachu", "Charmander", "Squirtle"]:
            v.add(name)
        path = tmp_path / "vocab.json"
        v.save(path)

        loaded = Vocabulary.load(path)
        assert len(loaded) == len(v)

    def test_load_id2token_populated(self, tmp_path):
        """Lines 102-105: _id2token rebuild loop."""
        v = Vocabulary()
        v.add("Garchomp")
        path = tmp_path / "vocab.json"
        v.save(path)

        loaded = Vocabulary.load(path)
        garchomp_id = loaded.get("Garchomp")
        assert loaded.token(garchomp_id) == "garchomp"


# ── FeatureExtractor.load() ───────────────────────────────────────────────────

class TestFeatureExtractorLoad:
    def test_load_restores_species_vocab(self, tmp_path):
        """Lines 168-176: FeatureExtractor.load() classmethod."""
        ext = FeatureExtractor()
        ext._add_species("Garchomp")
        ext._add_species("Pikachu")
        ext.save(tmp_path)

        loaded = FeatureExtractor.load(tmp_path)
        assert loaded.species_vocab.get("Garchomp") != UNKNOWN_ID
        assert loaded.species_vocab.get("Pikachu") != UNKNOWN_ID

    def test_load_sets_frozen(self, tmp_path):
        """Line 171: ext._frozen = True."""
        ext = FeatureExtractor()
        ext.save(tmp_path)

        loaded = FeatureExtractor.load(tmp_path)
        assert loaded._frozen is True

    def test_load_restores_move_vocab(self, tmp_path):
        ext = FeatureExtractor()
        ext._add_move("Earthquake")
        ext.save(tmp_path)

        loaded = FeatureExtractor.load(tmp_path)
        assert loaded.move_vocab.get("Earthquake") != UNKNOWN_ID

    def test_load_unknown_species_returns_zero(self, tmp_path):
        ext = FeatureExtractor()
        ext._add_species("Garchomp")
        ext.save(tmp_path)

        loaded = FeatureExtractor.load(tmp_path)
        assert loaded.species_vocab.get("UnknownMon") == UNKNOWN_ID


# ── FeatureExtractor.load_or_create() when files exist ───────────────────────

class TestLoadOrCreate:
    def test_returns_fresh_when_no_files(self, tmp_path):
        ext = FeatureExtractor.load_or_create(tmp_path)
        assert ext._frozen is False

    def test_returns_loaded_when_files_exist(self, tmp_path):
        """Line 184: cls.load(base_dir) branch."""
        # Create and save vocab files first
        existing = FeatureExtractor()
        existing._add_species("Mewtwo")
        existing.save(tmp_path)

        # Now load_or_create should detect the files and load
        ext = FeatureExtractor.load_or_create(tmp_path)
        assert ext._frozen is True
        assert ext.species_vocab.get("Mewtwo") != UNKNOWN_ID

    def test_loaded_extractor_recognises_saved_species(self, tmp_path):
        original = FeatureExtractor()
        original._add_species("Charmander")
        original.save(tmp_path)

        loaded = FeatureExtractor.load_or_create(tmp_path)
        charmander_id = loaded.species_vocab.get("Charmander")
        assert charmander_id != UNKNOWN_ID


# ── team_features() skip ties/unknowns ───────────────────────────────────────

class TestTeamFeaturesSkipNonWinners:
    def test_tie_record_skipped(self):
        """Line 216: continue when winner == 'tie'."""
        ext = FeatureExtractor()
        tie_rec = _make_record(winner="tie")
        X, y = ext.team_features([tie_rec])
        assert X.shape[0] == 0

    def test_unknown_winner_skipped(self):
        """Line 216: continue when winner == 'unknown'."""
        ext = FeatureExtractor()
        unk_rec = _make_record(winner="unknown")
        X, y = ext.team_features([unk_rec])
        assert X.shape[0] == 0

    def test_mix_keeps_only_p1_p2_winners(self):
        ext = FeatureExtractor()
        records = [
            _make_record(winner="p1"),
            _make_record(winner="tie"),
            _make_record(winner="p2"),
            _make_record(winner="unknown"),
        ]
        X, y = ext.team_features(records)
        assert X.shape[0] == 2   # only the p1 and p2 records

    def test_all_ties_returns_empty_arrays(self):
        ext = FeatureExtractor()
        records = [_make_record(winner="tie")] * 5
        X, y = ext.team_features(records)
        assert X.shape == (0, TEAM_SIZE * 2)
        assert y.shape == (0,)


# ── state_features() skip ties/unknowns ──────────────────────────────────────

class TestStateFeaturesSkipNonWinners:
    def test_tie_record_skipped(self):
        """Line 249: continue when winner == 'tie'."""
        ext = FeatureExtractor()
        tie_rec = _make_turn_record(winner="tie")
        X, y = ext.state_features([tie_rec])
        assert X.shape[0] == 0

    def test_unknown_winner_skipped(self):
        """Line 249: continue when winner == 'unknown'."""
        ext = FeatureExtractor()
        unk_rec = _make_turn_record(winner="unknown")
        X, y = ext.state_features([unk_rec])
        assert X.shape[0] == 0

    def test_mix_keeps_only_valid_winners(self):
        ext = FeatureExtractor()
        records = [
            _make_turn_record(winner="p1"),
            _make_turn_record(winner="tie"),
            _make_turn_record(winner="p2"),
        ]
        X, y = ext.state_features(records)
        assert X.shape[0] == 2   # one turn per p1/p2 record


# ── build_dataset() min_rating filter ────────────────────────────────────────

class TestBuildDatasetMinRating:
    def test_min_rating_filters_low_rated(self, tmp_path):
        """Line 331: records filtered by min_rating."""
        replay_dir = tmp_path / "replays"
        replay_dir.mkdir()
        output_dir = tmp_path / "output"

        high_rec = _make_record(winner="p1", rating=2000)
        low_rec  = _make_record(winner="p2", rating=500)

        with patch("src.ml.replay_parser.parse_replay_dir", return_value=[high_rec, low_rec]):
            result = build_dataset(replay_dir, output_dir, min_rating=1500)

        # Only high_rec passes filter → 1 row in X_team
        assert result["X_team"].shape[0] == 1

    def test_zero_min_rating_keeps_all(self, tmp_path):
        """No filter applied when min_rating=0."""
        replay_dir = tmp_path / "replays"
        replay_dir.mkdir()
        output_dir = tmp_path / "output"

        records = [_make_record(winner="p1", rating=r) for r in [0, 100, 500]]

        with patch("src.ml.replay_parser.parse_replay_dir", return_value=records):
            result = build_dataset(replay_dir, output_dir, min_rating=0)

        assert result["X_team"].shape[0] == 3

    def test_all_filtered_produces_empty(self, tmp_path):
        replay_dir = tmp_path / "replays"
        replay_dir.mkdir()
        output_dir = tmp_path / "output"

        low_records = [_make_record(winner="p1", rating=100)]

        with patch("src.ml.replay_parser.parse_replay_dir", return_value=low_records):
            result = build_dataset(replay_dir, output_dir, min_rating=2000)

        assert result["X_team"].shape[0] == 0
