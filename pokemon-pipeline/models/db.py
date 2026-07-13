"""SQLAlchemy 2.x async models for all 10 tables. mapped_column() style throughout."""

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import (
    ARRAY as PG_ARRAY,
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from config import settings

# Postgres keeps its native JSONB/ARRAY (with GIN/HNSW indexes below); the SQLite variant used
# by the test suite (conftest.py, in-memory DB) degrades to plain JSON since SQLite has neither.
JSONB = PG_JSONB().with_variant(JSON(), "sqlite")
TextArray = PG_ARRAY(Text).with_variant(JSON(), "sqlite")
SmallIntArray = PG_ARRAY(SmallInteger).with_variant(JSON(), "sqlite")

try:
    from pgvector.sqlalchemy import Vector

    PGVECTOR_AVAILABLE = True
except ImportError:  # pgvector optional — degrade gracefully per project convention
    PGVECTOR_AVAILABLE = False
    Vector = None  # type: ignore[assignment,misc]


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# 1. sources
# ---------------------------------------------------------------------------
class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_available: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    tournaments: Mapped[list["Tournament"]] = relationship(back_populates="source")


# ---------------------------------------------------------------------------
# 2. tournaments
# ---------------------------------------------------------------------------
class Tournament(Base):
    __tablename__ = "tournaments"
    __table_args__ = (
        UniqueConstraint("external_id", "source_id", name="uq_tournament_external_source"),
        Index("ix_tournaments_date_held", "date_held"),
        Index("ix_tournaments_source_external", "source_id", "external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    format_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    regulation: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    date_held: Mapped[Optional[datetime.date]] = mapped_column(nullable=True)
    location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    player_count: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    source: Mapped["Source"] = relationship(back_populates="tournaments")
    placements: Mapped[list["TournamentPlacement"]] = relationship(back_populates="tournament")


# ---------------------------------------------------------------------------
# 3. players
# ---------------------------------------------------------------------------
class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    placements: Mapped[list["TournamentPlacement"]] = relationship(back_populates="player")


# ---------------------------------------------------------------------------
# 4. teams
# ---------------------------------------------------------------------------
class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        Index("ix_teams_regulation", "regulation"),
        Index("ix_teams_format_type", "format_type"),
        Index("ix_teams_parsed_json_gin", "parsed_json", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    raw_paste: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    regulation: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    format_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    archetype_tags: Mapped[list[str]] = mapped_column(TextArray, default=list)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    pokemon_sets: Mapped[list["PokemonSet"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )
    placements: Mapped[list["TournamentPlacement"]] = relationship(back_populates="team")
    provenance: Mapped[list["SourceProvenance"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )
    embedding: Mapped[Optional["TeamEmbedding"]] = relationship(
        back_populates="team", cascade="all, delete-orphan", uselist=False
    )


# ---------------------------------------------------------------------------
# 5. pokemon_sets
# ---------------------------------------------------------------------------
class PokemonSet(Base):
    __tablename__ = "pokemon_sets"
    __table_args__ = (Index("ix_pokemon_sets_species", "species"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    slot_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    species: Mapped[str] = mapped_column(String(50), nullable=False)
    nickname: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    item: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ability: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    nature: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    tera_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    move1: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    move2: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    move3: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    move4: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ev_hp: Mapped[int] = mapped_column(SmallInteger, default=0)
    ev_atk: Mapped[int] = mapped_column(SmallInteger, default=0)
    ev_def: Mapped[int] = mapped_column(SmallInteger, default=0)
    ev_spa: Mapped[int] = mapped_column(SmallInteger, default=0)
    ev_spd: Mapped[int] = mapped_column(SmallInteger, default=0)
    ev_spe: Mapped[int] = mapped_column(SmallInteger, default=0)
    iv_hp: Mapped[int] = mapped_column(SmallInteger, default=31)
    iv_atk: Mapped[int] = mapped_column(SmallInteger, default=31)
    iv_def: Mapped[int] = mapped_column(SmallInteger, default=31)
    iv_spa: Mapped[int] = mapped_column(SmallInteger, default=31)
    iv_spd: Mapped[int] = mapped_column(SmallInteger, default=31)
    iv_spe: Mapped[int] = mapped_column(SmallInteger, default=31)
    level: Mapped[int] = mapped_column(SmallInteger, default=50)
    gender: Mapped[Optional[str]] = mapped_column(String(1), nullable=True)
    is_shiny: Mapped[bool] = mapped_column(Boolean, default=False)

    team: Mapped["Team"] = relationship(back_populates="pokemon_sets")


# ---------------------------------------------------------------------------
# 6. tournament_placements
# ---------------------------------------------------------------------------
class TournamentPlacement(Base):
    __tablename__ = "tournament_placements"
    __table_args__ = (
        Index("ix_placements_tournament_id", "tournament_id"),
        Index(
            "ix_placements_top16",
            "final_placing",
            postgresql_where="final_placing <= 16",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    final_placing: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    win_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    loss_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    bring_order: Mapped[Optional[list[int]]] = mapped_column(SmallIntArray, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    tournament: Mapped["Tournament"] = relationship(back_populates="placements")
    player: Mapped["Player"] = relationship(back_populates="placements")
    team: Mapped["Team"] = relationship(back_populates="placements")

    @hybrid_property
    def is_top16(self) -> bool:
        return self.final_placing is not None and self.final_placing <= 16


# ---------------------------------------------------------------------------
# 7. source_provenance
# ---------------------------------------------------------------------------
class SourceProvenance(Base):
    __tablename__ = "source_provenance"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_confidence_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scrape_method: Mapped[str] = mapped_column(String(30), nullable=False)
    scrape_timestamp: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    confidence: Mapped[int] = mapped_column(SmallInteger, default=100)
    raw_response: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    team: Mapped["Team"] = relationship(back_populates="provenance")
    source: Mapped["Source"] = relationship()


# ---------------------------------------------------------------------------
# 8. creator_registry
# ---------------------------------------------------------------------------
class CreatorRegistry(Base):
    __tablename__ = "creator_registry"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    youtube_channel_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    youtube_playlist_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    twitter_handle: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description_paste_regex: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scraped_at: Mapped[Optional[datetime.datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# 9. backfill_log
# ---------------------------------------------------------------------------
class BackfillLog(Base):
    __tablename__ = "backfill_log"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_backfill_source_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/done/failed
    processed_at: Mapped[Optional[datetime.datetime]] = mapped_column(nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# 10. team_embeddings (pgvector — optional)
# ---------------------------------------------------------------------------
if PGVECTOR_AVAILABLE:

    class TeamEmbedding(Base):
        __tablename__ = "team_embeddings"

        id: Mapped[int] = mapped_column(primary_key=True)
        team_id: Mapped[int] = mapped_column(
            ForeignKey("teams.id", ondelete="CASCADE"), unique=True, nullable=False
        )
        embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
        created_at: Mapped[datetime.datetime] = mapped_column(
            server_default=func.now(), nullable=False
        )

        team: Mapped["Team"] = relationship(back_populates="embedding")

else:
    TeamEmbedding = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Engine / session factory
# ---------------------------------------------------------------------------
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncSession:  # pragma: no cover - trivial DI helper
    async with async_session_factory() as session:
        yield session
