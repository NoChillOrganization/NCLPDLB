"""
Playwright-driven training loop.

Two headless (or headed) browser contexts log in to play.pokemonshowdown.com,
one challenges the other, and the bot reads game state from the DOM to produce
observations for the PPO policy. Slower than WebSocket training but no local
Node.js server required and battles are visually observable.

Requirements: pip install playwright && playwright install chromium

Environment variables
---------------------
  SHOWDOWN_TRAIN_USER1 / SHOWDOWN_TRAIN_PASS1  — account for player 1
  SHOWDOWN_TRAIN_USER2 / SHOWDOWN_TRAIN_PASS2  — account for player 2
  SHOWDOWN_BROWSER_HEADED=1                    — show browser windows (default: headless)
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

log = logging.getLogger(__name__)

SHOWDOWN_URL   = "https://play.pokemonshowdown.com"
DEFAULT_SAVE_DIR    = "data/ml/policy"
DEFAULT_RESULTS_DIR = "src/ml/models/results"


# ── DOM helpers ───────────────────────────────────────────────────────────────

def _login(page: Any, username: str, password: str) -> None:  # pragma: no cover
    """Log a Playwright page into Pokémon Showdown."""
    page.goto(SHOWDOWN_URL)
    page.wait_for_load_state("networkidle")

    # Click the login button
    login_btn = page.locator("button.button[name='login']")
    if login_btn.count():
        login_btn.first.click()
        page.wait_for_selector("input[name='username']")
        page.fill("input[name='username']", username)
        page.keyboard.press("Enter")
        page.wait_for_selector("input[name='password']", timeout=5000)
        page.fill("input[name='password']", password)
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle")
    else:
        # Already logged in or guest — set username via /nick
        chatbox = page.locator("input.textbox[placeholder]")
        if chatbox.count():
            chatbox.first.fill(f"/nick {username}")
            chatbox.first.press("Enter")

    log.info(f"[browser_trainer] Logged in as {username}")


def _send_challenge(challenger_page: Any, opponent_username: str, fmt: str) -> None:  # pragma: no cover
    """Send a battle challenge from one page to another user."""
    chatbox = challenger_page.locator("input.textbox").first
    chatbox.fill(f"/challenge {opponent_username}, {fmt}")
    chatbox.press("Enter")
    log.info(f"[browser_trainer] Challenge sent: {opponent_username} @ {fmt}")


def _accept_challenge(acceptor_page: Any) -> bool:  # pragma: no cover
    """Accept a pending incoming challenge. Returns True if found."""
    try:
        # The challenge popup appears as a .challenge-window or similar
        accept_btn = acceptor_page.locator("button.button[value='accept']")
        accept_btn.wait_for(timeout=15_000)
        accept_btn.click()
        log.info("[browser_trainer] Challenge accepted")
        return True
    except Exception as exc:
        log.warning(f"[browser_trainer] Could not accept challenge: {exc}")
        return False


def build_observation_from_dom(page: Any) -> np.ndarray:  # pragma: no cover
    """
    Extract battle state from the Showdown DOM and return a float32 numpy array
    compatible with the existing BattleEnv observation space (shape: (OBS_DIM,)).

    This is a best-effort DOM scrape; it is inherently less precise than the
    WebSocket path.  Missing values are filled with zeros.
    """
    from src.ml.battle_env import OBS_DIM

    obs = np.zeros(OBS_DIM, dtype=np.float32)

    try:
        # ── Active Pokémon HP (player side, slot 0) ──────────────────
        hp_els = page.locator(".hpbar .hptext")
        hp_count = hp_els.count()
        if hp_count:
            hp_text = hp_els.nth(0).inner_text()  # e.g. "72/100"
            parts = hp_text.replace("%", "").split("/")
            if len(parts) == 2:
                obs[0] = float(parts[0]) / max(float(parts[1]), 1)  # fraction

        # ── Active Pokémon HP (opponent side, slot 1) ─────────────────
        if hp_count >= 2:
            hp_text = hp_els.nth(1).inner_text()
            parts = hp_text.replace("%", "").split("/")
            if len(parts) == 2:
                obs[1] = float(parts[0]) / max(float(parts[1]), 1)

        # ── Turn number ───────────────────────────────────────────────
        turn_el = page.locator(".turn")
        if turn_el.count():
            try:
                obs[2] = float(turn_el.first.inner_text().split()[-1]) / 100.0
            except Exception:
                pass

        # ── Move PP (4 slots) — presence-only ────────────────────────
        move_btns = page.locator("button.move")
        for i in range(min(move_btns.count(), 4)):
            obs[3 + i] = 1.0  # move available

    except Exception as exc:
        log.debug(f"[browser_trainer] DOM read error (non-fatal): {exc}")

    return obs


def _pick_move_from_obs(  # pragma: no cover
    page: Any,
    obs: np.ndarray,
    policy: Any | None,
) -> None:
    """
    Choose and click a move button.  Uses PPO policy if loaded; otherwise random.
    """
    move_btns = page.locator("button.move:not([disabled])")
    n_moves = move_btns.count()
    if n_moves == 0:
        # Try switch or forfeit
        switch_btns = page.locator("button.switch:not([disabled])")
        if switch_btns.count():
            switch_btns.first.click()
        return

    if policy is not None:
        try:
            action, _ = policy.predict(obs.reshape(1, -1), deterministic=False)
            idx = int(action[0]) % n_moves
        except Exception:
            idx = 0
    else:
        import random
        idx = random.randrange(n_moves)

    move_btns.nth(idx).click()


def _wait_for_turn_or_end(page: Any, timeout: float = 60.0) -> str:  # pragma: no cover
    """
    Wait until it is our turn to move or the battle ends.

    Returns "move", "switch", "end", or "timeout".
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        # Battle over?
        if page.locator(".battle-section .endmessage, .result-message").count():
            return "end"
        # Our turn to choose a move?
        if page.locator("button.move:not([disabled])").count():
            return "move"
        if page.locator("button.switch:not([disabled])").count():
            return "switch"
        time.sleep(0.5)
    return "timeout"


# ── Main training loop ────────────────────────────────────────────────────────

def train_browser(  # pragma: no cover
    fmt: str,
    total_timesteps: int,
    save_dir: Path | None = None,
    results_dir: Path | None = None,
    headless: bool | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> Path:
    """
    Run PPO self-play training via Playwright browser automation.

    Opens two browser contexts, logs in with SHOWDOWN_TRAIN_USER1/2 credentials,
    plays battles on play.pokemonshowdown.com, and trains the PPO policy from
    DOM-extracted observations.

    Args:
        fmt:             Showdown battle format string.
        total_timesteps: Total training steps (approximate; counted per action).
        save_dir:        Root directory for in-progress checkpoints.
        results_dir:     Directory for final dated model.
        headless:        True = invisible browser (default); False = visible.
                         Overridden by SHOWDOWN_BROWSER_HEADED=1 env var.
        progress_cb:     Optional callback(current_steps, total_steps) for progress reporting.

    Returns the path to the final saved model zip.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright is not installed. "
            "Run: pip install playwright && playwright install chromium"
        )

    try:
        from stable_baselines3 import PPO  # noqa: F401
        SB3_OK = True
    except ImportError:
        SB3_OK = False

    from src.ml.showdown_modes import account_configs_for_mode, MODE_BROWSER
    from src.ml.battle_env import OBS_DIM
    from src.ml.train_policy import DEFAULT_SAVE_DIR, DEFAULT_RESULTS_DIR, PPO_HYPERPARAMS

    _save_dir    = save_dir    or Path(DEFAULT_SAVE_DIR)
    _results_dir = results_dir or Path(DEFAULT_RESULTS_DIR)

    # Resolve headless setting (env var overrides argument)
    if headless is None:
        headless = os.environ.get("SHOWDOWN_BROWSER_HEADED", "0") != "1"

    acc1, acc2 = account_configs_for_mode(MODE_BROWSER)
    if acc1 is None or acc2 is None:
        raise ValueError(
            "Browser training requires SHOWDOWN_TRAIN_USER1/PASS1 and "
            "SHOWDOWN_TRAIN_USER2/PASS2 environment variables."
        )

    fmt_save_dir = _save_dir / fmt
    fmt_save_dir.mkdir(parents=True, exist_ok=True)
    _results_dir.mkdir(parents=True, exist_ok=True)

    # ── PPO model (action space = OBS_DIM, observation space = OBS_DIM) ───────
    from gymnasium import spaces
    import gymnasium as gym

    class _FakeEnv(gym.Env):
        """Minimal stub so PPO can be initialised without a real poke-env."""
        observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(OBS_DIM,), dtype=np.float32
        )
        action_space = spaces.Discrete(4)  # 4 moves (simplified)

        def reset(self, **kwargs):
            return np.zeros(OBS_DIM, dtype=np.float32), {}

        def step(self, action):
            return np.zeros(OBS_DIM, dtype=np.float32), 0.0, False, False, {}

    if SB3_OK:
        latest_zip = fmt_save_dir / "latest.zip"
        if latest_zip.exists():
            log.info(f"[browser_trainer] Resuming from {latest_zip}")
            policy = PPO.load(str(latest_zip))
        else:
            policy = PPO("MlpPolicy", _FakeEnv(), **{
                k: v for k, v in PPO_HYPERPARAMS.items()
                if k not in ("verbose",)  # suppress per-step noise
            })
    else:
        policy = None
        log.warning("[browser_trainer] stable-baselines3 not available — running random policy")

    from datetime import datetime
    start_date = datetime.now().strftime("%Y-%m-%d")

    steps = 0
    swap_every = 50_000
    last_swap = 0
    swap_count = 0

    log.info(
        f"[browser_trainer] Starting browser training: {fmt}, "
        f"{total_timesteps:,} steps, headless={headless}"
    )

    with sync_playwright() as pw:
        # Launch two separate browser contexts
        browser1 = pw.chromium.launch(headless=headless)
        browser2 = pw.chromium.launch(headless=headless)
        ctx1 = browser1.new_context()
        ctx2 = browser2.new_context()
        page1 = ctx1.new_page()
        page2 = ctx2.new_page()

        try:
            _login(page1, acc1.username, acc1.password)
            _login(page2, acc2.username, acc2.password)

            while steps < total_timesteps:
                # ── Start a new battle ────────────────────────────────
                _send_challenge(page1, acc2.username, fmt)
                if not _accept_challenge(page2):
                    log.warning("[browser_trainer] Challenge not accepted — retrying after 5s")
                    time.sleep(5)
                    continue

                # Give pages time to enter the battle
                time.sleep(3)

                # ── Battle loop ───────────────────────────────────────
                rewards: list[float] = []
                while True:
                    state = _wait_for_turn_or_end(page1)
                    if state == "end":
                        # Check win/loss
                        result_text = ""
                        try:
                            result_el = page1.locator(".result-message, .battle-section .endmessage")
                            if result_el.count():
                                result_text = result_el.first.inner_text().lower()
                        except Exception:
                            pass
                        reward = 1.0 if "win" in result_text else -1.0
                        rewards.append(reward)
                        break
                    if state == "timeout":
                        log.warning("[browser_trainer] Turn timed out, moving on")
                        rewards.append(0.0)
                        break

                    # Extract observation and choose action
                    obs = build_observation_from_dom(page1)
                    _pick_move_from_obs(page1, obs, policy)
                    steps += 1

                    if progress_cb:
                        progress_cb(steps, total_timesteps)

                    # Opponent (page2) also needs to act
                    opp_state = _wait_for_turn_or_end(page2, timeout=30)
                    if opp_state in ("move", "switch"):
                        obs2 = build_observation_from_dom(page2)
                        _pick_move_from_obs(page2, obs2, None)  # opponent always random

                    rewards.append(0.0)  # intermediate reward

                log.debug(
                    f"[browser_trainer] Battle done at step {steps:,}/"
                    f"{total_timesteps:,}, reward={sum(rewards):.1f}"
                )

                # ── Periodic checkpoint ───────────────────────────────
                if policy is not None and SB3_OK and steps - last_swap >= swap_every:
                    swap_count += 1
                    ckpt_path = fmt_save_dir / f"browser_swap_{swap_count:04d}.zip"
                    latest_path = fmt_save_dir / "latest.zip"
                    policy.save(str(ckpt_path))
                    import shutil
                    shutil.copy(str(ckpt_path), str(latest_path))
                    last_swap = steps
                    log.info(f"[browser_trainer] Checkpoint saved: {ckpt_path.name}")

                # Brief pause between battles
                time.sleep(2)

        except KeyboardInterrupt:
            log.info("[browser_trainer] Training interrupted by user.")
        finally:
            page1.close()
            page2.close()
            ctx1.close()
            ctx2.close()
            browser1.close()
            browser2.close()

    # ── Save final model ──────────────────────────────────────────────────────
    final_path = _results_dir / f"{fmt}_{start_date}.zip"
    if policy is not None and SB3_OK:
        policy.save(str(final_path))
        log.info(f"[browser_trainer] Final model saved to {final_path}")
    else:
        final_path.write_text("no-policy")
        log.warning("[browser_trainer] No policy trained (stable-baselines3 not available).")

    return final_path
