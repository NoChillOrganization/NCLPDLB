"""Nearest-neighbor team recommendation on top of ml.embeddings' pgvector similarity search."""

from __future__ import annotations

from typing import Optional

from models.db import async_session_factory
from ml.embeddings import TeamEmbedder


async def recommend_teams(team_id: int, top_k: int = 10, regulation: Optional[str] = None) -> list[dict]:
    embedder = TeamEmbedder()
    async with async_session_factory() as session:
        return await embedder.find_similar_teams(session, team_id, top_k=top_k, regulation=regulation)


if __name__ == "__main__":  # pragma: no cover
    import asyncio
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m ml.similarity <team_id> [top_k]")
        raise SystemExit(1)

    tid = int(sys.argv[1])
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    results = asyncio.run(recommend_teams(tid, k))
    for r in results:
        print(f"team_id={r['team_id']} distance={r['distance']:.4f}")
