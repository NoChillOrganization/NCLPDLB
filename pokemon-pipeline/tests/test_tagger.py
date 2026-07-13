"""Rule-based archetype tagger tests."""

from tasks.process.tagger import RuleBasedTagger


def _mon(species, moves=None, ability=None, evs=None, ivs=None, tera_type=None):
    return {
        "species": species,
        "moves": moves or [],
        "ability": ability,
        "evs": evs or {},
        "ivs": ivs or {"hp": 31, "atk": 31, "def": 31, "spa": 31, "spd": 31, "spe": 31},
        "tera_type": tera_type,
    }


class TestTrickRoomTag:
    def test_trick_room_with_zero_speed_iv_tags(self):
        team = [
            _mon("Torkoal", moves=["Trick Room", "Eruption"], ivs={"hp": 31, "atk": 31, "def": 31, "spa": 31, "spd": 31, "spe": 0}),
            _mon("Hatterene", moves=["Psychic"]),
        ]
        tags = RuleBasedTagger().tag_team(team, "VGC")
        assert "trick_room" in tags

    def test_trick_room_without_zero_speed_iv_not_tagged(self):
        team = [_mon("Torkoal", moves=["Trick Room", "Eruption"])]
        tags = RuleBasedTagger().tag_team(team, "VGC")
        assert "trick_room" not in tags


class TestWeatherSunAbility:
    def test_drought_tags_weather_sun(self):
        team = [_mon("Torkoal", ability="Drought")]
        tags = RuleBasedTagger().tag_team(team, "VGC")
        assert "weather_sun" in tags


class TestRestrictedTag:
    def test_calyrex_shadow_triggers_restricted(self):
        team = [_mon("Calyrex-Shadow")]
        tags = RuleBasedTagger().tag_team(team, "VGC")
        assert "restricted" in tags


class TestNoFalsePositiveTags:
    def test_simple_balanced_team_no_incorrect_tags(self):
        team = [
            _mon("Incineroar", moves=["Fake Out", "Knock Off", "Parting Shot", "Flare Blitz"], ability="Intimidate"),
            _mon("Rillaboom", moves=["Fake Out", "Grassy Glide", "Wood Hammer", "U-turn"], ability="Grassy Surge"),
        ]
        tags = RuleBasedTagger().tag_team(team, "VGC")
        assert "restricted" not in tags
        assert "trick_room" not in tags
        assert "weather_sun" not in tags
        assert "smeargle" not in tags
        assert "tera_stellar" not in tags
