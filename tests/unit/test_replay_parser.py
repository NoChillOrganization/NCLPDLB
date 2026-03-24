"""
Tests for src/ml/replay_parser.py

Covers uncovered lines:
  98        — BattleRecord.to_dict()
  153-154   — _extract_species fallback (no regex match)
  170-174   — _parse_hp percentage format "72/100"
  212       — process_line: line doesn't start with "|"
  215       — process_line: len(parts) < 2
  249       — _on_player: len(parts) < 4
  259       — _on_poke: len(parts) < 4
  282       — _on_switch: len(parts) < 4
  286       — _on_switch: slot doesn't match _SLOT_RE
  297       — _on_switch: species added without prior team preview
  311       — _on_move: len(parts) < 4
  329       — _on_damage: len(parts) < 4
  340-345   — _on_heal handler
  351-356   — _on_status handler
  362-373   — _on_boost handler (boost + unboost + ValueError)
  380       — _on_faint: len(parts) < 3
  388       — _on_faint: p2 player faint counter
  394-399   — _on_tera handler
  406       — _on_win: len(parts) < 3
  410-413   — _on_win: p1/p2/unknown winner branches
  416-417   — _on_tie handler
  484-485   — parse_replay_file
  502       — parse_replay_dir: max_count slicing
  504-507   — parse_replay_dir: error handling
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ml.replay_parser import (
    BattleRecord,
    BattleEvent,
    TurnSnapshot,
    _extract_species,
    _parse_hp,
    parse_log,
    parse_replay_file,
    parse_replay_dir,
    parse_replay_json,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _minimal_log(winner: str = "Alice", p1: str = "Alice", p2: str = "Bob") -> str:
    return (
        f"|player|p1|{p1}\n"
        f"|player|p2|{p2}\n"
        f"|poke|p1|Garchomp|\n"
        f"|poke|p2|Iron Hands|\n"
        f"|turn|1\n"
        f"|switch|p1a: Garchomp|Garchomp|342/342\n"
        f"|move|p1a: Garchomp|Earthquake|p2a: Iron Hands\n"
        f"|-damage|p2a: Iron Hands|201/397\n"
        f"|win|{winner}\n"
    )


def _write_replay(tmp_path: Path, name: str = "battle.json", winner: str = "Alice",
                  rating: int = 1000, extra_log: str = "") -> Path:
    data = {
        "id": name.replace(".json", ""),
        "formatid": "gen9ou",
        "rating": rating,
        "log": _minimal_log(winner=winner) + extra_log,
    }
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ── BattleRecord.to_dict() ────────────────────────────────────────────────────

class TestBattleRecordToDict:
    def test_to_dict_returns_dict(self):
        """Line 98: to_dict() body."""
        record = parse_log(_minimal_log(), replay_id="abc", format="gen9ou", rating=1500)
        d = record.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_keys(self):
        record = parse_log(_minimal_log())
        d = record.to_dict()
        required = {"replay_id", "format", "rating", "p1_name", "p2_name",
                    "winner", "winner_name", "p1_team", "p2_team",
                    "total_turns", "p1_fainted", "p2_fainted", "turns"}
        assert required.issubset(d.keys())

    def test_to_dict_turns_is_list(self):
        record = parse_log(_minimal_log())
        d = record.to_dict()
        assert isinstance(d["turns"], list)

    def test_to_dict_events_structure(self):
        record = parse_log(_minimal_log())
        d = record.to_dict()
        for turn in d["turns"]:
            assert "turn" in turn
            assert "events" in turn
            for evt in turn["events"]:
                assert "kind" in evt
                assert "slot" in evt

    def test_to_dict_json_serializable(self):
        record = parse_log(_minimal_log(), replay_id="xyz", format="gen9ou", rating=1000)
        d = record.to_dict()
        serialized = json.dumps(d)  # should not raise
        assert "xyz" in serialized


# ── _extract_species ──────────────────────────────────────────────────────────

class TestExtractSpecies:
    def test_with_slot_prefix(self):
        assert _extract_species("p1a: Garchomp") == "Garchomp"

    def test_fallback_when_no_match(self):
        """Lines 153-154: else token.strip() branch."""
        assert _extract_species("Garchomp") == "Garchomp"

    def test_fallback_strips_whitespace(self):
        assert _extract_species("  Pikachu  ") == "Pikachu"

    def test_fallback_plain_name(self):
        assert _extract_species("Iron Hands") == "Iron Hands"


# ── _parse_hp ─────────────────────────────────────────────────────────────────

class TestParseHp:
    def test_normal_format(self):
        cur, mx, pct = _parse_hp("201/397")
        assert cur == 201
        assert mx == 397
        assert abs(pct - 201/397) < 0.001

    def test_faint_string(self):
        cur, mx, pct = _parse_hp("0 fnt")
        assert pct == 0.0

    def test_zero_string(self):
        cur, mx, pct = _parse_hp("0")
        assert pct == 0.0

    def test_empty_string(self):
        cur, mx, pct = _parse_hp("")
        assert pct == 0.0

    def test_percentage_format(self):
        """Lines 170-174: decimal '50.5/100' hits _HP_PCT_RE (not _HP_RE)."""
        cur, mx, pct = _parse_hp("50.5/100")
        assert cur == -1
        assert mx == -1
        assert abs(pct - 0.505) < 0.001

    def test_integer_slash_100_matches_hp_re(self):
        """'72/100' matches _HP_RE first — normal integer format."""
        cur, mx, pct = _parse_hp("72/100")
        assert cur == 72
        assert mx == 100
        assert abs(pct - 0.72) < 0.001

    def test_percentage_decimal(self):
        """Lines 170-174: decimal percentage '50.5/100'."""
        cur, mx, pct = _parse_hp("50.5/100")
        assert abs(pct - 0.505) < 0.001

    def test_unknown_format_returns_full_hp(self):
        cur, mx, pct = _parse_hp("invalid")
        assert pct == 1.0


# ── process_line early returns ────────────────────────────────────────────────

class TestProcessLineEarlyReturns:
    def test_non_pipe_line_ignored(self):
        """Line 212: lines not starting with | are skipped."""
        log_text = "This is not a pipe line\n|player|p1|Alice\n|player|p2|Bob\n|win|Alice"
        record = parse_log(log_text)
        assert record.p1_name == "Alice"

    def test_empty_line_ignored(self):
        log_text = "\n|player|p1|Alice\n|player|p2|Bob\n|win|Alice"
        record = parse_log(log_text)
        assert record.p1_name == "Alice"


# ── Handler guards (short parts) ─────────────────────────────────────────────

class TestHandlerGuards:
    def test_on_player_short_parts(self):
        """Line 249: |player|p1 without name — only 3 parts after split."""
        log_text = "|player|p1\n|win|Alice"
        record = parse_log(log_text)
        assert record.p1_name == ""   # not set because guard triggered

    def test_on_poke_short_parts(self):
        """Line 259: |poke|p1 without species."""
        log_text = "|poke|p1\n|win|Alice"
        record = parse_log(log_text)
        assert record.p1_team == []

    def test_on_switch_short_parts(self):
        """Line 282: |switch|p1a: Garchomp — only 3 parts."""
        log_text = "|player|p1|Alice\n|player|p2|Bob\n|turn|1\n|switch|p1a: Garchomp\n|win|Alice"
        record = parse_log(log_text)
        # Should not crash; no switch event added
        assert record.p1_team == []

    def test_on_move_short_parts(self):
        """Line 311: |move|p1a: Garchomp without move name."""
        log_text = "|player|p1|Alice\n|turn|1\n|move|p1a: Garchomp\n|win|Alice"
        record = parse_log(log_text)
        # Should not crash
        assert record.winner == "p1"

    def test_on_damage_short_parts(self):
        """Line 329: |-damage|p2a: Iron Hands without HP."""
        log_text = "|player|p1|Alice\n|player|p2|Bob\n|turn|1\n|-damage|p2a: Iron Hands\n|win|Alice"
        record = parse_log(log_text)
        assert record.winner == "p1"

    def test_on_faint_short_parts(self):
        """Line 380: |faint without slot."""
        log_text = "|player|p1|Alice\n|turn|1\n|faint\n|win|Alice"
        record = parse_log(log_text)
        # Should not crash; faint counter unchanged
        assert record.p1_fainted == 0
        assert record.p2_fainted == 0

    def test_on_win_short_parts(self):
        """Line 406: |win without a name."""
        log_text = "|player|p1|Alice\n|player|p2|Bob\n|win"
        record = parse_log(log_text)
        assert record.winner == "unknown"


# ── _on_switch slot matching ──────────────────────────────────────────────────

class TestSwitchHandler:
    def test_slot_regex_no_match_returns_early(self):
        """Line 286: slot_raw doesn't match _SLOT_RE."""
        log_text = "|player|p1|Alice\n|turn|1\n|switch|BADSLOT|Garchomp|342/342\n|win|Alice"
        record = parse_log(log_text)
        assert record.p1_team == []

    def test_switch_adds_species_without_preview(self):
        """Line 297: species appended from switch when not in team preview."""
        log_text = (
            "|player|p1|Alice\n"
            "|player|p2|Bob\n"
            "|turn|1\n"
            "|switch|p1a: Garchomp|Garchomp|342/342\n"
            "|win|Alice\n"
        )
        record = parse_log(log_text)
        assert "Garchomp" in record.p1_team

    def test_switch_does_not_duplicate_preview_species(self):
        """Species from preview not added again by switch."""
        log_text = (
            "|player|p1|Alice\n"
            "|poke|p1|Garchomp|\n"
            "|turn|1\n"
            "|switch|p1a: Garchomp|Garchomp|342/342\n"
            "|win|Alice\n"
        )
        record = parse_log(log_text)
        assert record.p1_team.count("Garchomp") == 1


# ── _on_heal ─────────────────────────────────────────────────────────────────

class TestOnHeal:
    def test_heal_event_recorded(self):
        """Lines 340-345: _on_heal handler."""
        log_text = (
            "|player|p1|Alice\n"
            "|turn|1\n"
            "|-heal|p1a: Garchomp|342/342\n"
            "|win|Alice\n"
        )
        record = parse_log(log_text)
        events = [e for t in record.turns for e in t.events if e.kind == "heal"]
        assert len(events) == 1
        assert events[0].slot == "p1a"
        assert events[0].hp_after == pytest.approx(1.0)


# ── _on_status ────────────────────────────────────────────────────────────────

class TestOnStatus:
    def test_status_event_recorded(self):
        """Lines 351-356: _on_status handler."""
        log_text = (
            "|player|p1|Alice\n"
            "|turn|1\n"
            "|-status|p1a: Garchomp|brn\n"
            "|win|Alice\n"
        )
        record = parse_log(log_text)
        events = [e for t in record.turns for e in t.events if e.kind == "status"]
        assert len(events) == 1
        assert events[0].slot == "p1a"
        assert events[0].detail == "brn"


# ── _on_boost ─────────────────────────────────────────────────────────────────

class TestOnBoost:
    def test_boost_event_recorded(self):
        """Lines 362-373: _on_boost handler."""
        log_text = (
            "|player|p1|Alice\n"
            "|turn|1\n"
            "|-boost|p1a: Garchomp|atk|2\n"
            "|win|Alice\n"
        )
        record = parse_log(log_text)
        events = [e for t in record.turns for e in t.events if e.kind == "boost"]
        assert len(events) == 1
        assert events[0].detail == "atk:+2"

    def test_unboost_event_negative(self):
        log_text = (
            "|player|p1|Alice\n"
            "|turn|1\n"
            "|-unboost|p1a: Garchomp|spe|1\n"
            "|win|Alice\n"
        )
        record = parse_log(log_text)
        events = [e for t in record.turns for e in t.events if e.kind == "boost"]
        assert len(events) == 1
        assert events[0].detail == "spe:-1"

    def test_boost_invalid_value_defaults_zero(self):
        """ValueError branch in _on_boost."""
        log_text = (
            "|player|p1|Alice\n"
            "|turn|1\n"
            "|-boost|p1a: Garchomp|atk|NOTANUMBER\n"
            "|win|Alice\n"
        )
        record = parse_log(log_text)
        events = [e for t in record.turns for e in t.events if e.kind == "boost"]
        assert len(events) == 1
        assert events[0].detail == "atk:+0"

    def test_boost_short_parts_ignored(self):
        """_on_boost needs at least 5 parts."""
        log_text = "|player|p1|Alice\n|turn|1\n|-boost|p1a: Garchomp|atk\n|win|Alice"
        record = parse_log(log_text)
        events = [e for t in record.turns for e in t.events if e.kind == "boost"]
        assert len(events) == 0


# ── _on_faint p2 ─────────────────────────────────────────────────────────────

class TestOnFaintP2:
    def test_p2_faint_increments_counter(self):
        """Line 388: elif player == 'p2' branch."""
        log_text = (
            "|player|p1|Alice\n"
            "|player|p2|Bob\n"
            "|turn|1\n"
            "|faint|p2a: Iron Hands\n"
            "|win|Alice\n"
        )
        record = parse_log(log_text)
        assert record.p2_fainted == 1
        assert record.p1_fainted == 0

    def test_p1_faint_increments_p1_counter(self):
        log_text = (
            "|player|p1|Alice\n"
            "|turn|1\n"
            "|faint|p1a: Garchomp\n"
            "|win|Alice\n"
        )
        record = parse_log(log_text)
        assert record.p1_fainted == 1


# ── _on_tera ─────────────────────────────────────────────────────────────────

class TestOnTera:
    def test_tera_event_recorded(self):
        """Lines 394-399: _on_tera handler."""
        log_text = (
            "|player|p1|Alice\n"
            "|turn|1\n"
            "|-terastallize|p1a: Garchomp|Dragon\n"
            "|win|Alice\n"
        )
        record = parse_log(log_text)
        events = [e for t in record.turns for e in t.events if e.kind == "tera"]
        assert len(events) == 1
        assert events[0].slot == "p1a"
        assert events[0].detail == "Dragon"

    def test_tera_short_parts_ignored(self):
        log_text = "|player|p1|Alice\n|turn|1\n|-terastallize|p1a: Garchomp\n|win|Alice"
        record = parse_log(log_text)
        events = [e for t in record.turns for e in t.events if e.kind == "tera"]
        assert len(events) == 0


# ── _on_win branches ─────────────────────────────────────────────────────────

class TestOnWinBranches:
    def test_p1_wins(self):
        """Line 410: winner_name == p1_name."""
        record = parse_log("|player|p1|Alice\n|player|p2|Bob\n|win|Alice")
        assert record.winner == "p1"

    def test_p2_wins(self):
        """Line 412: winner_name == p2_name."""
        record = parse_log("|player|p1|Alice\n|player|p2|Bob\n|win|Bob")
        assert record.winner == "p2"

    def test_unknown_winner(self):
        """Line 413: name matches neither player."""
        record = parse_log("|player|p1|Alice\n|player|p2|Bob\n|win|Charlie")
        assert record.winner == "unknown"
        assert record.winner_name == "Charlie"


# ── _on_tie ───────────────────────────────────────────────────────────────────

class TestOnTie:
    def test_tie_sets_winner(self):
        """Lines 416-417: _on_tie handler."""
        record = parse_log("|player|p1|Alice\n|player|p2|Bob\n|tie")
        assert record.winner == "tie"
        assert record.winner_name == ""


# ── parse_replay_file ─────────────────────────────────────────────────────────

class TestParseReplayFile:
    def test_reads_and_parses(self, tmp_path):
        """Lines 484-485: parse_replay_file."""
        path = _write_replay(tmp_path, "battle.json", winner="Alice", rating=1500)
        record = parse_replay_file(path)
        assert record.replay_id == "battle"
        assert record.format == "gen9ou"
        assert record.rating == 1500

    def test_winner_detected(self, tmp_path):
        path = _write_replay(tmp_path, "game.json", winner="Alice")
        record = parse_replay_file(path)
        assert record.winner == "p1"   # Alice is p1

    def test_formatid_preferred_over_format(self, tmp_path):
        data = {
            "id": "test-1",
            "formatid": "gen9ou",
            "format": "[Gen 9] OU",
            "rating": 1200,
            "log": "|win|Alice",
        }
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        record = parse_replay_file(path)
        assert record.format == "gen9ou"


# ── parse_replay_dir ──────────────────────────────────────────────────────────

class TestParseReplayDir:
    def test_parses_all_files(self, tmp_path):
        for i in range(3):
            _write_replay(tmp_path, f"battle{i}.json", winner="Alice")
        records = parse_replay_dir(tmp_path)
        assert len(records) == 3

    def test_max_count_limits_results(self, tmp_path):
        """Line 502: files[:max_count] slicing."""
        for i in range(5):
            _write_replay(tmp_path, f"battle{i}.json")
        records = parse_replay_dir(tmp_path, max_count=2)
        assert len(records) == 2

    def test_invalid_json_skipped(self, tmp_path):
        """Lines 504-507: error handling for bad files."""
        (tmp_path / "bad.json").write_text("not valid json", encoding="utf-8")
        records = parse_replay_dir(tmp_path)
        assert records == []

    def test_mix_valid_and_invalid(self, tmp_path):
        _write_replay(tmp_path, "good.json", winner="Alice")
        (tmp_path / "bad.json").write_text("INVALID", encoding="utf-8")
        records = parse_replay_dir(tmp_path)
        assert len(records) == 1

    def test_empty_dir(self, tmp_path):
        records = parse_replay_dir(tmp_path)
        assert records == []

    def test_max_count_zero_means_all(self, tmp_path):
        """max_count=0 should not slice."""
        for i in range(4):
            _write_replay(tmp_path, f"battle{i}.json")
        records = parse_replay_dir(tmp_path, max_count=0)
        assert len(records) == 4
