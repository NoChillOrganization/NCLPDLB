"""
SHOWDOWN_MODE constants and server-configuration factory.

Modes
-----
  localhost  — ws://127.0.0.1:8000  (default; requires local Node.js server)
  showdown   — wss://sim3.psim.us   (public server; requires 2 Showdown accounts)
  browser    — Playwright-driven battles on play.pokemonshowdown.com

Named accounts (localhost self-play)
-------------------------------------
  ACCOUNT_A / ACCOUNT_B — default guest names used when no credentials are set.
  Override via env vars SHOWDOWN_TRAIN_USER1/2 + SHOWDOWN_TRAIN_PASS1/2.

Usage
-----
  cfg = server_config_for_mode("showdown")          # → ShowdownServerConfiguration
  acc1, acc2 = account_configs_for_mode("showdown") # → (AccountConfiguration, AccountConfiguration)
  pool = client_pool_for_mode("localhost")          # → ShowdownClientPool
"""
from __future__ import annotations

MODE_LOCALHOST = "localhost"
MODE_SHOWDOWN  = "showdown"
MODE_BROWSER   = "browser"
VALID_MODES    = (MODE_LOCALHOST, MODE_SHOWDOWN, MODE_BROWSER)

# Default guest account names for local self-play (no-security server)
ACCOUNT_A = "AccountA"
ACCOUNT_B = "AccountB"
LOCAL_WS_URL = "ws://localhost:8000/showdown/websocket"


def server_config_for_mode(mode: str):
    """Return the poke-env ServerConfiguration for the given mode (localhost or showdown)."""
    from poke_env.ps_client.server_configuration import (
        LocalhostServerConfiguration, ShowdownServerConfiguration,
    )
    if mode == MODE_SHOWDOWN:
        return ShowdownServerConfiguration
    return LocalhostServerConfiguration   # localhost OR browser both use local initially


def account_configs_for_mode(mode: str) -> tuple:
    """
    Return (account1, account2) AccountConfiguration for self-play.
    For localhost: returns (None, None) — poke-env auto-assigns guest names.
    For showdown: reads SHOWDOWN_TRAIN_USER1/2 + SHOWDOWN_TRAIN_PASS1/2 from env.
    """
    import os
    from poke_env.ps_client.account_configuration import AccountConfiguration
    if mode == MODE_SHOWDOWN:
        u1 = os.environ.get("SHOWDOWN_TRAIN_USER1", "")
        p1 = os.environ.get("SHOWDOWN_TRAIN_PASS1", "")
        u2 = os.environ.get("SHOWDOWN_TRAIN_USER2", "")
        p2 = os.environ.get("SHOWDOWN_TRAIN_PASS2", "")
        if not all([u1, p1, u2, p2]):
            raise ValueError(
                "Public Showdown training requires 4 env vars: "
                "SHOWDOWN_TRAIN_USER1, SHOWDOWN_TRAIN_PASS1, "
                "SHOWDOWN_TRAIN_USER2, SHOWDOWN_TRAIN_PASS2"
            )
        return AccountConfiguration(u1, p1), AccountConfiguration(u2, p2)
    return None, None


def client_pool_for_mode(mode: str):
    """
    Return a ShowdownClientPool configured for the given mode.

    For localhost: uses ACCOUNT_A / ACCOUNT_B guest names.
    For showdown: reads credentials from env vars.

    Returns:
        ShowdownClientPool ready to connect().
    """
    import os
    from src.ml.showdown_client import ShowdownClientPool

    if mode == MODE_SHOWDOWN:
        u1 = os.environ.get("SHOWDOWN_TRAIN_USER1", ACCOUNT_A)
        p1 = os.environ.get("SHOWDOWN_TRAIN_PASS1", "")
        u2 = os.environ.get("SHOWDOWN_TRAIN_USER2", ACCOUNT_B)
        p2 = os.environ.get("SHOWDOWN_TRAIN_PASS2", "")
        return ShowdownClientPool(
            username_a=u1, password_a=p1,
            username_b=u2, password_b=p2,
            url="wss://sim3.psim.us/showdown/websocket",
        )

    # localhost / browser
    return ShowdownClientPool(
        username_a=ACCOUNT_A,
        username_b=ACCOUNT_B,
        url=LOCAL_WS_URL,
    )
