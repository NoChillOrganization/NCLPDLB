# Setting Up a Local Pokemon Showdown Server

The RL training script (`src/ml/train_policy.py`) requires a local
Pokemon Showdown server so the bot can play battles against itself
without hitting the public server's rate limits.

## Prerequisites

- Node.js 18+ — [nodejs.org](https://nodejs.org)
- Git

## Installation

```bash
# 1. Clone the Showdown repository
git clone https://github.com/smogon/pokemon-showdown.git
cd pokemon-showdown

# 2. Install dependencies
npm install

# 3. Copy the default config
cp config/config-example.js config/config.js
```

## Configuration

Edit `config/config.js` and set:

```js
exports.port = 8000;
exports.bindaddress = '127.0.0.1';
exports.workers = 1;

// Allow any account name for bot logins
exports.noipchecks = true;
exports.nothrottle = true;
```

## Running

```bash
# Start the server (keep this running while training)
node pokemon-showdown start --no-security

# Verify it's running — open: http://localhost:8000
```

## Training with the local server

Once the server is running on `ws://localhost:8000`, start training:

```bash
python -m src.ml.train_policy \
    --format gen9randombattle \
    --timesteps 500000

# Monitor with TensorBoard:
tensorboard --logdir data/ml/policy/gen9randombattle/tb_logs
```

## Notes

- The local server is **only needed for training** (self-play).
- For `/spar` live battles, the bot connects to the public
  `wss://sim3.psim.us` server using the configured Showdown account.
- Keep the Showdown server version in sync with the poke-env version
  you are using — check [poke-env releases](https://github.com/hsahovic/poke-env/releases)
  for compatible server versions.
