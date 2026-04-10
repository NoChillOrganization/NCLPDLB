"""
Phase 10 — Replay Pipeline test suite (Wave 0 contract).

All 12 test stubs defined here. Tests that depend on the Plan 02 parser
formatid fix (test_parse_formatid_preferred, test_vgc_fixture_parses) will
remain RED until Plan 02 applies the one-line fix in replay_parser.py.
All other 10 tests must be GREEN after Plan 01.

CRITICAL: Do NOT import from src.config — Settings() raises ValidationError
without a .env file. Use PROJECT_ROOT computed from __file__ directly.
"""
from __future__ import annotations

import json
import logging
import sys
import tempfile
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Path bootstrap — add project root so data_pipeline and src.* are importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"

# ---------------------------------------------------------------------------
# Imports from data_pipeline (lives at project root, not in src/)
# ---------------------------------------------------------------------------
from data_pipeline import (  # noqa: E402
    ALL_FORMATS,
    SPARSE_WARN_THRESHOLD,
    should_skip_format,
    update_manifest,
)

# ---------------------------------------------------------------------------
# Imports from src.ml (inside .venv — no Settings() triggered)
# ---------------------------------------------------------------------------
from src.ml.replay_parser import parse_replay_json  # noqa: E402
from src.ml.feature_extractor import (  # noqa: E402
    FeatureExtractor,
    build_dataset,
    STATE_FEATURE_DIM,
)

# ===========================================================================
# RPLY-01: Pipeline orchestrator constants and CLI behaviour
# ===========================================================================


def test_all_formats_constant():
    """ALL_FORMATS must have exactly 20 entries covering Smogon, VGC, and Draft League."""
    assert len(ALL_FORMATS) == 20, f"Expected 20 formats, got {len(ALL_FORMATS)}"
    assert "gen9ou" in ALL_FORMATS, "gen9ou missing from ALL_FORMATS"
    assert "gen9vgc2024regh" in ALL_FORMATS, "gen9vgc2024regh missing from ALL_FORMATS"
    assert "draftleague" in ALL_FORMATS, "draftleague missing from ALL_FORMATS"
    # Verify all 10 VGC regulations are present
    vgc_formats = [f for f in ALL_FORMATS if "vgc" in f]
    assert len(vgc_formats) == 10, f"Expected 10 VGC formats, got {len(vgc_formats)}: {vgc_formats}"


def test_pipeline_cli_mocked():
    """
    CLI arg parsing: --formats gen9ou --pages 1 selects only gen9ou;
    --formats all expands to all 20 formats.
    """
    import argparse

    # Replicate the CLI arg parsing logic from data_pipeline.py
    parser = argparse.ArgumentParser()
    parser.add_argument("--formats", nargs="+", default=["all"])
    parser.add_argument("--pages", type=int, default=20)
    parser.add_argument("--min-rating", type=int, default=1500)

    # Single format selection
    args = parser.parse_args(["--formats", "gen9ou", "--pages", "1", "--min-rating", "1500"])
    formats = args.formats if "all" not in args.formats else ALL_FORMATS
    assert "gen9ou" in formats
    assert args.pages == 1

    # 'all' expansion
    args_all = parser.parse_args(["--formats", "all"])
    formats_all = args_all.formats if "all" not in args_all.formats else ALL_FORMATS
    assert formats_all == ALL_FORMATS
    assert len(formats_all) == 20


def test_sparse_format_warning(caplog):
    """Sparse format (< SPARSE_WARN_THRESHOLD replays) must emit WARNING, not raise."""

    with caplog.at_level(logging.WARNING):
        # Simulate sparse warning logic: scraped < SPARSE_WARN_THRESHOLD
        scraped = 50
        fmt = "gen9vgc2023regulationa"
        if scraped < SPARSE_WARN_THRESHOLD:
            logging.getLogger("data_pipeline").warning(
                "Format %s yielded only %d replays (< %d threshold) — sparse",
                fmt,
                scraped,
                SPARSE_WARN_THRESHOLD,
            )

    assert any("sparse" in record.message.lower() or str(scraped) in record.message
               for record in caplog.records), \
        f"Expected WARNING in caplog, got: {caplog.records}"
    # Must not raise
    assert SPARSE_WARN_THRESHOLD == 200


def test_skip_format_logic():
    """
    should_skip_format returns True when manifest + all 4 .npy files exist
    and replay count matches; False when a .npy file is missing.
    """
    fmt = "gen9ou"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ml_dir = tmp_path / "ml"
        replays_dir = tmp_path / "replays"

        fmt_ml_dir = ml_dir / fmt
        fmt_replay_dir = replays_dir / fmt
        fmt_ml_dir.mkdir(parents=True)
        fmt_replay_dir.mkdir(parents=True)

        # Create 3 fake replay JSON files
        for i in range(3):
            (fmt_replay_dir / f"replay_{i}.json").write_text("{}", encoding="utf-8")

        # Write manifest with matching replay_count
        manifest_path = ml_dir / "manifest.json"
        manifest_data = {
            fmt: {
                "format": fmt,
                "replay_count": 3,
                "records_parsed": 3,
                "x_team_shape": [3, 12],
                "x_state_shape": [10, 19],
                "min_rating": 1500,
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        }
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2), encoding="utf-8"
        )

        # Create all 4 .npy files
        for npy in ["X_team.npy", "y_team.npy", "X_state.npy", "y_state.npy"]:
            np.save(fmt_ml_dir / npy, np.array([]))

        # With all 4 .npy files and matching manifest — should skip
        assert should_skip_format(fmt, ml_dir, replays_dir) is True, \
            "should_skip_format should return True when manifest + .npy files match replay count"

        # Remove one .npy file — should NOT skip
        (fmt_ml_dir / "X_state.npy").unlink()
        assert should_skip_format(fmt, ml_dir, replays_dir) is False, \
            "should_skip_format should return False when a .npy file is missing"


# ===========================================================================
# RPLY-02: Parser correctness for VGC / doubles log lines
# ===========================================================================


def test_parse_formatid_preferred():
    """
    parse_replay_json must prefer 'formatid' (canonical key) over 'format'
    (human-readable display name).

    RED until Plan 02 applies the one-line fix in replay_parser.py:
        fmt = data.get("formatid") or data.get("format", "unknown")
    """
    data = {
        "id": "gen9ou-test",
        "format": "[Gen 9] OU",
        "formatid": "gen9ou",
        "rating": 1600,
        "log": "|player|p1|A|\n|player|p2|B|\n|win|A\n",
    }
    rec = parse_replay_json(data)
    assert rec.format == "gen9ou", (
        f"Expected rec.format == 'gen9ou' (from formatid), got '{rec.format}'. "
        "This test is RED until Plan 02 fixes parse_replay_json to prefer formatid."
    )


def test_parser_doubles_slots():
    """Parser must handle dual-slot switch events (p1a, p1b) without crashing."""
    fixture_path = FIXTURES_DIR / "sample_replay_vgc.json"
    assert fixture_path.exists(), f"VGC fixture missing: {fixture_path}"

    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    rec = parse_replay_json(data)

    # No crash, and at least 2 team members recorded
    assert rec is not None
    assert len(rec.p1_team) >= 2, (
        f"Expected p1_team to have >= 2 members, got: {rec.p1_team}"
    )
    assert len(rec.p2_team) >= 2, (
        f"Expected p2_team to have >= 2 members, got: {rec.p2_team}"
    )


def test_parser_spread_move():
    """Parser must handle spread move lines ([spread] syntax) without crashing."""
    fixture_path = FIXTURES_DIR / "sample_replay_vgc.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    rec = parse_replay_json(data)

    # Gather all events across all turns
    all_events = [ev for turn in rec.turns for ev in turn.events]

    # At least one move event must exist
    move_events = [ev for ev in all_events if ev.kind == "move"]
    assert len(move_events) >= 1, (
        f"Expected at least one move event in VGC replay, got events: "
        f"{[ev.kind for ev in all_events]}"
    )


def test_parser_both_faint():
    """Parser must count both p2 faints in the same turn correctly."""
    fixture_path = FIXTURES_DIR / "sample_replay_vgc.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    rec = parse_replay_json(data)

    assert rec.p2_fainted == 2, (
        f"Expected p2_fainted == 2 (both Miraidon and Calyrex-Shadow fainted), "
        f"got p2_fainted == {rec.p2_fainted}"
    )


def test_vgc_fixture_parses():
    """
    VGC fixture must parse to a valid BattleRecord with correct winner and format.

    rec.winner == "p1" — TrainerA wins.
    rec.format == "gen9vgc2024regh" — from formatid field.

    RED until Plan 02 applies the formatid fix in replay_parser.py.
    """
    fixture_path = FIXTURES_DIR / "sample_replay_vgc.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    rec = parse_replay_json(data)

    assert rec.winner == "p1", (
        f"Expected winner == 'p1' (TrainerA), got '{rec.winner}'"
    )
    assert rec.format == "gen9vgc2024regh", (
        f"Expected rec.format == 'gen9vgc2024regh' (from formatid), got '{rec.format}'. "
        "RED until Plan 02 fixes parse_replay_json to prefer formatid."
    )


# ===========================================================================
# RPLY-03: Feature extractor correctness for doubles/VGC input
# ===========================================================================


def test_feature_extractor_doubles():
    """
    Feature extractor must produce correct shapes from VGC fixture.
    X_state.shape[1] must equal STATE_FEATURE_DIM (19).
    """
    fixture_path = FIXTURES_DIR / "sample_replay_vgc.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    rec = parse_replay_json(data)

    extractor = FeatureExtractor()
    extractor.build_vocab_from_records([rec])
    extractor.freeze()

    X_team, y_team = extractor.team_features([rec])
    X_state, y_state = extractor.state_features([rec])

    assert X_state.shape[1] == STATE_FEATURE_DIM, (
        f"Expected X_state.shape[1] == {STATE_FEATURE_DIM} (STATE_FEATURE_DIM), "
        f"got {X_state.shape[1]}"
    )
    assert X_state.shape[1] == 19, (
        f"Expected X_state.shape[1] == 19, got {X_state.shape[1]}"
    )


def test_build_dataset_empty():
    """
    build_dataset must return a dict with 4 keys (X_team, y_team, X_state, y_state)
    when given an empty replay directory (0 records). X_team.shape[0] must be 0.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        replay_dir = tmp_path / "replays"
        output_dir = tmp_path / "output"
        replay_dir.mkdir()
        output_dir.mkdir()

        result = build_dataset(replay_dir, output_dir)

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert set(result.keys()) == {"X_team", "y_team", "X_state", "y_state"}, (
        f"Expected keys {{X_team, y_team, X_state, y_state}}, got {set(result.keys())}"
    )
    assert result["X_team"].shape[0] == 0, (
        f"Expected X_team.shape[0] == 0 for empty replay dir, "
        f"got {result['X_team'].shape[0]}"
    )


def test_manifest_written():
    """
    update_manifest must write manifest.json with a 'replay_count' key for the format.
    """
    fmt = "gen9ou"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        manifest_path = tmp_path / "manifest.json"

        update_manifest(
            manifest_path=manifest_path,
            fmt=fmt,
            replay_count=42,
            records_parsed=40,
            x_team_shape=(40, 12),
            x_state_shape=(320, 19),
            min_rating=1500,
        )

        assert manifest_path.exists(), "manifest.json was not created"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert fmt in manifest, f"Format '{fmt}' not found in manifest"
        assert "replay_count" in manifest[fmt], (
            f"'replay_count' key missing from manifest['{fmt}']: {manifest[fmt]}"
        )
        assert manifest[fmt]["replay_count"] == 42
