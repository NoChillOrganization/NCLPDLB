"""Tournament browsing and detail endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.dependencies import get_db
from api.schemas import TournamentSchema
from models.db import Source, Team, Tournament, TournamentPlacement

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


@router.get("")
async def list_tournaments(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    event_type: Optional[str] = None,
    regulation: Optional[str] = None,
    source: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
    query = select(Tournament).options(selectinload(Tournament.source))
    if event_type:
        query = query.where(Tournament.event_type == event_type)
    if regulation:
        query = query.where(Tournament.regulation == regulation)
    if source:
        query = query.join(Source).where(Source.platform == source)
    if date_from:
        query = query.where(Tournament.date_held >= date_from)
    if date_to:
        query = query.where(Tournament.date_held <= date_to)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    query = query.order_by(Tournament.date_held.desc()).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(query)).scalars().unique().all()

    items = [
        TournamentSchema(
            id=t.id,
            name=t.name,
            event_type=t.event_type,
            format_type=t.format_type,
            regulation=t.regulation,
            date_held=t.date_held,
            location=t.location,
            player_count=t.player_count,
            source_platform=t.source.platform if t.source else None,
        )
        for t in rows
    ]
    return {"items": items, "total": total, "page": page, "pages": max(1, -(-total // per_page))}


@router.get("/{tournament_id}")
async def get_tournament(tournament_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    query = (
        select(Tournament)
        .where(Tournament.id == tournament_id)
        .options(selectinload(Tournament.source), selectinload(Tournament.placements))
    )
    tournament = (await db.execute(query)).scalar_one_or_none()
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")

    top16 = sorted(
        [p for p in tournament.placements if (p.final_placing or 999) <= 16],
        key=lambda p: p.final_placing or 999,
    )
    return {
        "tournament": TournamentSchema(
            id=tournament.id,
            name=tournament.name,
            event_type=tournament.event_type,
            format_type=tournament.format_type,
            regulation=tournament.regulation,
            date_held=tournament.date_held,
            location=tournament.location,
            player_count=tournament.player_count,
            source_platform=tournament.source.platform if tournament.source else None,
        ),
        "top16_placement_ids": [p.id for p in top16],
    }


@router.get("/{tournament_id}/teams")
async def get_tournament_teams(tournament_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    query = (
        select(TournamentPlacement)
        .where(TournamentPlacement.tournament_id == tournament_id)
        .options(selectinload(TournamentPlacement.team), selectinload(TournamentPlacement.player))
        .order_by(TournamentPlacement.final_placing.asc().nulls_last())
    )
    rows = (await db.execute(query)).scalars().all()
    if not rows:
        exists = await db.get(Tournament, tournament_id)
        if exists is None:
            raise HTTPException(status_code=404, detail="Tournament not found")

    return {
        "items": [
            {
                "player_name": p.player.name,
                "final_placing": p.final_placing,
                "team_id": p.team_id,
                "team_raw_paste": p.team.raw_paste if p.team else None,
                "archetype_tags": p.team.archetype_tags if p.team else [],
            }
            for p in rows
        ]
    }
