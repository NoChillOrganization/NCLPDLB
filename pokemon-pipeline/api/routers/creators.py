"""Creator registry admin endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, require_api_key
from api.schemas import CreatorCreateSchema, CreatorSchema
from celery_app import app as celery_app
from models.db import CreatorRegistry
from tasks.ingest.youtube_client import YouTubeClient

router = APIRouter(prefix="/creators", tags=["creators"])


@router.get("", response_model=list[CreatorSchema])
async def list_creators(db: AsyncSession = Depends(get_db)) -> list[CreatorSchema]:
    rows = (await db.execute(select(CreatorRegistry))).scalars().all()
    return [CreatorSchema.model_validate(r) for r in rows]


@router.post("", response_model=CreatorSchema, dependencies=[Depends(require_api_key)])
async def create_creator(payload: CreatorCreateSchema, db: AsyncSession = Depends(get_db)) -> CreatorSchema:
    playlist_id = None
    if payload.youtube_channel_id:
        try:
            playlist_id = YouTubeClient().get_uploads_playlist_id(payload.youtube_channel_id)
        except Exception:  # noqa: BLE001 - API key missing/invalid at creation time is non-fatal
            playlist_id = None

    creator = CreatorRegistry(
        name=payload.name,
        youtube_channel_id=payload.youtube_channel_id,
        youtube_playlist_id=playlist_id,
        twitter_handle=payload.twitter_handle,
        description_paste_regex=payload.description_paste_regex,
        is_active=True,
    )
    db.add(creator)
    await db.commit()
    await db.refresh(creator)
    return CreatorSchema.model_validate(creator)


@router.patch("/{creator_id}", response_model=CreatorSchema, dependencies=[Depends(require_api_key)])
async def update_creator(creator_id: int, payload: dict, db: AsyncSession = Depends(get_db)) -> CreatorSchema:
    creator = await db.get(CreatorRegistry, creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="Creator not found")
    for key, value in payload.items():
        if hasattr(creator, key):
            setattr(creator, key, value)
    await db.commit()
    await db.refresh(creator)
    return CreatorSchema.model_validate(creator)


@router.delete("/{creator_id}", dependencies=[Depends(require_api_key)])
async def deactivate_creator(creator_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    creator = await db.get(CreatorRegistry, creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="Creator not found")
    creator.is_active = False  # soft delete
    await db.commit()
    return {"deactivated": True}


@router.post("/{creator_id}/sync", dependencies=[Depends(require_api_key)])
async def sync_creator(creator_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    creator = await db.get(CreatorRegistry, creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="Creator not found")
    task = celery_app.send_task("tasks.ingest.youtube.sync_all_creators")
    return {"task_id": task.id}
