"""Pydantic v2 models for all API request/response objects."""

from __future__ import annotations

import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class PokemonSetSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slot_index: int
    species: str
    nickname: Optional[str] = None
    item: Optional[str] = None
    ability: Optional[str] = None
    nature: Optional[str] = None
    tera_type: Optional[str] = None
    move1: Optional[str] = None
    move2: Optional[str] = None
    move3: Optional[str] = None
    move4: Optional[str] = None
    ev_hp: int
    ev_atk: int
    ev_def: int
    ev_spa: int
    ev_spd: int
    ev_spe: int
    iv_hp: int
    iv_atk: int
    iv_def: int
    iv_spa: int
    iv_spd: int
    iv_spe: int
    level: int
    gender: Optional[str] = None
    is_shiny: bool


class TeamSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content_hash: str
    raw_paste: str
    parsed_json: list[dict] | dict
    regulation: Optional[str] = None
    format_type: Optional[str] = None
    archetype_tags: list[str] = []
    is_valid: bool
    created_at: datetime.datetime


class TournamentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    event_type: Optional[str] = None
    format_type: Optional[str] = None
    regulation: Optional[str] = None
    date_held: Optional[datetime.date] = None
    location: Optional[str] = None
    player_count: Optional[int] = None
    source_platform: Optional[str] = None


class PlacementSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    player_name: str
    final_placing: Optional[int] = None
    win_count: int
    loss_count: int
    bring_order: Optional[list[int]] = None
    tournament: TournamentSchema
    team: TeamSchema


class ProvenanceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_platform: str
    source_url: Optional[str] = None
    scrape_method: str
    scrape_timestamp: datetime.datetime
    confidence: int


class TeamDetailSchema(TeamSchema):
    placements: list[PlacementSchema] = []
    provenance: list[ProvenanceSchema] = []


class CreatorSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    youtube_channel_id: Optional[str] = None
    youtube_playlist_id: Optional[str] = None
    twitter_handle: Optional[str] = None
    description_paste_regex: Optional[str] = None
    is_active: bool
    last_scraped_at: Optional[datetime.datetime] = None


class CreatorCreateSchema(BaseModel):
    name: str
    youtube_channel_id: Optional[str] = None
    twitter_handle: Optional[str] = None
    description_paste_regex: Optional[str] = None


class ImportTriggerSchema(BaseModel):
    source: str
    external_id: str


class TaskStatusSchema(BaseModel):
    task_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None


class PaginatedTeamsSchema(BaseModel):
    items: list[TeamSchema]
    total: int
    page: int
    pages: int
