"""Pins Battle format behaviour through the src.ml.formats registry interface."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from src.ml import formats

REPO = Path(__file__).resolve().parents[2]

# spar format -> (train fmt, team fmt) exactly as shipped before the registry existed
EXPECTED = {
    "gen9randombattle": ("gen9randombattle", None),
    "gen9monotyperandombattle": ("gen9monotyperandombattle", None),
    "gen9randomdoublesbattle": ("gen9randomdoublesbattle", None),
    **{
        f: (f, f)
        for f in (
            "gen9ou gen9ubers gen9uu gen9ru gen9nu gen9pu gen9zu gen9lc gen9monotype "
            "gen9nationaldex gen9anythinggoes gen9doublesou gen9doublesubers gen9doublesuu"
        ).split()
    },
    "gen9championsou": ("gen9championsou", None),
    "gen9championsbssregmb": ("gen9championsbssregmb", None),
    "gen9championsvgc2026regmb": ("gen9championsvgc2026regmb", None),
    "gen9championsvgc2026regmbbo3": ("gen9championsvgc2026regmbbo3", None),
}
DOUBLES_SPAR = {
    "gen9randomdoublesbattle",
    "gen9doublesou",
    "gen9doublesubers",
    "gen9doublesuu",
    "gen9championsvgc2026regmb",
    "gen9championsvgc2026regmbbo3",
}


def test_spar_formats_and_train_team_formats():
    assert formats.TRAINING_MAP == EXPECTED
    assert formats.SPAR_FORMATS == list(EXPECTED)


@pytest.mark.parametrize("fmt", EXPECTED)
def test_spar_format_resolution(fmt):
    train_fmt, _ = EXPECTED[fmt]
    assert formats.is_doubles(fmt) == (fmt in DOUBLES_SPAR)
    assert formats.display_name(fmt) != fmt  # every spar format has a display name
    assert formats.resolve_training(fmt)[0] == formats.TRAINING_FORMAT_ALIASES.get(
        train_fmt, train_fmt
    )


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [
        ("gen9ou", ("gen9ou", None)),
        ("gen9vgc2026regibo3", ("gen9vgc2026regi", "gen9vgc2026regi")),
        ("gen9championsou", ("gen9ou", "gen9ou")),
        ("gen9championsbssregmb", ("gen9ou", "gen9ou")),
        ("gen9championsvgc2026regmb", ("gen9vgc2026regi", "gen9vgc2026regi")),
        ("gen9championsvgc2026regmbbo3", ("gen9vgc2026regi", "gen9vgc2026regi")),
    ],
)
def test_alias_inherits_team_format(fmt, expected):
    assert formats.resolve_training(fmt) == expected


def test_explicit_team_format_wins_over_alias_inheritance():
    assert formats.resolve_training("gen9championsou", "gen9ubers") == (
        "gen9ou",
        "gen9ubers",
    )


def test_doubles_detection_uses_alias_target():
    assert formats.is_doubles("gen9vgc2026regibo3")
    assert formats.is_doubles("gen9doublesnu")  # doubles but not a spar format
    assert not formats.is_doubles("gen9championsou")
    assert not formats.is_doubles("gen9ou")


def test_display_names():
    assert formats.display_name("gen9ou") == "Gen 9 OU"
    assert formats.display_name("gen9vgc2025reggbo3") == "VGC 2025 Reg G (Bo3)"
    assert formats.display_name("unknown") == "unknown"


def test_team_pool_keys_and_lookup():
    from src.ml.teams import FORMAT_TEAMS

    assert len(formats.TEAM_POOL_KEYS) == 23
    assert list(FORMAT_TEAMS) == formats.TEAM_POOL_KEYS
    assert formats.team_pool("gen9ou") is FORMAT_TEAMS["gen9ou"]
    assert len(formats.team_pool("gen9ou")) == 5
    assert formats.team_pool("gen9championsou") is None
    assert formats.team_pool("gen9randombattle") is None


def test_every_non_random_spar_team_format_has_a_pool():
    for _, team_fmt in formats.TRAINING_MAP.values():
        if team_fmt:
            assert formats.team_pool(team_fmt)


def test_alias_inheritance_always_lands_on_a_pool():
    for fmt in formats.TRAINING_FORMAT_ALIASES:
        assert formats.team_pool(formats.resolve_training(fmt)[1])


def _ci_matrix() -> dict[str, str]:
    text = (REPO / ".github/workflows/train-models.yml").read_text(encoding="utf-8")
    return dict(
        re.findall(
            r"^\s*- \{ format: (\w+),\s+team_format: \"?(\w*)\"?,\s+timesteps",
            text,
            re.MULTILINE,
        )
    )


def test_ci_matrix_formats_match_registry():
    matrix = list(_ci_matrix())
    assert len(matrix) == len(set(matrix))
    assert set(matrix) == set(formats.SPAR_FORMATS)


def test_ci_matrix_team_formats_match_registry_except_champions():
    # Known drift: CI passes team_format == format id for Champions formats, which
    # have no data/teams file; the registry says None (teams inherited via alias).
    for fmt, team_fmt in _ci_matrix().items():
        if "champions" in fmt:
            continue
        assert team_fmt == (formats.TRAINING_MAP[fmt][1] or ""), fmt


def test_registry_imports_cheaply():
    code = (
        "import sys, src.ml.formats; "
        "bad=[m for m in ('torch','poke_env','discord','stable_baselines3') if m in sys.modules]; "
        "sys.exit(1 if bad else 0)"
    )
    assert (
        subprocess.run([sys.executable, "-c", code], cwd=REPO, check=False).returncode
        == 0
    )
