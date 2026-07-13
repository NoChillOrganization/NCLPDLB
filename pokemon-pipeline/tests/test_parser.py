"""Unit tests for ShowdownPasteParser, resolve_paste_url, normalize_paste, dedup hashing."""

import pytest
import respx
from httpx import Response

from tasks.process.deduplicator import TeamDeduplicator
from tasks.process.parser import ShowdownPasteParser, normalize_paste, resolve_paste_url

FULL_TEAM = """Calyrex-Shadow @ Focus Sash
Ability: As One (Spectrier)
Level: 50
Tera Type: Ghost
EVs: 4 HP / 252 SpA / 252 Spe
Timid Nature
- Astral Barrage
- Draining Kiss
- Nasty Plot
- Protect

Incineroar @ Safety Goggles
Ability: Intimidate
Level: 50
Tera Type: Grass
EVs: 244 HP / 4 Def / 4 SpD / 4 Spe
Careful Nature
- Fake Out
- Knock Off
- Parting Shot
- Flare Blitz
"""

PARTIAL_TEAM = """Smeargle
Ability: Own Tempo
- Follow Me
- Spore
- Fake Out
- Wide Guard
"""

NICKNAME_TEAM = """Bigby (Calyrex-Ice) (M) @ Leftovers
Ability: As One (Glastrier)
Level: 50
- Glacial Lance
- High Horsepower
- Trick Room
- Protect
"""


class TestParseFullVgcTeam:
    def test_parses_all_members(self):
        sets = ShowdownPasteParser().parse(FULL_TEAM)
        assert len(sets) == 2
        assert sets[0]["species"] == "Calyrex-Shadow"
        assert sets[0]["item"] == "Focus Sash"
        assert sets[0]["moves"] == ["Astral Barrage", "Draining Kiss", "Nasty Plot", "Protect"]
        assert sets[1]["species"] == "Incineroar"
        assert sets[1]["evs"]["hp"] == 244


class TestParsePartialTeam:
    def test_missing_ivs_default_31_missing_tera_none(self):
        sets = ShowdownPasteParser().parse(PARTIAL_TEAM)
        assert sets[0]["ivs"] == {"hp": 31, "atk": 31, "def": 31, "spa": 31, "spd": 31, "spe": 31}
        assert sets[0]["tera_type"] is None


class TestParseWithNicknames:
    def test_nickname_separated_from_species(self):
        sets = ShowdownPasteParser().parse(NICKNAME_TEAM)
        assert sets[0]["nickname"] == "Bigby"
        assert sets[0]["species"] == "Calyrex-Ice"
        assert sets[0]["gender"] == "M"


class TestNormalizeHashDeterministic:
    def test_same_paste_different_whitespace_same_hash(self):
        messy = "  " + FULL_TEAM.replace("\n", "\n  \n").strip() + "  \n\n"
        h1 = TeamDeduplicator.compute_hash(FULL_TEAM)
        h2 = TeamDeduplicator.compute_hash(messy)
        assert h1 == h2

    def test_normalize_is_deterministic(self):
        assert normalize_paste(FULL_TEAM) == normalize_paste(FULL_TEAM)


class TestResolvePasteUrl:
    @pytest.mark.asyncio
    @respx.mock
    async def test_resolve_pokepaste_url(self):
        respx.get("https://pokepast.es/abc123/raw").mock(
            return_value=Response(200, text=FULL_TEAM)
        )
        result = await resolve_paste_url("https://pokepast.es/abc123")
        assert "Calyrex-Shadow" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_resolve_pastebin_url(self):
        respx.get("https://pastebin.com/raw/xyz789").mock(
            return_value=Response(200, text=PARTIAL_TEAM)
        )
        result = await resolve_paste_url("https://pastebin.com/xyz789")
        assert "Smeargle" in result

    @pytest.mark.asyncio
    async def test_raw_text_returned_as_is(self):
        result = await resolve_paste_url(PARTIAL_TEAM)
        assert result == PARTIAL_TEAM
