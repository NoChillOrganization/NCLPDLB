"""Team embedding computation and pgvector similarity search. Degrades gracefully if pgvector absent."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.db import PGVECTOR_AVAILABLE, Team, TeamEmbedding, async_session_factory

logger = logging.getLogger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"
_EMBEDDING_DIM = 384

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(_MODEL_NAME)
    return _model


class TeamEmbedder:
    async def embed_team(self, team_id: int, raw_paste: str) -> Optional[list[float]]:
        if not PGVECTOR_AVAILABLE:
            logger.warning("pgvector not installed, skipping embedding for team %d", team_id)
            return None

        model = _get_model()
        vector = model.encode(raw_paste, normalize_embeddings=True).tolist()

        async with async_session_factory() as session:
            existing = await session.execute(select(TeamEmbedding).where(TeamEmbedding.team_id == team_id))
            row = existing.scalar_one_or_none()
            if row is None:
                session.add(TeamEmbedding(team_id=team_id, embedding=vector))
            else:
                row.embedding = vector
            await session.commit()
        return vector

    async def find_similar_teams(
        self, session: AsyncSession, team_id: int, top_k: int = 10, regulation: Optional[str] = None
    ) -> list[dict]:
        if not PGVECTOR_AVAILABLE:
            logger.warning("pgvector not installed, similarity search unavailable")
            return []

        source_row = await session.execute(select(TeamEmbedding).where(TeamEmbedding.team_id == team_id))
        source_embedding = source_row.scalar_one_or_none()
        if source_embedding is None:
            return []

        query = (
            select(TeamEmbedding.team_id, TeamEmbedding.embedding.cosine_distance(source_embedding.embedding).label("distance"))
            .where(TeamEmbedding.team_id != team_id)
        )
        if regulation:
            query = query.join(Team, Team.id == TeamEmbedding.team_id).where(Team.regulation == regulation)
        query = query.order_by(text("distance")).limit(top_k)

        rows = (await session.execute(query)).all()
        return [{"team_id": tid, "distance": float(dist)} for tid, dist in rows]


async def embed_all_valid_teams() -> int:
    """Batch-embed every valid team missing an embedding. Standalone-runnable via python -m ml.embeddings."""
    embedder = TeamEmbedder()
    embedded = 0
    async with async_session_factory() as session:
        subq = select(TeamEmbedding.team_id)
        rows = (
            await session.execute(select(Team).where(Team.is_valid.is_(True), Team.id.not_in(subq)))
        ).scalars().all()
    for team in rows:
        result = await embedder.embed_team(team.id, team.raw_paste)
        if result is not None:
            embedded += 1
    return embedded


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    count = asyncio.run(embed_all_valid_teams())
    print(f"Embedded {count} teams")
