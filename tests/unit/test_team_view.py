"""Tests for TeamEmbedView.build_embed() — roster display logic."""
from unittest.mock import MagicMock

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

def test_build_embed_empty_team():
    """Empty roster shows 'No Pokemon drafted yet.' description."""
    owner = MagicMock()
    owner.display_name = "Alice"
    roster = TeamRoster(player_id="p1", guild_id="g1", pokemon=[])
    view = TeamEmbedView(roster, owner)
    embed = view.build_embed()
    assert "No Pokemon drafted yet." in embed.description


def test_build_embed_empty_team_no_fields():
    owner = MagicMock()
    owner.display_name = "Alice"
    roster = TeamRoster(player_id="p1", guild_id="g1", pokemon=[])
    view = TeamEmbedView(roster, owner)
    embed = view.build_embed()
    assert len(embed.fields) == 0


def test_build_embed_single_pokemon():
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


def test_build_embed_multiple_pokemon():
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


def test_build_embed_footer_shows_count():
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


def test_build_embed_type_coverage_field():
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


def test_build_embed_shows_tier_badge():
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


def test_build_embed_title_has_owner_name():
    owner = MagicMock()
    owner.display_name = "GracePlayer"
    roster = TeamRoster(player_id="p1", guild_id="g1", pokemon=[])
    view = TeamEmbedView(roster, owner)
    embed = view.build_embed()
    assert "GracePlayer" in embed.title
