# Architecture Patterns

**Domain:** RL Pokemon battle bot — BC pre-training + obs expansion + curriculum integration
**Researched:** 2026-03-17
**Milestone type:** SUBSEQUENT (integrating into existing PPO pipeline)

---

## Existing System Overview

```
replay_scraper.py
      |
      v
replay_parser.py  --> BattleRecord objects (turn-by-turn events)
      |
      v
feature_extractor.py  --> state feature arrays (float[])
      |
      v
battle_env.py          BattleEnv(SinglesEnv), OBS_DIM=44
  calc_reward()          +1 win, -1 loss, +0.3/faint
      |
      v
train_policy.py        PPO + SelfPlayCallback (swap opponent every 50k steps)
                       SelfPlayOpponent starts as RandomPlayer
```

---

## Change 1: OBS_DIM Expansion — Type Effectiveness

### What Changes

Add `type_effectiveness[0..3]` — one float per move slot — expanding OBS_DIM from 44 to 48.

### Component Boundaries

| File | Change |
|------|--------|
| `type_chart.py` (new) | Lookup table: `TYPE_CHART[atk_type][def_type] -> float` |
| `feature_extractor.py` | Call `TYPE_CHART` to compute effectiveness per move slot |
| `battle_env.py` | Update `OBS_DIM = 48` constant |

### Data Flow for Type Effectiveness

```
Battle state (move list + active opponent pokemon)
      |
      v
feature_extractor.py
  for slot in [0..3]:
    move_type = battle.available_moves[slot].type
    opp_types = battle.opponent_active_pokemon.types  # tuple of 1-2 Types
    eff = 1.0
    for t in opp_types:
        eff *= TYPE_CHART[move_type][t]
    type_effectiveness[slot] = eff   # 0.0 / 0.25 / 0.5 / 1.0 / 2.0 / 4.0
      |
      v
obs vector: [...existing 44 dims..., eff_0, eff_1, eff_2, eff_3]
```

### Implementation Notes

- Use `poke-env`'s `PokemonType` enum as keys — avoids string matching bugs.
- Cap/normalize: divide by 4.0 to keep values in [0.0, 1.0] for stable training.
- If fewer than 4 moves available, pad with `1.0` (neutral), same pattern as existing move slots.
- `OBS_DIM` is referenced in both `battle_env.py` (observation space definition) and
  `pretrain.py` (new). Keep it as a single shared constant, importable from `battle_env.py`.

### Pitfall

Any saved PPO checkpoint trained with OBS_DIM=44 is incompatible with OBS_DIM=48. The obs
expansion must happen at the same time as the BC pre-train step — the BC checkpoint and the PPO
policy must agree on obs dimensionality. Do not mix checkpoints across this boundary.

---

## Change 2: Curriculum — MaxDamagePlayer at Epoch 0

### poke-env API (MEDIUM confidence)

`SinglesEnv` wraps two players. The opponent is set via `SingleAgentWrapper(_env, _opponent: Player)`.
`MaxDamagePlayer` is a `Player` subclass — it can be passed as the opponent argument.

`SelfPlayCallback` in `train_policy.py` currently calls something like:

```python
opponent = RandomPlayer(battle_format=battle_format)
env = BattleEnv(opponent=opponent)
```

### Recommended Change

```python
# train_policy.py — opponent selection at startup
from poke_env.player import MaxDamagePlayer, RandomPlayer

def build_opponent(epoch: int, battle_format: str) -> Player:
    if epoch == 0:
        return MaxDamagePlayer(battle_format=battle_format)
    else:
        return SelfPlayOpponent(...)   # existing self-play logic

# Pass to BattleEnv constructor
opponent = build_opponent(epoch=args.epoch, battle_format=BATTLE_FORMAT)
env = BattleEnv(opponent=opponent)
```

### Curriculum Progression (Recommended)

```
Epoch 0:  MaxDamagePlayer      (simple greedy — teaches basic damage/type awareness)
Epoch 1+: SelfPlayOpponent     (existing self-play loop, swaps every 50k steps)
```

This is a one-time conditional at startup, not a dynamic swap mid-training. The SelfPlayCallback
continues to manage opponent swaps within epochs 1+. No changes to SelfPlayCallback internals
are needed for this milestone.

### Component Boundary

Only `train_policy.py` changes. `battle_env.py` accepts whatever `Player` is passed in —
`MaxDamagePlayer` requires no special handling.

---

## Change 3: BC Pre-Training — The Core Architectural Question

### Problem Statement

SB3 PPO uses `ActorCriticPolicy` which has:

```
features_extractor   (shared or split)
      |
      v
mlp_extractor        (separate latent dims for actor / critic)
  |- forward_actor() -> latent_pi
  |- forward_critic() -> latent_vf
      |
      v
action_net           (actor head: outputs action logits)
value_net            (critic head: outputs scalar value)
```

BC only trains the actor (move prediction from obs). The value head has no BC signal.
The question is how to initialize the PPO policy's actor weights from a BC checkpoint
without forking SB3.

### Recommended Architecture: Partial State Dict Copy (Option B)

This is the cleanest approach that does not fork SB3.

**Step 1 — pretrain.py trains a standalone actor network:**

```python
# pretrain.py
import torch
import torch.nn as nn
from stable_baselines3 import PPO
from battle_env import BattleEnv, OBS_DIM

# Build a throwaway PPO instance just to get the right architecture
dummy_env = build_dummy_env()
bc_model = PPO('MlpPolicy', dummy_env, verbose=0)

# bc_model.policy now has: mlp_extractor, action_net, value_net
# Train only action_net + mlp_extractor.forward_actor path

optimizer = torch.optim.Adam(
    list(bc_model.policy.mlp_extractor.parameters()) +
    list(bc_model.policy.action_net.parameters()),
    lr=3e-4
)

for obs_batch, action_batch in dataloader:
    dist = bc_model.policy.get_distribution(obs_batch)
    log_prob = dist.log_prob(action_batch)
    loss = -log_prob.mean()      # NLL / cross-entropy for discrete actions
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()

# Save only the actor-relevant weights
actor_state = {
    k: v for k, v in bc_model.policy.state_dict().items()
    if k.startswith('mlp_extractor') or k.startswith('action_net')
}
torch.save(actor_state, 'bc_actor_checkpoint.pt')
```

**Step 2 — train_policy.py loads BC weights into PPO actor:**

```python
# train_policy.py — when --pretrain flag is set
if args.pretrain:
    bc_state = torch.load(args.pretrain)          # partial state dict
    full_state = ppo_model.policy.state_dict()
    full_state.update(bc_state)                   # overwrite actor keys only
    ppo_model.policy.load_state_dict(full_state, strict=True)
    # value_net weights are untouched — remain randomly initialized
```

**Why this works without forking SB3:**

- `load_state_dict(strict=True)` still works because `full_state` is a complete dict
  (we updated keys in place, not removed any).
- Value head starts from random init — this is correct. BC provides no value signal.
  PPO will train the value head from scratch via TD bootstrapping.
- `mlp_extractor` is shared in SB3's default MlpPolicy, so BC pre-training the shared
  extractor also warm-starts the critic's feature extraction path. This is acceptable
  and typically beneficial.

### Alternative: `share_features_extractor=False`

If you want a clean separation (actor extractor BC-trained, critic extractor random):

```python
ppo_model = PPO(
    'MlpPolicy',
    env,
    policy_kwargs={'share_features_extractor': False}
)
```

Then BC trains only `pi_features_extractor` + `action_net`. More principled but adds
complexity. Not necessary for this milestone — the shared extractor approach is sufficient.

### How --pretrain Flag Should Work

Use it as a **custom init**, not as a resume. Resume (`--resume`) loads a full SB3 zip
including optimizer state, step counters, and value head weights. BC init should only
set network weights, then let PPO train from step 0.

```python
# train_policy.py argument handling
parser.add_argument('--pretrain', type=str, default=None,
    help='Path to BC actor checkpoint (.pt). Initializes policy actor weights before PPO training.')
parser.add_argument('--resume', type=str, default=None,
    help='Path to full SB3 PPO checkpoint (.zip). Resumes training from saved state.')

# Mutual exclusion — these two flags conflict
if args.pretrain and args.resume:
    raise ValueError('--pretrain and --resume are mutually exclusive')
```

The `--pretrain` path:
1. Build PPO model normally (random init)
2. Load BC partial state dict into actor weights
3. Start PPO training from timestep 0

The `--resume` path:
1. `PPO.load(args.resume, env=env)` — existing SB3 mechanism, unchanged

### pretrain.py Data Pipeline

```
replay_scraper.py / existing scraped replays
      |
      v
replay_parser.py  --> List[BattleRecord]
      |
      v
feature_extractor.py  --> obs arrays (float[OBS_DIM])  <-- must use OBS_DIM=48
      |
      v
action labels: index of chosen move in [0..3]
  (from BattleRecord.turns[i].action — which move was actually played)
      |
      v
torch.utils.data.DataLoader  (obs_batch, action_batch)
      |
      v
BC training loop in pretrain.py
      |
      v
bc_actor_checkpoint.pt
```

### Key Constraint: Action Space Alignment

The BC action labels must use the same action indexing as `BattleEnv.action_space`. Verify that
`feature_extractor.py`'s move ordering matches `battle_env.py`'s action ordering. If they differ,
BC-trained logits will map to wrong moves when loaded into PPO. This is the highest-risk
integration point.

---

## Full Component Map After All 3 Changes

```
type_chart.py          (NEW) TYPE_CHART lookup table
      |
      v
feature_extractor.py   (MODIFIED) +type_effectiveness[0..3], OBS_DIM awareness
      |
      v
battle_env.py          (MODIFIED) OBS_DIM = 48 constant
      |
      v
pretrain.py            (NEW) BC training loop
  - loads BattleRecords via replay_parser
  - calls feature_extractor for obs (OBS_DIM=48)
  - trains PPO actor via NLL loss
  - saves bc_actor_checkpoint.pt
      |
      v
train_policy.py        (MODIFIED)
  - --pretrain flag: partial weight load into PPO actor
  - --resume flag: unchanged SB3 zip load
  - epoch 0 opponent: MaxDamagePlayer instead of RandomPlayer
      |
      v
SelfPlayCallback       (UNCHANGED) manages opponent swaps in epochs 1+
```

---

## Architecture Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| BC weight loading | Partial state dict update, `load_state_dict(strict=True)` | No SB3 fork required |
| Feature extractor sharing | Keep shared (default SB3) | Simpler; BC warm-starts critic extractor too |
| Value head init after BC | Random (untouched) | No BC signal for value; PPO trains it from scratch |
| `--pretrain` vs `--resume` | Mutually exclusive; pretrain = custom init at step 0 | Semantically distinct operations |
| Type effectiveness normalization | Divide by 4.0 → [0.0, 1.0] | Consistent with rest of obs vector |
| OBS_DIM location | Single constant in `battle_env.py`, imported by `pretrain.py` | Single source of truth |
| Epoch 0 opponent | MaxDamagePlayer (startup conditional) | No SelfPlayCallback changes needed |

---

## Scalability Considerations

| Concern | Now | If scaled |
|---------|-----|-----------|
| BC dataset size | Replay files on disk, loaded in memory | Use DataLoader with file streaming |
| OBS_DIM changes | Constant in one file | Would need obs versioning if multiple checkpoints coexist |
| Curriculum stages | 2-stage (MaxDamage → SelfPlay) | Add stage parameter to `build_opponent()` |

---

## Sources

- [SB3 ActorCriticPolicy source](https://stable-baselines3.readthedocs.io/en/master/_modules/stable_baselines3/common/policies.html) — MEDIUM confidence (fetched 2026-03-17)
- [poke-env env module docs](https://poke-env.readthedocs.io/en/stable/modules/env.html) — MEDIUM confidence (fetched 2026-03-17)
- [poke-env RL with Gymnasium wrapper example](https://poke-env.readthedocs.io/en/stable/examples/rl_with_gymnasium_wrapper.html) — MEDIUM confidence
- SB3 `share_features_extractor` flag: HIGH confidence (official SB3 docs, `policy_kwargs`)
- `load_state_dict(strict=True)` partial update pattern: HIGH confidence (standard PyTorch)
