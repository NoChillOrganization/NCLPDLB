#!/usr/bin/env python3
"""
Run the NCLPDLB bot on the public Pokémon Showdown ladder.

The bot plays self-play battles on sim3.psim.us using two registered
Showdown accounts. You can watch the battles live at:
    https://play.pokemonshowdown.com

Usage
-----
  # Set credentials as env vars (recommended):
  export SHOWDOWN_TRAIN_USER1="YourBotAccount1"
  export SHOWDOWN_TRAIN_PASS1="password1"
  export SHOWDOWN_TRAIN_USER2="YourBotAccount2"
  export SHOWDOWN_TRAIN_PASS2="password2"

  python scripts/run_on_showdown.py --format gen9randombattle --timesteps 1000

  # Or pass credentials directly (not recommended for security):
  python scripts/run_on_showdown.py \\
      --format gen9ou \\
      --user1 BotAccount1 --pass1 password1 \\
      --user2 BotAccount2 --pass2 password2 \\
      --timesteps 500 \\
      --save-replays replays/

How to watch
------------
1. Go to https://play.pokemonshowdown.com
2. Log in as one of your bot accounts (or any account)
3. Click the bot account's username to view their profile
4. Any active battle will appear — click it to spectate
   OR search for the username in the battle search bar

Requirements
------------
  pip install poke-env>=0.8.1 stable-baselines3>=2.2.0

  Two registered Pokémon Showdown accounts are required.
  Register free at: https://play.pokemonshowdown.com
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run NCLPDLB bot on public Pokémon Showdown — watch live at play.pokemonshowdown.com",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--format", "-f", default="gen9randombattle",
                    help="Showdown battle format (default: gen9randombattle)")
    ap.add_argument("--timesteps", "-t", type=int, default=1000,
                    help="Number of training steps to run (default: 1000)")
    ap.add_argument("--swap-every", type=int, default=200,
                    help="Steps between self-play opponent swaps (default: 200)")
    ap.add_argument("--save-dir", default="data/ml/policy",
                    help="Directory to save model checkpoints")
    ap.add_argument("--save-replays", default=None, metavar="DIR",
                    help="Directory to save HTML battle replays (open in browser after)")
    ap.add_argument("--resume", default=None, metavar="MODEL.zip",
                    help="Resume from a saved checkpoint")
    ap.add_argument("--team-format", default=None, metavar="FORMAT",
                    help="Load custom teams for this format (e.g. gen9ou)")
    ap.add_argument("--user1", default=None, help="Showdown username for player 1 (or set SHOWDOWN_TRAIN_USER1)")
    ap.add_argument("--pass1", default=None, help="Showdown password for player 1 (or set SHOWDOWN_TRAIN_PASS1)")
    ap.add_argument("--user2", default=None, help="Showdown username for player 2 (or set SHOWDOWN_TRAIN_USER2)")
    ap.add_argument("--pass2", default=None, help="Showdown password for player 2 (or set SHOWDOWN_TRAIN_PASS2)")
    args = ap.parse_args()

    # Inject credentials into env vars if passed as args
    if args.user1: os.environ["SHOWDOWN_TRAIN_USER1"] = args.user1
    if args.pass1: os.environ["SHOWDOWN_TRAIN_PASS1"] = args.pass1
    if args.user2: os.environ["SHOWDOWN_TRAIN_USER2"] = args.user2
    if args.pass2: os.environ["SHOWDOWN_TRAIN_PASS2"] = args.pass2

    # Validate credentials are available
    required = ["SHOWDOWN_TRAIN_USER1", "SHOWDOWN_TRAIN_PASS1",
                "SHOWDOWN_TRAIN_USER2", "SHOWDOWN_TRAIN_PASS2"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"\nERROR: Missing credentials: {', '.join(missing)}")
        print("\nSet them as environment variables:")
        print("  export SHOWDOWN_TRAIN_USER1='YourBotAccount1'")
        print("  export SHOWDOWN_TRAIN_PASS1='password1'")
        print("  export SHOWDOWN_TRAIN_USER2='YourBotAccount2'")
        print("  export SHOWDOWN_TRAIN_PASS2='password2'")
        print("\nOr pass them as arguments: --user1 ... --pass1 ... --user2 ... --pass2 ...")
        print("\nRegister free Showdown accounts at: https://play.pokemonshowdown.com")
        sys.exit(1)

    u1 = os.environ["SHOWDOWN_TRAIN_USER1"]
    u2 = os.environ["SHOWDOWN_TRAIN_USER2"]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    print("\n" + "="*60)
    print("  NCLPDLB — Live Showdown Training")
    print("="*60)
    print(f"  Format    : {args.format}")
    print(f"  Steps     : {args.timesteps:,}")
    print(f"  Player 1  : {u1}")
    print(f"  Player 2  : {u2}")
    print()
    print("  Watch live at: https://play.pokemonshowdown.com")
    print(f"  Search for '{u1}' or '{u2}' in the battle search")
    print("="*60 + "\n")

    from src.ml.train_policy import train
    from src.ml.showdown_modes import MODE_SHOWDOWN

    train(
        fmt=args.format,
        total_timesteps=args.timesteps,
        swap_every=args.swap_every,
        save_dir=Path(args.save_dir),
        resume=args.resume,
        team_format=args.team_format,
        server=MODE_SHOWDOWN,
        save_replays=args.save_replays,
    )


if __name__ == "__main__":
    main()
