"""FastAPI application: core routers, WebSocket live feed, CORS, logging, lifespan."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from api.routers import admin, creators, export, ml, teams, tournaments
from config import settings
from models.db import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 - drop connections that error on send
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def _redis_pubsub_listener(app: FastAPI) -> None:
    """Subscribes to the 'team_ingested' channel and rebroadcasts to all WS clients.

    Celery ingest tasks publish here after tag_and_update_team commits.
    """
    client = redis.from_url(settings.redis_url)
    pubsub = client.pubsub()
    await pubsub.subscribe("team_ingested")
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                payload = json.loads(message["data"])
                await manager.broadcast(payload)
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("Bad pubsub payload: %s", exc)
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe("team_ingested")
        await client.aclose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = redis.from_url(settings.redis_url)
    listener_task = asyncio.create_task(_redis_pubsub_listener(app))

    yield

    listener_task.cancel()
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(
    title="pokemon-pipeline",
    description="Production-grade, live-updating Pokemon competitive team import and analysis pipeline.",
    version="0.1.0",
    contact={"name": "pipeline-admin"},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    logger.info(
        "%s %s -> %d (%.1fms)", request.method, request.url.path, response.status_code, duration_ms
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"error": "internal_server_error", "detail": str(exc)})


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket, token: str = Query(...)) -> None:
    if token != settings.api_secret_key:
        await websocket.close(code=4401)
        return

    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep connection open; client pings not required
    except WebSocketDisconnect:
        manager.disconnect(websocket)


app.include_router(teams.router)
app.include_router(tournaments.router)
app.include_router(admin.router)
app.include_router(creators.router)
app.include_router(export.router)
app.include_router(ml.router)
