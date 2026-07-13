"""Team browsing, detail, raw paste, and species search endpoints."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.dependencies import get_db
from api.schemas import PaginatedTeamsSchema, TeamDetailSchema, TeamSchema
from models.db import PokemonSet, Source, SourceProvenance, Team, Tournament, TournamentPlacement

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=PaginatedTeamsSchema)
async def list_teams(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    regulation: Optional[str] = None,
    format_type: Optional[str] = None,
    archetype_tags: Optional[str] = None,
    match_mode: str = Query("any", pattern="^(any|all)$"),
    top16_only: bool = False,
    source: Optional[str] = None,
    is_valid: bool = True,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> PaginatedTeamsSchema:
    query = select(Team).where(Team.is_valid == is_valid)

    if regulation:
        query = query.where(Team.regulation == regulation)
    if format_type:
        query = query.where(Team.format_type == format_type)
    if archetype_tags:
        tags = [t.strip() for t in archetype_tags.split(",") if t.strip()]
        if match_mode == "all":
            query = query.where(Team.archetype_tags.contains(tags))
        else:
            query = query.where(Team.archetype_tags.overlap(tags))
    if top16_only:
        query = query.join(TournamentPlacement).where(TournamentPlacement.final_placing <= 16)
    if source:
        query = query.join(SourceProvenance).join(Source).where(Source.platform == source)
    if date_from:
        query = query.where(Team.created_at >= date_from)
    if date_to:
        query = query.where(Team.created_at <= date_to)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(Team.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(query)).scalars().unique().all()

    return PaginatedTeamsSchema(
        items=[TeamSchema.model_validate(r) for r in rows],
        total=total,
        page=page,
        pages=max(1, -(-total // per_page)),
    )


@router.get("/search")
async def search_teams(q: str, db: AsyncSession = Depends(get_db)) -> PaginatedTeamsSchema:
    species_list = [s.strip() for s in q.split("+") if s.strip()]
    if not species_list:
        return PaginatedTeamsSchema(items=[], total=0, page=1, pages=1)

    subq = (
        select(PokemonSet.team_id)
        .where(PokemonSet.species.in_(species_list))
        .group_by(PokemonSet.team_id)
        .having(func.count(func.distinct(PokemonSet.species)) == len(species_list))
    )
    query = select(Team).where(Team.id.in_(subq), Team.is_valid.is_(True)).limit(50)
    rows = (await db.execute(query)).scalars().all()
    return PaginatedTeamsSchema(
        items=[TeamSchema.model_validate(r) for r in rows], total=len(rows), page=1, pages=1
    )


@router.get("/{team_id}", response_model=TeamDetailSchema)
async def get_team(team_id: int, db: AsyncSession = Depends(get_db)) -> TeamDetailSchema:
    query = (
        select(Team)
        .where(Team.id == team_id)
        .options(
            selectinload(Team.placements).selectinload(TournamentPlacement.tournament),
            selectinload(Team.placements).selectinload(TournamentPlacement.player),
            selectinload(Team.provenance).selectinload(SourceProvenance.source),
        )
    )
    team = (await db.execute(query)).scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    placements = []
    for p in team.placements:
        placements.append(
            {
                "player_name": p.player.name,
                "final_placing": p.final_placing,
                "win_count": p.win_count,
                "loss_count": p.loss_count,
                "bring_order": p.bring_order,
                "tournament": {
                    "id": p.tournament.id,
                    "name": p.tournament.name,
                    "event_type": p.tournament.event_type,
                    "format_type": p.tournament.format_type,
                    "regulation": p.tournament.regulation,
                    "date_held": p.tournament.date_held,
                    "location": p.tournament.location,
                    "player_count": p.tournament.player_count,
                    "source_platform": None,
                },
                "team": team,
            }
        )

    provenance = [
        {
            "source_platform": prov.source.platform if prov.source else "unknown",
            "source_url": prov.source_url,
            "scrape_method": prov.scrape_method,
            "scrape_timestamp": prov.scrape_timestamp,
            "confidence": prov.confidence,
        }
        for prov in team.provenance
    ]

    return TeamDetailSchema(
        **TeamSchema.model_validate(team).model_dump(), placements=placements, provenance=provenance
    )


@router.get("/{team_id}/paste", response_class=PlainTextResponse)
async def get_team_paste(team_id: int, db: AsyncSession = Depends(get_db)) -> str:
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return team.raw_paste


@router.get("/{team_id}/similar")
async def get_similar_teams(team_id: int, k: int = 10, db: AsyncSession = Depends(get_db)) -> dict:
    from ml.embeddings import TeamEmbedder

    try:
        results = await TeamEmbedder().find_similar_teams(db, team_id, top_k=k)
        return {"team_id": team_id, "similar": results}
    except Exception as exc:  # noqa: BLE001 - pgvector optional, degrade gracefully
        return {"team_id": team_id, "similar": [], "note": f"similarity unavailable: {exc}"}
