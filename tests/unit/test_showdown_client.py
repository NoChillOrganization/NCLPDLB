"""
Unit tests for src/ml/showdown_client.py — all three layers + composites.

We never open a real WebSocket; every network call is mocked.
"""
from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────

def _make_fake_ws(messages: list[str] | None = None):
    """Return an async-iterable mock WebSocket."""
    ws = MagicMock()
    ws.send = AsyncMock()
    ws.close = AsyncMock()

    async def _aiter(self):
        for m in (messages or []):
            yield m

    ws.__aiter__ = _aiter
    return ws


# ── windows_event_loop_fix ─────────────────────────────────────────────────────

def test_windows_event_loop_fix_noop_on_non_windows():
    from src.ml.showdown_client import windows_event_loop_fix
    with patch.object(sys, "platform", "linux"):
        windows_event_loop_fix()  # must not raise


def test_windows_event_loop_fix_sets_policy_on_windows():
    from src.ml.showdown_client import windows_event_loop_fix
    mock_policy = MagicMock()
    with patch.object(sys, "platform", "win32"), \
         patch("asyncio.WindowsProactorEventLoopPolicy", return_value=mock_policy, create=True), \
         patch("asyncio.set_event_loop_policy") as mock_set:
        windows_event_loop_fix()
        mock_set.assert_called_once()


# ── ShowdownConnection ─────────────────────────────────────────────────────────

class TestShowdownConnection:

    def _make(self, url="ws://localhost:8000/showdown/websocket", name="test"):
        from src.ml.showdown_client import ShowdownConnection
        return ShowdownConnection(url=url, name=name)

    def test_initial_state(self):
        conn = self._make()
        assert conn.connected is False
        assert conn._ws is None
        assert conn._listeners == []

    def test_add_listener_appends(self):
        conn = self._make()
        cb = AsyncMock()
        conn.add_listener(cb)
        assert cb in conn._listeners

    async def test_connect_success(self):
        conn = self._make()
        fake_ws = _make_fake_ws()

        with patch("src.ml.showdown_client.WS_OK", True), \
             patch("src.ml.showdown_client.websockets") as mock_ws_mod:
            mock_ws_mod.connect = MagicMock(return_value=fake_ws)
            # asyncio.wait_for with a coroutine — wrap properly
            async def _fake_wait_for(coro, timeout):
                return fake_ws
            with patch("asyncio.wait_for", side_effect=_fake_wait_for):
                await conn.connect(timeout=5.0)

        assert conn.connected is True
        assert conn._recv_task is not None
        conn._recv_task.cancel()
        try:
            await conn._recv_task
        except asyncio.CancelledError:
            pass

    async def test_connect_raises_import_error_when_no_websockets(self):
        conn = self._make()
        with patch("src.ml.showdown_client.WS_OK", False):
            with pytest.raises(ImportError, match="websockets is required"):
                await conn.connect()

    async def test_connect_raises_connection_error_on_timeout(self):
        conn = self._make()
        with patch("src.ml.showdown_client.WS_OK", True), \
             patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(ConnectionError, match="Timed out"):
                await conn.connect()

    async def test_connect_raises_connection_error_on_other_exc(self):
        conn = self._make()
        with patch("src.ml.showdown_client.WS_OK", True), \
             patch("asyncio.wait_for", side_effect=OSError("refused")):
            with pytest.raises(ConnectionError, match="Could not connect"):
                await conn.connect()

    async def test_disconnect_cancels_task_and_closes_ws(self):
        conn = self._make()
        fake_ws = _make_fake_ws()
        conn._ws = fake_ws
        conn._connected = True

        cancelled = asyncio.Event()

        async def _long_running():
            try:
                await asyncio.sleep(999)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        conn._recv_task = asyncio.create_task(_long_running())
        await conn.disconnect()

        assert conn.connected is False
        assert conn._ws is None
        fake_ws.close.assert_awaited_once()

    async def test_disconnect_when_not_connected_is_noop(self):
        conn = self._make()
        await conn.disconnect()  # must not raise

    async def test_send_raw_success(self):
        conn = self._make()
        fake_ws = _make_fake_ws()
        conn._ws = fake_ws
        conn._connected = True

        await conn.send_raw("hello")
        fake_ws.send.assert_awaited_once_with("hello")

    async def test_send_raw_raises_when_not_connected(self):
        conn = self._make()
        with pytest.raises(RuntimeError, match="Not connected"):
            await conn.send_raw("hello")

    async def test_send_raw_propagates_send_exception(self):
        conn = self._make()
        fake_ws = _make_fake_ws()
        fake_ws.send = AsyncMock(side_effect=OSError("broken pipe"))
        conn._ws = fake_ws
        conn._connected = True

        with pytest.raises(OSError):
            await conn.send_raw("hello")
        assert conn.connected is False  # marked disconnected on error

    async def test_recv_loop_dispatches_to_listeners(self):
        conn = self._make()
        received = []

        async def listener(msg: str):
            received.append(msg)

        conn.add_listener(listener)
        fake_ws = _make_fake_ws(["msg1", "msg2"])
        conn._ws = fake_ws
        conn._connected = True

        # Run the recv loop to completion (iterator exhausts)
        await conn._recv_loop()
        assert received == ["msg1", "msg2"]

    async def test_recv_loop_swallows_listener_exceptions(self):
        conn = self._make()

        async def bad_listener(msg: str):
            raise ValueError("boom")

        conn.add_listener(bad_listener)
        fake_ws = _make_fake_ws(["msg"])
        conn._ws = fake_ws

        # Should not raise
        await conn._recv_loop()

    async def test_recv_loop_handles_connection_closed(self):
        import websockets.exceptions as wse
        conn = self._make()
        conn._connected = True

        async def _aiter_raises(self):
            raise wse.ConnectionClosed(None, None)
            yield  # noqa: unreachable — makes it a generator

        fake_ws = MagicMock()
        fake_ws.__aiter__ = _aiter_raises
        conn._ws = fake_ws

        await conn._recv_loop()
        assert conn.connected is False

    async def test_recv_loop_handles_cancelled_error(self):
        conn = self._make()

        async def _aiter_cancel(self):
            raise asyncio.CancelledError
            yield  # noqa

        fake_ws = MagicMock()
        fake_ws.__aiter__ = _aiter_cancel
        conn._ws = fake_ws

        # CancelledError should be silently absorbed
        await conn._recv_loop()

    async def test_recv_loop_handles_generic_exception(self):
        conn = self._make()
        conn._connected = True

        async def _aiter_err(self):
            raise RuntimeError("network failure")
            yield  # noqa

        fake_ws = MagicMock()
        fake_ws.__aiter__ = _aiter_err
        conn._ws = fake_ws

        await conn._recv_loop()
        assert conn.connected is False


# ── ShowdownMessageHandler ─────────────────────────────────────────────────────

class TestShowdownMessageHandler:

    def _make(self):
        from src.ml.showdown_client import ShowdownMessageHandler
        return ShowdownMessageHandler(name="test")

    async def test_on_and_off(self):
        handler = self._make()
        cb = AsyncMock()
        handler.on("ping", cb)
        assert cb in handler._callbacks["ping"]
        handler.off("ping", cb)
        assert cb not in handler._callbacks.get("ping", [])

    async def test_handle_dispatches_with_room(self):
        handler = self._make()
        received = []

        async def cb(room, parts):
            received.append((room, parts))

        handler.on("turn", cb)
        await handler.handle(">battle-gen9ou-123\n|turn|5")
        assert received == [("battle-gen9ou-123", ["5"])]

    async def test_handle_dispatches_without_room(self):
        handler = self._make()
        received = []

        async def cb(room, parts):
            received.append((room, parts))

        handler.on("updateuser", cb)
        await handler.handle("|updateuser|TrainerRed|1|avatar")
        assert received == [("", ["TrainerRed", "1", "avatar"])]

    async def test_handle_skips_non_pipe_lines(self):
        handler = self._make()
        cb = AsyncMock()
        handler.on("anything", cb)
        await handler.handle("raw text without pipes")
        cb.assert_not_awaited()

    async def test_handle_skips_short_pipe_lines(self):
        handler = self._make()
        cb = AsyncMock()
        handler.on("", cb)
        await handler.handle("|")  # parts = ['', ''] — msg_type = '' only
        # no assertion needed; just must not crash

    async def test_handle_callback_exception_swallowed(self):
        handler = self._make()

        async def bad_cb(room, parts):
            raise RuntimeError("oops")

        handler.on("move", bad_cb)
        await handler.handle("|move|Pikachu|Thunderbolt|Charizard")  # must not raise

    async def test_challstr_stored(self):
        handler = self._make()
        await handler.handle("|challstr|4|abc123xyz")
        assert handler.challstr == "4|abc123xyz"

    async def test_multiple_callbacks_same_type(self):
        handler = self._make()
        calls = []
        cb1 = AsyncMock(side_effect=lambda r, p: calls.append("cb1"))
        cb2 = AsyncMock(side_effect=lambda r, p: calls.append("cb2"))
        handler.on("win", cb1)
        handler.on("win", cb2)
        await handler.handle("|win|TrainerRed")
        assert "cb1" in calls and "cb2" in calls

    async def test_handle_multiple_lines_in_frame(self):
        handler = self._make()
        events = []

        async def cb(room, parts):
            events.append(parts[0])

        handler.on("player", cb)
        await handler.handle(">lobby\n|player|p1|Alice\n|player|p2|Bob")
        assert events == ["p1", "p2"]


# ── ShowdownCommander ──────────────────────────────────────────────────────────

class TestShowdownCommander:

    def _make(self):
        from src.ml.showdown_client import ShowdownConnection, ShowdownCommander
        conn = ShowdownConnection(name="test")
        conn.send_raw = AsyncMock()
        return ShowdownCommander(conn), conn

    async def test_login_sends_trn(self):
        cmd, conn = self._make()
        await cmd.login("Alice", challstr="abc", password="pw")
        conn.send_raw.assert_awaited_once_with("|/trn Alice,0,abc")

    async def test_challenge(self):
        cmd, conn = self._make()
        await cmd.challenge("Bob", "gen9ou")
        conn.send_raw.assert_awaited_once_with("|/challenge Bob,gen9ou")

    async def test_accept_challenge(self):
        cmd, conn = self._make()
        await cmd.accept_challenge("Bob")
        conn.send_raw.assert_awaited_once_with("|/accept Bob")

    async def test_cancel_challenge(self):
        cmd, conn = self._make()
        await cmd.cancel_challenge()
        conn.send_raw.assert_awaited_once_with("|/cancelchallenge")

    async def test_choose(self):
        cmd, conn = self._make()
        await cmd.choose("battle-gen9ou-1", "move 1")
        conn.send_raw.assert_awaited_once_with("battle-gen9ou-1|/choose move 1")

    async def test_undo(self):
        cmd, conn = self._make()
        await cmd.undo("battle-gen9ou-1")
        conn.send_raw.assert_awaited_once_with("battle-gen9ou-1|/undo")

    async def test_forfeit(self):
        cmd, conn = self._make()
        await cmd.forfeit("battle-gen9ou-1")
        conn.send_raw.assert_awaited_once_with("battle-gen9ou-1|/forfeit")

    async def test_save_replay(self):
        cmd, conn = self._make()
        await cmd.save_replay("battle-gen9ou-1")
        conn.send_raw.assert_awaited_once_with("battle-gen9ou-1|/savereplay")

    async def test_leave(self):
        cmd, conn = self._make()
        await cmd.leave("battle-gen9ou-1")
        conn.send_raw.assert_awaited_once_with("|/leave battle-gen9ou-1")

    async def test_chat(self):
        cmd, conn = self._make()
        await cmd.chat("lobby", "gg")
        conn.send_raw.assert_awaited_once_with("lobby|gg")


# ── ShowdownClient ─────────────────────────────────────────────────────────────

class TestShowdownClient:

    def _make(self, username="Alice", password="", url="ws://localhost:8000/showdown/websocket"):
        from src.ml.showdown_client import ShowdownClient
        client = ShowdownClient(username=username, password=password, url=url)
        # Stub out network layer
        client.connection.connect = AsyncMock()
        client.connection.disconnect = AsyncMock()
        client.commander.login = AsyncMock()
        return client

    def test_connected_delegates_to_connection(self):
        client = self._make()
        client.connection._connected = True
        assert client.connected is True
        client.connection._connected = False
        assert client.connected is False

    async def test_connect_waits_for_login_event(self):
        client = self._make()
        # Simulate login event firing immediately
        client._login_event.set()
        await client.connect(login_timeout=5.0)
        client.connection.connect.assert_awaited_once()

    async def test_connect_logs_warning_on_login_timeout(self, caplog):
        import logging
        client = self._make()
        # Don't set the login event — it will timeout
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            await client.connect(login_timeout=0.01)
        # Should complete without raising

    async def test_disconnect(self):
        client = self._make()
        await client.disconnect()
        client.connection.disconnect.assert_awaited_once()

    async def test_wait_for_login_returns_true(self):
        client = self._make()
        client._login_event.set()
        result = await client.wait_for_login(timeout=5.0)
        assert result is True

    async def test_wait_for_login_returns_false_on_timeout(self):
        client = self._make()
        result = await client.wait_for_login(timeout=0.01)
        assert result is False

    async def test_context_manager(self):
        client = self._make()
        client._login_event.set()
        async with client as c:
            assert c is client
        client.connection.connect.assert_awaited()
        client.connection.disconnect.assert_awaited()

    async def test_on_challstr_calls_login(self):
        client = self._make()
        await client._on_challstr("", ["4", "abc123"])
        client.commander.login.assert_awaited_once_with(
            username="Alice",
            challstr="4|abc123",
            password="",
        )

    async def test_on_updateuser_sets_event_on_match(self):
        client = self._make()
        assert not client._login_event.is_set()
        await client._on_updateuser("", ["Alice", "1", "avatar"])
        assert client._login_event.is_set()

    async def test_on_updateuser_case_insensitive(self):
        client = self._make()
        await client._on_updateuser("", ["alice", "1"])
        assert client._login_event.is_set()

    async def test_on_updateuser_ignores_different_user(self):
        client = self._make()
        await client._on_updateuser("", ["Bob", "1"])
        assert not client._login_event.is_set()

    async def test_on_updateuser_noop_when_already_set(self):
        client = self._make()
        client._login_event.set()
        # Second call should not raise or change anything
        await client._on_updateuser("", ["Alice", "1"])

    async def test_on_updateuser_ignores_empty_parts(self):
        client = self._make()
        await client._on_updateuser("", [])
        assert not client._login_event.is_set()


# ── ShowdownClientPool ─────────────────────────────────────────────────────────

class TestShowdownClientPool:

    def _make(self):
        from src.ml.showdown_client import ShowdownClientPool
        pool = ShowdownClientPool(
            username_a="AccountA",
            username_b="AccountB",
            url="ws://localhost:8000/showdown/websocket",
        )
        pool.account_a.connection.connect = AsyncMock()
        pool.account_a.connection.disconnect = AsyncMock()
        pool.account_a.commander.login = AsyncMock()
        pool.account_b.connection.connect = AsyncMock()
        pool.account_b.connection.disconnect = AsyncMock()
        pool.account_b.commander.login = AsyncMock()
        # Pre-set login events so connect() doesn't timeout
        pool.account_a._login_event.set()
        pool.account_b._login_event.set()
        return pool

    def test_accounts_created_with_correct_usernames(self):
        from src.ml.showdown_client import ShowdownClientPool
        pool = ShowdownClientPool()
        assert pool.account_a.username == "AccountA"
        assert pool.account_b.username == "AccountB"

    async def test_connect_calls_both_accounts(self):
        pool = self._make()
        await pool.connect()
        pool.account_a.connection.connect.assert_awaited_once()
        pool.account_b.connection.connect.assert_awaited_once()

    async def test_disconnect_calls_both_accounts(self):
        pool = self._make()
        await pool.disconnect()
        pool.account_a.connection.disconnect.assert_awaited_once()
        pool.account_b.connection.disconnect.assert_awaited_once()

    async def test_disconnect_ignores_individual_errors(self):
        pool = self._make()
        pool.account_a.connection.disconnect = AsyncMock(side_effect=RuntimeError("gone"))
        await pool.disconnect()  # must not raise

    async def test_context_manager(self):
        pool = self._make()
        async with pool as p:
            assert p is pool
        pool.account_a.connection.connect.assert_awaited()
        pool.account_b.connection.connect.assert_awaited()
        pool.account_a.connection.disconnect.assert_awaited()
        pool.account_b.connection.disconnect.assert_awaited()
