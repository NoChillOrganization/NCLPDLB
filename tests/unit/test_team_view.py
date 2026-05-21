"""Tests for TeamEmbedView — build_embed() and button handlers."""
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot.views.team_view import TeamEmbedView
from src.data.models import Pokemon, PokemonStats, TeamRoster


def _make_pokemon(name: str, types: list, tier: str = "OU") -> Pokemon:
    return Pokemon(
        national_dex=1,
        name=name,
        types=types,
        base_stats=PokemonStats(hp=70, atk=70, def_=70, spa=70, spd=70, spe=70),
        generation=9,
        showdown_tier=tier,
    )


# ── build_embed() ─────────────────────────────────────────────────────────────

async def test_build_embed_empty_team():
    """Empty roster shows 'No Pokemon drafted yet.' description."""
    owner = MagicMock()
    owner.display_name = "Alice"
    roster = TeamRoster(player_id="p1", guild_id="g1", pokemon=[])
    view = TeamEmbedView(roster, owner)
    embed = view.build_embed()
    assert "No Pokemon drafted yet." in embed.description


async def test_build_embed_empty_team_no_fields():
    owner = MagicMock()
    owner.display_name = "Alice"
    roster = TeamRoster(player_id="p1", guild_id="g1", pokemon=[])
    view = TeamEmbedView(roster, owner)
    embed = view.build_embed()
    assert len(embed.fields) == 0


async def test_build_embed_single_pokemon():
    owner = MagicMock()
    owner.display_name = "Bob"
    roster = TeamRoster(
        player_id="p1",
        guild_id="g1",
        pokemon=[_make_pokemon("Garchomp", ["dragon", "ground"])],
    )
    view = TeamEmbedView(roster, owner)
    embed = view.build_embed()
    assert "Garchomp" in embed.description


async def test_build_embed_multiple_pokemon():
    owner = MagicMock()
    owner.display_name = "Charlie"
    roster = TeamRoster(
        player_id="p1",
        guild_id="g1",
        pokemon=[
            _make_pokemon("Garchomp", ["dragon", "ground"]),
            _make_pokemon("Corviknight", ["steel", "flying"]),
            _make_pokemon("Heatran", ["fire", "steel"]),
        ],
    )
    view = TeamEmbedView(roster, owner)
    embed = view.build_embed()
    assert "Garchomp" in embed.description
    assert "Corviknight" in embed.description
    assert "Heatran" in embed.description


async def test_build_embed_footer_shows_count():
    owner = MagicMock()
    owner.display_name = "Dave"
    roster = TeamRoster(
        player_id="p1",
        guild_id="g1",
        pokemon=[
            _make_pokemon("Kyogre", ["water"]),
            _make_pokemon("Groudon", ["ground"]),
        ],
    )
    view = TeamEmbedView(roster, owner)
    embed = view.build_embed()
    assert embed.footer.text.startswith("2 Pokemon")


async def test_build_embed_type_coverage_field():
    owner = MagicMock()
    owner.display_name = "Eve"
    roster = TeamRoster(
        player_id="p1",
        guild_id="g1",
        pokemon=[
            _make_pokemon("Charizard", ["fire", "flying"]),
        ],
    )
    view = TeamEmbedView(roster, owner)
    embed = view.build_embed()
    coverage_fields = [f for f in embed.fields if f.name == "Type Coverage"]
    assert len(coverage_fields) == 1
    assert "fire" in coverage_fields[0].value.lower() or "Fire" in coverage_fields[0].value


async def test_build_embed_shows_tier_badge():
    owner = MagicMock()
    owner.display_name = "Frank"
    roster = TeamRoster(
        player_id="p1",
        guild_id="g1",
        pokemon=[_make_pokemon("Garchomp", ["dragon", "ground"], tier="OU")],
    )
    view = TeamEmbedView(roster, owner)
    embed = view.build_embed()
    assert "[OU]" in embed.description


async def test_build_embed_title_has_owner_name():
    owner = MagicMock()
    owner.display_name = "GracePlayer"
    roster = TeamRoster(player_id="p1", guild_id="g1", pokemon=[])
    view = TeamEmbedView(roster, owner)
    embed = view.build_embed()
    assert "GracePlayer" in embed.title


# ── TeamEmbedView button handlers ──────────────────────────────────────────────

def _make_interaction(guild_id="1234", user_id="5678"):
    """Build a minimal mock discord.Interaction for button handler tests."""
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    return interaction


async def test_analysis_button_sends_analysis_embed():
    """Pressing the Full Analysis button calls AnalyticsService and sends embed."""
    owner = MagicMock()
    owner.display_name = "Alice"
    owner.id = "111"
    roster = TeamRoster(
        player_id="p1",
        guild_id="g1",
        pokemon=[_make_pokemon("Garchomp", ["dragon", "ground"])],
    )
    view = TeamEmbedView(roster, owner)
    interaction = _make_interaction()
    button = MagicMock()

    mock_report = MagicMock()
    mock_report.coverage_summary = "Covers: dragon, ground"
    mock_report.weakness_summary = "Ice x1"
    mock_report.speed_summary = "Garchomp: 102 (Fast)"
    mock_report.archetype = "Balance"
    mock_report.threat_score = 85

    mock_svc = MagicMock()
    mock_svc.analyze_pokemon_list = MagicMock(return_value=mock_report)

    # AnalyticsService is imported lazily inside the method body using 'from ... import'.
    # Patch the class at its defining module so the local import picks up the mock.
    with patch("src.services.analytics_service.AnalyticsService", return_value=mock_svc):
        # @discord.ui.button creates a descriptor; call via class to get the raw function
        await TeamEmbedView.analysis(view, interaction, button)

    interaction.response.send_message.assert_awaited_once()
    call_kwargs = interaction.response.send_message.call_args[1]
    embed = call_kwargs.get("embed")
    assert embed is not None
    assert "Alice" in embed.title


async def test_analysis_button_embed_has_required_fields():
    """The analysis embed includes Coverage, Weaknesses, Speed Tiers, Archetype, Threat Score."""
    owner = MagicMock()
    owner.display_name = "Bob"
    owner.id = "222"
    roster = TeamRoster(
        player_id="p1",
        guild_id="g1",
        pokemon=[_make_pokemon("Corviknight", ["steel", "flying"])],
    )
    view = TeamEmbedView(roster, owner)
    interaction = _make_interaction()
    button = MagicMock()

    mock_report = MagicMock()
    mock_report.coverage_summary = "Covers: steel"
    mock_report.weakness_summary = "Fire x2"
    mock_report.speed_summary = "Corviknight: 60 (Slow)"
    mock_report.archetype = "Stall / Bulky"
    mock_report.threat_score = 70

    mock_svc = MagicMock()
    mock_svc.analyze_pokemon_list = MagicMock(return_value=mock_report)

    with patch("src.services.analytics_service.AnalyticsService", return_value=mock_svc):
        await TeamEmbedView.analysis(view, interaction, button)

    embed = interaction.response.send_message.call_args[1]["embed"]
    field_names = [f.name for f in embed.fields]
    for expected_field in ("Coverage", "Weaknesses", "Speed Tiers", "Archetype", "Threat Score"):
        assert expected_field in field_names, f"Missing field: {expected_field}"


async def test_export_button_sends_showdown_text():
    """Pressing Showdown Export calls TeamService.export_showdown and includes text."""
    owner = MagicMock()
    owner.display_name = "Carol"
    owner.id = "333"
    roster = TeamRoster(player_id="p1", guild_id="g1", pokemon=[])
    view = TeamEmbedView(roster, owner)

    interaction = _make_interaction(guild_id="9999")
    button = MagicMock()

    mock_svc = MagicMock()
    mock_svc.export_showdown = AsyncMock(return_value="Garchomp @ Choice Scarf\n...")

    # TeamService is imported lazily inside the method body; patch at the source module
    with patch("src.services.team_service.TeamService", return_value=mock_svc):
        await TeamEmbedView.export(view, interaction, button)

    mock_svc.export_showdown.assert_awaited_once_with(
        guild_id="9999", player_id="333"
    )
    interaction.response.send_message.assert_awaited_once()
    sent_text = interaction.response.send_message.call_args[0][0]
    assert "Garchomp" in sent_text
    assert "Showdown Export" in sent_text
