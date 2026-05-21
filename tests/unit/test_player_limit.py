"""
Unit tests — 16-player draft pool hard cap.
"""
import pytest
from unittest.mock import patch

from src.data.models import MAX_PLAYERS_PER_DRAFT
from src.services.draft_service import DraftService
from src.data.models import DraftFormat


@pytest.mark.asyncio
async def test_max_player_constant_is_16():
    assert MAX_PLAYERS_PER_DRAFT == 16


@pytest.mark.asyncio
async def test_16_players_can_join():
    svc = DraftService()
    with patch("src.services.draft_service.sheets"):
        await svc.create_draft("gfull", "host", DraftFormat.SNAKE)
        for i in range(16):
            result = await svc.add_player("gfull", f"player{i}")
            assert result.success, f"Player {i} should be able to join"
        draft = await svc.get_active_draft("gfull")
    assert draft.player_count == 16


@pytest.mark.asyncio
async def test_17th_player_is_rejected():
    svc = DraftService()
    with patch("src.services.draft_service.sheets"):
        await svc.create_draft("gover", "host", DraftFormat.SNAKE)
        for i in range(16):
            await svc.add_player("gover", f"player{i}")
        result = await svc.add_player("gover", "player16")
    assert not result.success
    assert "full" in result.error.lower()
    assert "16" in result.error


@pytest.mark.asyncio
async def test_draft_count_shown_in_error():
    svc = DraftService()
    with patch("src.services.draft_service.sheets"):
        await svc.create_draft("gcount", "host", DraftFormat.SNAKE)
        for i in range(16):
            await svc.add_player("gcount", f"p{i}")
        result = await svc.add_player("gcount", "extra")
    assert "16" in result.error
