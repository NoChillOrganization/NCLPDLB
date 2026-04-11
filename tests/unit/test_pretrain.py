"""
Tests for src/ml/pretrain.py — check_mapping_gap, build_obs_from_snapshot,
ActionResolver, and pretrain().
"""
from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.ml.pretrain import (
    ABORT_THRESHOLD,
    WARN_THRESHOLD,
    ActionResolver,
    build_obs_from_snapshot,
    check_mapping_gap,
)
from src.ml.replay_parser import BattleEvent, BattleRecord, TurnSnapshot


# ── Helpers ───────────────────────────────────────────────────────────────────

def _snap(
    turn: int = 1,
    p1_active: str = "Garchomp",
    p2_active: str = "Pikachu",
    events: list[BattleEvent] | None = None,
) -> TurnSnapshot:
    s = TurnSnapshot(turn_number=turn, p1_active=p1_active, p2_active=p2_active)
    s.events = events or []
    return s


def _record(
    turns: list[TurnSnapshot],
    p1_team: list[str] | None = None,
    p2_team: list[str] | None = None,
    winner: str = "p1",
) -> BattleRecord:
    return BattleRecord(
        replay_id="test-001",
        format="gen9ou",
        rating=1500,
        p1_name="Alice",
        p2_name="Bob",
        winner=winner,
        winner_name="Alice",
        p1_team=p1_team or ["Garchomp"],
        p2_team=p2_team or ["Pikachu"],
        turns=turns,
        total_turns=len(turns),
    )


# ── check_mapping_gap ─────────────────────────────────────────────────────────

class TestCheckMappingGap:
    def test_zero_total_returns_zero(self):
        gap = check_mapping_gap(unmappable=0, total=0)
        assert gap == 0.0

    def test_no_gap_returns_zero(self):
        gap = check_mapping_gap(unmappable=0, total=100)
        assert gap == pytest.approx(0.0)

    def test_gap_below_warn_threshold_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.ml.pretrain"):
            gap = check_mapping_gap(unmappable=3, total=100)  # 3% < 5%
        assert gap == pytest.approx(0.03)
        assert not caplog.records

    def test_gap_above_warn_threshold_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.ml.pretrain"):
            gap = check_mapping_gap(unmappable=8, total=100)  # 8% > 5%
        assert gap == pytest.approx(0.08)
        assert caplog.records

    def test_gap_at_warn_threshold_not_logged(self, caplog):
        """Exactly at warn threshold is NOT > threshold — no warning."""
        with caplog.at_level(logging.WARNING, logger="src.ml.pretrain"):
            gap = check_mapping_gap(
                unmappable=int(WARN_THRESHOLD * 100), total=100,
            )
        assert gap == pytest.approx(WARN_THRESHOLD)
        assert not caplog.records

    def test_gap_above_abort_threshold_raises(self):
        with pytest.raises(RuntimeError, match="abort threshold"):
            check_mapping_gap(unmappable=20, total=100)  # 20% > 15%

    def test_gap_above_abort_threshold_force_only_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.ml.pretrain"):
            gap = check_mapping_gap(unmappable=20, total=100, force=True)
        assert gap == pytest.approx(0.20)
        assert caplog.records

    def test_gap_exactly_at_abort_threshold_does_not_raise(self):
        """Exactly at abort threshold is NOT > threshold — no raise."""
        gap = check_mapping_gap(
            unmappable=int(ABORT_THRESHOLD * 100), total=100,
        )
        assert gap == pytest.approx(ABORT_THRESHOLD)

    def test_returns_float(self):
        assert isinstance(check_mapping_gap(unmappable=5, total=50), float)

    def test_warn_threshold_constant(self):
        assert WARN_THRESHOLD == pytest.approx(0.05)

    def test_abort_threshold_constant(self):
        assert ABORT_THRESHOLD == pytest.approx(0.15)


# ── build_obs_from_snapshot ───────────────────────────────────────────────────

class TestBuildObsFromSnapshot:
    """build_obs_from_snapshot produces a correctly shaped, bounded obs vector."""

    def test_output_shape(self):
        from src.ml.battle_env import OBS_DIM
        snap = _snap()
        obs = build_obs_from_snapshot(snap)
        assert obs.shape == (OBS_DIM,)
        assert obs.dtype == np.float32

    def test_all_values_in_zero_one(self):
        """Every element should be in [0, 1]."""
        obs = build_obs_from_snapshot(_snap())
        assert np.all(obs >= 0.0) and np.all(obs <= 1.0)

    def test_empty_snapshot_does_not_crash(self):
        """Snapshot with no events and empty species strings."""
        snap = TurnSnapshot(turn_number=1)
        obs = build_obs_from_snapshot(snap)
        assert obs.shape[0] > 0

    def test_turn_number_encoded_in_field(self):
        """Turn 25 → field[-1] = 25/50 = 0.5."""
        snap = _snap(turn=25)
        obs = build_obs_from_snapshot(snap)
        assert obs[-1] == pytest.approx(0.5)

    def test_turn_capped_at_50(self):
        snap = _snap(turn=100)
        obs = build_obs_from_snapshot(snap)
        assert obs[-1] == pytest.approx(1.0)

    def test_species_hash_non_zero_for_known_species(self):
        snap = _snap(p1_active="Garchomp")
        obs = build_obs_from_snapshot(snap)
        assert obs[0] > 0.0

    def test_hp_from_damage_event(self):
        """Damage event for p1a sets hp_pct in obs."""
        events = [BattleEvent(kind="damage", slot="p1a", hp_after=0.5)]
        snap = _snap(events=events)
        obs = build_obs_from_snapshot(snap)
        assert obs[1] == pytest.approx(0.5)

    def test_status_burn_encoded(self):
        """Status 'brn' for p1a sets status slot to 1/6."""
        events = [BattleEvent(kind="status", slot="p1a", detail="brn")]
        snap = _snap(events=events)
        obs = build_obs_from_snapshot(snap)
        # status is at index 22 (1 species + 1 hp + 4*5 moves = 22)
        assert obs[22] == pytest.approx(1 / 6.0)

    def test_opponent_hp_from_damage(self):
        """Damage event for p2a sets opponent hp slot."""
        from src.ml.battle_env import N_MOVES, MOVE_FEATS
        events = [BattleEvent(kind="damage", slot="p2a", hp_after=0.25)]
        snap = _snap(events=events)
        obs = build_obs_from_snapshot(snap)
        # opponent starts at idx 29: [species(1), hp(1), status(1)]
        opp_hp_idx = 29 + 1
        assert obs[opp_hp_idx] == pytest.approx(0.25)

    def test_p2_perspective(self):
        """Player='p2' swaps active/opponent species."""
        snap = _snap(p1_active="Garchomp", p2_active="Dragonite")
        obs_p1 = build_obs_from_snapshot(snap, player="p1")
        obs_p2 = build_obs_from_snapshot(snap, player="p2")
        # p1 perspective: obs[0] = hash(Garchomp), opp = hash(Dragonite)
        # p2 perspective: obs[0] = hash(Dragonite), opp = hash(Garchomp)
        assert obs_p1[0] != obs_p2[0]
        assert obs_p1[0] == pytest.approx(obs_p2[29])  # p1's active == p2's opp species

    def test_boost_atk_encoded(self):
        """Boost event for atk:+2 for p1a is reflected in boosts block."""
        events = [BattleEvent(kind="boost", slot="p1a", detail="atk:+2")]
        snap = _snap(events=events)
        obs = build_obs_from_snapshot(snap)
        # boosts start at idx 23: [atk, def, spa, spd, spe, accuracy]
        # atk boost of +2: (2 + 6) / 12 = 8/12 ≈ 0.667
        assert obs[23] == pytest.approx(8 / 12.0)

    def test_team_list_used_for_active_hp_slot(self):
        """When p1_team is provided and matches active, team HP slot is set."""
        events = [BattleEvent(kind="damage", slot="p1a", hp_after=0.6)]
        snap = _snap(p1_active="Garchomp", events=events)
        obs = build_obs_from_snapshot(snap, p1_team=["Garchomp", "Corviknight"])
        # team HP starts at idx 32; slot 0 = Garchomp = active → hp from event
        assert obs[32] == pytest.approx(0.6)
        # slot 1 = Corviknight (benched) → defaults to 1.0
        assert obs[33] == pytest.approx(1.0)

    def test_field_zeros_except_turn(self):
        """Weather, terrain, trick_room are always 0."""
        snap = _snap(turn=1)
        obs = build_obs_from_snapshot(snap)
        # Field: [-4]=weather, [-3]=terrain, [-2]=trick_room, [-1]=turn
        assert obs[-4] == pytest.approx(0.0)
        assert obs[-3] == pytest.approx(0.0)
        assert obs[-2] == pytest.approx(0.0)
        assert obs[-1] == pytest.approx(1 / 50.0)

    def test_event_with_empty_slot_is_skipped(self):
        """Event with no slot (slot='') triggers the 'if not slot: continue' branch."""
        events = [BattleEvent(kind="damage", slot="", hp_after=0.5)]
        snap = _snap(events=events)
        obs = build_obs_from_snapshot(snap)
        # hp slot for p1a should remain 1.0 (default) since the event was skipped
        assert obs[1] == pytest.approx(1.0)

    def test_boost_with_non_numeric_value_is_skipped(self):
        """Boost event with non-integer value hits 'except ValueError: continue'."""
        events = [BattleEvent(kind="boost", slot="p1a", detail="atk:not-a-number")]
        snap = _snap(events=events)
        obs = build_obs_from_snapshot(snap)
        # Boost should remain at default (no boost applied)
        # boosts start at idx 23; atk at idx 23 → default = 6/12 = 0.5
        assert obs[23] == pytest.approx(6 / 12.0)


# ── ActionResolver ────────────────────────────────────────────────────────────

class TestActionResolver:

    def test_empty_record_returns_empty(self):
        resolver = ActionResolver()
        record = _record(turns=[])
        pairs = resolver.resolve(record)
        assert pairs == []
        assert resolver.total == 0
        assert resolver.unmappable == 0

    def test_move_maps_to_slot_6(self):
        """First move seen for a species → action 6."""
        events = [BattleEvent(kind="move", slot="p1a", detail="Earthquake")]
        snap = _snap(events=events)
        record = _record([snap])
        resolver = ActionResolver(player="p1")
        pairs = resolver.resolve(record)
        assert len(pairs) == 1
        obs, action = pairs[0]
        assert action == 6  # move slot 0 → 6 + 0

    def test_second_distinct_move_maps_to_slot_7(self):
        """Second distinct move for same species → action 7."""
        events1 = [BattleEvent(kind="move", slot="p1a", detail="Earthquake")]
        events2 = [BattleEvent(kind="move", slot="p1a", detail="Dragon Claw")]
        snap1 = _snap(turn=1, events=events1)
        snap2 = _snap(turn=2, events=events2)
        record = _record([snap1, snap2])
        resolver = ActionResolver(player="p1")
        pairs = resolver.resolve(record)
        assert pairs[0][1] == 6  # Earthquake → slot 0 → action 6
        assert pairs[1][1] == 7  # Dragon Claw → slot 1 → action 7

    def test_repeated_move_same_slot(self):
        """Same move used twice → same action index both times."""
        events = [BattleEvent(kind="move", slot="p1a", detail="Earthquake")]
        snap1 = _snap(turn=1, events=events)
        snap2 = _snap(turn=2, events=events)
        record = _record([snap1, snap2])
        resolver = ActionResolver(player="p1")
        pairs = resolver.resolve(record)
        assert pairs[0][1] == pairs[1][1] == 6

    def test_switch_maps_to_team_index(self):
        """Switch to Corviknight at team slot 1 → action 1."""
        events = [BattleEvent(kind="switch", slot="p1a", detail="Corviknight", hp_after=1.0)]
        snap = _snap(events=events)
        record = _record([snap], p1_team=["Garchomp", "Corviknight"])
        resolver = ActionResolver(player="p1")
        pairs = resolver.resolve(record)
        assert pairs[0][1] == 1

    def test_tera_move_maps_to_22_plus_slot(self):
        """Tera event before move → action 22 + move_slot."""
        events = [
            BattleEvent(kind="tera", slot="p1a", detail="Dragon"),
            BattleEvent(kind="move", slot="p1a", detail="Dragon Claw"),
        ]
        snap = _snap(events=events)
        record = _record([snap])
        resolver = ActionResolver(player="p1")
        pairs = resolver.resolve(record)
        assert pairs[0][1] == 22  # tera + move slot 0

    def test_fifth_move_is_unmappable(self):
        """A 5th distinct move for a species increments unmappable."""
        moves = ["Earthquake", "Dragon Claw", "Swords Dance", "Stealth Rock", "Fire Fang"]
        snaps = [
            _snap(turn=i + 1, events=[BattleEvent(kind="move", slot="p1a", detail=m)])
            for i, m in enumerate(moves)
        ]
        record = _record(snaps)
        resolver = ActionResolver(player="p1")
        pairs = resolver.resolve(record)
        assert len(pairs) == 4  # first 4 mapped
        assert resolver.unmappable == 1
        assert resolver.total == 5

    def test_unknown_switch_target_is_unmappable(self):
        """Switch to a species not in team_preview list → unmappable."""
        events = [BattleEvent(kind="switch", slot="p1a", detail="Mewtwo", hp_after=1.0)]
        snap = _snap(events=events)
        record = _record([snap], p1_team=["Garchomp"])
        resolver = ActionResolver(player="p1")
        pairs = resolver.resolve(record)
        assert pairs == []
        assert resolver.unmappable == 1

    def test_no_action_event_for_player_is_unmappable(self):
        """Turn with no move or switch for p1a → unmappable (e.g. forced turns)."""
        events = [BattleEvent(kind="move", slot="p2a", detail="Surf")]
        snap = _snap(events=events)
        record = _record([snap])
        resolver = ActionResolver(player="p1")
        pairs = resolver.resolve(record)
        assert pairs == []
        assert resolver.unmappable == 1

    def test_p2_perspective(self):
        """ActionResolver from p2's perspective uses p2a slot."""
        events = [BattleEvent(kind="move", slot="p2a", detail="Surf")]
        snap = _snap(p2_active="Vaporeon", events=events)
        record = _record([snap], p2_team=["Vaporeon"])
        resolver = ActionResolver(player="p2")
        pairs = resolver.resolve(record)
        assert len(pairs) == 1
        assert pairs[0][1] == 6  # first move → slot 0 → action 6

    def test_obs_shape_in_pairs(self):
        """Each pair's obs has shape (OBS_DIM,)."""
        from src.ml.battle_env import OBS_DIM
        events = [BattleEvent(kind="move", slot="p1a", detail="Earthquake")]
        snap = _snap(events=events)
        record = _record([snap])
        resolver = ActionResolver(player="p1")
        pairs = resolver.resolve(record)
        assert pairs[0][0].shape == (OBS_DIM,)

    def test_tera_after_move_does_not_trigger_tera_action(self):
        """Tera event AFTER the move event should not set tera_this_turn."""
        events = [
            BattleEvent(kind="move", slot="p1a", detail="Earthquake"),
            BattleEvent(kind="tera", slot="p1a", detail="Ground"),  # tera after move
        ]
        snap = _snap(events=events)
        record = _record([snap])
        resolver = ActionResolver(player="p1")
        pairs = resolver.resolve(record)
        assert pairs[0][1] == 6  # no tera → action 6, not 22

    def test_total_and_unmappable_accumulate_across_records(self):
        """resolve() called twice accumulates totals."""
        good_events = [BattleEvent(kind="move", slot="p1a", detail="Earthquake")]
        bad_events  = []  # no action → unmappable
        record1 = _record([_snap(events=good_events)])
        record2 = _record([_snap(events=bad_events)])
        resolver = ActionResolver(player="p1")
        resolver.resolve(record1)
        resolver.resolve(record2)
        assert resolver.total == 2
        assert resolver.unmappable == 1


# ── pretrain() ────────────────────────────────────────────────────────────────

def _make_fake_record() -> BattleRecord:
    """One-turn replay record with a single move action for p1."""
    events = [BattleEvent(kind="move", slot="p1a", detail="Earthquake")]
    snap = TurnSnapshot(turn_number=1, p1_active="Garchomp", p2_active="Pikachu")
    snap.events = events
    return BattleRecord(
        replay_id="fake-001",
        format="gen9ou",
        rating=1500,
        p1_name="Alice",
        p2_name="Bob",
        winner="p1",
        winner_name="Alice",
        p1_team=["Garchomp"],
        p2_team=["Pikachu"],
        turns=[snap],
        total_turns=1,
    )


def _mock_deps():
    """
    Inject fake imitation + stable_baselines3 into sys.modules so pretrain()
    can be exercised without those packages installed.
    The mock PPO instance's policy.state_dict() returns a real dict of MagicMocks
    so the dict-comprehension in pretrain() iterates cleanly.
    """
    mock_ppo_instance = MagicMock()
    mock_ppo_instance.policy.state_dict.return_value = {
        "actor.weight": MagicMock(),
        "value_net.weight": MagicMock(),   # filtered out by name prefix
    }
    mock_ppo_class = MagicMock(return_value=mock_ppo_instance)

    mock_bc_instance = MagicMock()
    mock_bc_class = MagicMock(return_value=mock_bc_instance)

    fake_bc_mod = MagicMock()
    fake_bc_mod.BC = mock_bc_class
    fake_types_mod = MagicMock()
    fake_types_mod.Transitions = MagicMock()
    fake_sb3_mod = MagicMock()
    fake_sb3_mod.PPO = mock_ppo_class

    return patch.dict(sys.modules, {
        "imitation": MagicMock(),
        "imitation.algorithms": MagicMock(),
        "imitation.algorithms.bc": fake_bc_mod,
        "imitation.data": MagicMock(),
        "imitation.data.types": fake_types_mod,
        "stable_baselines3": fake_sb3_mod,
    })


class TestPretrain:
    """Tests for the pretrain() entry-point (lines 364-447)."""

    def test_import_error_when_imitation_missing(self, tmp_path):
        """pretrain() raises ImportError when imitation is not installed."""
        from src.ml.pretrain import pretrain
        # imitation not in sys.modules → ImportError re-raised with helpful message
        with pytest.raises(ImportError, match="imitation"):
            pretrain(tmp_path, "gen9ou", tmp_path / "bc.pt")

    def test_raises_value_error_when_no_records(self, tmp_path):
        """pretrain() raises ValueError when replay_dir contains no JSON files."""
        from src.ml.pretrain import pretrain
        with _mock_deps(), \
             patch("src.ml.replay_parser.parse_replay_dir", return_value=[]):
            with pytest.raises(ValueError, match="No replay"):
                pretrain(tmp_path, "gen9ou", tmp_path / "bc.pt")

    def test_raises_value_error_when_no_pairs(self, tmp_path):
        """pretrain() raises ValueError when all turns are unmappable."""
        from src.ml.pretrain import pretrain
        empty_snap = TurnSnapshot(turn_number=1)
        empty_snap.events = []
        record = BattleRecord(
            replay_id="x", format="gen9ou", rating=1500,
            p1_name="A", p2_name="B", winner="p1", winner_name="A",
            p1_team=["Garchomp"], p2_team=["Pikachu"],
            turns=[empty_snap], total_turns=1,
        )
        with _mock_deps(), \
             patch("src.ml.replay_parser.parse_replay_dir", return_value=[record]):
            with pytest.raises(ValueError, match="No mappable"):
                pretrain(tmp_path, "gen9ou", tmp_path / "bc.pt", force=True)

    def test_happy_path_saves_weights(self, tmp_path):
        """pretrain() processes pairs, trains BC, and saves actor weights."""
        from src.ml.pretrain import pretrain
        record = _make_fake_record()
        with _mock_deps(), \
             patch("src.ml.replay_parser.parse_replay_dir", return_value=[record]), \
             patch("torch.save") as mock_save:
            pretrain(tmp_path, "gen9ou", tmp_path / "bc.pt", n_epochs=1)
        mock_save.assert_called_once()
        saved_path = mock_save.call_args[0][1]
        assert str(saved_path).endswith("bc.pt")
