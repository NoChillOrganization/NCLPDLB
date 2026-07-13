"""Two-layer archetype tagging: Python rule-based (fast) + Node.js @pkmn/stats classifier."""

from __future__ import annotations

import logging

import httpx
from sqlalchemy import update

from config import settings
from models.db import Team

logger = logging.getLogger(__name__)

# Module-level config constant, not hardcoded inline, per project convention.
RESTRICTED_POKEMON_LIST = {
    "Calyrex-Ice",
    "Calyrex-Shadow",
    "Koraidon",
    "Miraidon",
    "Zacian",
    "Zacian-Crowned",
    "Zamazenta",
    "Zamazenta-Crowned",
    "Kyogre",
    "Groudon",
    "Rayquaza",
    "Eternatus",
    "Mewtwo",
    "Lugia",
    "Ho-Oh",
    "Dialga",
    "Dialga-Origin",
    "Palkia",
    "Palkia-Origin",
    "Giratina",
    "Giratina-Origin",
    "Reshiram",
    "Zekrom",
    "Kyurem",
    "Kyurem-White",
    "Kyurem-Black",
    "Solgaleo",
    "Lunala",
    "Necrozma",
}


class RuleBasedTagger:
    def tag_team(self, parsed_json: list[dict], format_type: str | None) -> list[str]:
        tags: set[str] = set()

        all_moves = {m for mon in parsed_json for m in (mon.get("moves") or []) if m}
        all_abilities = {mon.get("ability") for mon in parsed_json if mon.get("ability")}
        species_set = {mon.get("species") for mon in parsed_json if mon.get("species")}

        if "Trick Room" in all_moves and any(
            (mon.get("ivs") or {}).get("spe", 31) == 0 for mon in parsed_json
        ):
            tags.add("trick_room")

        if "Drought" in all_abilities or "Sunny Day" in all_moves:
            tags.add("weather_sun")
        if "Drizzle" in all_abilities or "Rain Dance" in all_moves:
            tags.add("weather_rain")
        if "Sand Stream" in all_abilities or "Sandstorm" in all_moves:
            tags.add("weather_sand")
        if "Snow Warning" in all_abilities or "Snowscape" in all_moves:
            tags.add("weather_snow")

        if species_set & RESTRICTED_POKEMON_LIST:
            tags.add("restricted")

        if "Smeargle" in species_set:
            tags.add("smeargle")

        if "Tailwind" in all_moves:
            tags.add("tailwind")

        if "Follow Me" in all_moves or "Rage Powder" in all_moves:
            tags.add("redirection")

        if any(mon.get("tera_type") == "Stellar" for mon in parsed_json):
            tags.add("tera_stellar")

        hyperoffense_count = sum(
            1
            for mon in parsed_json
            if (mon.get("evs") or {}).get("atk", 0) == 252 or (mon.get("evs") or {}).get("spa", 0) == 252
        )
        if hyperoffense_count >= 4:
            tags.add("hyperoffense")

        if format_type == "VGC":
            tags.add("doubles_vgc")

        return sorted(tags)


async def classify_team(parsed_json: list[dict]) -> dict:
    """POST to NODE_CLASSIFIER_URL/classify. Unavailable -> {} (never fails the pipeline)."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post(
                f"{settings.node_classifier_url}/classify", json={"team_json": parsed_json}
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # noqa: BLE001 - classifier down must not fail the pipeline
        logger.warning("Node classifier unavailable: %s", exc)
        return {}


async def tag_and_update_team(session, team_id: int, parsed_json: list[dict], format_type: str | None) -> list[str]:
    rule_tags = set(RuleBasedTagger().tag_team(parsed_json, format_type))
    node_result = await classify_team(parsed_json)
    node_tags = set(node_result.get("tags", []))

    merged = sorted(rule_tags | node_tags)
    await session.execute(update(Team).where(Team.id == team_id).values(archetype_tags=merged))
    await session.commit()
    await _publish_team_ingested(team_id, merged)
    return merged


async def _publish_team_ingested(team_id: int, archetype_tags: list[str]) -> None:
    """Best-effort notify /ws/live subscribers. Redis being briefly unavailable must not fail ingestion."""
    try:
        import json

        import redis.asyncio as redis

        client = redis.from_url(settings.redis_url)
        await client.publish("team_ingested", json.dumps({"team_id": team_id, "archetype_tags": archetype_tags}))
        await client.aclose()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not publish team_ingested event: %s", exc)
