"""Thin wrapper around google-api-python-client YouTube Data API v3 with quota tracking."""

from __future__ import annotations

import logging

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import settings
from tasks.utils import chunk_list

logger = logging.getLogger(__name__)

_DAILY_QUOTA = 10_000
_COST_PLAYLIST_ITEMS_LIST = 1
_COST_VIDEOS_LIST = 1
_COST_CHANNELS_LIST = 1


class YouTubeQuotaExceeded(RuntimeError):
    pass


class YouTubeClient:
    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or settings.youtube_api_key
        self._service = build("youtube", "v3", developerKey=self._api_key)
        self._quota_used = 0

    def _track(self, cost: int) -> None:
        self._quota_used += cost
        remaining = _DAILY_QUOTA - self._quota_used
        if remaining < 1000:
            logger.warning("YouTube quota running low: %d units remaining today", remaining)

    def get_uploads_playlist_id(self, channel_id: str) -> str:
        try:
            resp = self._service.channels().list(part="contentDetails", id=channel_id).execute()
            self._track(_COST_CHANNELS_LIST)
        except HttpError as exc:
            if exc.resp.status == 403:
                raise YouTubeQuotaExceeded(str(exc)) from exc
            raise
        items = resp.get("items", [])
        if not items:
            raise ValueError(f"No channel found for id={channel_id}")
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    def get_playlist_videos(self, playlist_id: str, published_after: str | None = None) -> list[dict]:
        videos: list[dict] = []
        page_token = None
        while True:
            try:
                resp = (
                    self._service.playlistItems()
                    .list(part="snippet", playlistId=playlist_id, maxResults=50, pageToken=page_token)
                    .execute()
                )
                self._track(_COST_PLAYLIST_ITEMS_LIST)
            except HttpError as exc:
                if exc.resp.status == 403:
                    raise YouTubeQuotaExceeded(str(exc)) from exc
                raise

            for item in resp.get("items", []):
                snippet = item["snippet"]
                published_at = snippet["publishedAt"]
                if published_after and published_at < published_after:
                    continue
                videos.append(
                    {
                        "video_id": snippet["resourceId"]["videoId"],
                        "title": snippet["title"],
                        "published_at": published_at,
                    }
                )

            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return videos

    def get_video_descriptions(self, video_ids: list[str]) -> dict[str, str]:
        descriptions: dict[str, str] = {}
        for chunk in chunk_list(video_ids, 50):
            try:
                resp = self._service.videos().list(part="snippet", id=",".join(chunk)).execute()
                self._track(_COST_VIDEOS_LIST)
            except HttpError as exc:
                if exc.resp.status == 403:
                    raise YouTubeQuotaExceeded(str(exc)) from exc
                raise
            for item in resp.get("items", []):
                descriptions[item["id"]] = item["snippet"].get("description", "")
        return descriptions

    @property
    def quota_used(self) -> int:
        return self._quota_used
