"""
Showdown Integration — Fetches and parses Showdown tier data from the smogon/pokemon-showdown repo.
Updates the local pokemon.json with current tier assignments.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import aiohttp

log = logging.getLogger(__name__)

TIERS_URL = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data/formats-data.ts"
DATA_FILE = Path(__file__).parent.parent.parent / "data" / "tiers.json"

# Showdown tier names mapped to canonical short names
TIER_MAP = {
    "AG": "AG", "Uber": "Uber", "OU": "OU", "UUBL": "UUBL",
    "UU": "UU", "RUBL": "RUBL", "RU": "RU", "NUBL": "NUBL",
    "NU": "NU", "PUBL": "PUBL", "PU": "PU", "NFE": "NFE",
    "LC": "LC", "Untiered": "Untiered",
}


async def fetch_showdown_tiers() -> dict[str, str]:
    """
    Fetch current Showdown tier assignments from the PS GitHub repo.
    Returns a dict of {pokemon_name_lower: tier}.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TIERS_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    log.warning(f"Failed to fetch Showdown tiers (HTTP {resp.status})")
                    return {}
                text = await resp.text()
    except Exception as e:
        log.error(f"Showdown tier fetch error: {e}")
        return {}

    return _parse_formats_data(text)


def _parse_formats_data(ts_source: str) -> dict[str, str]:
    """
    Parse the formats-data.ts TypeScript file from the Showdown repo.
    Extracts tier assignments: {pokemon_id: tier}.
    Example line: Garchomp: {tier: "OU", doublesTier: "DOU"},
    """
    tiers: dict[str, str] = {}
    pattern = re.compile(r'"?(\w+)"?:\s*\{[^}]*?tier:\s*"([^"]+)"', re.MULTILINE)
    for match in pattern.finditer(ts_source):
        name = match.group(1).lower()
        tier = match.group(2)
        canonical = TIER_MAP.get(tier, "Untiered")
        tiers[name] = canonical
    log.info(f"Parsed {len(tiers)} tier assignments from Showdown data")
    return tiers


async def update_pokemon_tiers(pokemon_file: Path) -> int:
    """
    Fetch current tiers and update the local pokemon.json file.
    Returns number of Pokemon updated.
    """
    if not pokemon_file.exists():
        log.warning("pokemon.json not found — run seed script first")
        return 0

    tiers = await fetch_showdown_tiers()
    if not tiers:
        return 0

    with pokemon_file.open(encoding="utf-8") as f:
        pokemon_list = json.load(f)

    updated = 0
    for entry in pokemon_list:
        name_key = entry["name"].lower().replace(" ", "").replace("-", "")
        if name_key in tiers:
            entry["showdown_tier"] = tiers[name_key]
            updated += 1

    with pokemon_file.open("w", encoding="utf-8") as f:
        json.dump(pokemon_list, f, indent=2, ensure_ascii=False)

    # Save tiers cache
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(tiers, f, indent=2)

    log.info(f"Updated tiers for {updated} Pokemon")
    return updated
