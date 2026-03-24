"""
Bot-wide constants for the Pokemon Draft League Bot.
"""

# Mapping of Pokémon Showdown format string -> human-readable display name.
# Used by /teamimport autocomplete and TeamImportConfirmView.
# Keys must match Showdown format strings exactly (case-sensitive).
SUPPORTED_FORMATS: dict[str, str] = {
    # Smogon Gen 9
    "gen9ou": "Gen 9 OU",
    "gen9ubers": "Gen 9 Ubers",
    "gen9uu": "Gen 9 UU",
    "gen9ru": "Gen 9 RU",
    "gen9nu": "Gen 9 NU",
    "gen9pu": "Gen 9 PU",
    "gen9lc": "Gen 9 Little Cup",
    "gen9monotype": "Gen 9 Monotype",
    "gen9doublesou": "Gen 9 Doubles OU",
    # VGC Gen 9 Regulations — 2024 season
    "gen9vgc2024rega": "VGC 2024 Reg A",
    "gen9vgc2024regb": "VGC 2024 Reg B",
    "gen9vgc2024regc": "VGC 2024 Reg C",
    # VGC Gen 9 Regulations — 2025 season
    "gen9vgc2025regg": "VGC 2025 Reg G",
    "gen9vgc2025regh": "VGC 2025 Reg H",
    "gen9vgc2025regi": "VGC 2025 Reg I",
    # VGC Gen 9 Regulations — 2026 season
    "gen9vgc2026regf": "VGC 2026 Reg F",
    "gen9vgc2026regi": "VGC 2026 Reg I",
    # Draft League
    "draftleague": "Draft League",
}
