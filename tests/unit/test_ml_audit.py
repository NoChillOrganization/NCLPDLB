"""
ML Audit Test Suite — Phase 8 Plan 01
======================================

Three-tier audit of all 11 modules in src/ml/:

  Level 1 — Import tests (parametrized): verifies each module can be imported
             without raising. Deps that are absent in .venv are guarded with
             pytest.importorskip() so missing-dep cases SKIP rather than ERROR.

  Level 2 — Smoke tests: calls public APIs with minimal fixture data to confirm
             the module's core logic is functional, not just importable.

  Level 3 — Infra notes: documents modules that require a live Pokemon Showdown
             server (battle_env, train_policy, train_all, showdown_player) via
             explicit pytest.skip() calls with informative messages.

Run command (from projects/pokemon-draft-bot/):
    .venv/Scripts/pytest tests/unit/test_ml_audit.py -v

Environment notes:
    - Must use .venv/Scripts/pytest (not system Python) — torch/poke-env/numpy live in .venv
    - aiohttp is ABSENT from .venv by design (ML env isolation); replay_scraper SKIPS
    - sklearn was installed during audit setup: scikit-learn 1.8.0

AUDIT RESULTS (run 2026-03-17 with .venv/Scripts/pytest):
# replay_parser:       PASS (import + smoke: parse_log, BattleRecord structure)
# teams:               PASS (import + smoke: FORMAT_TEAMS 18+ formats, GEN9OU 5+ teams, @ notation)
# train_all:           PASS (import)
# replay_scraper:      SKIP (aiohttp absent in .venv — ML env isolation by design)
# feature_extractor:   PASS (import + smoke: build_vocab, team_features X/y shapes)
# train_matchup:       PASS (import + smoke: _embed_team_matrix runs; predict_matchup needs model file)
# battle_env:          PASS (import; POKE_ENV_AVAILABLE=True — poke-env 0.12.0 in .venv)
# train_policy:        PASS (import; POKE_ENV_AVAILABLE=True — poke-env 0.12.0 in .venv)
# showdown_player:     SKIP (gspread absent in .venv; top-level sheets import blocks import)
#                           AUDIT FINDING: showdown_player.py has unguarded cross-env dep
#                           (src.data.sheets requires gspread, a system Python package)
# teambuilder:         PASS (import + smoke: RotatingTeambuilder round-robin over gen9ou teams)
# models/__init__:     PASS (import; skeletal — single comment, no symbols exported)
#
# Summary: 17 passed, 4 skipped (0 failed) across 21 test cases
#   - aiohttp absent: replay_scraper import + instantiation skip (expected)
#   - gspread absent: showdown_player import skips (audit finding: unguarded cross-env dep)
#   - infra skip: 1 documentation test for Showdown server requirement
#   - sklearn 1.8.0 installed during audit setup (was absent; now in .venv)
"""
from __future__ import annotations

import importlib

import pytest

# ── Fixture data ──────────────────────────────────────────────────────────────

MINIMAL_LOG = (
    "|player|p1|Ash|\n|player|p2|Gary|\n"
    "|poke|p1|Garchomp, M|\n|poke|p1|Corviknight|\n"
    "|poke|p2|Miraidon|\n|poke|p2|Flutter Mane|\n"
    "|turn|1\n"
    "|switch|p1a: Garchomp|Garchomp, M|342/342\n"
    "|switch|p2a: Miraidon|Miraidon|397/397\n"
    "|move|p1a: Garchomp|Earthquake|p2a: Miraidon\n"
    "|-damage|p2a: Miraidon|0 fnt\n"
    "|faint|p2a: Miraidon\n"
    "|turn|2\n"
    "|win|Ash\n"
)


# ── Level 1: Import tests (all 11 modules) ────────────────────────────────────

@pytest.mark.parametrize("module_path,requires", [
    ("src.ml.replay_parser", []),
    ("src.ml.teams", []),
    ("src.ml.train_all", []),
    ("src.ml.replay_scraper", ["aiohttp"]),
    ("src.ml.feature_extractor", ["numpy"]),
    ("src.ml.train_matchup", ["numpy", "sklearn"]),
    ("src.ml.battle_env", ["numpy"]),
    ("src.ml.train_policy", ["numpy"]),
    ("src.ml.showdown_player", ["numpy", "gspread"]),  # top-level sheets import requires gspread
    ("src.ml.teambuilder", ["poke_env"]),
    ("src.ml.models", []),
])
def test_module_imports(module_path, requires):
    """Level 1: every ml module must import without raising."""
    for dep in requires:
        pytest.importorskip(dep)
    mod = importlib.import_module(module_path)
    assert mod is not None


# ── Level 2: Smoke tests ──────────────────────────────────────────────────────

def test_replay_parser_smoke():
    """Level 2: parse_log() produces a correct BattleRecord from MINIMAL_LOG."""
    from src.ml.replay_parser import parse_log

    record = parse_log(MINIMAL_LOG, replay_id="test-001", format="gen9ou", rating=1500)

    assert record.p1_name == "Ash"
    assert record.p2_name == "Gary"
    assert record.winner == "p1"
    # Team preview: Garchomp listed first for p1
    assert any("Garchomp" in species for species in record.p1_team)
    assert record.total_turns == 2


def test_feature_extractor_smoke():
    """Level 2: build vocab and extract team features from a parsed record."""
    pytest.importorskip("numpy")

    from src.ml.replay_parser import parse_log
    from src.ml.feature_extractor import FeatureExtractor

    record = parse_log(MINIMAL_LOG, replay_id="test-001", format="gen9ou", rating=1500)
    extractor = FeatureExtractor()
    extractor.build_vocab_from_records([record])
    X, y = extractor.team_features([record])

    assert X.shape[0] == 1, f"Expected 1 row, got {X.shape[0]}"
    assert y.shape == (1,), f"Expected shape (1,), got {y.shape}"
    # TEAM_SIZE is 6 — X.shape[1] should be 12 (6 pokemon per side)
    assert X.shape[1] == 12, f"Expected 12 features (6+6), got {X.shape[1]}"
    assert y[0] == 1, f"p1 won so label should be 1, got {y[0]}"


def test_replay_scraper_instantiation(tmp_path):
    """Level 2: ReplayScraper can be instantiated without network calls.

    # Skips in .venv (ML env) — aiohttp is system Python only.
    # aiohttp was NOT installed into .venv by design (ML env isolation).
    """
    pytest.importorskip("aiohttp")  # SKIPS in .venv

    from src.ml.replay_scraper import ReplayScraper

    scraper = ReplayScraper(format="gen9ou", output_dir=tmp_path)
    assert scraper.format == "gen9ou"
    assert scraper.out_dir == tmp_path / "gen9ou"


def test_train_matchup_smoke():
    """Level 2: _embed_team_matrix() runs without a trained model file."""
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("sklearn")

    from src.ml.train_matchup import _embed_team_matrix

    # X_raw shape (n, 12): 6 pokemon IDs per side, int32
    X_raw = numpy.array([[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]], dtype=numpy.int32)
    result = _embed_team_matrix(X_raw, vocab_size=20)
    # Shape[0] must be 1 (one game)
    assert result.shape[0] == 1, f"Expected 1 row, got {result.shape[0]}"
    # Note: predict_matchup requires a trained model file — do NOT call it here


def test_teambuilder_smoke():
    """Level 2: RotatingTeambuilder instantiates with gen9ou teams.

    # teambuilder.py has no import guard — unlike battle_env/train_policy.
    # poke-env 0.12.0 is installed in .venv so this should PASS.
    """
    pytest.importorskip("poke_env")

    from src.ml.teambuilder import RotatingTeambuilder
    from src.ml.teams import FORMAT_TEAMS

    teams = FORMAT_TEAMS.get("gen9ou", [])
    assert len(teams) > 0, "FORMAT_TEAMS['gen9ou'] is empty"

    tb = RotatingTeambuilder(teams)
    assert tb is not None
    assert len(tb) == len(teams)


def test_teams_structure():
    """Level 2: FORMAT_TEAMS has 10+ formats, each with at least one team; GEN9OU has 5+."""
    from src.ml.teams import FORMAT_TEAMS, GEN9OU

    assert len(FORMAT_TEAMS) >= 10, f"Expected 10+ formats, got {len(FORMAT_TEAMS)}"
    for fmt, teams in FORMAT_TEAMS.items():
        assert len(teams) > 0, f"FORMAT_TEAMS['{fmt}'] is empty"

    assert len(GEN9OU) >= 5, f"Expected 5+ GEN9OU teams, got {len(GEN9OU)}"


def test_teams_showdown_format():
    """Level 2: Every format's teams contain at least one team with '@' item notation."""
    from src.ml.teams import FORMAT_TEAMS

    for fmt, teams in FORMAT_TEAMS.items():
        assert any("@" in t for t in teams), (
            f"FORMAT_TEAMS['{fmt}'] has no team string containing '@' (item notation)"
        )


# ── Level 3: Infra documentation ──────────────────────────────────────────────

def test_infra_dependent_modules_require_showdown():
    """Level 3: Documents infra requirements — always skips (documentation artifact).

    battle_env, train_policy, train_all, showdown_player require a live Pokemon
    Showdown server (ps.lookclient.com:8000 or local). poke-env 0.12.0 must be
    installed. Run manually when infra is available. Import-only tests for these
    run in test_module_imports.
    """
    pytest.skip(
        "battle_env, train_policy, train_all, showdown_player require a live Pokemon "
        "Showdown server (ps.lookclient.com:8000 or local). poke-env 0.12.0 must be "
        "installed. Run manually when infra is available. Import-only tests for these "
        "run in test_module_imports."
    )


# ── Level 3: POKE_ENV_AVAILABLE flag checks ───────────────────────────────────

def test_battle_env_poke_env_flag():
    """Level 3: Import battle_env and record POKE_ENV_AVAILABLE value."""
    pytest.importorskip("numpy")  # top-level numpy import in battle_env

    import src.ml.battle_env as battle_env_mod

    flag_value = battle_env_mod.POKE_ENV_AVAILABLE
    # Record the value — True in .venv (poke-env installed), False otherwise
    # Do NOT assert True unconditionally — audit records the actual value
    print(f"\n[AUDIT] battle_env.POKE_ENV_AVAILABLE = {flag_value}")
    assert isinstance(flag_value, bool), (
        f"POKE_ENV_AVAILABLE should be bool, got {type(flag_value)}"
    )


def test_train_policy_poke_env_flag():
    """Level 3: Import train_policy and record POKE_ENV_AVAILABLE value."""
    pytest.importorskip("numpy")  # needed for top-level numpy import in battle_env (dep)

    import src.ml.train_policy as train_policy_mod

    flag_value = train_policy_mod.POKE_ENV_AVAILABLE
    # Record the value — True in .venv (poke-env installed), False otherwise
    print(f"\n[AUDIT] train_policy.POKE_ENV_AVAILABLE = {flag_value}")
    assert isinstance(flag_value, bool), (
        f"POKE_ENV_AVAILABLE should be bool, got {type(flag_value)}"
    )
