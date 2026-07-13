"""SHA-256 content-hash deduplication with full source-provenance lineage preserved."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.db import PokemonSet, SourceProvenance, Team
from tasks.process.parser import normalize_paste


class TeamDeduplicator:
    @staticmethod
    def compute_hash(raw_paste: str) -> str:
        canonical = normalize_paste(raw_paste)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    async def find_existing(session: AsyncSession, content_hash: str) -> Optional[Team]:
        result = await session.execute(select(Team).where(Team.content_hash == content_hash))
        return result.scalar_one_or_none()

    async def upsert_team(
        self,
        session: AsyncSession,
        raw_paste: str,
        parsed_json: list[dict],
        regulation: Optional[str],
        format_type: Optional[str],
        source_meta: dict,
    ) -> tuple[Team, bool]:
        """Returns (Team, was_created). Always inserts a new source_provenance record."""
        content_hash = self.compute_hash(raw_paste)
        existing = await self.find_existing(session, content_hash)

        if existing is not None:
            await self.record_provenance(session, existing.id, **source_meta)
            return existing, False

        team = Team(
            content_hash=content_hash,
            raw_paste=raw_paste,
            parsed_json=parsed_json,
            regulation=regulation,
            format_type=format_type,
        )
        session.add(team)
        await session.flush()  # obtain team.id before creating child rows

        for mon in parsed_json:
            evs = mon.get("evs", {})
            ivs = mon.get("ivs", {})
            moves = (mon.get("moves") or [None, None, None, None])[:4]
            while len(moves) < 4:
                moves.append(None)
            session.add(
                PokemonSet(
                    team_id=team.id,
                    slot_index=mon.get("slot_index", 0),
                    species=mon.get("species") or "unknown",
                    nickname=mon.get("nickname"),
                    item=mon.get("item"),
                    ability=mon.get("ability"),
                    nature=mon.get("nature"),
                    tera_type=mon.get("tera_type"),
                    move1=moves[0],
                    move2=moves[1],
                    move3=moves[2],
                    move4=moves[3],
                    ev_hp=evs.get("hp", 0),
                    ev_atk=evs.get("atk", 0),
                    ev_def=evs.get("def", 0),
                    ev_spa=evs.get("spa", 0),
                    ev_spd=evs.get("spd", 0),
                    ev_spe=evs.get("spe", 0),
                    iv_hp=ivs.get("hp", 31),
                    iv_atk=ivs.get("atk", 31),
                    iv_def=ivs.get("def", 31),
                    iv_spa=ivs.get("spa", 31),
                    iv_spd=ivs.get("spd", 31),
                    iv_spe=ivs.get("spe", 31),
                    level=mon.get("level", 50),
                    gender=mon.get("gender"),
                    is_shiny=mon.get("is_shiny", False),
                )
            )

        await self.record_provenance(session, team.id, **source_meta)
        return team, True

    @staticmethod
    async def record_provenance(
        session: AsyncSession,
        team_id: int,
        source_id: int,
        source_url: Optional[str] = None,
        scrape_method: str = "api",
        confidence: int = 100,
        raw_response: Optional[dict] = None,
    ) -> SourceProvenance:
        provenance = SourceProvenance(
            team_id=team_id,
            source_id=source_id,
            source_url=source_url,
            scrape_method=scrape_method,
            scrape_timestamp=datetime.now(timezone.utc),
            confidence=confidence,
            raw_response=raw_response,
        )
        session.add(provenance)
        await session.flush()
        return provenance
