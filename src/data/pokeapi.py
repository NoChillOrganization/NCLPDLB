"""
Pokemon Data Layer — Local JSON cache + PokéAPI + Showdown tiers.
Cross-platform: uses pathlib for all file operations.
"""
from __future__ import annotations

import json
import logging

from src.config import settings
from src.data.models import Pokemon, PokemonStats

log = logging.getLogger(__name__)

DATA_DIR = settings.data_dir


class PokemonDatabase:
    """In-memory Pokemon database loaded from local JSON + enriched from APIs."""

    def __init__(self) -> None:
        self._db: dict[str, Pokemon] = {}  # name_lower -> Pokemon
        self._by_dex: dict[int, Pokemon] = {}

    def load(self) -> None:
        """Load all Pokemon from local JSON cache."""
        pokemon_file = DATA_DIR / "pokemon.json"
        if not pokemon_file.exists():
            log.warning(f"Pokemon data file not found at {pokemon_file}. Run seed script first.")
            return
        with pokemon_file.open(encoding="utf-8") as f:
            data = json.load(f)
        for entry in data:
            p = Pokemon(
                national_dex=entry["national_dex"],
                name=entry["name"],
                types=entry["types"],
                base_stats=PokemonStats(**entry["base_stats"]),
                abilities=entry.get("abilities", []),
                hidden_ability=entry.get("hidden_ability"),
                generation=entry.get("generation", 1),
                is_legendary=entry.get("is_legendary", False),
                is_mythical=entry.get("is_mythical", False),
                showdown_tier=entry.get("showdown_tier", "Untiered"),
                vgc_legal=entry.get("vgc_legal", False),
                console_legal=entry.get("console_legal", {}),
                tier_points=entry.get("tier_points", 1),
                smogon_strategy=entry.get("smogon_strategy", ""),
                sprite_url=entry.get("sprite_url", ""),
            )
            key = p.name.lower().replace(" ", "-").replace("'", "").replace(".", "")
            self._db[key] = p
            self._by_dex[p.national_dex] = p
        log.info(f"Loaded {len(self._db)} Pokemon from {pokemon_file}")

    def find(self, name: str) -> Pokemon | None:
        """Find Pokemon by name (fuzzy-tolerant)."""
        key = name.lower().strip().replace(" ", "-").replace("'", "").replace(".", "")
        # Direct match
        if p := self._db.get(key):
            return p
        # Partial match
        for k, p in self._db.items():
            if key in k or k in key:
                return p
        return None

    def find_by_dex(self, dex: int) -> Pokemon | None:
        return self._by_dex.get(dex)

    def filter_by_tier(self, tier: str) -> list[Pokemon]:
        return [p for p in self._db.values() if p.showdown_tier.lower() == tier.lower()]

    def filter_by_generation(self, gen: int) -> list[Pokemon]:
        return [p for p in self._db.values() if p.generation == gen]

    def filter_vgc_legal(self) -> list[Pokemon]:
        return [p for p in self._db.values() if p.vgc_legal]

    def filter_console_legal(self, game: str) -> list[Pokemon]:
        """Return Pokemon legal in a specific console game (sv, swsh, bdsp, legends)."""
        return [p for p in self._db.values() if p.console_legal.get(game, False)]

    def search(self, query: str, limit: int = 25) -> list[Pokemon]:
        """Autocomplete search — returns up to `limit` matching Pokemon."""
        q = query.lower()
        results = [p for k, p in self._db.items() if q in k]
        return results[:limit]

    def all(self) -> list[Pokemon]:
        return list(self._db.values())


# Global singleton — loaded on bot startup
pokemon_db = PokemonDatabase()
