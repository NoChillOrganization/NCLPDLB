"""
Playwright-driven browser training — DISABLED (offline learning not implemented).

The browser path scrapes battle state from play.pokemonshowdown.com's DOM and
*could* feed a policy, but PPO is on-policy: replaying recorded (obs, action)
transitions through it is a no-op (it samples its own random actions and ignores
the data). Until behaviour cloning (supervised cross-entropy on the actor head)
or an off-policy algorithm exists, ``train_browser`` raises immediately rather
than burning a full browser session to produce an untrained model.

``build_observation_from_dom`` is kept — it's the working DOM scraper that a
future behaviour-cloning implementation will build on.

ponytail: the PPO/Playwright self-play loop, _ReplayEnv, and the DOM action
helpers were removed (they only fed the no-op learner). git history has them
when BC work starts. Track: TODO(H16).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import numpy as np

log = logging.getLogger(__name__)

SHOWDOWN_URL        = "https://play.pokemonshowdown.com"
DEFAULT_SAVE_DIR    = "data/ml/policy"
DEFAULT_RESULTS_DIR = "data/ml/results"


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


def train_browser(  # pragma: no cover
    fmt: str,
    total_timesteps: int,
    save_dir: Path | None = None,
    results_dir: Path | None = None,
    headless: bool | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> Path:
    """Browser training entry point — currently disabled (see module docstring).

    Fails fast so callers get a clear error instead of running a full browser
    session and receiving an untrained model. Signature is preserved so the
    train_policy dispatch path keeps importing/calling it unchanged.
    """
    # ponytail: fail at entry, not after a wasted session. Re-implement the
    # play+learn loop here once behaviour cloning lands. Track: TODO(H16).
    raise NotImplementedError(
        "[browser_trainer] Offline learning not yet implemented. "
        "PPO on-policy replay is a no-op — it samples its own random actions and "
        "ignores recorded DOM transitions. Implement behaviour cloning on the "
        "actor head (supervised cross-entropy) before using browser-mode training. "
        "Track: TODO(H16)."
    )
