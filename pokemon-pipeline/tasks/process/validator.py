"""Team legality validation — Python pre-validation + Node.js @pkmn/sim deep validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select, update

from celery_app import app
from config import settings
from models.db import Team, async_session_factory

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)


class PreValidator:
    """Fast, network-free checks for obvious errors before calling the Node.js deep validator."""

    def validate(self, parsed_json: list[dict], format_type: str | None, regulation: str | None) -> ValidationResult:
        errors: list[str] = []

        if len(parsed_json) != 6:
            errors.append(f"Team has {len(parsed_json)} Pokemon, expected exactly 6.")

        species_seen: dict[str, int] = {}
        for mon in parsed_json:
            species = mon.get("species") or "unknown"
            species_seen[species] = species_seen.get(species, 0) + 1
        duplicates = [s for s, count in species_seen.items() if count > 1]
        if duplicates:
            errors.append(f"Duplicate species in team: {', '.join(duplicates)}.")

        for i, mon in enumerate(parsed_json):
            species = mon.get("species") or f"slot {i}"
            moves = (mon.get("moves") or []) + [None] * 4
            moves = moves[:4]
            non_null_moves = [m for m in moves if m]
            if len(non_null_moves) == 0:
                errors.append(f"{species}: has no moves.")

            evs = mon.get("evs") or {}
            ev_total = sum(evs.get(stat, 0) for stat in ("hp", "atk", "def", "spa", "spd", "spe"))
            if ev_total > 510:
                errors.append(f"{species}: EV total {ev_total} exceeds 510.")
            for stat, value in evs.items():
                if value > 252:
                    errors.append(f"{species}: {stat} EV {value} exceeds 252.")

            ivs = mon.get("ivs") or {}
            for stat, value in ivs.items():
                if not (0 <= value <= 31):
                    errors.append(f"{species}: {stat} IV {value} outside 0-31 range.")

            level = mon.get("level", 50)
            if not (1 <= level <= 100):
                errors.append(f"{species}: level {level} outside 1-100 range.")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)


async def _deep_validate(parsed_json: list[dict], format_type: str | None, regulation: str | None) -> ValidationResult:
    format_key = regulation or format_type
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post(
                f"{settings.node_classifier_url}/validate",
                json={"team_json": parsed_json, "format": format_key},
            )
            resp.raise_for_status()
            data = resp.json()
            return ValidationResult(is_valid=data.get("is_valid", True), errors=data.get("errors", []))
    except Exception as exc:  # noqa: BLE001 - classifier down must not block ingestion
        logger.warning("Node deep validator unavailable, skipping: %s", exc)
        return ValidationResult(is_valid=True, errors=[])


async def validate_team(session, team_id: int, parsed_json: list[dict], format_type: str | None, regulation: str | None) -> ValidationResult:
    pre_result = PreValidator().validate(parsed_json, format_type, regulation)

    if pre_result.is_valid:
        deep_result = await _deep_validate(parsed_json, format_type, regulation)
        final = deep_result
    else:
        final = pre_result

    await session.execute(
        update(Team)
        .where(Team.id == team_id)
        .values(is_valid=final.is_valid, validation_notes="\n".join(final.errors) or None)
    )
    await session.commit()
    return final


@app.task(bind=True, name="tasks.process.validator.revalidate_invalid_teams")
def revalidate_invalid_teams(self) -> dict:
    import asyncio

    return asyncio.run(_revalidate_invalid_teams())


async def _revalidate_invalid_teams() -> dict:
    revalidated = 0
    now_valid = 0

    async with async_session_factory() as session:
        rows = (await session.execute(select(Team).where(Team.is_valid.is_(False)))).scalars().all()
        for team in rows:
            result = await validate_team(session, team.id, team.parsed_json, team.format_type, team.regulation)
            revalidated += 1
            if result.is_valid:
                now_valid += 1

    logger.info("revalidate_invalid_teams: revalidated=%d now_valid=%d", revalidated, now_valid)
    return {"revalidated": revalidated, "now_valid": now_valid}
