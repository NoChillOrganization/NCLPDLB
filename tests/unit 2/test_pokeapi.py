"""Tests for src/data/pokeapi.py — PokemonDatabase methods."""
import json
import pytest

import src.data.pokeapi as pokeapi_mod
from src.data.pokeapi import PokemonDatabase

SAMPLE_DATA = [
    {
        "national_dex": 1,
        "name": "Bulbasaur",
        "types": ["grass", "poison"],
        "base_stats": {"hp": 45, "atk": 49, "def_": 49, "spa": 65, "spd": 65, "spe": 45},
        "abilities": ["Overgrow"],
        "hidden_ability": "Chlorophyll",
        "generation": 1,
        "is_legendary": False,
        "is_mythical": False,
        "showdown_tier": "NU",
        "vgc_legal": True,
        "console_legal": {"sv": True, "swsh": False},
        "tier_points": 1,
        "smogon_strategy": "Bulky attacker",
        "sprite_url": "https://example.com/1.png",
    },
    {
        "national_dex": 6,
        "name": "Charizard",
        "types": ["fire", "flying"],
        "base_stats": {"hp": 78, "atk": 84, "def_": 78, "spa": 109, "spd": 85, "spe": 100},
        "abilities": ["Blaze"],
        "hidden_ability": "Solar Power",
        "generation": 1,
        "is_legendary": False,
        "is_mythical": False,
        "showdown_tier": "OU",
        "vgc_legal": True,
        "console_legal": {"sv": True, "swsh": True},
        "tier_points": 3,
        "smogon_strategy": "Special attacker",
        "sprite_url": "https://example.com/6.png",
    },
    {
        "national_dex": 144,
        "name": "Articuno",
        "types": ["ice", "flying"],
        "base_stats": {"hp": 90, "atk": 85, "def_": 100, "spa": 95, "spd": 125, "spe": 85},
        "abilities": ["Pressure"],
        "hidden_ability": "Snow Cloak",
        "generation": 1,
        "is_legendary": True,
        "is_mythical": False,
        "showdown_tier": "UU",
        "vgc_legal": False,
        "console_legal": {"sv": False, "swsh": True},
        "tier_points": 5,
        "smogon_strategy": "Wall",
        "sprite_url": "",
    },
]


@pytest.fixture
def db_with_data(tmp_path, monkeypatch):
    """A PokemonDatabase loaded from temp JSON."""
    pokemon_file = tmp_path / "pokemon.json"
    pokemon_file.write_text(json.dumps(SAMPLE_DATA))
    monkeypatch.setattr(pokeapi_mod, "DATA_DIR", tmp_path)
    db = PokemonDatabase()
    db.load()
    return db


def test_load_missing_file_does_not_crash(tmp_path, monkeypatch):
    """load() logs a warning when file doesn't exist; db stays empty."""
    monkeypatch.setattr(pokeapi_mod, "DATA_DIR", tmp_path)
    db = PokemonDatabase()
    db.load()  # No exception
    assert db.find("Bulbasaur") is None


def test_load_populates_db(db_with_data):
    assert db_with_data.find("Bulbasaur") is not None
    assert db_with_data.find("Charizard") is not None


def test_load_by_dex(db_with_data):
    assert db_with_data.find_by_dex(1) is not None
    assert db_with_data.find_by_dex(6) is not None


def test_find_direct_match(db_with_data):
    mon = db_with_data.find("Bulbasaur")
    assert mon is not None
    assert mon.name == "Bulbasaur"


def test_find_case_insensitive(db_with_data):
    assert db_with_data.find("bulbasaur") is not None
    assert db_with_data.find("CHARIZARD") is not None


def test_find_partial_match(db_with_data):
    result = db_with_data.find("chariz")
    assert result is not None


def test_find_not_found(db_with_data):
    assert db_with_data.find("Mewtwo") is None


def test_find_by_dex_found(db_with_data):
    mon = db_with_data.find_by_dex(6)
    assert mon.name == "Charizard"


def test_find_by_dex_not_found(db_with_data):
    assert db_with_data.find_by_dex(999) is None


def test_filter_by_tier(db_with_data):
    ou = db_with_data.filter_by_tier("OU")
    assert len(ou) == 1
    assert ou[0].name == "Charizard"


def test_filter_by_tier_empty(db_with_data):
    assert db_with_data.filter_by_tier("Uber") == []


def test_filter_by_generation(db_with_data):
    gen1 = db_with_data.filter_by_generation(1)
    assert len(gen1) == 3


def test_filter_by_generation_empty(db_with_data):
    assert db_with_data.filter_by_generation(9) == []


def test_filter_vgc_legal(db_with_data):
    legal = db_with_data.filter_vgc_legal()
    names = [p.name for p in legal]
    assert "Bulbasaur" in names
    assert "Charizard" in names
    assert "Articuno" not in names


def test_filter_console_legal_sv(db_with_data):
    sv = db_with_data.filter_console_legal("sv")
    names = [p.name for p in sv]
    assert "Bulbasaur" in names
    assert "Charizard" in names
    assert "Articuno" not in names


def test_filter_console_legal_swsh(db_with_data):
    swsh = db_with_data.filter_console_legal("swsh")
    names = [p.name for p in swsh]
    assert "Charizard" in names
    assert "Articuno" in names
    assert "Bulbasaur" not in names


def test_search_by_prefix(db_with_data):
    results = db_with_data.search("bul")
    assert any(p.name == "Bulbasaur" for p in results)


def test_search_respects_limit(db_with_data):
    results = db_with_data.search("a", limit=1)
    assert len(results) <= 1


def test_all_returns_all(db_with_data):
    all_pokemon = db_with_data.all()
    assert len(all_pokemon) == 3
