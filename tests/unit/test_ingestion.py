"""
Unit tests for data/ingestion.py — offline replay ingestion module.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from data.ingestion import (
    OBS_DIM,
    ReplayIngester,
    _BattleState,
    _infer_action,
    _load_species_vocab,
    _one_hot_action,
    record_to_transitions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(kind: str, slot: str = "", detail: str = "", hp_after: float = -1.0):
    return SimpleNamespace(kind=kind, slot=slot, detail=detail, hp_after=hp_after)


def _make_turn(turn_number: int, p1_active: str, p2_active: str, events=None):
    return SimpleNamespace(
        turn_number=turn_number,
        p1_active=p1_active,
        p2_active=p2_active,
        events=events or [],
    )


def _make_record(
    p1_team=None, p2_team=None, winner="p1", turns=None, rating=1500
):
    return SimpleNamespace(
        replay_id="test-replay",
        format="gen9ou",
        rating=rating,
        p1_name="Alice",
        p2_name="Bob",
        winner=winner,
        winner_name="Alice" if winner == "p1" else "Bob",
        p1_team=p1_team or ["Garchomp", "Miraidon", "Iron Hands", "Rillaboom", "Incineroar", "Torkoal"],
        p2_team=p2_team or ["Flutter Mane", "Urshifu", "Pelipper", "Amoonguss", "Landorus", "Annihilape"],
        turns=turns or [],
        total_turns=len(turns or []),
        p1_fainted=0,
        p2_fainted=0,
    )


# ---------------------------------------------------------------------------
# _load_species_vocab
# ---------------------------------------------------------------------------

class TestLoadSpeciesVocab:
    def test_missing_dir_returns_empty(self, tmp_path):
        result = _load_species_vocab(tmp_path / "nonexistent")
        assert result == {}

    def test_empty_json_returns_empty(self, tmp_path):
        (tmp_path / "species_vocab.json").write_text("{}", encoding="utf-8")
        result = _load_species_vocab(tmp_path)
        assert result == {}

    def test_token2id_format(self, tmp_path):
        data = {"token2id": {"<UNK>": 0, "Garchomp": 1, "Miraidon": 2}}
        (tmp_path / "species_vocab.json").write_text(json.dumps(data), encoding="utf-8")
        result = _load_species_vocab(tmp_path)
        assert result["Garchomp"] == pytest.approx(0.5)
        assert result["Miraidon"] == pytest.approx(1.0)

    def test_flat_format(self, tmp_path):
        data = {"<UNK>": 0, "Pikachu": 1, "Raichu": 2}
        (tmp_path / "species_vocab.json").write_text(json.dumps(data), encoding="utf-8")
        result = _load_species_vocab(tmp_path)
        assert "Pikachu" in result
        assert result["Raichu"] == pytest.approx(1.0)

    def test_fallback_to_vocab_json(self, tmp_path):
        data = {"token2id": {"<UNK>": 0, "Eevee": 1}}
        (tmp_path / "vocab.json").write_text(json.dumps(data), encoding="utf-8")
        result = _load_species_vocab(tmp_path)
        assert "Eevee" in result


# ---------------------------------------------------------------------------
# _BattleState
# ---------------------------------------------------------------------------

class TestBattleState:
    def setup_method(self):
        self.state = _BattleState(
            ["Garchomp", "Miraidon", "Iron Hands"],
            ["Flutter Mane", "Urshifu"],
        )

    def test_team_padded_to_six(self):
        assert len(self.state.p1_team) == 6
        assert len(self.state.p2_team) == 6

    def test_default_hp_is_full(self):
        assert self.state.hp("Garchomp") == pytest.approx(1.0)
        assert self.state.hp("Flutter Mane") == pytest.approx(1.0)
        assert self.state.hp("Unknown") == pytest.approx(1.0)

    def test_damage_event_updates_hp(self):
        active = {"p1a": "Garchomp", "p2a": "Flutter Mane"}
        evt = _make_event("damage", slot="p1a", hp_after=0.4)
        self.state.apply_events([evt], active)
        assert self.state.hp("Garchomp") == pytest.approx(0.4)

    def test_faint_event_sets_hp_zero(self):
        active = {"p1a": "Garchomp", "p2a": "Flutter Mane"}
        evt = _make_event("faint", slot="p2a")
        self.state.apply_events([evt], active)
        assert self.state.hp("Flutter Mane") == pytest.approx(0.0)

    def test_status_event(self):
        active = {"p1a": "Garchomp"}
        evt = _make_event("status", slot="p1a", detail="brn")
        self.state.apply_events([evt], active)
        assert self.state.status("p1a") > 0.0

    def test_switch_event_updates_active(self):
        active = {"p1a": "Garchomp", "p2a": "Flutter Mane"}
        evt = _make_event("switch", slot="p1a", detail="Miraidon")
        self.state.apply_events([evt], active)
        assert active["p1a"] == "Miraidon"

    def test_build_obs_shape(self):
        obs = self.state.build_obs("Garchomp", "Flutter Mane", 3, {})
        assert obs.shape == (OBS_DIM,)
        assert obs.dtype == np.float32

    def test_build_obs_species_ids(self):
        vocab = {"Garchomp": 0.3, "Flutter Mane": 0.7}
        obs = self.state.build_obs("Garchomp", "Flutter Mane", 5, vocab)
        assert obs[0] == pytest.approx(0.3)   # active species
        assert obs[29] == pytest.approx(0.7)  # opponent species

    def test_build_obs_turn_normalised(self):
        obs = self.state.build_obs("Garchomp", "Flutter Mane", 25, {})
        assert obs[47] == pytest.approx(0.5)

        obs100 = self.state.build_obs("Garchomp", "Flutter Mane", 100, {})
        assert obs100[47] == pytest.approx(1.0)  # capped at 1.0

    def test_team_hps_in_obs(self):
        active = {"p1a": "Garchomp", "p2a": "Flutter Mane"}
        self.state.apply_events([_make_event("damage", slot="p1a", hp_after=0.5)], active)
        obs = self.state.build_obs("Garchomp", "Flutter Mane", 1, {})
        assert obs[1] == pytest.approx(0.5)   # active hp
        assert obs[32] == pytest.approx(0.5)  # team slot 0 HP (same Pokemon)


# ---------------------------------------------------------------------------
# _infer_action
# ---------------------------------------------------------------------------

class TestInferAction:
    def test_switch_action(self):
        team = ["Garchomp", "Miraidon", "Iron Hands", "Rillaboom", "Incineroar", "Torkoal"]
        events = [_make_event("switch", slot="p1a", detail="Iron Hands")]
        action = _infer_action(events, "p1", team)
        assert action == 2  # slot 2 in team list

    def test_switch_first_slot(self):
        team = ["Garchomp", "Miraidon"]
        events = [_make_event("switch", slot="p1a", detail="Garchomp")]
        action = _infer_action(events, "p1", team)
        assert action == 0

    def test_move_action_default(self):
        events = [_make_event("move", slot="p1a", detail="Earthquake")]
        action = _infer_action(events, "p1", [])
        assert action == 6   # _ACTION_MOVE_BASE

    def test_tera_move_action(self):
        events = [
            _make_event("tera", slot="p1a", detail="Ground"),
            _make_event("move", slot="p1a", detail="Earthquake"),
        ]
        action = _infer_action(events, "p1", [])
        assert action == 22  # _ACTION_TERA_BASE

    def test_p2_events_ignored_for_p1(self):
        team = ["Garchomp", "Miraidon"]
        events = [_make_event("switch", slot="p2a", detail="Miraidon")]
        action = _infer_action(events, "p1", team)
        assert action == 6   # falls back to move default

    def test_no_events_returns_default(self):
        action = _infer_action([], "p1", [])
        assert action == 6

    def test_switch_unknown_species_defaults_to_slot0(self):
        team = ["Garchomp", "Miraidon"]
        events = [_make_event("switch", slot="p1a", detail="Pikachu")]
        action = _infer_action(events, "p1", team)
        assert action == 0


# ---------------------------------------------------------------------------
# _one_hot_action
# ---------------------------------------------------------------------------

class TestOneHotAction:
    def test_shape(self):
        probs = _one_hot_action(6)
        assert probs.shape == (26,)
        assert probs[6] == pytest.approx(1.0)
        assert probs.sum() == pytest.approx(1.0)

    def test_custom_n_actions(self):
        probs = _one_hot_action(3, n_actions=10)
        assert probs.shape == (10,)
        assert probs[3] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# record_to_transitions
# ---------------------------------------------------------------------------

class TestRecordToTransitions:
    def test_winner_perspective_skip_tie(self):
        record = _make_record(winner="tie")
        obs, acts, probs, reward = record_to_transitions(record, {}, perspective="winner")
        assert obs == []

    def test_winner_perspective_skip_unknown(self):
        record = _make_record(winner="unknown")
        obs, acts, probs, reward = record_to_transitions(record, {}, perspective="winner")
        assert obs == []

    def test_winner_gets_positive_reward(self):
        turns = [_make_turn(1, "Garchomp", "Flutter Mane")]
        record = _make_record(winner="p1", turns=turns)
        _, _, _, reward = record_to_transitions(record, {}, perspective="winner")
        assert reward == pytest.approx(1.0)

    def test_p1_loser_gets_negative_reward(self):
        turns = [_make_turn(1, "Garchomp", "Flutter Mane")]
        record = _make_record(winner="p2", turns=turns)
        _, _, _, reward = record_to_transitions(record, {}, perspective="p1")
        assert reward == pytest.approx(-1.0)

    def test_output_lengths_match(self):
        turns = [
            _make_turn(1, "Garchomp", "Flutter Mane"),
            _make_turn(2, "Garchomp", "Urshifu"),
            _make_turn(3, "Miraidon", "Urshifu"),
        ]
        record = _make_record(winner="p1", turns=turns)
        obs, acts, probs, reward = record_to_transitions(record, {}, perspective="winner")
        assert len(obs) == 3
        assert len(acts) == 3
        assert len(probs) == 3

    def test_obs_shape(self):
        turns = [_make_turn(1, "Garchomp", "Flutter Mane")]
        record = _make_record(winner="p1", turns=turns)
        obs, _, _, _ = record_to_transitions(record, {}, perspective="p1")
        assert obs[0].shape == (OBS_DIM,)

    def test_invalid_perspective_raises(self):
        record = _make_record()
        with pytest.raises(ValueError):
            record_to_transitions(record, {}, perspective="invalid")

    def test_p2_perspective_swaps_team_hps(self):
        """Verify that p2 perspective flips the my/opp HP halves in the obs."""
        turns = [_make_turn(1, "Garchomp", "Flutter Mane")]
        record = _make_record(winner="p2", turns=turns)
        vocab = {"Garchomp": 0.1, "Flutter Mane": 0.9}

        p1_obs, _, _, _ = record_to_transitions(record, vocab, perspective="p1")
        p2_obs, _, _, _ = record_to_transitions(record, vocab, perspective="p2")

        # p1's active species should appear at position 0 in p1 obs
        assert p1_obs[0][0] == pytest.approx(0.1)
        # p2 obs should have Flutter Mane as active (p2's own mon)
        assert p2_obs[0][0] == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# ReplayIngester
# ---------------------------------------------------------------------------

class TestReplayIngester:
    def test_list_formats_empty_dir(self, tmp_path):
        ingester = ReplayIngester(replays_dir=tmp_path / "replays")
        assert ingester.list_available_formats() == []

    def test_count_replays_nonexistent(self, tmp_path):
        ingester = ReplayIngester(replays_dir=tmp_path)
        assert ingester.count_replays("gen9ou") == 0

    def test_count_replays(self, tmp_path):
        fmt_dir = tmp_path / "gen9ou"
        fmt_dir.mkdir()
        (fmt_dir / "a.json").write_text("{}", encoding="utf-8")
        (fmt_dir / "b.json").write_text("{}", encoding="utf-8")
        ingester = ReplayIngester(replays_dir=tmp_path)
        assert ingester.count_replays("gen9ou") == 2

    def test_ingest_no_replays_returns_zero(self, tmp_path):
        """ingest_into_buffer returns 0 when no replays are available."""
        buffer = MagicMock()
        ingester = ReplayIngester(replays_dir=tmp_path / "replays")
        result = ingester.ingest_into_buffer(buffer, formats=["gen9ou"])
        assert result == 0
        buffer.add_game.assert_not_called()

    def test_ingest_to_arrays_no_replays(self, tmp_path):
        ingester = ReplayIngester(replays_dir=tmp_path)
        obs, acts = ingester.ingest_to_arrays(formats=["gen9ou"])
        assert obs.shape == (0, OBS_DIM)
        assert acts.shape == (0,)

    def test_ingest_malformed_json_skipped(self, tmp_path):
        fmt_dir = tmp_path / "gen9ou"
        fmt_dir.mkdir()
        (fmt_dir / "bad.json").write_text("not json", encoding="utf-8")
        buffer = MagicMock()
        ingester = ReplayIngester(replays_dir=tmp_path)
        result = ingester.ingest_into_buffer(buffer, formats=["gen9ou"])
        assert result == 0

    def test_list_formats_detected(self, tmp_path):
        for fmt in ("gen9ou", "gen9vgc2024regh"):
            d = tmp_path / fmt
            d.mkdir()
            (d / "r.json").write_text("{}", encoding="utf-8")
        ingester = ReplayIngester(replays_dir=tmp_path)
        fmts = ingester.list_available_formats()
        assert "gen9ou" in fmts
        assert "gen9vgc2024regh" in fmts

    def test_vocab_lazy_loaded(self, tmp_path):
        """Vocab is only loaded once per ingester instance."""
        ingester = ReplayIngester(replays_dir=tmp_path, vocab_dir=tmp_path)
        assert ingester._species_vocab is None
        ingester._get_vocab()
        assert ingester._species_vocab is not None
        # Second call should reuse the cached dict
        first = ingester._species_vocab
        ingester._get_vocab()
        assert ingester._species_vocab is first
