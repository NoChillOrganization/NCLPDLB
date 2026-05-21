"""
Scrape replays for every active Pokemon Showdown format.

Probes each format first — skips ones with no replay data.
Saves everything to data/replays/<format>/.

Usage:
    python scripts/scrape_all_formats.py
    python scripts/scrape_all_formats.py --pages 100 --min-rating 1500
    python scripts/scrape_all_formats.py --gen 9            # Gen 9 formats only
    python scripts/scrape_all_formats.py --tier ou          # OU tier across all gens
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Make sure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ml.replay_scraper import ReplayScraper, replay_stats

log = logging.getLogger(__name__)

# ── Complete Showdown format catalog ─────────────────────────────────────────
# Organized by generation.  Probed before scraping — inactive ones are skipped.

ALL_FORMATS: list[str] = [
    # ── Gen 9 (Scarlet / Violet) ──────────────────────────────────
    "gen9randombattle",
    "gen9randomdoublesbattle",
    "gen9ou",
    "gen9ubers",
    "gen9uu",
    "gen9ru",
    "gen9nu",
    "gen9pu",
    "gen9lc",
    "gen9monotype",
    "gen9doubleou",
    "gen9doublesou",
    "gen9vgc2024regh",
    "gen9vgc2024rege",
    "gen9vgc2024regf",
    "gen9bssregulationh",
    "gen9battlestadiumsingles",
    "gen9battlestadiumdoubles",
    "gen9nationaldex",
    "gen9nationaldexag",
    "gen9ag",
    "gen9hackmons",
    "gen9purehackmons",
    "gen9balancedhackmons",
    "gen9almostanyability",
    "gen9stabmons",
    "gen9monotyperandomteam",
    "gen9camomons",
    "gen9mixandmega",
    "gen9inheritedpokemon",
    "gen9cap",
    "gen9battlefactory",
    "gen9letsgoou",

    # ── Gen 8 (Sword / Shield) ────────────────────────────────────
    "gen8randombattle",
    "gen8ou",
    "gen8ubers",
    "gen8uu",
    "gen8ru",
    "gen8nu",
    "gen8pu",
    "gen8lc",
    "gen8monotype",
    "gen8doublesou",
    "gen8vgc2022",
    "gen8vgc2021",
    "gen8vgc2020",
    "gen8nationaldex",
    "gen8nationaldexag",
    "gen8ag",
    "gen8hackmons",
    "gen8balancedhackmons",
    "gen8almostanyability",
    "gen8stabmons",
    "gen8cap",
    "gen8battlefactory",
    "gen8bss",
    "gen8bdspou",
    "gen8bdspdoubles",

    # ── Gen 7 (Sun / Moon) ────────────────────────────────────────
    "gen7randombattle",
    "gen7ou",
    "gen7ubers",
    "gen7uu",
    "gen7ru",
    "gen7nu",
    "gen7pu",
    "gen7lc",
    "gen7monotype",
    "gen7doublesou",
    "gen7vgc2019",
    "gen7vgc2018",
    "gen7vgc2017",
    "gen7ag",
    "gen7hackmons",
    "gen7almostanyability",
    "gen7stabmons",
    "gen7cap",
    "gen7battlefactory",

    # ── Gen 6 (X / Y) ────────────────────────────────────────────
    "gen6ou",
    "gen6ubers",
    "gen6uu",
    "gen6ru",
    "gen6nu",
    "gen6pu",
    "gen6lc",
    "gen6monotype",
    "gen6doublesou",
    "gen6vgc2016",
    "gen6ag",
    "gen6hackmons",
    "gen6battlefactory",
    "gen6randombattle",

    # ── Gen 5 (Black / White) ─────────────────────────────────────
    "gen5ou",
    "gen5ubers",
    "gen5uu",
    "gen5ru",
    "gen5nu",
    "gen5lc",
    "gen5doublesou",
    "gen5ag",
    "gen5randombattle",
    "gen5hackmons",

    # ── Gen 4 (Diamond / Pearl) ───────────────────────────────────
    "gen4ou",
    "gen4ubers",
    "gen4uu",
    "gen4nu",
    "gen4lc",
    "gen4doublesou",
    "gen4ag",
    "gen4randombattle",

    # ── Gen 3 (Ruby / Sapphire) ───────────────────────────────────
    "gen3ou",
    "gen3ubers",
    "gen3uu",
    "gen3nu",
    "gen3doublesou",
    "gen3ag",
    "gen3randombattle",

    # ── Gen 2 (Gold / Silver) ─────────────────────────────────────
    "gen2ou",
    "gen2ubers",
    "gen2uu",
    "gen2nu",
    "gen2randombattle",

    # ── Gen 1 (Red / Blue) ────────────────────────────────────────
    "gen1ou",
    "gen1ubers",
    "gen1uu",
    "gen1nu",
    "gen1randombattle",
]


async def probe_format(fmt: str) -> bool:
    """Return True if the format has at least one replay on Showdown."""
    import aiohttp
    url = "https://replay.pokemonshowdown.com/search.json"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params={"format": fmt, "page": 1},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return False
                data = await resp.json(content_type=None)
                return isinstance(data, list) and len(data) > 0
    except Exception:
        return False


async def scrape_all(
    pages: int,
    min_rating: int,
    gen_filter: int | None,
    tier_filter: str | None,
) -> None:
    # Filter by gen / tier if requested
    formats = ALL_FORMATS
    if gen_filter:
        prefix = f"gen{gen_filter}"
        formats = [f for f in formats if f.startswith(prefix)]
    if tier_filter:
        formats = [f for f in formats if tier_filter.lower() in f]

    print(f"\n=== Pokemon Showdown — Scraping {len(formats)} formats ===")
    print(f"    pages={pages}  min_rating={min_rating}")
    if gen_filter:
        print(f"    gen filter: gen{gen_filter}")
    if tier_filter:
        print(f"    tier filter: {tier_filter}")
    print()

    # Probe all formats to find which are active
    print("Probing formats for active replay data...")
    probe_tasks = [probe_format(fmt) for fmt in formats]
    active_flags = await asyncio.gather(*probe_tasks)
    active = [fmt for fmt, ok in zip(formats, active_flags) if ok]
    inactive = [fmt for fmt, ok in zip(formats, active_flags) if not ok]

    print(f"  Active:   {len(active)}")
    print(f"  Inactive: {len(inactive)}")
    if inactive:
        print(f"  Skipping: {', '.join(inactive[:10])}" + (" ..." if len(inactive) > 10 else ""))
    print()

    # Scrape active formats sequentially (respectful of Showdown servers)
    grand_total = 0
    for i, fmt in enumerate(active, 1):
        print(f"[{i}/{len(active)}] {fmt}")
        scraper = ReplayScraper(format=fmt, min_rating=min_rating)
        count   = await scraper.scrape(pages=pages)
        grand_total += count
        print(f"      +{count} new replays\n")

    # Summary
    print("=" * 50)
    print(f"Done! Grand total: {grand_total} new replays\n")
    stats = replay_stats()
    print("Replay counts per format:")
    for fmt, n in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {fmt:<35} {n:>5}")
    total_on_disk = sum(stats.values())
    print(f"\n  TOTAL on disk: {total_on_disk}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser(description="Scrape all Showdown formats")
    ap.add_argument("--pages",      type=int, default=50,  help="Pages per format (default: 50)")
    ap.add_argument("--min-rating", type=int, default=1500, help="Min rating filter (default: 1500)")
    ap.add_argument("--gen",        type=int, default=None, help="Only scrape this generation")
    ap.add_argument("--tier",       type=str, default=None, help="Only scrape formats containing this string")
    args = ap.parse_args()

    asyncio.run(scrape_all(
        pages      = args.pages,
        min_rating = args.min_rating,
        gen_filter = args.gen,
        tier_filter= args.tier,
    ))
