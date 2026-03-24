"""
Train a battle policy using PPO + self-play via poke-env.

The agent learns to play Pokemon battles by competing against copies of
itself (self-play curriculum).  Every N steps the opponent is replaced
with the latest checkpoint so the agent always faces a challenging but
beatable opponent.

Architecture
────────────
  Observation : float32 vector of shape (OBS_DIM,) — see battle_env.py
  Action      : Discrete(26) for gen9 — see battle_env.py action map
  Algorithm   : PPO (Proximal Policy Optimization) via stable-baselines3
  Policy net  : MlpPolicy  64→64 hidden layers (configurable)

Self-play curriculum
────────────────────
  Epoch 0          : agent plays vs RandomPlayer baseline
  Epoch 1+         : agent plays vs latest saved checkpoint
  Every swap_every : checkpoint saved, opponent model reloaded

Requirements
────────────
  • A local Pokemon Showdown server on ws://localhost:8000
    (See scripts/setup_showdown_server.md)
  • pip install poke-env>=0.8.1 stable-baselines3>=2.2.0 tensorboard>=2.16.0

Usage
─────
  python -m src.ml.train_policy --format gen9randombattle --timesteps 500000
  python -m src.ml.train_policy --format gen9ou --timesteps 2000000 --swap-every 50000
  python -m src.ml.train_policy --eval-only data/ml/policy/gen9randombattle/best_model.zip
"""
from __future__ import annotations

import argparse
import logging
import shutil
import socket
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Dependency guards ─────────────────────────────────────────────────────────

try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv
    SB3_OK = True
except ImportError:
    SB3_OK = False

try:
    from poke_env.environment.single_agent_wrapper import SingleAgentWrapper
    from poke_env.player import RandomPlayer
    from poke_env.ps_client.server_configuration import LocalhostServerConfiguration
    POKE_ENV_OK = True
except ImportError:
    POKE_ENV_OK = False

from src.ml.showdown_modes import VALID_MODES, MODE_LOCALHOST, MODE_BROWSER
from src.ml.showdown_modes import server_config_for_mode, account_configs_for_mode

from src.ml.battle_env import (
    POKE_ENV_AVAILABLE,
    BattleDoubleEnv,
    BattleEnv,
    build_doubles_observation,
    build_observation,
)

# ── Constants ─────────────────────────────────────────────────────────────────

SHOWDOWN_HOST = "127.0.0.1"
SHOWDOWN_PORT = 8000


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


DEFAULT_FORMAT      = "gen9randombattle"
DEFAULT_TIMESTEPS   = 500_000
DEFAULT_SWAP_EVERY  = 50_000          # steps between opponent model swaps
DEFAULT_SAVE_DIR    = "data/ml/policy"
DEFAULT_RESULTS_DIR = "src/ml/models/results"

# Formats that use the doubles environment
DOUBLES_FORMATS = {
    # Smogon Doubles
    "gen9doublesou",
    "gen9randomdoublesbattle",
    "gen9doublesubers",
    "gen9doublesuu",
    "gen9doublesnu",
    # VGC 2025
    "gen9vgc2025regg",
    "gen9vgc2025regh",
    "gen9vgc2025regi",
    "gen9vgc2025reggbo3",
    "gen9vgc2025reghbo3",
    "gen9vgc2025regibo3",
    # VGC 2026
    "gen9vgc2026regf",
    "gen9vgc2026regi",
    "gen9vgc2026regfbo3",
    "gen9vgc2026regibo3",
}

PPO_HYPERPARAMS: dict[str, Any] = {
    "learning_rate"      : 3e-4,
    "n_steps"            : 2048,
    "batch_size"         : 64,
    "n_epochs"           : 10,
    "gamma"              : 0.99,
    "gae_lambda"         : 0.95,
    "clip_range"         : 0.2,
    "ent_coef"           : 0.01,
    "vf_coef"            : 0.5,
    "max_grad_norm"      : 0.5,
    "policy_kwargs"      : {"net_arch": [64, 64]},
    "verbose"            : 1,
}


# ── Self-play callback ────────────────────────────────────────────────────────

class SelfPlayCallback(BaseCallback):
    """
    Every `swap_every` steps:
      1. Save the latest agent weights to <save_dir>/latest.zip
      2. Signal the opponent player to reload from that checkpoint
    """

    def __init__(
        self,
        opponent_player: "SelfPlayOpponent",
        save_dir: Path,
        swap_every: int = DEFAULT_SWAP_EVERY,
        verbose: int = 0,
    ) -> None:
        super().__init__(verbose=verbose)
        self.opponent_player  = opponent_player
        self.save_dir         = save_dir
        self.swap_every       = swap_every
        self._last_swap       = 0
        self._swap_count      = 0

    def _on_step(self) -> bool:
        if self.num_timesteps - self._last_swap >= self.swap_every:
            self._save_and_swap()
            self._last_swap = self.num_timesteps
        return True

    def _save_and_swap(self) -> None:
        self._swap_count += 1
        ckpt_path = self.save_dir / f"swap_{self._swap_count:04d}.zip"
        latest_path = self.save_dir / "latest.zip"

        self.model.save(str(ckpt_path))
        shutil.copy(str(ckpt_path), str(latest_path))
        self.opponent_player.load_policy(latest_path)

        if self.verbose:
            log.info(
                f"[SelfPlay] Swap #{self._swap_count} at step "
                f"{self.num_timesteps}: saved {ckpt_path.name}"
            )


# ── Opponent wrapper ──────────────────────────────────────────────────────────

if POKE_ENV_AVAILABLE and POKE_ENV_OK:
    class SelfPlayOpponent(RandomPlayer):
        """
        poke-env player that uses a frozen PPO policy to choose moves.
        Falls back to random play until a policy is loaded.
        Supports both singles and doubles battle formats.
        """

        def __init__(self, *args: Any, is_doubles: bool = False, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._policy: "PPO | None" = None
            self._is_doubles = is_doubles

        def load_policy(self, path: Path) -> None:
            if not SB3_OK:
                return
            try:
                self._policy = PPO.load(str(path))
                log.info(f"[Opponent] Loaded policy from {path}")
            except Exception as exc:
                log.warning(f"[Opponent] Failed to load policy: {exc}")
                self._policy = None

        def choose_move(self, battle: Any) -> Any:
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

else:
    class SelfPlayOpponent:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("poke-env is not available")


# ── Training ──────────────────────────────────────────────────────────────────

def train(
    fmt: str,
    total_timesteps: int,
    swap_every: int,
    save_dir: Path,
    results_dir: Path | None = None,
    resume: str | None = None,
    team_format: str | None = None,
    server: str = MODE_LOCALHOST,
) -> Path:
    """
    Run PPO self-play training for the given Showdown format.

    Args:
        fmt: The Showdown battle format string (e.g. "gen9ou").
        total_timesteps: Total number of environment steps to train for.
        swap_every: How often (in steps) to swap the self-play opponent.
        save_dir: Root directory where in-progress checkpoints are saved.
        results_dir: Directory where the final dated model is saved.
                     Defaults to src/ml/models/results/.
        resume: Path to a saved checkpoint to resume training from.
        team_format: If set, load teams from FORMAT_TEAMS[team_format] and use
                     a RotatingTeambuilder (for formats that require custom teams).
        server:      Connection mode — "localhost", "showdown", or "browser".

    Returns the path to the final saved model zip.
    """
    start_date = datetime.now().strftime("%Y-%m-%d")

    # Delegate browser mode entirely to the Playwright trainer
    if server == MODE_BROWSER:
        from src.ml.browser_trainer import train_browser
        return train_browser(
            fmt=fmt,
            total_timesteps=total_timesteps,
            save_dir=save_dir,
            results_dir=results_dir,
        )

    _check_showdown_server_if_local(server)

    if not POKE_ENV_AVAILABLE:
        raise RuntimeError(
            "poke-env is not installed or failed to import. "
            "Run: pip install poke-env>=0.8.1"
        )
    if not SB3_OK:
        raise RuntimeError(
            "stable-baselines3 not installed. "
            "Run: pip install stable-baselines3>=2.2.0"
        )

    is_doubles = fmt in DOUBLES_FORMATS

    # ── Optional team builder ──────────────────────────────────────
    team_builder = None
    if team_format:
        try:
            from src.ml.teambuilder import RotatingTeambuilder
            from src.ml.teams import FORMAT_TEAMS
            teams = FORMAT_TEAMS.get(team_format)
            if teams:
                team_builder = RotatingTeambuilder(teams)
                log.info(f"[train] Using RotatingTeambuilder for {team_format} ({len(teams)} teams)")
            else:
                log.warning(f"[train] No teams found for {team_format}, training without custom teams")
        except Exception as exc:
            log.warning(f"[train] Could not load teams for {team_format}: {exc}")

    fmt_save_dir = save_dir / fmt
    fmt_save_dir.mkdir(parents=True, exist_ok=True)
    log_dir = fmt_save_dir / "tb_logs"
    log_dir.mkdir(exist_ok=True)

    # ── Resolve server config and accounts ────────────────────────
    srv_cfg = server_config_for_mode(server)
    acc1, acc2 = account_configs_for_mode(server)

    # ── Opponent player (drives agent2 in SingleAgentWrapper) ──────
    opp_kwargs: dict[str, Any] = dict(
        battle_format=fmt,
        server_configuration=srv_cfg,
        is_doubles=is_doubles,
    )
    # SelfPlayOpponent is a move-picker only inside SingleAgentWrapper;
    # Showdown auth for player 2 is handled via account_configuration2 on the env.
    if team_builder is not None:
        opp_kwargs["team"] = team_builder

    opponent = SelfPlayOpponent(**opp_kwargs)

    # ── Build Gymnasium-compatible env via SingleAgentWrapper ───────
    # strict=False: invalid actions (e.g. tera when unavailable) fall back
    # to a random legal order instead of raising ValueError
    # poke-env 0.12.x: SinglesEnv/DoublesEnv use account_configuration1 / 2
    # (not the bare account_configuration kwarg accepted by Player subclasses).
    def make_env():
        env_kwargs: dict[str, Any] = dict(
            battle_format=fmt,
            server_configuration=srv_cfg,
            strict=False,
        )
        if acc1 is not None:
            env_kwargs["account_configuration1"] = acc1
        if acc2 is not None:
            env_kwargs["account_configuration2"] = acc2
        if team_builder is not None:
            env_kwargs["team"] = team_builder
        if is_doubles:
            poke_env = BattleDoubleEnv(**env_kwargs)
        else:
            poke_env = BattleEnv(**env_kwargs)
        wrapped = SingleAgentWrapper(poke_env, opponent)
        return Monitor(wrapped)

    vec_env = DummyVecEnv([make_env])

    # ── PPO model ──────────────────────────────────────────────────
    if resume:
        log.info(f"Resuming from {resume}")
        model = PPO.load(
            resume,
            env=vec_env,
            tensorboard_log=str(log_dir),
        )
    else:
        model = PPO(
            "MlpPolicy",
            vec_env,
            tensorboard_log=str(log_dir),
            **PPO_HYPERPARAMS,
        )

    # ── Callbacks ──────────────────────────────────────────────────
    checkpoint_cb = CheckpointCallback(
        save_freq=swap_every,
        save_path=str(fmt_save_dir),
        name_prefix="ppo_ckpt",
    )
    selfplay_cb = SelfPlayCallback(
        opponent_player=opponent,
        save_dir=fmt_save_dir,
        swap_every=swap_every,
        verbose=1,
    )

    _server_desc = {
        "localhost": "ws://127.0.0.1:8000 (local Node.js server)",
        "showdown":  "wss://sim3.psim.us (public Showdown)",
    }.get(server, server)
    print(f"\n{'='*60}")
    print(f"  PPO Self-Play Training")
    print(f"  Format       : {fmt}")
    print(f"  Server mode  : {server} — {_server_desc}")
    print(f"  Total steps  : {total_timesteps:,}")
    print(f"  Swap every   : {swap_every:,}")
    print(f"  Save dir     : {fmt_save_dir}")
    print(f"  TensorBoard  : tensorboard --logdir {log_dir}")
    print(f"{'='*60}\n")
    if server == MODE_LOCALHOST:
        print("Make sure Pokemon Showdown server is running on ws://localhost:8000")
    print("Press Ctrl+C to stop training early.\n")

    try:
        model.learn(
            total_timesteps=total_timesteps,
            callback=[checkpoint_cb, selfplay_cb],
            reset_num_timesteps=(resume is None),
            tb_log_name=f"ppo_{fmt}",
        )
    except KeyboardInterrupt:
        log.info("Training interrupted by user.")

    # ── Save final model to results dir with date-stamped name ─────
    # CI expects save_dir/fmt/final_model.zip
    final_path = fmt_save_dir / "final_model.zip"
    model.save(str(final_path))
    print(f"\nFinal model saved to {final_path}")

    return final_path


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate(
    model_path: str,
    fmt: str,
    n_battles: int = 100,
) -> dict:
    """
    Evaluate a trained policy against a RandomPlayer baseline.

    Returns win/loss/tie rates.
    """
    if not POKE_ENV_AVAILABLE or not SB3_OK:
        raise RuntimeError("poke-env and stable-baselines3 are required for evaluation.")

    model = PPO.load(model_path)
    opponent = RandomPlayer(
        battle_format=fmt,
        server_configuration=LocalhostServerConfiguration,
    )

    poke_env = BattleEnv(
        battle_format=fmt,
        server_configuration=LocalhostServerConfiguration,
        strict=False,
    )
    env = SingleAgentWrapper(poke_env, opponent)

    wins = losses = ties = 0
    for i in range(n_battles):
        obs, _ = env.reset()
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, _ = env.step(int(action))
            done = terminated or truncated

        battle = poke_env.battle1
        if battle and battle.won:
            wins += 1
        elif battle and battle.lost:
            losses += 1
        else:
            ties += 1

        if (i + 1) % 10 == 0:
            print(f"  Battle {i+1}/{n_battles}: W={wins} L={losses} T={ties}")

    total = wins + losses + ties
    results = {
        "format"    : fmt,
        "battles"   : total,
        "wins"      : wins,
        "losses"    : losses,
        "ties"      : ties,
        "win_rate"  : wins / total if total > 0 else 0.0,
        "loss_rate" : losses / total if total > 0 else 0.0,
    }
    print(f"\n=== Evaluation vs RandomPlayer ({n_battles} battles) ===")
    print(f"  Win rate : {results['win_rate']*100:.1f}%")
    print(f"  Loss rate: {results['loss_rate']*100:.1f}%")
    print(f"  Ties     : {ties}")
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Train / evaluate PPO battle policy via poke-env self-play"
    )
    ap.add_argument(
        "--format", "-f",
        default=DEFAULT_FORMAT,
        help=f"Showdown battle format (default: {DEFAULT_FORMAT})",
    )
    ap.add_argument(
        "--timesteps", "-t",
        type=int,
        default=DEFAULT_TIMESTEPS,
        help=f"Total training timesteps (default: {DEFAULT_TIMESTEPS:,})",
    )
    ap.add_argument(
        "--swap-every",
        type=int,
        default=DEFAULT_SWAP_EVERY,
        help=f"Steps between self-play opponent swaps (default: {DEFAULT_SWAP_EVERY:,})",
    )
    ap.add_argument(
        "--save-dir",
        default=DEFAULT_SAVE_DIR,
        help=f"Root directory for checkpoints (default: {DEFAULT_SAVE_DIR})",
    )
    ap.add_argument(
        "--resume",
        default=None,
        metavar="MODEL.zip",
        help="Resume training from a saved checkpoint",
    )
    ap.add_argument(
        "--eval-only",
        default=None,
        metavar="MODEL.zip",
        help="Skip training — only evaluate the given model",
    )
    ap.add_argument(
        "--eval-battles",
        type=int,
        default=100,
        help="Number of evaluation battles (default: 100)",
    )
    ap.add_argument(
        "--results-dir",
        default=DEFAULT_RESULTS_DIR,
        help=f"Directory where final dated models are saved (default: {DEFAULT_RESULTS_DIR})",
    )
    ap.add_argument(
        "--team-format",
        default=None,
        metavar="FORMAT",
        help="Load teams from FORMAT_TEAMS[FORMAT] for custom-team formats "
             "(e.g. gen9ou, gen9doublesou, gen9vgc2026regi)",
    )
    ap.add_argument(
        "--server",
        default=MODE_LOCALHOST,
        choices=list(VALID_MODES),
        help=(
            "Showdown connection mode: "
            "localhost (local Node.js server, default), "
            "showdown (public sim3.psim.us — needs 2 accounts), "
            "browser (Playwright automation — needs 2 accounts)"
        ),
    )
    return ap.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    args = _parse_args()

    if args.eval_only:
        evaluate(
            model_path=args.eval_only,
            fmt=args.format,
            n_battles=args.eval_battles,
        )
    else:
        train(
            fmt=args.format,
            total_timesteps=args.timesteps,
            swap_every=args.swap_every,
            save_dir=Path(args.save_dir),
            results_dir=Path(args.results_dir),
            resume=args.resume,
            team_format=args.team_format,
            server=args.server,
        )
