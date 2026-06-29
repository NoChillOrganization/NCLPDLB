"""Seed canonical_species + species_alias. Run once (or after data/pokemon.json updates)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import asyncpg

from src.platform.normalize.replay import _normalized_key
from src.platform.store.repositories import add_species_alias, upsert_canonical_species

POKEMON_JSON = Path(__file__).parents[2] / "data" / "pokemon.json"
ALIASES_TS = Path(__file__).parents[2] / "pokemon-showdown" / "data" / "aliases.ts"

_ALIAS_LINE = re.compile(r'^\s*(\w+):\s*"([^"]+)",?\s*$')


def parse_species_aliases(text: str) -> list[tuple[str, str]]:
    """aliases.ts mixes format/species/move aliases as `key: "Value"` lines.
    Format/move values start with '[' or contain spaces+hyphens we don't care about;
    # ponytail: keep it simple — only species-shaped values (no leading '[') pass through.
    Caller (seed_species) drops any whose canonical name isn't a known species slug.
    """
    pairs = []
    for line in text.splitlines():
        m = _ALIAS_LINE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if value.startswith("["):
            continue
        pairs.append((key, value))
    return pairs


async def seed_species(conn: asyncpg.Connection) -> dict:
    """Returns counts: {species, self_aliases, ts_aliases, ts_aliases_skipped}."""
    species_list = json.loads(POKEMON_JSON.read_text(encoding="utf-8"))
    slug_to_id: dict[str, int] = {}
    for mon in species_list:
        slug = _normalized_key(mon["name"])
        species_id = await upsert_canonical_species(
            conn,
            slug=slug,
            national_dex=mon["national_dex"],
            display_name=mon["name"],
        )
        slug_to_id[slug] = species_id
        await add_species_alias(
            conn,
            canonical_species_id=species_id,
            source=None,
            raw_name=mon["name"],
            normalized_key=slug,
        )

    ts_added = ts_skipped = 0
    if ALIASES_TS.exists():
        for alias_key, canonical_name in parse_species_aliases(
            ALIASES_TS.read_text(encoding="utf-8")
        ):
            target_slug = _normalized_key(canonical_name)
            species_id = slug_to_id.get(target_slug)
            if species_id is None:
                ts_skipped += 1
                continue
            await add_species_alias(
                conn,
                canonical_species_id=species_id,
                source=None,
                raw_name=alias_key,
                normalized_key=_normalized_key(alias_key),
            )
            ts_added += 1

    return {
        "species": len(species_list),
        "self_aliases": len(species_list),
        "ts_aliases": ts_added,
        "ts_aliases_skipped": ts_skipped,
    }
