"""
Unit tests for VideoService — Discord CDN URL recording.
sheets is mocked; no external storage required.
"""
from unittest.mock import MagicMock, patch

from src.services.video_service import VideoService, VideoUploadResult, MAX_FILE_SIZE_MB


def make_attachment(
    filename: str = "match.mp4",
    content_type: str = "video/mp4",
    size_mb: float = 10,
    url: str = "https://cdn.discordapp.com/attachments/123/456/match.mp4",
) -> MagicMock:
    att = MagicMock()
    att.filename = filename
    att.content_type = content_type
    att.size = int(size_mb * 1024 * 1024)
    att.url = url
    return att


# ── Size validation ───────────────────────────────────────────

async def test_upload_rejects_oversized_file():
    svc = VideoService()
    att = make_attachment(size_mb=MAX_FILE_SIZE_MB + 1)

    result = await svc.upload_match_video("g1", "p1", "p2", att)

    assert not result.success
    assert "too large" in result.error.lower()


async def test_upload_accepts_max_size_file():
    svc = VideoService()
    att = make_attachment(size_mb=MAX_FILE_SIZE_MB)

    with patch("src.services.video_service.sheets"):
        result = await svc.upload_match_video("g1", "p1", "p2", att)

    assert result.success


# ── Discord CDN recording ─────────────────────────────────────

async def test_upload_records_discord_cdn_url():
    svc = VideoService()
    cdn_url = "https://cdn.discordapp.com/attachments/999/888/game.mp4"
    att = make_attachment(url=cdn_url)

    with patch("src.services.video_service.sheets"):
        result = await svc.upload_match_video("g1", "p1", "p2", att)

    assert result.success
    assert result.public_url == cdn_url


async def test_upload_saves_metadata_to_sheets():
    svc = VideoService()
    att = make_attachment()

    with patch("src.services.video_service.sheets") as mock_sheets:
        _ = await svc.upload_match_video("g1", "p1", "p2", att, notes="great match")

    mock_sheets.save_video.assert_called_once()
    call_args = mock_sheets.save_video.call_args[0][0]
    assert call_args["uploader_id"] == "p1"
    assert call_args["opponent_id"] == "p2"
    assert "timestamp" in call_args


async def test_upload_returns_video_id():
    svc = VideoService()
    att = make_attachment()

    with patch("src.services.video_service.sheets"):
        result = await svc.upload_match_video("g1", "p1", "p2", att)

    assert result.success
    assert result.video_id != ""


async def test_upload_result_dataclass_defaults():
    r = VideoUploadResult(success=True)
    assert r.video_id == ""
    assert r.public_url == ""
    assert r.thumbnail_url == ""
    assert r.error == ""
