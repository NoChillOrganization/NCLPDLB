"""Training data export — streamed JSONL/CSV/JSON for the ML pipeline."""

from __future__ import annotations

import csv
import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.dependencies import get_db
from models.db import Team, TournamentPlacement

router = APIRouter(tags=["export"])


async def _iter_training_rows(
    db: AsyncSession, regulation: Optional[str], format_type: Optional[str], top16_only: bool, include_invalid: bool
):
    query = (
        select(TournamentPlacement)
        .join(Team)
        .options(selectinload(TournamentPlacement.team), selectinload(TournamentPlacement.player))
    )
    if not include_invalid:
        query = query.where(Team.is_valid.is_(True))
    if regulation:
        query = query.where(Team.regulation == regulation)
    if format_type:
        query = query.where(Team.format_type == format_type)
    if top16_only:
        query = query.where(TournamentPlacement.final_placing <= 16)

    result = await db.stream(query)
    async for (placement,) in result:
        yield placement


@router.get("/export/training-data")
async def export_training_data(
    db: AsyncSession = Depends(get_db),
    regulation: Optional[str] = None,
    format_type: Optional[str] = None,
    top16_only: bool = True,
    format_output: str = Query("jsonl", pattern="^(jsonl|csv|json)$"),
    include_invalid: bool = False,
) -> StreamingResponse:
    if format_output == "jsonl":
        return StreamingResponse(
            _jsonl_stream(db, regulation, format_type, top16_only, include_invalid),
            media_type="application/x-ndjson",
        )
    if format_output == "csv":
        return StreamingResponse(
            _csv_stream(db, regulation, format_type, top16_only, include_invalid),
            media_type="text/csv",
        )
    return StreamingResponse(
        _json_stream(db, regulation, format_type, top16_only, include_invalid),
        media_type="application/json",
    )


def _record(placement) -> dict:
    team = placement.team
    return {
        "regulation": team.regulation,
        "format_type": team.format_type,
        "final_placing": placement.final_placing,
        "win_count": placement.win_count,
        "is_top16": (placement.final_placing or 999) <= 16,
        "archetype_tags": team.archetype_tags,
        "raw_paste": team.raw_paste,
        "parsed_json": team.parsed_json,
    }


async def _jsonl_stream(db, regulation, format_type, top16_only, include_invalid):
    async for placement in _iter_training_rows(db, regulation, format_type, top16_only, include_invalid):
        yield json.dumps(_record(placement)) + "\n"


async def _json_stream(db, regulation, format_type, top16_only, include_invalid):
    yield "["
    first = True
    async for placement in _iter_training_rows(db, regulation, format_type, top16_only, include_invalid):
        if not first:
            yield ","
        yield json.dumps(_record(placement))
        first = False
    yield "]"


async def _csv_stream(db, regulation, format_type, top16_only, include_invalid):
    header_written = False
    async for placement in _iter_training_rows(db, regulation, format_type, top16_only, include_invalid):
        record = _record(placement)
        for mon in record["parsed_json"] or [{}]:
            row = {
                "regulation": record["regulation"],
                "format_type": record["format_type"],
                "final_placing": record["final_placing"],
                "win_count": record["win_count"],
                "is_top16": record["is_top16"],
                "archetype_tags": "|".join(record["archetype_tags"] or []),
                "species": mon.get("species"),
                "item": mon.get("item"),
                "ability": mon.get("ability"),
                "nature": mon.get("nature"),
                "tera_type": mon.get("tera_type"),
            }
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=list(row.keys()))
            if not header_written:
                writer.writeheader()
                header_written = True
            writer.writerow(row)
            yield buf.getvalue()
