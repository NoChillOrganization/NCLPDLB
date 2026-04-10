"""
Phase 9 test suite — Command Registry & Team Import.

Test stubs are created first (Wave 0) to establish Nyquist compliance.
Implementations in later plans replace the pytest.fail() bodies.

Requirements covered:
  CMD-01, CMD-02, CMD-03, CMD-04 — command_registry workstream
  TEAM-01, TEAM-02, TEAM-03, TEAM-04 — team_import workstream
"""
import csv
from pathlib import Path

from src.bot.constants import SUPPORTED_FORMATS


# ── CMD-01: CSV schema ─────────────────────────────────────────────────────────

def test_csv_schema_valid():
    """CMD-01: discord_commands.csv exists with required columns."""
    csv_path = Path(__file__).parent.parent.parent / "discord_commands.csv"
    assert csv_path.exists(), f"discord_commands.csv not found at {csv_path}"

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

    required = {"Category", "Command", "Description", "Parameters", "Permission Required", "Notes"}
    missing = required - set(fieldnames)
    assert not missing, f"CSV missing required columns: {missing}"


# ── CMD-02: Drift check ────────────────────────────────────────────────────────

def test_csv_drift_check():
    """CMD-02: drift_check_commands returns commands in tree but not in CSV."""
    from src.bot.main import drift_check_commands

    csv_names = {"help", "draft", "pick"}
    registered = {"help", "draft", "pick", "undocumented_cmd"}
    drift = drift_check_commands(csv_names, registered)
    assert drift == {"undocumented_cmd"}, f"Expected {{'undocumented_cmd'}}, got {drift}"


# ── CMD-03: New row picked up ──────────────────────────────────────────────────

def test_csv_new_row_picked_up():
    """CMD-03: When CSV is updated to include a command, drift set goes to empty."""
    from src.bot.main import drift_check_commands

    # Before CSV update: 'mystery' is in registered but not CSV
    drift_before = drift_check_commands(
        csv_names={"help", "draft"},
        registered_names={"help", "draft", "mystery"},
    )
    assert "mystery" in drift_before

    # After CSV update: 'mystery' row added to csv_names
    drift_after = drift_check_commands(
        csv_names={"help", "draft", "mystery"},
        registered_names={"help", "draft", "mystery"},
    )
    assert len(drift_after) == 0, f"Expected empty drift after CSV update, got {drift_after}"


# ── CMD-04: /help reflects CSV ────────────────────────────────────────────────

def test_help_output_reflects_csv():
    """CMD-04: build_help_embed returns embed with fields matching CSV categories."""
    from src.bot.cogs.misc import build_help_embed

    csv_path = Path(__file__).parent.parent.parent / "discord_commands.csv"
    embed = build_help_embed(csv_path)

    assert embed.title == "Bot Commands"
    assert len(embed.fields) > 0, "Embed should have at least one category field"

    # Verify known categories from existing CSV are present
    field_names = {f.name for f in embed.fields}
    assert "Draft" in field_names, f"Expected 'Draft' category, got: {field_names}"
    assert "Team" in field_names, f"Expected 'Team' category, got: {field_names}"


# ── TEAM-01: .txt parse ───────────────────────────────────────────────────────

def test_team_import_txt_parse():
    """
    TEAM-01: Given raw bytes of a valid Showdown export (.txt file content),
    decode_attachment_bytes() returns a str that TeamService.import_showdown()
    can parse successfully (at least 1 Pokemon found).
    """
    from src.bot.cogs.team import decode_attachment_bytes

    # Simulate bytes content of a .txt Showdown export
    sample_bytes = (
        b"Garchomp @ Choice Scarf\n"
        b"Ability: Rough Skin\n"
        b"EVs: 252 Atk / 4 SpD / 252 Spe\n"
        b"Jolly Nature\n"
        b"- Scale Shot\n"
        b"\n"
        b"Corviknight @ Leftovers\n"
        b"Ability: Pressure\n"
        b"- Body Press\n"
    )
    result = decode_attachment_bytes(sample_bytes)
    assert isinstance(result, str), "decode_attachment_bytes must return str"
    assert "Garchomp" in result, "Decoded text should contain the Pokemon name"
    assert "Corviknight" in result, "Decoded text should contain the second Pokemon name"


# ── TEAM-02: Format autocomplete ─────────────────────────────────────────────

def test_format_autocomplete():
    """
    TEAM-02: SUPPORTED_FORMATS contains exactly 18 format entries covering
    9 Smogon Gen 9 tiers, 8 VGC Reg A-H regulations, and Draft League.
    """
    assert len(SUPPORTED_FORMATS) == 18, (
        f"Expected 18 formats, got {len(SUPPORTED_FORMATS)}: {list(SUPPORTED_FORMATS.keys())}"
    )
    # Verify presence of key categories
    smogon = [k for k in SUPPORTED_FORMATS if k.startswith("gen9") and "vgc" not in k]
    vgc = [k for k in SUPPORTED_FORMATS if "vgc" in k]
    draft = [k for k in SUPPORTED_FORMATS if k == "draftleague"]
    assert len(smogon) == 9, f"Expected 9 Smogon formats, got {len(smogon)}"
    assert len(vgc) == 8, f"Expected 8 VGC formats, got {len(vgc)}"
    assert len(draft) == 1, "Expected draftleague key"


# ── TEAM-03: Confirmation flow ────────────────────────────────────────────────

def test_team_import_confirmation_flow():
    """
    TEAM-03: TeamImportConfirmView.build_confirm_embed() returns a discord.Embed
    with title containing the format display name and a 'Pokemon' field listing
    pokemon names with their held items.
    """
    from src.bot.views.team_import_view import build_confirm_embed

    pokemon_list = ["Garchomp @ Choice Scarf", "Corviknight @ Leftovers"]
    embed = build_confirm_embed("gen9ou", pokemon_list)

    assert "Gen 9 OU" in embed.title, (
        f"Embed title should contain format display name 'Gen 9 OU', got: {embed.title!r}"
    )
    pokemon_fields = [f for f in embed.fields if f.name == "Pokemon"]
    assert pokemon_fields, f"Embed must have a 'Pokemon' field, got fields: {[f.name for f in embed.fields]}"
    assert "Garchomp @ Choice Scarf" in pokemon_fields[0].value, (
        f"Pokemon field must contain 'Garchomp @ Choice Scarf', got: {pokemon_fields[0].value!r}"
    )


# ── TEAM-04: Per-format storage ───────────────────────────────────────────────

def test_per_format_storage():
    """
    TEAM-04: TeamService._cache_key(guild_id, player_id, format_key="gen9ou") returns
    a different key than _cache_key(guild_id, player_id, format_key="gen9uu"), and
    both differ from the legacy key _cache_key(guild_id, player_id).
    """
    from src.services.team_service import TeamService

    ts = TeamService()
    key_ou = ts._cache_key("guild1", "player1", format_key="gen9ou")
    key_uu = ts._cache_key("guild1", "player1", format_key="gen9uu")
    key_legacy = ts._cache_key("guild1", "player1")

    assert key_ou != key_uu, f"gen9ou and gen9uu keys must differ: {key_ou!r} == {key_uu!r}"
    assert key_ou != key_legacy, f"format key must differ from legacy key: {key_ou!r} == {key_legacy!r}"
    assert key_uu != key_legacy, f"format key must differ from legacy key: {key_uu!r} == {key_legacy!r}"
    assert key_legacy == "guild1:player1", f"Legacy key format unchanged: {key_legacy!r}"
