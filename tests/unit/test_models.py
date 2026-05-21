"""Tests for src/data/models.py — model properties not covered elsewhere."""
from src.data.models import Draft, DraftFormat, DraftStatus, TeamRoster, PlayerElo


def test_total_picks_empty():
    d = Draft(
        draft_id="d1", guild_id="g1", commissioner_id="p1",
        format=DraftFormat.SNAKE, status=DraftStatus.ACTIVE,
        total_rounds=3, player_order=["p1", "p2"],
    )
    assert d.total_picks == 0


def test_total_picks_after_picks(make_pokemon):
    from src.data.models import DraftPick
    d = Draft(
        draft_id="d1", guild_id="g1", commissioner_id="p1",
        format=DraftFormat.SNAKE, status=DraftStatus.ACTIVE,
        total_rounds=3, player_order=["p1", "p2"],
    )
    d.picks.append(DraftPick(draft_id="d1", player_id="p1", pokemon_name="Garchomp", round=1, pick_number=1))
    d.picks.append(DraftPick(draft_id="d1", player_id="p2", pokemon_name="Corviknight", round=1, pick_number=2))
    assert d.total_picks == 2


def test_current_player_id_even_round_reversal():
    """In snake draft, even rounds reverse the order."""
    d = Draft(
        draft_id="d1", guild_id="g1", commissioner_id="p1",
        format=DraftFormat.SNAKE, status=DraftStatus.ACTIVE,
        total_rounds=4, player_order=["p1", "p2", "p3"],
        current_round=2, current_pick_index=0,
    )
    # Round 2 (even) → reversed: index 0 maps to len-1-0 = 2 → player_order[2] = "p3"
    assert d.current_player_id == "p3"


def test_current_player_id_even_round_middle():
    """Even round, pick index 1 of 3 players → len-1-1 = 1 → middle player."""
    d = Draft(
        draft_id="d1", guild_id="g1", commissioner_id="p1",
        format=DraftFormat.SNAKE, status=DraftStatus.ACTIVE,
        total_rounds=4, player_order=["p1", "p2", "p3"],
        current_round=2, current_pick_index=1,
    )
    assert d.current_player_id == "p2"


def test_type_coverage_property(make_pokemon):
    """TeamRoster.type_coverage returns sorted unique types."""
    garchomp = make_pokemon(name="Garchomp", types=["dragon", "ground"])
    corviknight = make_pokemon(name="Corviknight", types=["flying", "steel"])
    roster = TeamRoster(player_id="p1", guild_id="g1", pokemon=[garchomp, corviknight])
    coverage = roster.type_coverage
    assert "dragon" in coverage
    assert "ground" in coverage
    assert "flying" in coverage
    assert "steel" in coverage
    assert coverage == sorted(coverage)


def test_type_coverage_deduplicates(make_pokemon):
    """Duplicate types across Pokemon are deduplicated."""
    a = make_pokemon(name="A", types=["fire", "flying"])
    b = make_pokemon(name="B", types=["fire", "steel"])
    roster = TeamRoster(player_id="p1", guild_id="g1", pokemon=[a, b])
    assert roster.type_coverage.count("fire") == 1


def test_win_rate_with_games():
    elo = PlayerElo(player_id="p1", guild_id="g1", wins=3, losses=1)
    assert elo.win_rate == 75.0


def test_win_rate_no_games():
    elo = PlayerElo(player_id="p1", guild_id="g1", wins=0, losses=0)
    assert elo.win_rate == 0.0


def test_win_rate_all_wins():
    elo = PlayerElo(player_id="p1", guild_id="g1", wins=5, losses=0)
    assert elo.win_rate == 100.0


def test_current_player_id_empty_player_order():
    """current_player_id returns None when player_order is empty."""
    d = Draft(
        draft_id="d1", guild_id="g1", commissioner_id="p1",
        format=DraftFormat.SNAKE, status=DraftStatus.SETUP,
        total_rounds=3, player_order=[],
    )
    assert d.current_player_id is None


def test_pokemon_stats_total():
    from src.data.models import PokemonStats
    stats = PokemonStats(hp=10, atk=20, def_=30, spa=40, spd=50, spe=60)
    assert stats.total == 210


def test_pokemon_name_normalization():
    from src.data.models import Pokemon, PokemonStats
    # Test normalization in model_post_init
    p = Pokemon(
        national_dex=1, name="Mr. Mime Jr.",
        types=["Psychic", "Fairy"],
        base_stats=PokemonStats(), generation=1
    )
    assert p.name_normalized == "mr-mime-jr"


def test_pokemon_type_string():
    from src.data.models import Pokemon, PokemonStats
    p = Pokemon(
        national_dex=1, name="T", types=["grass", "poison"],
        base_stats=PokemonStats(), generation=1
    )
    assert p.type_string == "Grass / Poison"


def test_speed_tier_values():
    from src.data.models import Pokemon, PokemonStats
    def get_pkmn(spe):
        return Pokemon(national_dex=1, name="T", types=["f"], base_stats=PokemonStats(spe=spe), generation=1)

    assert get_pkmn(150).speed_tier == "Hyper Fast (130+)"
    assert get_pkmn(120).speed_tier == "Very Fast (110-129)"
    assert get_pkmn(100).speed_tier == "Fast (90-109)"
    assert get_pkmn(80).speed_tier == "Average (70-89)"
    assert get_pkmn(60).speed_tier == "Slow (50-69)"
    assert get_pkmn(40).speed_tier == "Very Slow (<50)"


def test_draft_player_count():
    d = Draft(
        draft_id="d1", guild_id="g1", commissioner_id="p1",
        player_order=["p1", "p2", "p3"]
    )
    assert d.player_count == 3


def test_current_player_id_linear():
    d = Draft(
        draft_id="d1", guild_id="g1", commissioner_id="p1",
        player_order=["p1", "p2"], total_rounds=2,
        format=DraftFormat.LINEAR, current_pick_index=1,
    )
    # current_pick_index=1 -> idx=1 -> player_order[1] = "p2"
    assert d.current_player_id == "p2"


def test_current_player_id_overflow():
    d = Draft(
        draft_id="d1", guild_id="g1", commissioner_id="p1",
        player_order=["p1", "p2"], total_rounds=1,
        format=DraftFormat.LINEAR, current_round=2,
    )
    # current_round=2 > total_rounds=1 -> draft finished -> None
    assert d.current_player_id is None
