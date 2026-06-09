#!/usr/bin/env python3
"""
check_showdown_ws.py -- CI helper for train-models.yml

Verifies that a Pokemon Showdown server is reachable via WebSocket at
ws://localhost:8000/showdown/websocket.

poke-env communicates over WebSocket only -- a successful HTTP health check
is not sufficient to confirm that battles can be started.  This script
connects and waits for the server's initial challenge message, then exits 0.

Usage:
    python3 scripts/check_showdown_ws.py
"""
import asyncio
import sys

try:
    import websockets
except ImportError:
    print("ERROR: websockets package is not installed. Run: pip install websockets", file=sys.stderr)
    sys.exit(1)


URI = "ws://localhost:8000/showdown/websocket"
OPEN_TIMEOUT = 10
RECV_TIMEOUT = 15


async def check() -> None:
    try:
        async with websockets.connect(URI, open_timeout=OPEN_TIMEOUT) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT)
            print(f"WebSocket OK -- server challenge received ({len(str(msg))} bytes): {str(msg)[:80]}")
    except ConnectionRefusedError:
        print(f"ERROR: WebSocket connection refused at {URI}", file=sys.stderr)
        sys.exit(1)
    except asyncio.TimeoutError:
        print(f"ERROR: WebSocket timed out waiting for server challenge at {URI}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: WebSocket check failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(check())
