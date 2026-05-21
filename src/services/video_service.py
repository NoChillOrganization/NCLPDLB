"""
Video Service — records Discord attachment CDN URLs for match videos.
No external storage required; Discord CDN is used directly.

Note: Discord CDN URLs may expire after some time. For permanent storage,
users should share YouTube/Twitch links instead.

Exports:
    VideoService       — async service for recording match video metadata.
    VideoUploadResult  — dataclass returned by upload_match_video.
    MAX_FILE_SIZE_MB   — enforcement ceiling (100 MB by default).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
import discord

from src.data.sheets import sheets

log = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/avi"}
MAX_FILE_SIZE_MB = 100


@dataclass
class VideoUploadResult:
    success: bool
    video_id: str = ""
    public_url: str = ""
    thumbnail_url: str = ""
    error: str = ""


class VideoService:
    async def upload_match_video(
        self,
        guild_id: str,
        uploader_id: str,
        opponent_id: str,
        attachment: discord.Attachment,
        notes: str = "",
    ) -> VideoUploadResult:
        if attachment.size > MAX_FILE_SIZE_MB * 1024 * 1024:
            return VideoUploadResult(
                success=False,
                error=f"File too large. Max {MAX_FILE_SIZE_MB}MB. Consider uploading to YouTube and sharing the link instead."
            )

        video_id = str(uuid.uuid4())[:12]
        public_url = attachment.url

        # Save metadata to Google Sheets
        sheets.save_video({
            "video_id": video_id,
            "match_id": "",
            "uploader_id": uploader_id,
            "opponent_id": opponent_id,
            "storage_url": public_url,
            "thumbnail_url": "",
            "notes": notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        log.info(f"Video {video_id} recorded by {uploader_id} in guild {guild_id} (Discord CDN)")
        return VideoUploadResult(
            success=True,
            video_id=video_id,
            public_url=public_url,
        )
