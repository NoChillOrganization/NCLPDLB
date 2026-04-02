"""
Behavioral Cloning Pre-Training — Phase 03 Plan (NOT YET IMPLEMENTED).

This module is a planning stub.  It documents the architecture, data pipeline,
and integration points for BC pre-training before PPO fine-tuning.  Implementation
requires the ``imitation`` library and a corpus of Showdown replay files.

═══════════════════════════════════════════════════════════════════════════════
 ARCHITECTURE OVERVIEW
═══════════════════════════════════════════════════════════════════════════════

  Replay files  ──▶  ReplayParser  ──▶  ActionResolver  ──▶  BC Dataset
       │                                                            │
       │                                                    (obs, expert_action)
       │                                                            │
       └──────────────────────────────────────────────────▶  imitation.BC
                                                                    │
                                                        actor-only weights (no value head)
                                                                    │
                                                         PPO.policy.load_actor(...)
                                                                    │
                                                     PPO fine-tune (ent_coef=0.05, 100k steps)

═══════════════════════════════════════════════════════════════════════════════
 DATA PIPELINE
═══════════════════════════════════════════════════════════════════════════════

Step 1 — Parse replays
    replay_parser.parse_replay_dir(replay_dir)  →  list[BattleRecord]

Step 2 — Resolve actions (the key gap identified in the Phase 03 audit)
    For each TurnSnapshot in BattleRecord:
      a) Reconstruct the battle state at that turn (obs = build_obs_from_snapshot(...))
      b) Map human-readable move name → action index:
           move_slot = active_pokemon.moveset.index(event.detail)
           action = 6 + move_slot            # no gimmick
           # OR: 22 + move_slot if tera event precedes move in turn.events
         For switches:
           switch_slot = team.index(event.detail)
           action = switch_slot              # 0-5

    Action mapping gap tracking:
      - "Unmappable" = move name not found in active Pokemon's moveset (team preview
        gap, transformed Pokemon, or mid-battle forme change).
      - Track: unmappable_count / total_turns.
      - Warn if gap > 5 %; abort if gap > 15 % (unless --force flag is set).

Step 3 — Build obs vectors from parsed state
    The replay parser produces human-readable state, not BattleEnv observations.
    Options:
      A. Mock-battle approach: reconstruct a poke-env AbstractBattle from parsed
         state and call build_observation().  Requires accurate HP, team, field state.
      B. Lightweight obs: derive the 48-dim vector directly from the parsed
         TurnSnapshot without poke-env objects (custom reconstruction function).
    Recommendation: Option B for portability; implement build_obs_from_snapshot()
    that mirrors build_observation() but accepts TurnSnapshot fields directly.

═══════════════════════════════════════════════════════════════════════════════
 BC TRAINING (imitation library)
═══════════════════════════════════════════════════════════════════════════════

    from imitation.algorithms.bc import BC
    from imitation.data import rollout
    from stable_baselines3 import PPO

    # Build SB3 PPO with MlpPolicy (same arch as production)
    policy = PPO("MlpPolicy", env, **PPO_HYPERPARAMS)

    # Build transitions from resolved (obs, action) pairs
    transitions = rollout.flatten_trajectories(expert_trajectories)

    # BC training — actor only
    bc_trainer = BC(
        observation_space=env.observation_space,
        action_space=env.action_space,
        demonstrations=transitions,
        policy=policy.policy,
        rng=np.random.default_rng(42),
    )
    bc_trainer.train(n_epochs=10)

    # Save actor weights, excluding value head
    actor_weights = {
        k: v for k, v in policy.policy.state_dict().items()
        if not k.startswith("value_net") and not k.startswith("mlp_extractor.value_net")
    }
    torch.save(actor_weights, "bc_actor.pt")

═══════════════════════════════════════════════════════════════════════════════
 PPO INTEGRATION
═══════════════════════════════════════════════════════════════════════════════

Load actor-only BC weights at PPO step 0:

    ppo_model = PPO("MlpPolicy", env, **PPO_HYPERPARAMS, ent_coef=0.05)
    bc_state = torch.load("bc_actor.pt")
    # Load with strict=False to skip value head keys missing from bc_state
    ppo_model.policy.load_state_dict(bc_state, strict=False)

    # Train with elevated entropy for first 100k steps to prevent premature collapse
    ppo_model.learn(total_timesteps=100_000, ...)

    # Then reduce ent_coef to standard 0.01 for the remainder
    ppo_model.ent_coef = 0.01
    ppo_model.learn(total_timesteps=remaining_timesteps, reset_num_timesteps=False, ...)

═══════════════════════════════════════════════════════════════════════════════
 ACTION MAPPING GAP TRACKING
═══════════════════════════════════════════════════════════════════════════════

    WARN_THRESHOLD  = 0.05   # 5 % unmappable turns
    ABORT_THRESHOLD = 0.15   # 15 % unmappable turns

    def check_mapping_gap(unmappable: int, total: int, force: bool = False) -> None:
        gap = unmappable / total if total > 0 else 0.0
        if gap > ABORT_THRESHOLD and not force:
            raise RuntimeError(
                f"Action mapping gap {gap:.1%} exceeds abort threshold "
                f"{ABORT_THRESHOLD:.0%}. Use --force to override."
            )
        if gap > WARN_THRESHOLD:
            log.warning(
                "Action mapping gap %.1f%% exceeds warn threshold %.0f%%.",
                gap * 100, WARN_THRESHOLD * 100,
            )

═══════════════════════════════════════════════════════════════════════════════
 BENCHMARK TARGETS (Phase 03)
═══════════════════════════════════════════════════════════════════════════════

  • BC-only (before PPO): > 50 % win rate vs RandomPlayer
  • After 200k PPO steps : > 85 % win rate vs RandomPlayer
  • After 500k PPO steps : > 65 % win rate vs MaxBasePowerPlayer

═══════════════════════════════════════════════════════════════════════════════
 CLI (planned)
═══════════════════════════════════════════════════════════════════════════════

  python -m src.ml.pretrain \\
      --replay-dir data/replays/gen9ou \\
      --format gen9ou \\
      --output bc_actor.pt \\
      [--force]          # bypass 15 % gap abort for research runs
      [--n-epochs 10]
      [--batch-size 64]

═══════════════════════════════════════════════════════════════════════════════
 IMPLEMENTATION TODO (ordered)
═══════════════════════════════════════════════════════════════════════════════

  1. build_obs_from_snapshot(snapshot: TurnSnapshot) -> np.ndarray
       Mirror build_observation() without live poke-env objects.
  2. ActionResolver.resolve(record: BattleRecord) -> list[tuple[np.ndarray, int]]
       Returns (obs, action_idx) pairs with gap tracking.
  3. check_mapping_gap(unmappable, total, force) — raise/warn as above.
  4. pretrain(replay_dir, fmt, output_path, force, n_epochs, batch_size)
       Full BC pipeline: parse → resolve → train → save actor weights.
  5. CLI entrypoint (__main__ block) with argparse.
  6. tests/unit/test_pretrain.py — unit tests for ActionResolver and gap tracking.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Action gap thresholds (used by the planned ActionResolver).
WARN_THRESHOLD  = 0.05   # 5 %  — log warning
ABORT_THRESHOLD = 0.15   # 15 % — raise RuntimeError unless force=True


def check_mapping_gap(unmappable: int, total: int, force: bool = False) -> float:
    """
    Validate action-mapping completeness; warn or abort on excessive gaps.

    Parameters
    ----------
    unmappable : int
        Number of turns whose move name could not be mapped to an action index.
    total : int
        Total number of turns processed.
    force : bool
        If True, downgrade an abort-threshold breach to a warning (research mode).

    Returns
    -------
    float
        The gap fraction (unmappable / total).
    """
    gap = unmappable / total if total > 0 else 0.0

    if gap > ABORT_THRESHOLD:
        msg = (
            f"Action mapping gap {gap:.1%} exceeds abort threshold "
            f"{ABORT_THRESHOLD:.0%}. "
            "Use --force to override for research runs."
        )
        if force:
            log.warning(msg)
        else:
            raise RuntimeError(msg)
    elif gap > WARN_THRESHOLD:
        log.warning(
            "Action mapping gap %.1f%% exceeds warn threshold %.0f%%.",
            gap * 100,
            WARN_THRESHOLD * 100,
        )

    return gap
