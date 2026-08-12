"""
Training building blocks for train_policy.py: BC pre-training helpers, the
transformer feature extractor, the Dict->Box observation unwrapper, the
self-play curriculum callback, and the opponent player wrappers it swaps in.

Extracted from train_policy.py (which had grown past the project's
800-line guideline) — train()/evaluate()/CLI parsing stay in train_policy.py
and import these pieces from here.
"""

from __future__ import annotations

import logging
import socket
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

# ── Dependency guards (mirrors train_policy.py's own guards — duplicated
# rather than imported to avoid a circular import between the two modules) ──

try:  # pragma: no cover
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
    import torch as _torch
    import gymnasium as _gym

    SB3_OK = True
except ImportError:  # pragma: no cover
    SB3_OK = False
    PPO = None  # type: ignore
    BaseFeaturesExtractor = object  # type: ignore

    class BaseCallback:  # type: ignore
        """Stub so class definitions below don't crash when SB3 is absent."""

        def __init__(self, verbose: int = 0) -> None:
            self.verbose = verbose
            self.model: object = None
            self.num_timesteps: int = 0
            self.locals: dict = {}

        def _on_step(self) -> bool:
            return True


try:
    from poke_env.player import MaxBasePowerPlayer, RandomPlayer

    POKE_ENV_OK = True
except ImportError:  # pragma: no cover
    POKE_ENV_OK = False

from src.ml.showdown_modes import MODE_LOCALHOST  # noqa: E402

try:
    from src.data.learning_sheets import learning_sheets as _learning_sheets

    _SHEETS_OK = True
except Exception:  # pragma: no cover
    _learning_sheets = None  # type: ignore
    _SHEETS_OK = False

from src.ml.battle_env import (  # noqa: E402
    POKE_ENV_AVAILABLE,
    build_doubles_observation,
    build_observation,
)

SHOWDOWN_HOST = "127.0.0.1"
SHOWDOWN_PORT = 8000
DEFAULT_SWAP_EVERY = (
    50_000  # steps between opponent model swaps — mirrors train_policy.py
)
N_MAX_EPOCH0_STEPS = (
    2_000_000  # force-graduate after this many warmup steps — mirrors train_policy.py
)


def _check_showdown_server() -> None:
    """Raise RuntimeError if the local Showdown server is not reachable."""
    try:
        with socket.create_connection((SHOWDOWN_HOST, SHOWDOWN_PORT), timeout=3):
            pass
    except OSError:
        raise RuntimeError(
            f"Cannot reach local Showdown server at {SHOWDOWN_HOST}:{SHOWDOWN_PORT}.\n"
            "Start it with:\n"
            "  cd pokemon-showdown && node pokemon-showdown start --no-security\n"
            "See scripts/setup_showdown_server.md for full instructions."
        )


def _check_showdown_server_if_local(server: str) -> None:
    """Run server reachability check only for localhost mode."""
    if server == MODE_LOCALHOST:
        _check_showdown_server()


def _log_meta_context(fmt: str, meta_path: str | None) -> None:
    """Log competitive meta context (usage leaders, archetypes) before training.

    Reads data/competitive/format_meta.json when meta_path is provided.
    Pure logging — does not alter training behaviour.
    """
    if not meta_path:
        return
    import json as _json

    meta_file = Path(meta_path) / "format_meta.json"
    if not meta_file.exists():
        log.info(
            f"[meta] No format_meta.json found in {meta_path} — skipping context log"
        )
        return
    try:
        data = _json.loads(meta_file.read_text())
    except Exception as exc:
        log.warning(f"[meta] Could not read format_meta.json: {exc}")
        return
    entry = data.get(fmt)
    if not entry:
        log.info(f"[meta] No meta entry for {fmt!r}")
        return
    top10 = entry.get("top10_usage", [])
    if top10:
        names = ", ".join(r["pokemon"] for r in top10[:10])
        log.info(f"[meta] {fmt} — top usage: {names}")
    archetypes = entry.get("archetypes", [])
    for arch in archetypes[:4]:
        label = arch.get("archetype", arch.get("style", "?"))
        core = arch.get("core_pokemon", arch.get("restricted", ""))
        log.info(f"[meta] {fmt} archetype: {label} — {core}")


# ── BC pre-training helpers ────────────────────────────────────────────────────

# ent_coef schedule when --pretrain is used:
#   Steps 0–100k:    0.05 (higher entropy → more exploration after BC init)
#   Steps 100k–200k: linear anneal 0.05 → 0.01
#   Steps 200k+:     hold at 0.01
#
# SB3 passes `remaining_progress` to an ent_coef callable, where
#   remaining_progress = 1.0 at the very start, 0.0 at total_timesteps.
# We need total_timesteps to convert back to absolute step counts, so
# `make_bc_ent_coef_schedule` closes over that value.

_BC_ENT_HIGH = 0.05
_BC_ENT_LOW = 0.01
_BC_ENT_STEPS1 = 100_000  # hold high until this many steps
_BC_ENT_STEPS2 = 200_000  # finish anneal by this many steps


def make_bc_ent_coef_schedule(total_timesteps: int):
    """
    Return an ent_coef callable suitable for PPO's ``ent_coef`` parameter.

    SB3 calls ``ent_coef(remaining_progress)`` at each update, where
    ``remaining_progress`` decreases from 1.0 (start) to 0.0 (end).

    Schedule:
        0 – 100k steps  : 0.05
        100k – 200k     : linear anneal 0.05 → 0.01
        200k+           : 0.01
    """

    def _schedule(remaining_progress: float) -> float:
        step = (1.0 - remaining_progress) * total_timesteps
        if step <= _BC_ENT_STEPS1:
            return _BC_ENT_HIGH
        if step >= _BC_ENT_STEPS2:
            return _BC_ENT_LOW
        frac = (step - _BC_ENT_STEPS1) / (_BC_ENT_STEPS2 - _BC_ENT_STEPS1)
        return _BC_ENT_HIGH + frac * (_BC_ENT_LOW - _BC_ENT_HIGH)

    return _schedule


def _load_pretrain_weights(model: Any, checkpoint_path: str | Path) -> None:
    """
    Load actor-only weights from a BC checkpoint into a PPO model in-place.

    The checkpoint produced by ``pretrain.py`` contains only keys that do NOT
    start with ``value_net`` or ``mlp_extractor.value_net`` — i.e. the shared
    trunk (``mlp_extractor.policy_net.*``) and the action head (``action_net.*``).

    Any key present in the checkpoint but absent from the policy state dict is
    silently skipped (forward-compatibility).
    """
    try:
        import torch
    except ImportError as exc:  # pragma: no cover
        raise ImportError("torch is required for --pretrain weight loading") from exc

    checkpoint_path = Path(checkpoint_path)
    state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    policy_sd = model.policy.state_dict()
    loaded_keys: list[str] = []
    for k, v in state.items():
        if k in policy_sd:
            policy_sd[k] = v
            loaded_keys.append(k)
    model.policy.load_state_dict(policy_sd)
    log.info(
        "Loaded %d pretrained actor keys from %s",
        len(loaded_keys),
        checkpoint_path,
    )


# ── Transformer feature extractor ─────────────────────────────────────────────

if SB3_OK:

    class BattleTransformerExtractor(BaseFeaturesExtractor):
        """
        SB3-compatible features extractor backed by BattleTransformer's encoder.

        Wraps the transformer's input projection + positional encoding +
        encoder stack.  The policy and value *heads* remain SB3's standard
        linear layers — only the shared trunk is replaced.

        Output shape: (batch, d_model)  where d_model defaults to 64.
        """

        def __init__(
            self,
            observation_space: "_gym.Space",
            d_model: int = 64,
            n_heads: int = 4,
            n_layers: int = 2,
            ffn_dim: int = 128,
            dropout: float = 0.1,
        ) -> None:
            super().__init__(observation_space, features_dim=d_model)
            from src.ml.transformer_model import BattleTransformer

            obs_dim = observation_space.shape[0]
            self._transformer = BattleTransformer(
                obs_dim=obs_dim,
                n_actions=1,  # heads unused; only encoder is called
                d_model=d_model,
                n_heads=n_heads,
                n_layers=n_layers,
                ffn_dim=ffn_dim,
                dropout=dropout,
            )

        def forward(self, obs: "_torch.Tensor") -> "_torch.Tensor":
            # obs: (batch, obs_dim) — SB3 flat vector format
            x = obs.unsqueeze(1)  # (batch, 1, obs_dim)
            x = self._transformer.input_proj(x)  # (batch, 1, d_model)
            x = self._transformer.pos_enc(x)  # add positional encoding
            x = self._transformer.encoder(x)  # (batch, 1, d_model)
            return x[:, -1, :]  # (batch, d_model)
else:  # pragma: no cover

    class BattleTransformerExtractor:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "stable-baselines3 is required for BattleTransformerExtractor"
            )


# ── Dict → Box observation unwrapper ───────────────────────────────────────────

if SB3_OK:

    class _UnwrapDictObs(_gym.ObservationWrapper):
        """poke-env 0.15+ wraps env observations in Dict{action_mask, observation};
        SB3's MlpPolicy requires the flat Box the rest of this module assumes
        (BattleTransformerExtractor, checkpoint loading, inference obs-dim guard).
        Extract 'observation' and pass flat arrays through unchanged — the
        terminal-obs fast path in battle_env.py's step() override returns a bare
        ndarray (not a dict) when a battle ends mid-rollout.
        """

        def __init__(self, env: Any) -> None:
            super().__init__(env)
            space = env.observation_space
            if isinstance(space, _gym.spaces.Dict) and "observation" in space.spaces:
                self.observation_space = space.spaces["observation"]

        def observation(self, obs: Any) -> Any:
            return obs["observation"] if isinstance(obs, dict) else obs

else:  # pragma: no cover

    class _UnwrapDictObs:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("gymnasium/stable-baselines3 required for _UnwrapDictObs")


# ── Curriculum callback ───────────────────────────────────────────────────────

from collections import deque  # noqa: E402 (after SB3 guard)


class CurriculumCallback(BaseCallback):
    """
    Two-phase training curriculum:

    Phase 1 — warmup:
        Opponent is a CurriculumOpponent whose policy is None, so it acts like
        MaxBasePowerPlayer.  We track episode outcomes in a rolling window.
        Once the agent reaches `win_threshold` win-rate over `min_episodes`
        consecutive episodes, we save the first checkpoint and signal the
        opponent to switch to PPO play (``_graduate()``).

    Phase 2 — selfplay:
        Every `swap_every` steps we save a new checkpoint and reload it into
        the opponent, keeping a rolling-lag opponent.
    """

    def __init__(
        self,
        opponent_player,
        save_dir: Path,
        fmt: str = "",
        swap_every: int = DEFAULT_SWAP_EVERY,
        win_threshold: float = 0.70,
        min_episodes: int = 500,
        mean_type_eff_threshold: float = 1.2,
        min_type_eff_samples: int = 200,
        n_max_epoch0_steps: int = N_MAX_EPOCH0_STEPS,
        verbose: int = 0,
    ) -> None:
        super().__init__(verbose=verbose)
        self.opponent_player = opponent_player
        self.save_dir = save_dir
        self.fmt = fmt
        self.swap_every = swap_every
        self.win_threshold = win_threshold
        self.min_episodes = min_episodes
        self.mean_type_eff_threshold = mean_type_eff_threshold
        self.min_type_eff_samples = min_type_eff_samples
        self.n_max_epoch0_steps = n_max_epoch0_steps

        self._phase = "warmup"
        self._win_window: deque = deque(maxlen=min_episodes)
        self._type_eff_window: deque = deque(maxlen=min_type_eff_samples)
        self._last_swap = 0
        self._swap_count = 0
        self._action_counts: dict[int, int] = {}
        self._action_total = 0

    # ── helpers ───────────────────────────────────────────────────

    def _should_graduate(self) -> bool:
        """Return True when both graduation metrics are satisfied."""
        if len(self._win_window) < self.min_episodes:
            return False
        win_rate = sum(self._win_window) / len(self._win_window)
        if win_rate < self.win_threshold:
            return False
        # Secondary metric only enforced once enough type_eff data is collected.
        if len(self._type_eff_window) >= self.min_type_eff_samples:
            mean_eff = sum(self._type_eff_window) / len(self._type_eff_window)
            if mean_eff < self.mean_type_eff_threshold:
                return False
        return True

    def _track_step_type_eff(self) -> None:
        """Append the raw type-effectiveness multiplier for the chosen move to the rolling window."""
        from src.ml.battle_env import MOVE_TYPE_EFF_OBS_IDXS

        obs_tensor = self.locals.get("obs_tensor")
        actions = self.locals.get("actions")
        if obs_tensor is None or actions is None:
            return
        try:
            obs_np = (
                obs_tensor.detach().cpu().numpy()
                if hasattr(obs_tensor, "detach")
                else np.asarray(obs_tensor)
            )
            for i, a in enumerate(np.asarray(actions).flatten()):
                action = int(a)
                if 6 <= action <= 25:  # move action (not a switch)
                    move_slot = (action - 6) % 4
                    eff_obs_val = float(obs_np[i, MOVE_TYPE_EFF_OBS_IDXS[move_slot]])
                    # Convert log2-normalized value to raw damage multiplier.
                    # eff_obs ∈ [-1, 1] → mult = 2^(eff_obs × 2)
                    raw_mult = 2.0 ** (eff_obs_val * 2.0)
                    self._type_eff_window.append(raw_mult)
        except Exception:
            pass

    def _check_policy_collapse(self) -> None:
        """Warn if a single action dominates > 80 % of steps in the last check window."""
        actions = self.locals.get("actions")
        if actions is None:
            return
        try:
            for a in np.asarray(actions).flatten():
                action = int(a)
                self._action_counts[action] = self._action_counts.get(action, 0) + 1
                self._action_total += 1
        except Exception:
            return

        if self._action_total >= 1000:
            max_freq = max(self._action_counts.values()) / self._action_total
            if max_freq > 0.8:
                log.warning(
                    "[PolicyCollapse] Action distribution concentrated: top action = %.1f%% "
                    "of all steps at timestep %d — possible policy collapse.",
                    max_freq * 100,
                    self.num_timesteps,
                )
            # Reset counters for the next check window.
            self._action_counts = {}
            self._action_total = 0

    def _graduate(self) -> None:
        """Save first checkpoint and promote opponent to self-play mode."""
        self._swap_count += 1
        ckpt = self.save_dir / f"swap_{self._swap_count:04d}.zip"
        latest = self.save_dir / "latest.zip"
        self.model.save(str(ckpt))
        self.model.save(str(latest))
        self.opponent_player.load_policy(latest)
        self._phase = "selfplay"
        self._last_swap = self.num_timesteps
        win_rate = (
            sum(self._win_window) / len(self._win_window) if self._win_window else 0.0
        )
        if self.verbose:
            mean_eff = (
                sum(self._type_eff_window) / len(self._type_eff_window)
                if self._type_eff_window
                else float("nan")
            )
            log.info(
                "[Curriculum] Graduated to self-play at step %d "
                "(win-rate=%.1f%%, mean_type_eff=%.3f)",
                self.num_timesteps,
                win_rate * 100,
                mean_eff,
            )
        if _SHEETS_OK and _learning_sheets:
            _learning_sheets.save_training_run(
                {
                    "format": self.fmt,
                    "phase": "graduated",
                    "checkpoint": ckpt.name,
                    "training_step": self.num_timesteps,
                    "win_rate": f"{win_rate:.4f}",
                    "episodes": len(self._win_window),
                    "mean_reward": "",
                    "notes": "warmup → self-play",
                }
            )

    def _save_and_swap(self) -> None:
        """Save a self-play checkpoint and reload into the opponent."""
        self._swap_count += 1
        ckpt = self.save_dir / f"swap_{self._swap_count:04d}.zip"
        latest = self.save_dir / "latest.zip"
        self.model.save(str(ckpt))
        self.model.save(str(latest))
        self.opponent_player.load_policy(latest)
        win_rate = (
            sum(self._win_window) / len(self._win_window) if self._win_window else 0.0
        )
        if self.verbose:
            log.info(
                f"[Curriculum] Swap #{self._swap_count} at step "
                f"{self.num_timesteps}: saved {ckpt.name}"
            )
        if _SHEETS_OK and _learning_sheets:
            _learning_sheets.save_training_run(
                {
                    "format": self.fmt,
                    "phase": "selfplay",
                    "checkpoint": ckpt.name,
                    "training_step": self.num_timesteps,
                    "win_rate": f"{win_rate:.4f}",
                    "episodes": len(self._win_window),
                    "mean_reward": "",
                    "notes": f"swap #{self._swap_count}",
                }
            )

    # ── main hook ─────────────────────────────────────────────────

    def _on_step(self) -> bool:
        # Collect episode outcomes from the info dicts SB3 provides each step.
        for info in self.locals.get("infos", []):
            ep = info.get("episode")
            if ep is not None:
                self._win_window.append(1 if ep["r"] > 0 else 0)

        self._track_step_type_eff()
        self._check_policy_collapse()

        if self._phase == "warmup":
            if self.num_timesteps >= self.n_max_epoch0_steps:
                win_rate = (
                    sum(self._win_window) / len(self._win_window)
                    if self._win_window
                    else 0.0
                )
                log.warning(
                    "forced graduation after %d steps — win rate %.2f%% below threshold",
                    self.num_timesteps,
                    win_rate * 100,
                )
                self._graduate()
            elif self._should_graduate():
                self._graduate()
        else:  # selfplay
            if self.num_timesteps - self._last_swap >= self.swap_every:
                self._save_and_swap()
                self._last_swap = self.num_timesteps

        return True


# ── Opponent wrapper ──────────────────────────────────────────────────────────

if POKE_ENV_AVAILABLE and POKE_ENV_OK:

    class SelfPlayOpponent(RandomPlayer):
        """
        poke-env player that uses a frozen PPO policy to choose moves.
        Falls back to random play until a policy is loaded.
        Supports both singles and doubles battle formats.
        """

        def __init__(
            self, *args: Any, is_doubles: bool = False, **kwargs: Any
        ) -> None:  # pragma: no cover
            super().__init__(*args, **kwargs)
            self._policy: "PPO | None" = None
            self._is_doubles = is_doubles

        def load_policy(self, path: Path) -> None:  # pragma: no cover
            if not SB3_OK:
                return
            try:
                self._policy = PPO.load(str(path))
                log.info(f"[Opponent] Loaded policy from {path}")
            except Exception as exc:
                log.warning(f"[Opponent] Failed to load policy: {exc}")
                self._policy = None

        def choose_move(self, battle: Any) -> Any:  # pragma: no cover
            if self._policy is None:
                return self.choose_random_move(battle)
            try:
                if self._is_doubles:
                    obs = build_doubles_observation(battle).reshape(1, -1)
                    action, _ = self._policy.predict(obs, deterministic=False)
                    from poke_env.environment.doubles_env import DoublesEnv

                    return DoublesEnv.action_to_order(int(action[0]), battle)
                else:
                    obs = build_observation(battle).reshape(1, -1)
                    action, _ = self._policy.predict(obs, deterministic=False)
                    from poke_env.environment.singles_env import SinglesEnv

                    return SinglesEnv.action_to_order(int(action[0]), battle)
            except Exception as exc:
                log.warning(f"[Opponent] Prediction error: {exc}")
                return self.choose_random_move(battle)

    class CurriculumOpponent(MaxBasePowerPlayer):
        """
        poke-env player used during curriculum training.

        Phase 0 (policy is None): delegates to MaxBasePowerPlayer for move
        selection, giving the agent a stronger-than-random baseline to learn
        against while still being beatable.

        Phase 1 (policy loaded): acts like SelfPlayOpponent — uses the frozen
        PPO checkpoint to pick moves.
        """

        def __init__(
            self, *args: Any, is_doubles: bool = False, **kwargs: Any
        ) -> None:  # pragma: no cover
            super().__init__(*args, **kwargs)
            self._policy: "PPO | None" = None
            self._is_doubles = is_doubles

        def load_policy(self, path: Path) -> None:  # pragma: no cover
            if not SB3_OK:
                return
            try:
                self._policy = PPO.load(str(path))
                log.info(f"[CurriculumOpponent] Loaded policy from {path}")
            except Exception as exc:
                log.warning(f"[CurriculumOpponent] Failed to load policy: {exc}")
                self._policy = None

        def choose_move(self, battle: Any) -> Any:  # pragma: no cover
            if self._policy is None:
                return super().choose_move(battle)  # MaxBasePower behaviour
            try:
                if self._is_doubles:
                    obs = build_doubles_observation(battle).reshape(1, -1)
                    action, _ = self._policy.predict(obs, deterministic=False)
                    from poke_env.environment.doubles_env import DoublesEnv

                    return DoublesEnv.action_to_order(int(action[0]), battle)
                else:
                    obs = build_observation(battle).reshape(1, -1)
                    action, _ = self._policy.predict(obs, deterministic=False)
                    from poke_env.environment.singles_env import SinglesEnv

                    return SinglesEnv.action_to_order(int(action[0]), battle)
            except Exception as exc:
                log.warning(f"[CurriculumOpponent] Prediction error: {exc}")
                return super().choose_move(battle)

else:  # pragma: no cover

    class SelfPlayOpponent:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("poke-env is not available")

    class CurriculumOpponent:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("poke-env is not available")
