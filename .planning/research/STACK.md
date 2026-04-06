# Technology Stack

**Project:** NCLPDLB ML Knowledge Injection
**Researched:** 2026-03-17
**Mode:** Subsequent milestone (adding to existing system)

## Existing Stack (Verified)

| Technology | Version | Purpose |
|------------|---------|---------|
| poke-env | 0.12.1 (latest, Mar 16 2026) | Pokemon battle environment + player classes |
| stable-baselines3 | current | PPO training |
| Python | 3.x | Runtime |
| aiohttp | current | Async replay scraping |
| GitHub Actions | — | CI training runs |

## Research Findings

### 1. poke-env Heuristic Player — VERIFIED

**Answer: Use `MaxBasePowerPlayer`**

Confirmed in `poke-env/src/poke_env/player/baselines.py`. The class exists and overrides
`choose_move()` with static helpers `choose_singles_move()` and `choose_doubles_move()`.

There is NO class named `MaxDamagePlayer` in poke-env. The correct class name is:

```python
from poke_env.player import MaxBasePowerPlayer
```

**API signature (from baselines.py):**

```python
class MaxBasePowerPlayer(Player):
    def choose_move(self, battle) -> str: ...
    @staticmethod
    def choose_singles_move(battle) -> str: ...
    @staticmethod
    def choose_doubles_move(battle) -> str: ...
```

Instantiation for curriculum use:

```python
opponent = MaxBasePowerPlayer(battle_format="gen9randombattle")
```

The PROJECT.md constraint note was correct: `MaxBasePowerPlayer` exists; `MaxDamagePlayer` does not.
Confidence: HIGH (verified against source file).

Other baseline players available: `RandomPlayer`, `SimpleHeuristicsPlayer`.

---

### 2. Behavioral Cloning Pre-training — VERIFIED

**Answer: Use the `imitation` library**

The `imitation` library (CHAI / DLR-RM) is the standard approach. It builds directly on
stable-baselines3 and provides `BC` (Behavioral Cloning), DAgger, GAIL, and AIRL.
SB3's own docs explicitly defer to `imitation` for BC — there is no built-in BC in SB3 itself.

```bash
pip install imitation
```

**`BC` class constructor:**

```python
from imitation.algorithms import bc
from imitation.data import rollout

bc_trainer = bc.BC(
    observation_space=env.observation_space,
    action_space=env.action_space,
    rng=np.random.default_rng(seed),
    demonstrations=transitions,   # imitation.data.types.Transitions
    batch_size=32,
    optimizer_cls=torch.optim.Adam,
    ent_weight=0.001,
    l2_weight=0.0,
    device="auto",
)
bc_trainer.train(n_epochs=10)
```

**Key: Loading BC policy into PPO**

The BC trainer exposes `bc_trainer.policy` which returns an `ActorCriticPolicy` object.
To transfer weights into a PPO model:

```python
# After BC training:
bc_policy = bc_trainer.policy

# Load into PPO — copy state dict directly:
ppo_model = PPO("MlpPolicy", env)
ppo_model.policy.load_state_dict(bc_policy.state_dict())
```

Alternatively, save/load via file:

```python
bc_trainer.policy.save("bc_checkpoint.pt")
# Then in train_policy.py with --pretrain flag:
ppo_model.policy.load_state_dict(torch.load("bc_checkpoint.pt"))
```

**Input format — `Transitions` object:**

```python
from imitation.data.types import Transitions

transitions = Transitions(
    obs=np.array([...]),         # shape (N, OBS_DIM)
    acts=np.array([...]),        # shape (N,) — integer actions 0-25
    infos=np.array([{}] * N),
    next_obs=np.array([...]),    # shape (N, OBS_DIM)
    dones=np.array([...]),       # shape (N,) bool
)
```

The `feature_extractor.py` already produces numpy arrays from `BattleRecord` objects —
the main integration work is mapping those arrays into `Transitions` format and ensuring
action integers (0-25) match the PPO action space exactly.

Confidence: HIGH (official SB3 docs + imitation readthedocs verified).

---

### 3. Gen 9 Type Chart (18x18) — HIGH confidence

Types (index 0-17): Normal, Fire, Water, Electric, Grass, Ice, Fighting, Poison, Ground,
Flying, Psychic, Bug, Rock, Ghost, Dragon, Dark, Steel, Fairy

**Effectiveness matrix — rows = attacking type, cols = defending type**
Values: 2.0 = super effective, 0.5 = not very effective, 0.0 = immune, 1.0 = normal

```python
# Shape: (18, 18) — TYPE_CHART[atk_idx][def_idx]
TYPE_CHART = [
# Nor  Fir  Wat  Ele  Gra  Ice  Fig  Poi  Gro  Fly  Psy  Bug  Roc  Gho  Dra  Dar  Ste  Fai
  [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.5, 0.0, 1.0, 1.0, 0.5, 1.0],  # Normal
  [1.0, 0.5, 0.5, 1.0, 2.0, 2.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 0.5, 1.0, 0.5, 1.0, 2.0, 1.0],  # Fire
  [1.0, 2.0, 0.5, 1.0, 0.5, 1.0, 1.0, 1.0, 2.0, 1.0, 1.0, 1.0, 2.0, 1.0, 0.5, 1.0, 1.0, 1.0],  # Water
  [1.0, 1.0, 2.0, 0.5, 0.5, 1.0, 1.0, 1.0, 0.0, 2.0, 1.0, 1.0, 1.0, 1.0, 0.5, 1.0, 1.0, 1.0],  # Electric
  [1.0, 0.5, 2.0, 1.0, 0.5, 1.0, 1.0, 0.5, 2.0, 0.5, 1.0, 0.5, 2.0, 1.0, 0.5, 1.0, 0.5, 1.0],  # Grass
  [1.0, 0.5, 0.5, 1.0, 2.0, 0.5, 1.0, 1.0, 2.0, 2.0, 1.0, 1.0, 1.0, 1.0, 2.0, 1.0, 0.5, 1.0],  # Ice
  [2.0, 1.0, 1.0, 1.0, 1.0, 2.0, 1.0, 0.5, 1.0, 0.5, 0.5, 0.5, 2.0, 0.0, 1.0, 2.0, 2.0, 0.5],  # Fighting
  [1.0, 1.0, 1.0, 1.0, 2.0, 1.0, 1.0, 0.5, 0.5, 1.0, 1.0, 1.0, 0.5, 0.5, 1.0, 1.0, 0.0, 2.0],  # Poison
  [1.0, 2.0, 1.0, 2.0, 0.5, 1.0, 1.0, 2.0, 1.0, 0.0, 1.0, 0.5, 2.0, 1.0, 1.0, 1.0, 2.0, 1.0],  # Ground
  [1.0, 1.0, 1.0, 0.5, 2.0, 1.0, 2.0, 1.0, 1.0, 1.0, 1.0, 2.0, 0.5, 1.0, 1.0, 1.0, 0.5, 1.0],  # Flying
  [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 1.0, 1.0, 0.5, 1.0, 1.0, 1.0, 1.0, 0.0, 0.5, 1.0],  # Psychic
  [1.0, 0.5, 1.0, 1.0, 2.0, 1.0, 0.5, 0.5, 1.0, 0.5, 2.0, 1.0, 1.0, 0.5, 1.0, 2.0, 0.5, 0.5],  # Bug
  [1.0, 2.0, 1.0, 1.0, 1.0, 2.0, 0.5, 1.0, 0.5, 2.0, 1.0, 2.0, 1.0, 1.0, 1.0, 1.0, 0.5, 1.0],  # Rock
  [0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 1.0, 1.0, 2.0, 1.0, 0.5, 1.0, 1.0],  # Ghost
  [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 1.0, 0.5, 0.0],  # Dragon
  [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.5, 1.0, 1.0, 1.0, 2.0, 2.0, 1.0, 0.5, 1.0, 0.5, 1.0, 0.5],  # Dark
  [1.0, 0.5, 0.5, 0.5, 1.0, 2.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 1.0, 1.0, 1.0, 0.5, 2.0],  # Steel
  [1.0, 0.5, 1.0, 1.0, 1.0, 1.0, 2.0, 0.5, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 0.5, 0.5],  # Fairy
]

TYPE_NAMES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
]
TYPE_TO_IDX = {t: i for i, t in enumerate(TYPE_NAMES)}
```

For the obs vector: given move type index and opponent active type indices, look up
`TYPE_CHART[move_type_idx][opponent_type1_idx]` (and type2 if dual-typed, multiply).

Confidence: HIGH (Gen 9 chart is stable — no type changes since Gen 6 introduced Fairy).

---

### 4. OBS_DIM Change and Checkpoint Incompatibility — VERIFIED

**Answer: Changing OBS_DIM invalidates all saved checkpoints. This is hard-incompatible.**

When SB3 saves a PPO model, the policy network weights are serialized with specific layer
dimensions derived from `observation_space.shape[0]`. Loading an OBS_DIM=44 checkpoint
into an OBS_DIM=48 environment raises a shape mismatch error at `model.set_parameters()`
or `model.load()` time. There is no built-in migration path.

Confirmed in SB3 GitHub issue #2031: "Can a model be used in environments with different
observation_space sizes?" — answer is no without a custom feature extractor workaround.

**Practical implications for this milestone:**

1. Any existing checkpoints trained at OBS_DIM=44 are abandoned after the type-chart change.
2. BC pre-training must use OBS_DIM=48 (the new size) — the `Transitions.obs` arrays must
   be built with the expanded feature extractor, not the old one.
3. If rollback is needed, keep old checkpoints in a separate directory; do not overwrite.
4. GitHub Actions CI must clear checkpoint cache or use a new checkpoint path after the
   OBS_DIM bump to avoid cryptic load errors on the first post-change run.

Confidence: HIGH (SB3 source + official issue tracker verified).

---

### 5. Observation Space Expansion Design

**Recommended: 4 floats, one per move slot**

Each float = `effectiveness(move_type, opponent_active_type)` clamped to `[0.0, 2.0]`
(or log-scaled). For dual-typed opponents: multiply both type matchups.

```
OBS layout change:
  OLD: [...44 features...]
  NEW: [...44 features..., eff_move0, eff_move1, eff_move2, eff_move3]
       OBS_DIM = 48 (singles), OBS_DIM_DOUBLES = 76
```

poke-env exposes `battle.available_moves` (list of `Move` objects) with `.type` attribute,
and `battle.opponent_active_pokemon.type_1` / `.type_2`. Use these in `embed_battle()`.

---

## Recommended Add/Install

```bash
pip install imitation          # BC pre-training
# poke-env 0.12.1 already satisfies MaxBasePowerPlayer requirement
# stable-baselines3 — no version change needed
```

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| BC library | `imitation` | Custom supervised loop | imitation has SB3-native Transitions/policy types; custom loop requires manually matching policy architecture |
| BC library | `imitation` | SB3 built-in | SB3 does not have built-in BC in v2.x; its own docs link to `imitation` |
| Curriculum opponent | `MaxBasePowerPlayer` | `SimpleHeuristicsPlayer` | SimpleHeuristics is stronger but harder to beat at epoch 0; MaxBasePower is the right difficulty step |
| Type chart storage | Inline 18x18 matrix | PokéAPI lookup | Zero latency, no network dep, chart is static for Gen 9 |

## Sources

- poke-env PyPI (latest version): https://pypi.org/project/poke-env/
- poke-env baselines.py (player classes): https://github.com/hsahovic/poke-env/blob/master/src/poke_env/player/baselines.py
- imitation BC docs: https://imitation.readthedocs.io/en/latest/algorithms/bc.html
- imitation BC tutorial: https://imitation.readthedocs.io/en/stable/tutorials/1_train_bc.html
- SB3 imitation learning guide: https://stable-baselines3.readthedocs.io/en/master/guide/imitation.html
- SB3 obs space incompatibility issue #2031: https://github.com/DLR-RM/stable-baselines3/issues/2031
