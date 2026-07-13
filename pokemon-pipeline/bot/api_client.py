"""Async FastAPI client wrapper used by all Discord cogs. No direct DB/Celery access from the bot."""

from __future__ import annotations

import aiohttp

from bot.config import API_BASE_URL, API_SECRET_KEY


class PipelineAPIError(RuntimeError):
    pass


class PipelineAPIClient:
    def __init__(self, base_url: str = API_BASE_URL):
        self._base_url = base_url.rstrip("/")

    def _admin_headers(self) -> dict:
        return {"X-API-Key": API_SECRET_KEY}

    async def _request(self, method: str, path: str, admin: bool = False, **kwargs) -> dict:
        headers = self._admin_headers() if admin else {}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method, f"{self._base_url}{path}", headers=headers, timeout=aiohttp.ClientTimeout(total=15), **kwargs
                ) as resp:
                    if resp.status >= 400:
                        raise PipelineAPIError(f"{method} {path} -> {resp.status}: {await resp.text()}")
                    return await resp.json()
        except aiohttp.ClientError as exc:
            raise PipelineAPIError(f"Pipeline API is unavailable: {exc}") from exc

    # --- Teams ---
    async def get_team(self, team_id: int) -> dict:
        return await self._request("GET", f"/teams/{team_id}")

    async def search_teams(self, filters: dict) -> dict:
        return await self._request("GET", "/teams", params=filters)

    async def get_team_paste(self, team_id: int) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/teams/{team_id}/paste") as resp:
                return await resp.text()

    async def get_similar_teams(self, team_id: int, k: int = 5) -> dict:
        return await self._request("GET", f"/teams/{team_id}/similar", params={"k": k})

    # --- Tournaments ---
    async def get_tournament(self, tournament_id: int) -> dict:
        return await self._request("GET", f"/tournaments/{tournament_id}")

    async def get_tournament_teams(self, tournament_id: int) -> dict:
        return await self._request("GET", f"/tournaments/{tournament_id}/teams")

    # --- Import / admin ---
    async def trigger_import(self, source: str, external_id: str) -> dict:
        return await self._request(
            "POST", "/admin/import/tournament", admin=True, json={"source": source, "external_id": external_id}
        )

    async def get_task_status(self, task_id: str) -> dict:
        return await self._request("GET", f"/admin/tasks/{task_id}", admin=True)

    async def get_pipeline_stats(self) -> dict:
        return await self._request("GET", "/admin/stats", admin=True)

    async def backfill_start(self, source: str | None = None) -> dict:
        return await self._request("POST", "/admin/backfill/start", admin=True, json={"source": source})

    async def backfill_status(self) -> dict:
        return await self._request("GET", "/admin/backfill/status", admin=True)

    # --- Creators ---
    async def list_creators(self) -> dict:
        return await self._request("GET", "/creators")

    async def add_creator(self, data: dict) -> dict:
        return await self._request("POST", "/creators", admin=True, json=data)

    async def trigger_creator_sync(self, creator_id: int) -> dict:
        return await self._request("POST", f"/creators/{creator_id}/sync", admin=True)
