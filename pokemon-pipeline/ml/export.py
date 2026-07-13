"""Training data export utilities: JSONL, feature matrix (.npz), Ollama fine-tune format.

Expected data volumes (documented per project convention): with ~5 sources syncing daily/weekly
from 2026-04-01 onward, expect roughly 50-200 top-16 teams/week for major VGC regulations once
backfill completes — low thousands of rows per regulation over a season, well within what these
export routines hold in memory for a single call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.db import Team, TournamentPlacement, async_session_factory

# Fixed vocabularies for one-hot / index encoding. Extend as new species/moves are seen;
# unseen values map to index 0 ("unknown") so encoding never raises.
_SPECIES_VOCAB_PATH = Path(__file__).parent / "vocab_species.json"
_MOVE_VOCAB_PATH = Path(__file__).parent / "vocab_moves.json"


def _load_or_build_vocab(path: Path, values: set[str]) -> dict[str, int]:
    if path.exists():
        return json.loads(path.read_text())
    vocab = {"unknown": 0, **{v: i + 1 for i, v in enumerate(sorted(values))}}
    path.write_text(json.dumps(vocab, indent=2))
    return vocab


class TrainingDataExporter:
    def __init__(self):
        pass

    async def _fetch_top16_placements(self, regulation: Optional[str], format_type: Optional[str]):
        query = (
            select(TournamentPlacement)
            .join(Team)
            .where(Team.is_valid.is_(True), TournamentPlacement.final_placing <= 16)
            .options(selectinload(TournamentPlacement.team))
        )
        if regulation:
            query = query.where(Team.regulation == regulation)
        if format_type:
            query = query.where(Team.format_type == format_type)

        async with async_session_factory() as session:
            return (await session.execute(query)).scalars().all()

    async def export_jsonl(
        self, output_path: str, regulation: Optional[str] = None, format_type: Optional[str] = None
    ) -> int:
        placements = await self._fetch_top16_placements(regulation, format_type)
        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for p in placements:
                team = p.team
                record = {
                    "regulation": team.regulation,
                    "format_type": team.format_type,
                    "final_placing": p.final_placing,
                    "win_count": p.win_count,
                    "archetype_tags": team.archetype_tags,
                    "raw_paste": team.raw_paste,
                    "parsed_json": team.parsed_json,
                }
                f.write(json.dumps(record) + "\n")
                count += 1
        return count

    async def export_feature_matrix(self, output_path: str, regulation: Optional[str] = None) -> tuple[int, int]:
        placements = await self._fetch_top16_placements(regulation, None)

        all_species: set[str] = set()
        all_moves: set[str] = set()
        for p in placements:
            for mon in p.team.parsed_json or []:
                if mon.get("species"):
                    all_species.add(mon["species"])
                for m in mon.get("moves") or []:
                    if m:
                        all_moves.add(m)

        species_vocab = _load_or_build_vocab(_SPECIES_VOCAB_PATH, all_species)
        move_vocab = _load_or_build_vocab(_MOVE_VOCAB_PATH, all_moves)

        rows = []
        labels_top16 = []
        labels_placing = []
        for p in placements:
            for mon in p.team.parsed_json or []:
                species_idx = species_vocab.get(mon.get("species"), 0)
                move_idxs = [move_vocab.get(m, 0) for m in (mon.get("moves") or [None] * 4)][:4]
                while len(move_idxs) < 4:
                    move_idxs.append(0)
                evs = mon.get("evs") or {}
                ivs = mon.get("ivs") or {}
                feature_row = (
                    [species_idx]
                    + move_idxs
                    + [evs.get(k, 0) for k in ("hp", "atk", "def", "spa", "spd", "spe")]
                    + [ivs.get(k, 31) for k in ("hp", "atk", "def", "spa", "spd", "spe")]
                )
                rows.append(feature_row)
                labels_top16.append(1)
                labels_placing.append(p.final_placing or 16)

        X = np.array(rows, dtype=np.int32)
        y_top16 = np.array(labels_top16, dtype=np.int8)
        y_placing = np.array(labels_placing, dtype=np.int16)
        np.savez(output_path, X=X, y_top16=y_top16, y_placing=y_placing)
        return X.shape[0], X.shape[1] if X.size else 0

    async def export_ollama_finetune(self, output_path: str, system_prompt: Optional[str] = None) -> int:
        placements = await self._fetch_top16_placements(None, None)
        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for p in placements:
                team = p.team
                sp = system_prompt or (
                    f"You are a competitive Pokemon VGC team builder. You build teams for "
                    f"{team.regulation or 'the current'} regulation based on tournament-winning data."
                )
                record = {
                    "messages": [
                        {"role": "system", "content": sp},
                        {"role": "user", "content": f"Build me a {team.regulation or 'VGC'} VGC team"},
                        {"role": "assistant", "content": team.raw_paste},
                    ]
                }
                f.write(json.dumps(record) + "\n")
                count += 1
        return count


if __name__ == "__main__":  # pragma: no cover - manual CLI entry point
    import argparse
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["jsonl", "feature-matrix", "ollama"], default="jsonl")
    parser.add_argument("--output", default="data/export.jsonl")
    parser.add_argument("--regulation", default=None)
    parser.add_argument("--format-type", default=None)
    args = parser.parse_args()

    exporter = TrainingDataExporter()
    if args.mode == "jsonl":
        n = asyncio.run(exporter.export_jsonl(args.output, args.regulation, args.format_type))
    elif args.mode == "feature-matrix":
        n, _ = asyncio.run(exporter.export_feature_matrix(args.output, args.regulation))
    else:
        n = asyncio.run(exporter.export_ollama_finetune(args.output))
    print(f"Exported {n} records to {args.output}")
