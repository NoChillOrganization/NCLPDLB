"""001 initial schema — all 10 tables + pgvector extension

Revision ID: 001
Revises:
Create Date: 2026-07-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform", sa.String(50), unique=True, nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_available", sa.Boolean(), server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "tournaments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=True),
        sa.Column("format_type", sa.String(50), nullable=True),
        sa.Column("regulation", sa.String(20), nullable=True),
        sa.Column("date_held", sa.Date(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("player_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("external_id", "source_id", name="uq_tournament_external_source"),
    )
    op.create_index("ix_tournaments_date_held", "tournaments", ["date_held"])
    op.create_index(
        "ix_tournaments_source_external", "tournaments", ["source_id", "external_id"]
    )

    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column("country", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("raw_paste", sa.Text(), nullable=False),
        sa.Column("parsed_json", postgresql.JSONB(), nullable=False),
        sa.Column("regulation", sa.String(20), nullable=True),
        sa.Column("format_type", sa.String(50), nullable=True),
        sa.Column("archetype_tags", postgresql.ARRAY(sa.Text()), server_default="{}"),
        sa.Column("is_valid", sa.Boolean(), server_default=sa.true()),
        sa.Column("validation_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_teams_regulation", "teams", ["regulation"])
    op.create_index("ix_teams_format_type", "teams", ["format_type"])
    op.create_index(
        "ix_teams_parsed_json_gin", "teams", ["parsed_json"], postgresql_using="gin"
    )

    op.create_table(
        "pokemon_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "team_id",
            sa.Integer(),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slot_index", sa.SmallInteger(), nullable=False),
        sa.Column("species", sa.String(50), nullable=False),
        sa.Column("nickname", sa.String(50), nullable=True),
        sa.Column("item", sa.String(50), nullable=True),
        sa.Column("ability", sa.String(50), nullable=True),
        sa.Column("nature", sa.String(20), nullable=True),
        sa.Column("tera_type", sa.String(20), nullable=True),
        sa.Column("move1", sa.String(50), nullable=True),
        sa.Column("move2", sa.String(50), nullable=True),
        sa.Column("move3", sa.String(50), nullable=True),
        sa.Column("move4", sa.String(50), nullable=True),
        sa.Column("ev_hp", sa.SmallInteger(), server_default="0"),
        sa.Column("ev_atk", sa.SmallInteger(), server_default="0"),
        sa.Column("ev_def", sa.SmallInteger(), server_default="0"),
        sa.Column("ev_spa", sa.SmallInteger(), server_default="0"),
        sa.Column("ev_spd", sa.SmallInteger(), server_default="0"),
        sa.Column("ev_spe", sa.SmallInteger(), server_default="0"),
        sa.Column("iv_hp", sa.SmallInteger(), server_default="31"),
        sa.Column("iv_atk", sa.SmallInteger(), server_default="31"),
        sa.Column("iv_def", sa.SmallInteger(), server_default="31"),
        sa.Column("iv_spa", sa.SmallInteger(), server_default="31"),
        sa.Column("iv_spd", sa.SmallInteger(), server_default="31"),
        sa.Column("iv_spe", sa.SmallInteger(), server_default="31"),
        sa.Column("level", sa.SmallInteger(), server_default="50"),
        sa.Column("gender", sa.String(1), nullable=True),
        sa.Column("is_shiny", sa.Boolean(), server_default=sa.false()),
    )
    op.create_index("ix_pokemon_sets_species", "pokemon_sets", ["species"])

    op.create_table(
        "tournament_placements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id"), nullable=False
        ),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("final_placing", sa.SmallInteger(), nullable=True),
        sa.Column("win_count", sa.SmallInteger(), server_default="0"),
        sa.Column("loss_count", sa.SmallInteger(), server_default="0"),
        sa.Column("bring_order", postgresql.ARRAY(sa.SmallInteger()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_placements_tournament_id", "tournament_placements", ["tournament_id"])
    op.create_index(
        "ix_placements_top16",
        "tournament_placements",
        ["final_placing"],
        postgresql_where=sa.text("final_placing <= 16"),
    )

    op.create_table(
        "source_provenance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "team_id",
            sa.Integer(),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("scrape_method", sa.String(30), nullable=False),
        sa.Column(
            "scrape_timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("confidence", sa.SmallInteger(), server_default="100"),
        sa.Column("raw_response", postgresql.JSONB(), nullable=True),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_confidence_range"),
    )

    op.create_table(
        "creator_registry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("youtube_channel_id", sa.String(50), nullable=True),
        sa.Column("youtube_playlist_id", sa.String(50), nullable=True),
        sa.Column("twitter_handle", sa.String(50), nullable=True),
        sa.Column("description_paste_regex", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "backfill_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.UniqueConstraint("source", "external_id", name="uq_backfill_source_external"),
    )

    # team_embeddings requires pgvector — wrap in try/except in case extension creation
    # above failed silently on a host without pgvector packaged.
    try:
        op.create_table(
            "team_embeddings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "team_id",
                sa.Integer(),
                sa.ForeignKey("teams.id", ondelete="CASCADE"),
                unique=True,
                nullable=False,
            ),
            sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=False),  # placeholder type
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        # Real vector column + HNSW index — separate statements so a missing
        # extension degrades gracefully instead of aborting the whole migration.
        op.execute("ALTER TABLE team_embeddings ALTER COLUMN embedding TYPE vector(384) USING embedding::vector(384)")
        op.execute(
            "CREATE INDEX ix_team_embeddings_hnsw ON team_embeddings "
            "USING hnsw (embedding vector_cosine_ops)"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: pgvector unavailable, team_embeddings degraded: {exc}")


def downgrade() -> None:
    op.drop_table("team_embeddings")
    op.drop_table("backfill_log")
    op.drop_table("creator_registry")
    op.drop_table("source_provenance")
    op.drop_table("tournament_placements")
    op.drop_table("pokemon_sets")
    op.drop_table("teams")
    op.drop_table("players")
    op.drop_table("tournaments")
    op.drop_table("sources")
