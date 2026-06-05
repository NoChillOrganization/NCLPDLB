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
DEFAULT_RESULTS_DIR = "data/ml/results"


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

    This is a *sparse*, best-effort DOM scrape.  Only a handful of dims are
    populated; the rest stay at 0.  It is inherently less precise than the
    WebSocket path (battle_env.build_observation).

    Obs-space layout reference (battle_env.OBS_DIM = 78):
      [0]         active species_id (not available via DOM — left 0)
      [1]         active HP fraction (own)
      [2..21]     move feats: 4 × (base_power, accuracy, type_id, priority, eff)
                  We set obs[2 + 5*i] = 1.0 as "move available" proxy for slot i
      [22]        status (not available via DOM — left 0)
      [23..28]    boosts (not available via DOM — left 0)
      [29]        opp species_id (not available via DOM — left 0)
      [30]        opp active HP fraction
      [31..43]    opp status + team HPs (not available — left 0)
      [44..46]    weather/terrain/trick_room (not available — left 0)
      [47]        turn / 100.0 (clamped)
      [48..77]    STAB/speed/ability/item buckets (not available — left 0)
    """
    from src.ml.battle_env import OBS_DIM

    obs = np.zeros(OBS_DIM, dtype=np.float32)

    try:
        # ── Active Pokémon HP (own, obs[1]) ──────────────────────────
        hp_els = page.locator(".hpbar .hptext")
        hp_count = hp_els.count()
        if hp_count:
            hp_text = hp_els.nth(0).inner_text()  # e.g. "72/100"
            parts = hp_text.replace("%", "").split("/")
            if len(parts) == 2:
                obs[1] = float(parts[0]) / max(float(parts[1]), 1)  # fraction

        # ── Active Pokémon HP (opponent, obs[30]) ─────────────────────
        if hp_count >= 2:
            hp_text = hp_els.nth(1).inner_text()
            parts = hp_text.replace("%", "").split("/")
            if len(parts) == 2:
                obs[30] = float(parts[0]) / max(float(parts[1]), 1)

        # ── Turn number (obs[47]) ─────────────────────────────────────
        turn_el = page.locator(".turn")
        if turn_el.count():
            try:
                obs[47] = float(turn_el.first.inner_text().split()[-1]) / 100.0
            except Exception:
                pass

        # ── Move availability (obs[2], [7], [12], [17]) — presence proxy
        # Each move slot starts at obs[2 + 5*i]; we set base_power to 1.0
        # as a binary "this move exists" signal (no DOM-accessible PP/power).
        move_btns = page.locator("button.move")
        for i in range(min(move_btns.count(), 4)):
            obs[2 + 5 * i] = 1.0

    except Exception as exc:
        log.debug(f"[browser_trainer] DOM read error (non-fatal): {exc}")

    return obs


def _pick_move_from_obs(  # pragma: no cover
    page: Any,
    obs: np.ndarray,
    policy: Any | None,
) -> None:
    """
    Choose and click a move or switch button.

    Decodes the 26-action space (same as BattleEnv):
      0-5   → switch to bench slot
      6-25  → move (with optional gimmick; gimmick ignored in DOM)
    """
    from src.ml.battle_env import N_ACTIONS_GEN9

    move_btns   = page.locator("button.move:not([disabled])")
    switch_btns = page.locator("button.switch:not([disabled])")
    n_moves   = move_btns.count()
    n_switches = switch_btns.count()

    if n_moves == 0 and n_switches == 0:
        return  # nothing clickable (waiting for opponent)

    if policy is not None:
        try:
            action, _ = policy.predict(obs.reshape(1, -1), deterministic=False)
            action_idx = int(action[0])
        except Exception:
            action_idx = 6  # default: first move
    else:
        import random
        action_idx = random.randrange(N_ACTIONS_GEN9)

    if action_idx <= 5:
        # Switch action — click bench slot if available, else fall through to move
        if n_switches > 0:
            switch_btns.nth(action_idx % n_switches).click()
            return
        # No bench available — fall through to move
        action_idx = 6

    # Move action: 6-9=move, 10-13=mega, 14-17=zmove, 18-21=dyna, 22-25=tera
    # DOM doesn't expose gimmick toggles reliably — map to base move slot (0-3)
    move_slot = (action_idx - 6) % 4
    if n_moves > 0:
        move_btns.nth(move_slot % n_moves).click()


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


class _ReplayEnv:
    """Replays (obs, reward, done) transitions from browser self-play for SB3 learn()."""

    def __init__(self, transitions: list) -> None:
        from gymnasium import spaces
        from src.ml.battle_env import OBS_DIM, N_ACTIONS_GEN9
        # Match real env bounds: low=-1.0 (intimidate/status), high=2.0 (choicescarf speed)
        self.observation_space = spaces.Box(low=-1.0, high=2.0, shape=(OBS_DIM,), dtype=np.float32)
        self.action_space = spaces.Discrete(N_ACTIONS_GEN9)
        self._transitions = list(transitions)
        self._idx = 0
        self._obs_dim = OBS_DIM

    def reset(self, **kwargs):
        self._idx = 0
        return np.zeros(self._obs_dim, dtype=np.float32), {}

    def step(self, action):
        if self._idx < len(self._transitions):
            obs, reward, done = self._transitions[self._idx]
            self._idx += 1
        else:
            obs = np.zeros(self._obs_dim, dtype=np.float32)
            reward = 0.0
            done = True
        return obs, reward, done, False, {}


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
    from src.ml.battle_env import OBS_DIM, N_ACTIONS_GEN9
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
        # Match real env bounds: low=-1.0 (intimidate/status), high=2.0 (choicescarf speed)
        observation_space = spaces.Box(
            low=-1.0, high=2.0, shape=(OBS_DIM,), dtype=np.float32
        )
        action_space = spaces.Discrete(N_ACTIONS_GEN9)

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
    all_transitions: list[tuple] = []

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
                transitions: list[tuple] = []
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
                        transitions.append((build_observation_from_dom(page1), reward, True))
                        break
                    if state == "timeout":
                        log.warning("[browser_trainer] Turn timed out, moving on")
                        rewards.append(0.0)
                        break

                    # Extract observation and choose action
                    obs = build_observation_from_dom(page1)
                    _pick_move_from_obs(page1, obs, policy)
                    transitions.append((obs.copy(), 0.0, False))
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
                all_transitions.extend(transitions)

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
                    if all_transitions:
                        n_trans = len(all_transitions)
                        # TODO(H16): PPO is on-policy — calling policy.learn() against
                        # _ReplayEnv causes PPO to sample its own random actions and
                        # ignore the recorded (obs, action) transitions entirely.  No
                        # learning happens from the replays.  A real offline update
                        # requires behaviour cloning (supervised cross-entropy on the
                        # actor head) or an off-policy algorithm (SAC, DQN).  Until
                        # that is implemented the transitions are discarded.
                        log.warning(
                            "[browser_trainer] %d transitions collected but NOT used for "
                            "offline learning — PPO on-policy replay is a no-op. "
                            "Implement behaviour cloning to enable offline updates.",
                            n_trans,
                        )
                        all_transitions.clear()

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
    if policy is not None and SB3_OK and all_transitions:
        n_trans = len(all_transitions)
        # TODO(H16): same PPO on-policy no-op as the periodic checkpoint path above.
        log.warning(
            "[browser_trainer] %d final transitions discarded — offline learning "
            "not yet implemented (PPO replay is a no-op; needs behaviour cloning).",
            n_trans,
        )
        all_transitions.clear()
    final_path = _results_dir / f"{fmt}_{start_date}.zip"
    if policy is not None and SB3_OK:
        policy.save(str(final_path))
        log.info(f"[browser_trainer] Final model saved to {final_path}")
    else:
        final_path.write_text("no-policy")
        log.warning("[browser_trainer] No policy trained (stable-baselines3 not available).")

    return final_path
