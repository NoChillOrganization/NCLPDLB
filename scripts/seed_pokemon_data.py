"""
Seed Script — Fetches all Gen 1-9 Pokemon from PokéAPI and saves to data/pokemon.json.
Run once: python scripts/seed_pokemon_data.py
Cross-platform (Windows/macOS/Linux) — uses pathlib and asyncio.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import aiohttp

OUTPUT_FILE = Path(__file__).parent.parent / "data" / "pokemon.json"
POKEAPI_BASE = "https://pokeapi.co/api/v2"
TOTAL_POKEMON = 1025
BATCH_SIZE = 20
SV_AVAILABLE_GENS = {1, 2, 3, 4, 5, 6, 7, 8, 9}


async def fetch_pokemon(session: aiohttp.ClientSession, dex_id: int) -> dict | None:
    try:
        async with session.get(f"{POKEAPI_BASE}/pokemon/{dex_id}") as r:
            if r.status != 200:
                return None
            poke = await r.json()
        async with session.get(f"{POKEAPI_BASE}/pokemon-species/{dex_id}") as r:
            species = await r.json() if r.status == 200 else {}

        name = poke["name"].replace("-", " ").title()
        types = [t["type"]["name"].lower() for t in poke["types"]]
        raw = {s["stat"]["name"]: s["base_stat"] for s in poke["stats"]}
        gen_url = species.get("generation", {}).get("url", "/1/")
        gen = int(gen_url.rstrip("/").split("/")[-1])

        return {
            "national_dex": dex_id,
            "name": name,
            "types": types,
            "base_stats": {
                "hp": raw.get("hp", 0), "atk": raw.get("attack", 0),
                "def": raw.get("defense", 0), "spa": raw.get("special-attack", 0),
                "spd": raw.get("special-defense", 0), "spe": raw.get("speed", 0),
            },
            "abilities": [a["ability"]["name"].title() for a in poke["abilities"] if not a["is_hidden"]],
            "hidden_ability": next((a["ability"]["name"].title() for a in poke["abilities"] if a["is_hidden"]), None),
            "generation": gen,
            "is_legendary": species.get("is_legendary", False),
            "is_mythical": species.get("is_mythical", False),
            "showdown_tier": "Untiered",
            "vgc_legal": False,
            "vgc_season": "",
            "console_legal": {"sv": True, "swsh": gen <= 8, "bdsp": gen <= 4, "legends": gen <= 4},
            "tier_points": 5 if species.get("is_mythical") else (4 if species.get("is_legendary") else 1),
            "smogon_strategy": "",
            # Animated GIFs from Showdown sprites CDN — covers all Gen 1-9
            "sprite_url": f"https://play.pokemonshowdown.com/sprites/ani/{poke['name']}.gif",
            "sprite_url_shiny": f"https://play.pokemonshowdown.com/sprites/ani-shiny/{poke['name']}.gif",
            "sprite_url_back": f"https://play.pokemonshowdown.com/sprites/ani-back/{poke['name']}.gif",
        }
    except Exception as e:
        print(f"  Error #{dex_id}: {e}")
        return None


async def main() -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[int, dict] = {}
    if OUTPUT_FILE.exists():
        with OUTPUT_FILE.open(encoding="utf-8") as f:
            for e in json.load(f):
                existing[e["national_dex"]] = e
        print(f"Resuming from {len(existing)} entries...")

    results = list(existing.values())
    to_fetch = [i for i in range(1, TOTAL_POKEMON + 1) if i not in existing]
    print(f"Fetching {len(to_fetch)} Pokemon...")

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=BATCH_SIZE)) as session:
        for i in range(0, len(to_fetch), BATCH_SIZE):
            batch = to_fetch[i:i + BATCH_SIZE]
            for r in await asyncio.gather(*[fetch_pokemon(session, d) for d in batch]):
                if r:
                    results.append(r)
            pct = (len(existing) + i + len(batch)) / TOTAL_POKEMON * 100
            print(f"  {pct:.1f}% — saving...")
            with OUTPUT_FILE.open("w", encoding="utf-8") as f:
                json.dump(sorted(results, key=lambda x: x["national_dex"]), f, indent=2, ensure_ascii=False)
            await asyncio.sleep(0.3)

    print(f"Done! {len(results)} Pokemon saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
