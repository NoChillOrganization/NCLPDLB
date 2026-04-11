"""
Showdown WebSocket Client — 3-layer architecture.

Layers
------
  ShowdownConnection    — raw WebSocket lifecycle (connect / recv / send)
  ShowdownMessageHandler — parse Showdown protocol lines and dispatch callbacks
  ShowdownCommander      — high-level commands (login, challenge, choose, etc.)

Composite
---------
  ShowdownClient        — single account (connection + handler + commander)
  ShowdownClientPool    — two named accounts for self-play (AccountA vs AccountB)

Default server
--------------
  wss://sim3.psim.us/showdown/websocket  (play.pokemonshowdown.com)
  Auth: https://play.pokemonshowdown.com/action.php

Windows notes
-------------
  Python 3.8+ uses ProactorEventLoop by default on Windows which supports
  asyncio sub-processes and WebSockets.  Call windows_event_loop_fix() at
  program startup if you hit "Event loop closed" errors.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from typing import Awaitable, Callable

log = logging.getLogger(__name__)

# ── Dependency guard ──────────────────────────────────────────────────────────

try:
    import websockets
    import websockets.exceptions
    WS_OK = True
except ImportError:  # pragma: no cover
    WS_OK = False
    websockets = None  # type: ignore


# ── Windows compatibility helper ──────────────────────────────────────────────

def windows_event_loop_fix() -> None:
    """
    Ensure asyncio uses ProactorEventLoop on Windows.

    Call once at the top of any script that uses ShowdownClient.
    No-op on macOS / Linux.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


# ── Layer 1: Connection ───────────────────────────────────────────────────────

class ShowdownConnection:
    """
    Layer 1 — raw WebSocket lifecycle management.

    Responsibilities:
      • open / close the WebSocket connection
      • background receive loop
      • dispatch raw messages to registered listeners
      • automatic ping / keepalive
    """

    DEFAULT_URL = "ws://localhost:8000/showdown/websocket"

    def __init__(self, url: str = DEFAULT_URL, name: str = "") -> None:
        self.url = url
        self._name = name or "conn"
        self._log = logging.getLogger(f"{__name__}.{self._name}.conn")
        self._ws = None
        self._connected = False
        self._recv_task: asyncio.Task | None = None
        self._listeners: list[Callable[[str], Awaitable[None]]] = []

    # ── Public API ──────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self._connected

    def add_listener(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Register a coroutine to receive every raw server message."""
        self._listeners.append(callback)

    async def connect(self, timeout: float = 10.0) -> None:
        """Open WebSocket connection and start the receive loop."""
        if not WS_OK:
            raise ImportError(
                "websockets is required. Run: pip install websockets>=12.0"
            )
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    self.url,
                    ping_interval=30,
                    ping_timeout=10,
                    open_timeout=timeout,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise ConnectionError(
                f"[{self._name}] Timed out connecting to {self.url}\n"
                "Make sure Pokemon Showdown is running: "
                "node pokemon-showdown start --no-security"
            )
        except Exception as exc:
            raise ConnectionError(
                f"[{self._name}] Could not connect to {self.url}: {exc}"
            ) from exc

        self._connected = True
        self._log.info(f"Connected to {self.url}")
        self._recv_task = asyncio.create_task(
            self._recv_loop(), name=f"recv-{self._name}"
        )

    async def disconnect(self) -> None:
        """Close WebSocket and cancel the receive loop cleanly."""
        self._connected = False
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._ws:
            try:
                await self._ws.close()
            except Exception:  # pragma: no cover
                pass
            self._ws = None
        self._log.info("Disconnected")

    async def send_raw(self, message: str) -> None:
        """Send a raw string to the Showdown server."""
        if not self._ws or not self._connected:
            raise RuntimeError(f"[{self._name}] Not connected — call connect() first")
        try:
            await self._ws.send(message)
            self._log.debug("→ %s", message[:120])
        except Exception as exc:
            self._log.error("Send error: %s", exc)
            self._connected = False
            raise

    # ── Internal ────────────────────────────────────────────────────────

    async def _recv_loop(self) -> None:
        """Background task: receive messages and dispatch to all listeners."""
        try:
            async for raw_msg in self._ws:
                self._log.debug("← %s", str(raw_msg)[:120])
                for listener in self._listeners:
                    try:
                        await listener(str(raw_msg))
                    except Exception as exc:
                        self._log.warning("Listener error: %s", exc)
        except websockets.exceptions.ConnectionClosed as exc:
            self._log.warning("Connection closed: %s", exc)
            self._connected = False
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._log.error("Recv loop error: %s", exc, exc_info=True)
            self._connected = False


# ── Layer 2: Message Handler ──────────────────────────────────────────────────

class ShowdownMessageHandler:
    """
    Layer 2 — Showdown protocol message parsing and dispatching.

    Showdown messages look like:
      >room-name
      |msgtype|arg1|arg2|...

    Multiple lines can appear in a single WebSocket frame.

    Usage:
        handler = ShowdownMessageHandler()
        handler.on("challstr", my_async_callback)   # callback(room, parts)
        handler.on("updateuser", another_callback)
        connection.add_listener(handler.handle)
    """

    def __init__(self, name: str = "") -> None:
        self._name = name or "handler"
        self._log = logging.getLogger(f"{__name__}.{self._name}.handler")
        self._callbacks: dict[str, list[Callable]] = {}

        # Internally store latest challstr so ShowdownCommander can retrieve it
        self.challstr: str = ""
        self.on("challstr", self._store_challstr)

    def on(self, msg_type: str, callback: Callable) -> None:
        """Register a callback for messages of a given type.

        Callback signature:  async def cb(room: str, parts: list[str]) -> None
        """
        self._callbacks.setdefault(msg_type, []).append(callback)

    def off(self, msg_type: str, callback: Callable) -> None:
        """Unregister a previously registered callback."""
        cbs = self._callbacks.get(msg_type, [])
        if callback in cbs:
            cbs.remove(callback)

    async def handle(self, raw: str) -> None:
        """Parse one WebSocket frame (may contain multiple protocol lines)."""
        lines = raw.strip().split("\n")
        room = ""

        # First line might be ">room-name" establishing room context
        if lines and lines[0].startswith(">"):
            room = lines[0][1:].strip()
            lines = lines[1:]

        for line in lines:
            if not line.startswith("|"):
                continue
            parts = line.split("|")
            msg_type = parts[1]
            payload = parts[2:] if len(parts) > 2 else []

            for cb in self._callbacks.get(msg_type, []):
                try:
                    await cb(room, payload)
                except Exception as exc:
                    self._log.warning(
                        "Callback error for %r: %s", msg_type, exc
                    )

    # ── Internal callbacks ──────────────────────────────────────────────

    async def _store_challstr(self, room: str, parts: list[str]) -> None:
        self.challstr = "|".join(parts)
        self._log.debug("challstr stored (%d chars)", len(self.challstr))


# ── Layer 3: Commander ────────────────────────────────────────────────────────

class ShowdownCommander:
    """
    Layer 3 — high-level Showdown commands.

    All methods are async and delegate to ShowdownConnection.send_raw().
    """

    def __init__(self, connection: ShowdownConnection) -> None:
        self._conn = connection
        self._log = logging.getLogger(f"{__name__}.{connection._name}.cmd")

    # ── Auth ────────────────────────────────────────────────────────────

    async def login(
        self,
        username: str,
        challstr: str = "",
        password: str = "",
    ) -> None:
        """
        Login to a Pokemon Showdown server.

        For local servers started with --no-security, password is ignored and
        challstr is passed as-is (the server accepts any assertion).
        """
        # Local no-security: /trn username,0,challstr
        await self._conn.send_raw(f"|/trn {username},0,{challstr}")
        self._log.info("Login sent for %s", username)

    # ── Matchmaking ─────────────────────────────────────────────────────

    async def challenge(self, opponent: str, format: str) -> None:
        """Send a direct battle challenge to another user."""
        await self._conn.send_raw(f"|/challenge {opponent},{format}")
        self._log.info("Challenged %s in %s", opponent, format)

    async def accept_challenge(self, opponent: str) -> None:
        """Accept an incoming challenge from a user."""
        await self._conn.send_raw(f"|/accept {opponent}")
        self._log.info("Accepted challenge from %s", opponent)

    async def cancel_challenge(self) -> None:
        """Cancel any outgoing challenge."""
        await self._conn.send_raw("|/cancelchallenge")

    # ── In-battle ───────────────────────────────────────────────────────

    async def choose(self, battle_id: str, choice: str) -> None:
        """
        Send a battle decision (move or switch).

        Args:
            battle_id: Battle room ID, e.g. "battle-gen9randombattle-12345"
            choice:    Showdown choice string, e.g. "move 1", "switch 2",
                       "move 1 mega", "move 1 terastallize"
        """
        await self._conn.send_raw(f"{battle_id}|/choose {choice}")

    async def undo(self, battle_id: str) -> None:
        """Undo last move choice (if still possible)."""
        await self._conn.send_raw(f"{battle_id}|/undo")

    async def forfeit(self, battle_id: str) -> None:
        """Forfeit the current battle."""
        await self._conn.send_raw(f"{battle_id}|/forfeit")

    async def save_replay(self, battle_id: str) -> None:
        """Request the server to save a public replay."""
        await self._conn.send_raw(f"{battle_id}|/savereplay")

    # ── Room management ─────────────────────────────────────────────────

    async def leave(self, room_id: str) -> None:
        """Leave a battle or chat room."""
        await self._conn.send_raw(f"|/leave {room_id}")

    async def chat(self, room_id: str, message: str) -> None:
        """Send a chat message to a room."""
        await self._conn.send_raw(f"{room_id}|{message}")


# ── Composite: single-account client ─────────────────────────────────────────

class ShowdownClient:
    """
    Single Showdown account — combines all three layers.

    Auto-login: once a challstr arrives, logs in automatically.
    Use `await client.wait_for_login()` to block until authenticated.

    Args:
        username: Showdown username (any string on local no-security server)
        password: Unused for local no-security server; kept for public use
        url:      WebSocket URL (default: ws://localhost:8000/showdown/websocket)
        name:     Friendly label used in log output (default: username)
    """

    DEFAULT_URL = ShowdownConnection.DEFAULT_URL

    def __init__(
        self,
        username: str,
        password: str = "",
        url: str = DEFAULT_URL,
        name: str = "",
    ) -> None:
        self.username = username
        self.password = password
        self._label = name or username
        self._log = logging.getLogger(f"{__name__}.{self._label}")

        self.connection = ShowdownConnection(url=url, name=self._label)
        self.handler = ShowdownMessageHandler(name=self._label)
        self.commander = ShowdownCommander(self.connection)

        # Wire raw messages → handler
        self.connection.add_listener(self.handler.handle)

        # Wire challstr → auto-login
        self.handler.on("challstr", self._on_challstr)

        # Signal for login completion
        self._login_event: asyncio.Event = asyncio.Event()
        self.handler.on("updateuser", self._on_updateuser)

    # ── Public API ──────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self.connection.connected

    async def connect(self, login_timeout: float = 15.0) -> None:
        """
        Open the WebSocket and wait for login to complete.

        Raises:
            ConnectionError: If the server is unreachable.
            asyncio.TimeoutError: If login doesn't complete within login_timeout.
        """
        await self.connection.connect()
        try:
            await asyncio.wait_for(self._login_event.wait(), timeout=login_timeout)
        except asyncio.TimeoutError:
            self._log.warning(
                "Login confirmation not received within %.1fs — proceeding anyway",
                login_timeout,
            )

    async def disconnect(self) -> None:
        """Disconnect cleanly."""
        await self.connection.disconnect()

    async def wait_for_login(self, timeout: float = 15.0) -> bool:
        """Wait up to `timeout` seconds for login to complete. Returns True if logged in."""
        try:
            await asyncio.wait_for(self._login_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    # ── Context manager support ─────────────────────────────────────────

    async def __aenter__(self) -> "ShowdownClient":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.disconnect()

    # ── Internal handlers ───────────────────────────────────────────────

    async def _on_challstr(self, room: str, parts: list[str]) -> None:
        challstr = "|".join(parts)
        await self.commander.login(
            username=self.username,
            challstr=challstr,
            password=self.password,
        )

    async def _on_updateuser(self, room: str, parts: list[str]) -> None:
        # |updateuser|username|...
        if parts and parts[0].strip().lower() == self.username.lower():
            if not self._login_event.is_set():
                self._login_event.set()
                self._log.info("Authenticated as %s", self.username)


# ── Composite: two-account pool ───────────────────────────────────────────────

class ShowdownClientPool:
    """
    Two named clients for local self-play: AccountA vs AccountB.

    Both connect to the same local Showdown server on
    ws://localhost:8000/showdown/websocket (configurable).

    Usage:
        async with ShowdownClientPool() as pool:
            await pool.account_a.commander.challenge(
                "AccountB", "gen9randombattle"
            )

    With custom names:
        pool = ShowdownClientPool(
            username_a="TrainerRed",
            username_b="TrainerBlue",
        )
    """

    DEFAULT_URL = ShowdownConnection.DEFAULT_URL

    def __init__(
        self,
        username_a: str = "AccountA",
        password_a: str = "",
        username_b: str = "AccountB",
        password_b: str = "",
        url: str = DEFAULT_URL,
    ) -> None:
        self.account_a = ShowdownClient(
            username=username_a,
            password=password_a,
            url=url,
            name="AccountA",
        )
        self.account_b = ShowdownClient(
            username=username_b,
            password=password_b,
            url=url,
            name="AccountB",
        )
        self._log = logging.getLogger(f"{__name__}.pool")

    async def connect(self) -> None:
        """Connect both accounts concurrently and wait for both to log in."""
        await asyncio.gather(
            self.account_a.connect(),
            self.account_b.connect(),
        )
        self._log.info(
            "Pool ready: %s + %s",
            self.account_a.username,
            self.account_b.username,
        )

    async def disconnect(self) -> None:
        """Disconnect both accounts, ignoring individual errors."""
        await asyncio.gather(
            self.account_a.disconnect(),
            self.account_b.disconnect(),
            return_exceptions=True,
        )
        self._log.info("Pool disconnected")

    async def __aenter__(self) -> "ShowdownClientPool":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.disconnect()
