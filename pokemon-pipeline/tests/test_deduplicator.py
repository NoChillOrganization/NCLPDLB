"""Deduplication tests against an in-memory SQLite database."""

import pytest

from models.db import Source, Team
from tasks.process.deduplicator import TeamDeduplicator
from tasks.process.parser import ShowdownPasteParser

PASTE_A = """Smeargle
Ability: Own Tempo
- Follow Me
- Spore
- Fake Out
- Wide Guard
"""

PASTE_B = """Incineroar @ Safety Goggles
Ability: Intimidate
EVs: 244 HP / 4 Def / 4 SpD / 4 Spe
Careful Nature
- Fake Out
- Knock Off
- Parting Shot
- Flare Blitz
"""


async def _make_source(session, platform="test_source") -> Source:
    source = Source(platform=platform, base_url="https://example.com", api_available=False)
    session.add(source)
    await session.flush()
    return source


@pytest.mark.asyncio
class TestDeduplicator:
    async def test_first_insert_creates_team(self, db_session):
        source = await _make_source(db_session)
        dedup = TeamDeduplicator()
        parsed = ShowdownPasteParser().parse(PASTE_A)

        team, was_created = await dedup.upsert_team(
            db_session,
            raw_paste=PASTE_A,
            parsed_json=parsed,
            regulation="Reg M-B",
            format_type="VGC",
            source_meta={"source_id": source.id, "scrape_method": "api"},
        )
        assert was_created is True
        assert team.id is not None

    async def test_duplicate_insert_reuses_team(self, db_session):
        source = await _make_source(db_session)
        dedup = TeamDeduplicator()
        parsed = ShowdownPasteParser().parse(PASTE_A)

        team1, created1 = await dedup.upsert_team(
            db_session, raw_paste=PASTE_A, parsed_json=parsed, regulation=None, format_type=None,
            source_meta={"source_id": source.id, "scrape_method": "api"},
        )
        team2, created2 = await dedup.upsert_team(
            db_session, raw_paste=PASTE_A, parsed_json=parsed, regulation=None, format_type=None,
            source_meta={"source_id": source.id, "scrape_method": "api"},
        )
        assert created1 is True
        assert created2 is False
        assert team1.id == team2.id

    async def test_duplicate_creates_new_provenance(self, db_session):
        source1 = await _make_source(db_session, "source_one")
        source2 = await _make_source(db_session, "source_two")
        dedup = TeamDeduplicator()
        parsed = ShowdownPasteParser().parse(PASTE_A)

        await dedup.upsert_team(
            db_session, raw_paste=PASTE_A, parsed_json=parsed, regulation=None, format_type=None,
            source_meta={"source_id": source1.id, "scrape_method": "api"},
        )
        await dedup.upsert_team(
            db_session, raw_paste=PASTE_A, parsed_json=parsed, regulation=None, format_type=None,
            source_meta={"source_id": source2.id, "scrape_method": "scrape_requests"},
        )

        from sqlalchemy import select

        from models.db import SourceProvenance

        teams = (await db_session.execute(select(Team))).scalars().all()
        provenances = (await db_session.execute(select(SourceProvenance))).scalars().all()

        assert len(teams) == 1
        assert len(provenances) == 2

    async def test_different_paste_creates_new_team(self, db_session):
        source = await _make_source(db_session)
        dedup = TeamDeduplicator()
        parser = ShowdownPasteParser()

        team_a, _ = await dedup.upsert_team(
            db_session, raw_paste=PASTE_A, parsed_json=parser.parse(PASTE_A), regulation=None, format_type=None,
            source_meta={"source_id": source.id, "scrape_method": "api"},
        )
        team_b, _ = await dedup.upsert_team(
            db_session, raw_paste=PASTE_B, parsed_json=parser.parse(PASTE_B), regulation=None, format_type=None,
            source_meta={"source_id": source.id, "scrape_method": "api"},
        )
        assert team_a.id != team_b.id
