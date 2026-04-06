"""
Showdown Player — a poke-env player backed by a trained PPO policy.

This module provides:
  • ShowdownBotPlayer  — poke-env Player that uses the RL policy to choose moves
  • BotChallenger      — high-level interface to challenge a Showdown user and
                        stream the battle result back (used by the Discord /spar command)

Usage (standalone)
──────────────────
  # Challenge a user on Pokemon Showdown:
  python -m src.ml.showdown_player \\
      --model data/ml/policy/gen9randombattle/final_model.zip \\
      --format gen9randombattle \\
      --username "YourShowdownName" \\
      --password "hunter2" \\
      --challenge "OpponentShowdownName"

  # Accept the first incoming challenge:
  python -m src.ml.showdown_player \\
      --model data/ml/policy/gen9randombattle/final_model.zip \\
      --format gen9randombattle \\
      --username "YourBotName" \\
      --password "hunter2" \\
      --accept-challenges

Usage (from Discord bot)
────────────────────────
  from src.ml.showdown_player import BotChallenger
  challenger = BotChallenger(model_path=..., fmt=..., username=..., password=...)
  result = await challenger.challenge_user("TargetShowdownName")
  # result: {"winner": "p1"|"p2"|"tie", "turns": int, "replay_url": str|None}

Requirements
────────────
  pip install poke-env>=0.8.1 stable-baselines3>=2.2.0
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Dependency guards ─────────────────────────────────────────────────────────

try:
    from stable_baselines3 import PPO
    SB3_OK = True
except ImportError:  # pragma: no cover
    SB3_OK = False
    PPO = None  # type: ignore

try:
    from poke_env.battle import AbstractBattle
    from poke_env.player import Player
    from poke_env.ps_client.server_configuration import (
        LocalhostServerConfiguration,
        ShowdownServerConfiguration,
    )
    POKE_ENV_OK = True
except ImportError:  # pragma: no cover
    POKE_ENV_OK = False
    Player = object  # type: ignore
    AbstractBattle = LocalhostServerConfiguration = ShowdownServerConfiguration = None  # type: ignore

try:
    from src.data.sheets import learning_sheets
    SHEETS_AVAILABLE = True
except ImportError:  # pragma: no cover
    learning_sheets = None  # type: ignore
    SHEETS_AVAILABLE = False

from src.ml.battle_env import POKE_ENV_AVAILABLE, build_observation  # noqa: E402

# ── Bot player ────────────────────────────────────────────────────────────────

if POKE_ENV_AVAILABLE:
    class ShowdownBotPlayer(Player):
        """
        poke-env Player that drives decisions from a trained PPO policy.

        If the model isn't loaded or an action is invalid, it falls back
        to the best available legal move (random).
        """

        def __init__(  # pragma: no cover
            self,
            model_path: str | Path | None = None,
            *args: Any,
            **kwargs: Any,
        ) -> None:
            super().__init__(*args, **kwargs)
            self._policy: "PPO | None" = None
            if model_path:
                self.load_model(model_path)

        # ── Model management ───────────────────────────────────────

        def load_model(self, path: str | Path) -> None:  # pragma: no cover
            """Load (or reload) the PPO policy from a .zip checkpoint."""
            if not SB3_OK:
                raise ImportError(
                    "stable-baselines3 is required. "
                    "Run: pip install stable-baselines3>=2.2.0"
                )
            self._policy = PPO.load(str(path))
            log.info(f"[ShowdownBotPlayer] Policy loaded from {path}")

        # ── Move selection ─────────────────────────────────────────

        def choose_move(self, battle: AbstractBattle) -> None:  # pragma: no cover  # type: ignore[override]
            if self._policy is None:
                log.debug("[ShowdownBotPlayer] No policy loaded — using random")
                return self.choose_random_move(battle)

            try:
                obs = build_observation(battle).reshape(1, -1)
                action, _ = self._policy.predict(obs, deterministic=True)
                action_id = int(action[0])
                return self._action_to_move(action_id, battle)
            except Exception as exc:
                log.warning(f"[ShowdownBotPlayer] Policy error: {exc} — falling back to random")
                return self.choose_random_move(battle)

        def _action_to_move(self, action: int, battle: AbstractBattle):  # pragma: no cover
            """Map discrete action ID → poke-env BattleOrder using SinglesEnv mapper."""
            try:
                from poke_env.environment.singles_env import SinglesEnv
                return SinglesEnv.action_to_order(action, battle)
            except Exception:
                return self.choose_random_move(battle)

        async def save_replay(self, battle: AbstractBattle) -> str | None:  # pragma: no cover
            """
            Send /savereplay to Showdown and return the replay URL.

            Returns None if the command fails or the server doesn't respond.
            The URL is deterministic: https://replay.pokemonshowdown.com/<battle_tag>
            """
            try:
                tag = battle.battle_tag
                await self._communicator.send(f"{tag}|/savereplay")
                return f"https://replay.pokemonshowdown.com/{tag}"
            except Exception as exc:
                log.warning(f"[ShowdownBotPlayer] /savereplay failed: {exc}")
                return None

else:  # pragma: no cover
    class ShowdownBotPlayer:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "poke-env is not properly installed. "
                "Run: pip install poke-env>=0.8.1"
            )


# ── High-level challenger ─────────────────────────────────────────────────────

class BotChallenger:
    """
    High-level wrapper used by the Discord /spar command.

    Manages a ShowdownBotPlayer, initiates or accepts a battle challenge,
    and returns a structured result dict when the battle finishes.
    """

    def __init__(  # pragma: no cover
        self,
        model_path: str | Path,
        fmt: str,
        username: str,
        password: str,
        server: str = "showdown",   # "showdown" | "localhost"
    ) -> None:
        if not POKE_ENV_AVAILABLE:
            raise ImportError("poke-env is required for live battles.")

        self.model_path = Path(model_path)
        self.fmt        = fmt
        self.username   = username
        self.password   = password

        server_cfg = (
            ShowdownServerConfiguration
            if server == "showdown"
            else LocalhostServerConfiguration
        )

        self._player = ShowdownBotPlayer(
            model_path=self.model_path,
            battle_format=fmt,
            server_configuration=server_cfg,
            account_configuration=_make_account_config(username, password),
        )

    # ── Public API ─────────────────────────────────────────────────────

    async def challenge_user(  # pragma: no cover
        self,
        target_username: str,
        timeout: int = 300,
    ) -> dict:
        """
        Send a challenge to `target_username` and wait for the battle to finish.

        Returns
        -------
        dict with keys:
          winner     : "bot" | "opponent" | "tie"
          turns      : int
          replay_url : str | None   (Showdown doesn't auto-upload; always None here)
          format     : str
          bot_name   : str
          opponent   : str
        """
        log.info(f"[BotChallenger] Challenging {target_username} ({self.fmt})")
        await self._player.send_challenges(
            target_username,
            n_challenges=1,
            to_wait=None,
        )
        result = await asyncio.wait_for(
            self._wait_for_result(),
            timeout=timeout,
        )
        return result

    async def accept_one_challenge(self, timeout: int = 600) -> dict:  # pragma: no cover
        """
        Wait for and accept the next incoming challenge.

        Useful for testing: the Discord user challenges the bot's Showdown account.
        """
        log.info(f"[BotChallenger] Waiting for incoming challenge ({self.fmt})")
        await self._player.accept_challenges(
            opponent=None,
            n_challenges=1,
        )
        result = await asyncio.wait_for(
            self._wait_for_result(),
            timeout=timeout,
        )
        return result

    # ── Internal helpers ───────────────────────────────────────────────

    async def _wait_for_result(self) -> dict:  # pragma: no cover
        """Poll until the latest battle is finished, save replay URL, and return the result."""
        while True:
            await asyncio.sleep(1)
            battles = list(self._player.battles.values())
            if battles:
                battle = battles[-1]
                if battle.finished:
                    replay_url = await self._player.save_replay(battle)
                    result = self._format_result(battle, replay_url=replay_url)
                    if SHEETS_AVAILABLE:
                        learning_sheets.save_replay_url({
                            "format":     self.fmt,
                            "battle_id":  battle.battle_tag,
                            "bot":        self.username,
                            "opponent":   _get_opponent_name(battle),
                            "winner":     result["winner"],
                            "turns":      result["turns"],
                            "replay_url": replay_url or "",
                        })
                    return result

    def _format_result(self, battle: AbstractBattle, replay_url: str | None = None) -> dict:
        if battle.won:
            winner = "bot"
        elif battle.lost:
            winner = "opponent"
        else:
            winner = "tie"

        return {
            "winner"     : winner,
            "turns"      : getattr(battle, "turn", 0),
            "replay_url" : replay_url,
            "format"     : self.fmt,
            "bot_name"   : self.username,
            "opponent"   : _get_opponent_name(battle),
        }


def _make_account_config(username: str, password: str):  # pragma: no cover
    """Build a poke-env AccountConfiguration."""
    from poke_env.ps_client.account_configuration import AccountConfiguration
    return AccountConfiguration(username, password)


def _get_opponent_name(battle: AbstractBattle) -> str:
    try:
        return battle.opponent_username or "Unknown"
    except Exception:
        return "Unknown"


# ── Model selector ────────────────────────────────────────────────────────────

def best_model_for_format(
    fmt: str,
    save_dir: str = "data/ml/policy",
    results_dir: str = "src/ml/models/results",
) -> Path | None:
    """
    Return the path to the best available model for a given format.

    Preference order:
      1. Most recent dated model in results_dir  ({fmt}_YYYY-MM-DD.zip)
      2. latest.zip in save_dir  (in-progress checkpoint)
      3. Newest ppo_ckpt_*.zip in save_dir
    """
    # 1. Dated final models — check per-format subdir first, then flat root
    subdir_results = sorted((Path(results_dir) / fmt).glob(f"{fmt}_*.zip"))
    if subdir_results:
        return subdir_results[-1]
    flat_results = sorted(Path(results_dir).glob(f"{fmt}_*.zip"))
    if flat_results:
        return flat_results[-1]

    # 2. In-progress checkpoint
    base = Path(save_dir) / fmt
    latest = base / "latest.zip"
    if latest.exists():
        return latest

    # 3. Newest PPO checkpoint
    ckpts = sorted(base.glob("ppo_ckpt_*.zip"))
    if ckpts:
        return ckpts[-1]

    return None


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    ap = argparse.ArgumentParser(description="Run the Showdown bot player")
    ap.add_argument("--model",    required=True, help="Path to trained PPO model .zip")
    ap.add_argument("--format",   default="gen9randombattle", help="Showdown battle format")
    ap.add_argument("--username", required=True, help="Showdown account username")
    ap.add_argument("--password", required=True, help="Showdown account password")
    ap.add_argument("--challenge",          default=None, metavar="USER",
                    help="Challenge this Showdown username")
    ap.add_argument("--accept-challenges",  action="store_true",
                    help="Wait and accept the next incoming challenge")
    ap.add_argument("--server", default="showdown", choices=["showdown", "localhost"],
                    help="Server to connect to")
    args = ap.parse_args()

    if not args.challenge and not args.accept_challenges:
        ap.error("Specify --challenge <user> or --accept-challenges")

    challenger = BotChallenger(
        model_path=args.model,
        fmt=args.format,
        username=args.username,
        password=args.password,
        server=args.server,
    )

    async def main() -> None:
        if args.challenge:
            result = await challenger.challenge_user(args.challenge)
        else:
            result = await challenger.accept_one_challenge()

        print("\n=== Battle Result ===")
        for k, v in result.items():
            print(f"  {k:<12} : {v}")

    asyncio.run(main())
