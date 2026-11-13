"""
Battle format registry — single home for the Train/Spar/Team format relationship.

Stdlib-only on purpose: the Bot, scripts and trainers all import this, so it must
not pull in torch / poke-env / discord.

Terms (see GLOSSARY.md):
  Spar format  — key in TRAINING_MAP with a non-None train format (what /spar offers)
  Train format — actual Showdown format string trained on (after aliasing)
  Team format  — key into the Team pool (data/teams/<key>.txt); None = no teams
"""

from __future__ import annotations

# ── Spar format → (train format, team format) ────────────────────────────────
# train_fmt: actual Showdown format string passed to train_policy.py (None = SKIP)
# team_fmt : key into the Team pool for RotatingTeambuilder (None = no teams;
#            aliased formats then inherit their base format's teams, see
#            resolve_training()).
# Mirrors the train-models.yml matrix (asserted by tests/unit/test_formats.py).
TRAINING_MAP: dict[str, tuple[str | None, str | None]] = {
    # Random Battle (no teams needed)
    "gen9randombattle": ("gen9randombattle", None),
    "gen9monotyperandombattle": ("gen9monotyperandombattle", None),
    "gen9randomdoublesbattle": ("gen9randomdoublesbattle", None),
    # Smogon Singles
    "gen9ou": ("gen9ou", "gen9ou"),
    "gen9ubers": ("gen9ubers", "gen9ubers"),
    "gen9uu": ("gen9uu", "gen9uu"),
    "gen9ru": ("gen9ru", "gen9ru"),
    "gen9nu": ("gen9nu", "gen9nu"),
    "gen9pu": ("gen9pu", "gen9pu"),
    "gen9zu": ("gen9zu", "gen9zu"),
    "gen9lc": ("gen9lc", "gen9lc"),
    "gen9monotype": ("gen9monotype", "gen9monotype"),
    "gen9nationaldex": ("gen9nationaldex", "gen9nationaldex"),
    "gen9anythinggoes": ("gen9anythinggoes", "gen9anythinggoes"),
    # Smogon Doubles
    "gen9doublesou": ("gen9doublesou", "gen9doublesou"),
    "gen9doublesubers": ("gen9doublesubers", "gen9doublesubers"),
    "gen9doublesuu": ("gen9doublesuu", "gen9doublesuu"),
    # Champions
    "gen9championsou": ("gen9championsou", None),
    "gen9championsbssregmb": ("gen9championsbssregmb", None),
    "gen9championsvgc2026regmb": ("gen9championsvgc2026regmb", None),
    "gen9championsvgc2026regmbbo3": ("gen9championsvgc2026regmbbo3", None),
}

SPAR_FORMATS: list[str] = [
    fmt for fmt, (train_fmt, _) in TRAINING_MAP.items() if train_fmt is not None
]

# Formats that use the doubles environment
DOUBLES_FORMATS = {
    # Smogon Doubles
    "gen9doublesou",
    "gen9randomdoublesbattle",
    "gen9doublesubers",
    "gen9doublesuu",
    "gen9doublesnu",
    # VGC 2025
    "gen9vgc2025regg",
    "gen9vgc2025regh",
    "gen9vgc2025regi",
    "gen9vgc2025reggbo3",
    "gen9vgc2025reghbo3",
    "gen9vgc2025regibo3",
    # VGC 2026
    "gen9vgc2026regi",
    "gen9vgc2026regibo3",
    # Champions Doubles
    "gen9championsvgc2026regmb",
    "gen9championsvgc2026regmbbo3",
}

# Some formats use the same Showdown battle mechanics as a base format.
# poke-env doesn't support the BO3 series protocol, so we train these
# using the base single-battle format while keeping artifact paths intact.
TRAINING_FORMAT_ALIASES: dict[str, str] = {
    # BO3 variants → train as the equivalent single-battle format
    "gen9vgc2026regibo3": "gen9vgc2026regi",
    # Champions formats → not on the standard Showdown server; train as
    # the closest standard format so battles can actually start.
    "gen9championsou": "gen9ou",
    "gen9championsbssregmb": "gen9ou",
    "gen9championsvgc2026regmb": "gen9vgc2026regi",
    "gen9championsvgc2026regmbbo3": "gen9vgc2026regi",
}

# Keys of the Team pool: one data/teams/<key>.txt each.
TEAM_POOL_KEYS = [
    "gen9ou",
    "gen9nationaldex",
    "gen9monotype",
    "gen9anythinggoes",
    "gen9doublesou",
    "gen9vgc2026regi",
    "gen9ubers",
    "gen9uu",
    "gen9ru",
    "gen9nu",
    "gen9pu",
    "gen9zu",
    "gen9lc",
    "gen9doublesubers",
    "gen9doublesuu",
    "gen9doublesnu",
    "gen9vgc2025regg",
    "gen9vgc2025regh",
    "gen9vgc2025regi",
    "gen9vgc2025reggbo3",
    "gen9vgc2025reghbo3",
    "gen9vgc2025regibo3",
    "gen9vgc2026regibo3",
]

FORMAT_DISPLAY = {
    # Random Battle
    "gen9randombattle": "Gen 9 Random Battle",
    "gen9monotyperandombattle": "Gen 9 Monotype Random Battle",
    "gen9randomdoublesbattle": "Gen 9 Random Doubles",
    "gen7randombattle": "Gen 7 Random Battle",
    "gen6randombattle": "Gen 6 Random Battle",
    # Smogon Singles
    "gen9ou": "Gen 9 OU",
    "gen9ubers": "Gen 9 Ubers",
    "gen9uu": "Gen 9 UU",
    "gen9ru": "Gen 9 RU",
    "gen9nu": "Gen 9 NU",
    "gen9pu": "Gen 9 PU",
    "gen9zu": "Gen 9 ZU",
    "gen9lc": "Gen 9 LC",
    "gen9monotype": "Gen 9 Monotype",
    "gen9nationaldex": "Gen 9 National Dex",
    "gen9anythinggoes": "Gen 9 Anything Goes",
    # Smogon Doubles
    "gen9doublesou": "Gen 9 Doubles OU",
    "gen9doublesubers": "Gen 9 Doubles Ubers",
    "gen9doublesuu": "Gen 9 Doubles UU",
    "gen9doublesnu": "Gen 9 Doubles NU",
    # VGC 2025
    "gen9vgc2025regg": "VGC 2025 Reg G",
    "gen9vgc2025regh": "VGC 2025 Reg H",
    "gen9vgc2025regi": "VGC 2025 Reg I",
    "gen9vgc2025reggbo3": "VGC 2025 Reg G (Bo3)",
    "gen9vgc2025reghbo3": "VGC 2025 Reg H (Bo3)",
    "gen9vgc2025regibo3": "VGC 2025 Reg I (Bo3)",
    # VGC 2026
    "gen9vgc2026regi": "VGC 2026 Reg I",
    "gen9vgc2026regibo3": "VGC 2026 Reg I (Bo3)",
    # Champions
    "gen9championsou": "Champions OU",
    "gen9championsbssregmb": "Champions BSS Reg M-B",
    "gen9championsvgc2026regmb": "Champions VGC 2026 Reg M-B",
    "gen9championsvgc2026regmbbo3": "Champions VGC 2026 Reg M-B (Bo3)",
}


def display_name(fmt: str) -> str:
    """Human-readable name; falls back to the raw format id."""
    return FORMAT_DISPLAY.get(fmt, fmt)


def resolve_training(
    fmt: str, team_format: str | None = None
) -> tuple[str, str | None]:
    """Return (train format, team format) for ``fmt``.

    Applies TRAINING_FORMAT_ALIASES; an aliased format with no explicit
    team_format inherits the base format's teams (so non-random battles can start).
    """
    training_fmt = TRAINING_FORMAT_ALIASES.get(fmt, fmt)
    if training_fmt != fmt and not team_format:
        team_format = training_fmt
    return training_fmt, team_format


def is_doubles(fmt: str) -> bool:
    """True if ``fmt`` (after aliasing) uses the doubles environment."""
    return TRAINING_FORMAT_ALIASES.get(fmt, fmt) in DOUBLES_FORMATS


def team_pool(team_format: str) -> list[str] | None:
    """Team pool for a team format, or None if it has none."""
    from src.ml.teams import FORMAT_TEAMS  # lazy: reads data/teams on first import

    return FORMAT_TEAMS.get(team_format)
