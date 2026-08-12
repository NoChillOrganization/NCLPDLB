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
  • pip install poke-env>=0.15.0 stable-baselines3>=2.2.0 tensorboard>=2.16.0

Usage
─────
  python -m src.ml.train_policy --format gen9randombattle --timesteps 500000
  python -m src.ml.train_policy --format gen9ou --timesteps 2000000 --swap-every 50000
  python -m src.ml.train_policy --eval-only data/ml/policy/gen9randombattle/best_model.zip
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Dependency guards ─────────────────────────────────────────────────────────

try:  # pragma: no cover
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    SB3_OK = True
except ImportError:  # pragma: no cover
    SB3_OK = False
    PPO = None  # type: ignore
    CheckpointCallback = None  # type: ignore
    Monitor = None  # type: ignore
    DummyVecEnv = None  # type: ignore

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
    from poke_env.environment.single_agent_wrapper import SingleAgentWrapper
    from poke_env.player import RandomPlayer

    POKE_ENV_OK = True
except ImportError:  # pragma: no cover
    POKE_ENV_OK = False

from src.ml.showdown_modes import VALID_MODES, MODE_LOCALHOST, MODE_BROWSER  # noqa: E402
from src.ml.showdown_modes import server_config_for_mode, account_configs_for_mode  # noqa: E402

try:
    from src.data.learning_sheets import learning_sheets as _learning_sheets

    _SHEETS_OK = True
except Exception:  # pragma: no cover
    _learning_sheets = None  # type: ignore
    _SHEETS_OK = False

from src.ml.battle_env import (  # noqa: E402
    POKE_ENV_AVAILABLE,
    BattleDoubleEnv,
    BattleEnv,
)

# ── Constants ─────────────────────────────────────────────────────────────────

SHOWDOWN_HOST = "127.0.0.1"
SHOWDOWN_PORT = 8000


# Re-exported for backward compatibility: BC pre-training helpers, the
# transformer feature extractor, the Dict->Box observation unwrapper, the
# self-play curriculum callback, and opponent wrappers live in
# train_policy_components.py (extracted to keep this file under the
# project's 800-line guideline), but existing call sites and tests still
# import some of these names from here.
from src.ml.train_policy_components import (  # noqa: E402, F401
    CurriculumCallback,
    CurriculumOpponent,
    SelfPlayOpponent,
    BattleTransformerExtractor,
    _UnwrapDictObs,
    _check_showdown_server,
    _check_showdown_server_if_local,
    _log_meta_context,
    make_bc_ent_coef_schedule,
    _load_pretrain_weights,
)

DEFAULT_FORMAT = "gen9randombattle"
DEFAULT_TIMESTEPS = 500_000
DEFAULT_SWAP_EVERY = 50_000  # steps between opponent model swaps
N_MAX_EPOCH0_STEPS = 2_000_000  # force-graduate after this many warmup steps
DEFAULT_SAVE_DIR = "data/ml/policy"
DEFAULT_RESULTS_DIR = "data/ml/results"

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
    "gen9vgc2026regi",
    "gen9vgc2026regibo3",
    # Champions Doubles
    "gen9championsvgc2026regmb",
    "gen9championsvgc2026regmbbo3",
}

# Some formats use the same Showdown battle mechanics as a base format.
# poke-env doesn't support the BO3 series protocol, so we train these
# using the base single-battle format while keeping artifact paths intact.
TRAINING_FORMAT_ALIASES: dict[str, str] = {
    # BO3 variants → train as the equivalent single-battle format
    "gen9vgc2026regibo3": "gen9vgc2026regi",
    # Champions formats → not on the standard Showdown server; train as
    # the closest standard format so battles can actually start.
    "gen9championsou": "gen9ou",
    "gen9championsbssregmb": "gen9ou",
    "gen9championsvgc2026regmb": "gen9vgc2026regi",
    "gen9championsvgc2026regmbbo3": "gen9vgc2026regi",
}

PPO_HYPERPARAMS: dict[str, Any] = {
    "learning_rate": 3e-4,
    "n_steps": 2048,
    "batch_size": 64,
    "n_epochs": 10,
    "gamma": 0.99,
    "gae_lambda": 0.95,
    "clip_range": 0.2,
    "ent_coef": 0.01,
    "vf_coef": 0.5,
    "max_grad_norm": 0.5,
    "policy_kwargs": {"net_arch": [64, 64]},
    "verbose": 1,
}


# ── Training ──────────────────────────────────────────────────────────────────


def train(  # pragma: no cover
    fmt: str,
    total_timesteps: int,
    swap_every: int,
    save_dir: Path,
    results_dir: Path | None = None,
    resume: str | None = None,
    pretrain: str | None = None,
    team_format: str | None = None,
    server: str = MODE_LOCALHOST,
    save_replays: str | None = None,
    use_transformer: bool = False,
    meta_path: str | None = None,
    opponent_type: str = "curriculum",
    opponent_checkpoint: str | None = None,
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
        pretrain: Path to a BC actor checkpoint (.pt) to warm-start the policy.
                  Mutually exclusive with ``resume``.
        team_format: If set, load teams from FORMAT_TEAMS[team_format] and use
                     a RotatingTeambuilder (for formats that require custom teams).
        server:      Connection mode — "localhost", "showdown", or "browser".
        save_replays: If set, directory to save HTML battle replays.

    Returns the path to the final saved model zip.
    """
    if resume and pretrain:
        raise ValueError("--pretrain and --resume are mutually exclusive")
    # Delegate browser mode entirely to the Playwright trainer
    if server == MODE_BROWSER:
        from src.ml.browser_trainer import train_browser

        return train_browser(
            fmt=fmt,
            total_timesteps=total_timesteps,
            save_dir=save_dir,
            results_dir=results_dir,
        )

    # Resolve aliased formats (BO3 variants, Champions formats that don't exist
    # on the standard Showdown server).  When no explicit team_format was
    # supplied, inherit the base format's teams so non-random battles can start.
    training_fmt = TRAINING_FORMAT_ALIASES.get(fmt, fmt)
    if training_fmt != fmt:
        log.info(f"[train] Format alias: {fmt!r} -> {training_fmt!r}")
        if not team_format:
            team_format = training_fmt
            log.info(
                f"[train] Auto-inherited team_format from base format: {team_format!r}"
            )

    _check_showdown_server_if_local(server)
    _log_meta_context(fmt, meta_path)

    if not POKE_ENV_AVAILABLE:
        raise RuntimeError(
            "poke-env is not installed or failed to import. "
            "Run: pip install poke-env>=0.15.0"
        )
    if not SB3_OK:
        raise RuntimeError(
            "stable-baselines3 not installed. Run: pip install stable-baselines3>=2.2.0"
        )

    is_doubles = training_fmt in DOUBLES_FORMATS

    # ── Optional team builder ──────────────────────────────────────
    team_builder = None
    if team_format:
        try:
            from src.ml.teambuilder import RotatingTeambuilder
            from src.ml.teams import FORMAT_TEAMS

            teams = FORMAT_TEAMS.get(team_format)
            if teams:
                team_builder = RotatingTeambuilder(teams)
                log.info(
                    f"[train] Using RotatingTeambuilder for {team_format} ({len(teams)} teams)"
                )
            else:
                log.warning(
                    f"[train] No teams found for {team_format}, training without custom teams"
                )
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
    # CurriculumOpponent generates moves locally (choose_move + CurriculumCallback).
    # It is NOT the player that connects to Showdown for battle. The actual Showdown
    # battle is between env.agent1 (acc1) and env.agent2 (acc2) inside PokeEnv.reset().
    opp_kwargs: dict[str, Any] = dict(
        battle_format=training_fmt,
        server_configuration=srv_cfg,
        is_doubles=is_doubles,
    )
    if team_builder is not None:
        opp_kwargs["team"] = team_builder

    if opponent_type == "mcts":
        if is_doubles:
            raise ValueError(
                "--opponent mcts is not supported for doubles formats. "
                "MCTSPlayer uses a gen9-singles action space only."
            )
        from src.ml.self_play import MCTSPlayer
        from src.ml.mcts import MCTSConfig
        from src.ml.transformer_model import build_default_model, load_model

        # Strip is_doubles — MCTSPlayer does not accept that kwarg
        mcts_kwargs = {k: v for k, v in opp_kwargs.items() if k != "is_doubles"}
        tmodel = (
            load_model(opponent_checkpoint)
            if opponent_checkpoint
            else build_default_model()
        )
        opponent = MCTSPlayer(
            model=tmodel,
            mcts_config=MCTSConfig(),
            replay_buffer=None,
            stats=None,
            **mcts_kwargs,
        )
        log.info(
            "[train] Using MCTSPlayer as self-play opponent (checkpoint=%s)",
            opponent_checkpoint,
        )
    else:
        opponent = CurriculumOpponent(**opp_kwargs)

    # ── Build Gymnasium-compatible env via SingleAgentWrapper ───────
    # strict=False: invalid actions (e.g. tera when unavailable) fall back
    # to a random legal order instead of raising ValueError
    # poke-env 0.12.x: SinglesEnv/DoublesEnv use account_configuration1 / 2
    # (not the bare account_configuration kwarg accepted by Player subclasses).
    # Both acc1 and acc2 go to env.agent1/agent2 — these are the players that
    # actually battle on Showdown. CurriculumOpponent only generates moves locally.
    def make_env():
        env_kwargs: dict[str, Any] = dict(
            battle_format=training_fmt,
            server_configuration=srv_cfg,
            strict=False,
        )
        if acc1 is not None:
            env_kwargs["account_configuration1"] = acc1
        if acc2 is not None:
            env_kwargs["account_configuration2"] = acc2
        if team_builder is not None:
            env_kwargs["team"] = team_builder
        if save_replays:
            Path(save_replays).mkdir(parents=True, exist_ok=True)
            env_kwargs["save_replays"] = save_replays
        if is_doubles:
            poke_env = BattleDoubleEnv(**env_kwargs)
        else:
            poke_env = BattleEnv(**env_kwargs)
        wrapped = _UnwrapDictObs(SingleAgentWrapper(poke_env, opponent))
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
    elif use_transformer:
        transformer_kwargs = {
            k: v for k, v in PPO_HYPERPARAMS.items() if k != "policy_kwargs"
        }
        transformer_kwargs["policy_kwargs"] = {
            "features_extractor_class": BattleTransformerExtractor,
            "features_extractor_kwargs": {"d_model": 64},
            "net_arch": [64, 64],
        }
        log.info("[train] Using BattleTransformerExtractor as PPO feature encoder")
        model = PPO(
            "MlpPolicy",
            vec_env,
            tensorboard_log=str(log_dir),
            **transformer_kwargs,
        )
    elif pretrain:
        # BC warm-start: fresh PPO model with elevated-then-annealed ent_coef
        ent_schedule = make_bc_ent_coef_schedule(total_timesteps)
        pretrain_hyperparams = {**PPO_HYPERPARAMS, "ent_coef": ent_schedule}
        model = PPO(
            "MlpPolicy",
            vec_env,
            tensorboard_log=str(log_dir),
            **pretrain_hyperparams,
        )
        log.info(f"[train] Loading BC pretrain weights from {pretrain}")
        _load_pretrain_weights(model, pretrain)
        log.info("[train] ent_coef schedule: 0.05 (0–100k) → anneal → 0.01 (200k+)")
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
    curriculum_cb = CurriculumCallback(
        opponent_player=opponent,
        save_dir=fmt_save_dir,
        fmt=fmt,
        swap_every=swap_every,
        verbose=1,
    )

    _server_desc = {
        "localhost": "ws://127.0.0.1:8000 (local Node.js server)",
        "showdown": "wss://sim3.psim.us (public Showdown)",
    }.get(server, server)
    log.info("============================================================")
    log.info("  PPO Curriculum Training")
    log.info(
        f"  Format       : {fmt}"
        + (f" (training as {training_fmt})" if training_fmt != fmt else "")
    )
    log.info(f"  Server mode  : {server} — {_server_desc}")
    log.info(f"  Total steps  : {total_timesteps:,}")
    log.info(f"  Swap every   : {swap_every:,} (after graduation)")
    log.info(f"  Save dir     : {fmt_save_dir}")
    log.info(f"  TensorBoard  : tensorboard --logdir {log_dir}")
    if save_replays:
        log.info(f"  Replays      : {save_replays}  (open .html files in browser)")
    log.info("============================================================")
    if server == MODE_LOCALHOST:
        log.info("Make sure Pokemon Showdown server is running on ws://localhost:8000")
    log.info("Press Ctrl+C to stop training early.")

    # Drop per-message WS traffic logs (<<< / >>>) so the job log stays under
    # GitHub's ~1 GB API limit and the actual crash (if any) remains visible.
    # Must attach to handlers, not the root logger: child logger propagation calls
    # callHandlers() directly, bypassing the root logger's own filter() method.
    class _DropWSTraffic(logging.Filter):
        def filter(self, record):
            if record.levelno < logging.WARNING:
                msg = record.getMessage()
                return "<<<" not in msg and ">>>" not in msg
            return True

    _ws_filter = _DropWSTraffic()
    _root = logging.getLogger()
    _root.addFilter(_ws_filter)
    for _h in _root.handlers:
        _h.addFilter(_ws_filter)

    _train_exc: BaseException | None = None
    # Declare final_path before try/finally so the finally block can reference it.
    final_path = fmt_save_dir / "final_model.zip"
    try:
        model.learn(
            total_timesteps=total_timesteps,
            callback=[checkpoint_cb, curriculum_cb],
            reset_num_timesteps=(
                resume is None
            ),  # pretrain also resets (it's not resume)
            tb_log_name=f"ppo_{fmt}",
        )
    except KeyboardInterrupt:
        log.info("Training interrupted by user.")
    except BaseException as exc:
        # Catches asyncio.CancelledError (BaseException since Python 3.8) that fires when
        # the poke_env event loop shuts down after Showdown server dies (WinError 64).
        log.warning(
            f"[train] Training error: {type(exc).__name__}: {exc}; saving checkpoint."
        )
        _train_exc = exc
    finally:
        # ── Save final model ──────────────────────────────────────────
        # In finally so the model is always written to disk, even if BaseException
        # (CancelledError, SystemExit, etc.) is propagating.
        try:
            model.save(str(final_path))
            log.info(f"\nFinal model saved to {final_path}")
        except Exception as save_exc:
            log.error(f"[train] model.save() FAILED: {save_exc!r}")
    if _SHEETS_OK and _learning_sheets:
        final_win_rate = (
            sum(curriculum_cb._win_window) / len(curriculum_cb._win_window)
            if curriculum_cb._win_window
            else 0.0
        )
        _learning_sheets.save_training_run(
            {
                "format": fmt,
                "phase": "final",
                "checkpoint": final_path.name,
                "training_step": curriculum_cb.num_timesteps,
                "win_rate": f"{final_win_rate:.4f}",
                "episodes": len(curriculum_cb._win_window),
                "mean_reward": "",
                "notes": f"training complete — {total_timesteps:,} steps",
            }
        )

    # Dated copy in results_dir so _model_done() can detect completion
    _results_dir = results_dir if results_dir is not None else Path(DEFAULT_RESULTS_DIR)
    _results_dir.mkdir(parents=True, exist_ok=True)
    from datetime import date as _date

    dated_path = _results_dir / f"{fmt}_{_date.today()}.zip"
    model.save(str(dated_path))
    log.info(f"Dated model saved to {dated_path}")

    if _train_exc is not None:
        # "Agent is not challenging" = poke-env challenge timeout (team rejection
        # or transient server issue).  Model was already saved above; treat as a
        # clean early-stop ONLY when meaningful training occurred.  A 0-step or
        # near-zero checkpoint is indistinguishable from an untrained stub and must
        # not be published as a real model.
        if "not challenging" in str(_train_exc):
            steps_done = getattr(curriculum_cb, "num_timesteps", 0)
            # Floor: at least 1 % of requested timesteps, minimum 1 000 steps.
            # Anything below signals the server rejected every challenge before
            # training could start — raise so the CI job goes red.
            min_steps = max(1_000, total_timesteps // 100)
            log.warning(
                f"[train] Battle challenge timeout — "
                f"{steps_done:,} steps trained (floor: {min_steps:,}). "
                f"Model saved at {final_path}."
            )
            if steps_done < min_steps:
                raise RuntimeError(
                    f"[train] Aborting: only {steps_done:,} steps completed before "
                    f"'Agent is not challenging' (floor={min_steps:,}). "
                    f"The model at {final_path} is untrained. "
                    f"Fix the Showdown server / team generation for '{fmt}' and retry."
                ) from _train_exc
        else:
            raise _train_exc

    return final_path


# ── Evaluation ────────────────────────────────────────────────────────────────


def evaluate(  # pragma: no cover
    model_path: str,
    fmt: str,
    n_battles: int = 100,
    server: str = MODE_LOCALHOST,
) -> dict:
    """
    Evaluate a trained policy against a RandomPlayer baseline.

    Returns win/loss/tie rates.
    """
    if not POKE_ENV_AVAILABLE or not SB3_OK:
        raise RuntimeError(
            "poke-env and stable-baselines3 are required for evaluation."
        )

    srv_cfg = server_config_for_mode(server)
    model = PPO.load(model_path)
    opponent = RandomPlayer(
        battle_format=fmt,
        server_configuration=srv_cfg,
    )

    poke_env = BattleEnv(
        battle_format=fmt,
        server_configuration=srv_cfg,
        strict=False,
    )
    env = _UnwrapDictObs(SingleAgentWrapper(poke_env, opponent))

    wins = losses = ties = 0
    for i in range(n_battles):
        obs, _ = env.reset()
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, _ = env.step(int(action))
            done = terminated or truncated

        # poke_env.battle1 is version-dependent; use getattr fallback (M23)
        battle = getattr(poke_env, "battle1", None) or getattr(
            poke_env, "_current_battle", None
        )
        if battle and getattr(battle, "won", False):
            wins += 1
        elif battle and getattr(battle, "lost", False):
            losses += 1
        else:
            ties += 1

        if (i + 1) % 10 == 0:
            log.info(f"  Battle {i + 1}/{n_battles}: W={wins} L={losses} T={ties}")

    total = wins + losses + ties
    results = {
        "format": fmt,
        "battles": total,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_rate": wins / total if total > 0 else 0.0,
        "loss_rate": losses / total if total > 0 else 0.0,
    }
    log.info(f"\n=== Evaluation vs RandomPlayer ({n_battles} battles) ===")
    log.info(f"  Win rate : {results['win_rate'] * 100:.1f}%")
    log.info(f"  Loss rate: {results['loss_rate'] * 100:.1f}%")
    log.info(f"  Ties     : {ties}")
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:  # pragma: no cover
    ap = argparse.ArgumentParser(
        description="Train / evaluate PPO battle policy via poke-env self-play"
    )
    ap.add_argument(
        "--format",
        "-f",
        default=DEFAULT_FORMAT,
        help=f"Showdown battle format (default: {DEFAULT_FORMAT})",
    )
    ap.add_argument(
        "--timesteps",
        "-t",
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
        "--pretrain",
        default=None,
        metavar="BC_ACTOR.pt",
        help=(
            "Warm-start PPO from a BC actor checkpoint (.pt file saved by pretrain.py). "
            "Loads actor-only keys (mlp_extractor.*, action_net.*) and resets step counter. "
            "Mutually exclusive with --resume."
        ),
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
        "--save-replays",
        default=None,
        metavar="DIR",
        help="Directory to save HTML battle replays (viewable in any browser). "
        "Each battle is saved as a .html file.",
    )
    ap.add_argument(
        "--server",
        default=MODE_LOCALHOST,
        choices=list(VALID_MODES),
        help=(
            "Showdown connection mode: "
            "localhost (ws://127.0.0.1:8000 — local Node.js server, default), "
            "showdown (wss://sim3.psim.us — requires 2 accounts), "
            "browser (Playwright-driven)"
        ),
    )
    ap.add_argument(
        "--use-transformer",
        action="store_true",
        default=False,
        help="Use BattleTransformerExtractor (transformer encoder) instead of default MLP policy",
    )
    ap.add_argument(
        "--meta-path",
        default=None,
        metavar="DIR",
        help="Directory containing competitive meta data (format_meta.json). "
        "When set, usage leaders and archetypes are logged before training.",
    )
    ap.add_argument(
        "--opponent",
        default="curriculum",
        choices=["curriculum", "mcts"],
        help=(
            "Self-play opponent type: "
            "'curriculum' (MaxBasePowerPlayer → frozen PPO checkpoint, default) or "
            "'mcts' (BattleTransformer + MCTS tree search, singles formats only)"
        ),
    )
    ap.add_argument(
        "--opponent-checkpoint",
        default=None,
        metavar="TRANSFORMER.pt",
        help=(
            "Path to a BattleTransformer checkpoint (.pt) used when --opponent mcts. "
            "Defaults to randomly-initialised weights when omitted."
        ),
    )
    return ap.parse_args()


if __name__ == "__main__":  # pragma: no cover
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
        if args.resume and args.pretrain:
            raise ValueError("--pretrain and --resume are mutually exclusive")
        train(
            fmt=args.format,
            total_timesteps=args.timesteps,
            swap_every=args.swap_every,
            save_dir=Path(args.save_dir),
            results_dir=Path(args.results_dir),
            resume=args.resume,
            pretrain=args.pretrain,
            team_format=args.team_format,
            server=args.server,
            save_replays=args.save_replays,
            use_transformer=args.use_transformer,
            meta_path=args.meta_path,
            opponent_type=args.opponent,
            opponent_checkpoint=args.opponent_checkpoint,
        )
