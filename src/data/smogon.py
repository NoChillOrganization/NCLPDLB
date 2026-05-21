"""
Smogon strategy scraper — fetches tier data and strategy descriptions.
Uses httpx (async) + BeautifulSoup to parse Smogon's analysis pages.
Falls back gracefully if network is unavailable.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)

SMOGON_BASE = "https://www.smogon.com"
SMOGON_DEX_API = "https://smogon.com/dex/_rg/pokemon"   # returns embedded JSON
LOCAL_TIERS_FILE = Path(__file__).parent.parent.parent / "data" / "tiers.json"

# Mapping of Smogon gen slugs used in URLs
GEN_SLUGS = {
    9: "sv", 8: "ss", 7: "sm", 6: "xy", 5: "bw",
    4: "dp", 3: "rs", 2: "gs", 1: "rb",
}


async def fetch_smogon_tiers(gen: int = 9) -> dict[str, str]:
    """
    Fetch current Smogon tier assignments for a generation.
    Returns {pokemon_name_lower: tier_string}.
    Caches result to data/tiers.json.
    """
    slug = GEN_SLUGS.get(gen, "sv")
    url = f"{SMOGON_BASE}/dex/{slug}/formats/"

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("[smogon] Warning: could not fetch tiers — %s", e)
            return _load_cached_tiers()

    # Smogon embeds a JSON blob in a <script> tag
    match = re.search(r"dexSettings\s*=\s*(\{.*?\});", resp.text, re.DOTALL)
    if not match:
        return _load_cached_tiers()

    try:
        data: dict[str, Any] = json.loads(match.group(1))
        injectRpcs: list = data.get("injectRpcs", [])
    except json.JSONDecodeError:
        return _load_cached_tiers()

    tiers: dict[str, str] = {}
    for rpc in injectRpcs:
        if not isinstance(rpc, list) or len(rpc) < 2:
            continue
        payload = rpc[1]
        if not isinstance(payload, dict):
            continue
        for poke_data in payload.get("pokemon", []):
            name: str = poke_data.get("name", "").lower()
            formats: list[str] = poke_data.get("formats", [])
            if name and formats:
                tiers[name] = formats[0]   # First format is the primary tier

    if tiers:
        _save_cached_tiers(tiers)
    else:
        return _load_cached_tiers()

    return tiers


async def fetch_pokemon_strategy(pokemon_name: str, gen: int = 9) -> str:
    """
    Fetch a brief strategy/role description for a Pokemon from Smogon.
    Returns empty string on failure.
    """
    slug = GEN_SLUGS.get(gen, "sv")
    name_slug = pokemon_name.lower().replace(" ", "").replace("-", "").replace("'", "")
    url = f"{SMOGON_BASE}/dex/{slug}/pokemon/{name_slug}/"

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError:
            return ""

    # Extract embedded dexSettings JSON for the overview
    match = re.search(r"dexSettings\s*=\s*(\{.*?\});", resp.text, re.DOTALL)
    if not match:
        return ""

    try:
        data: dict[str, Any] = json.loads(match.group(1))
    except json.JSONDecodeError:
        return ""

    for rpc in data.get("injectRpcs", []):
        if not isinstance(rpc, list) or len(rpc) < 2:
            continue
        payload = rpc[1]
        if isinstance(payload, dict):
            pokemon_list = payload.get("pokemon", [])
            for poke in pokemon_list:
                if poke.get("name", "").lower() == pokemon_name.lower():
                    strategies = poke.get("strategies", [])
                    if strategies:
                        # Return first strategy overview
                        overview = strategies[0].get("overview", "")
                        # Strip HTML tags
                        clean = re.sub(r"<[^>]+>", "", overview).strip()
                        return clean[:300]   # Truncate for Discord embed
    return ""


async def update_pokemon_strategies(
    pokemon_json_path: Path,
    gen: int = 9,
    limit: int | None = None,
) -> None:
    """
    Batch update smogon_strategy field for all Pokemon in the local JSON.
    Rate-limited to avoid hammering Smogon.
    """
    import asyncio

    if not pokemon_json_path.exists():
        log.warning("[smogon] No pokemon.json found — run seed_pokemon_data.py first")
        return

    with pokemon_json_path.open(encoding="utf-8") as f:
        entries: list[dict] = json.load(f)

    to_update = [e for e in entries if not e.get("smogon_strategy")]
    if limit:
        to_update = to_update[:limit]

    log.info("[smogon] Fetching strategies for %d Pokemon (gen %s)…", len(to_update), gen)
    updated = 0
    for entry in to_update:
        strategy = await fetch_pokemon_strategy(entry["name"], gen)
        if strategy:
            entry["smogon_strategy"] = strategy
            updated += 1
        await asyncio.sleep(0.5)   # Polite rate limit

    with pokemon_json_path.open("w", encoding="utf-8") as f:
        json.dump(sorted(entries, key=lambda x: x["national_dex"]), f, indent=2, ensure_ascii=False)

    log.info("[smogon] Done — updated %d strategy descriptions", updated)


# ── Cache helpers ──────────────────────────────────────────────

def _load_cached_tiers() -> dict[str, str]:
    if LOCAL_TIERS_FILE.exists():
        with LOCAL_TIERS_FILE.open(encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cached_tiers(tiers: dict[str, str]) -> None:
    LOCAL_TIERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCAL_TIERS_FILE.open("w", encoding="utf-8") as f:
        json.dump(tiers, f, indent=2)


# ── CLI entrypoint ─────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    import sys
    from pathlib import Path

    pokemon_path = Path(__file__).parent.parent.parent / "data" / "pokemon.json"
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(update_pokemon_strategies(pokemon_path, limit=limit))
