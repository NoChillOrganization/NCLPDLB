# Pokemon Draft League Bot - Setup Status

**Last Updated:** 2026-06-09

---

## ✅ Completed

### Data & Configuration

- ✅ **Pokemon Database**: 1,025 Gen 1-9 Pokemon seeded in `data/pokemon.json`
- ✅ **Google Sheets**: 17 tabs created and configured
  - Setup, Rules, Cover, Draft, Draft Board, Pool A/B Boards
  - Schedule, Match Stats, Standings, Pokemon Stats, MVP Race
  - Transactions, Playoffs, Pokédex (populated with all 1,025 Pokemon), Team Template, Data
- ✅ **Configuration Files**: `.env` and `credentials.json` in place
- ✅ **Spreadsheet ID**: set via `GOOGLE_SHEETS_SPREADSHEET_ID` in `.env`

### Tests

- ✅ **Unit Tests**: 1,495 tests collected, 0 collection errors

### Code & Documentation

- ✅ **ML Infrastructure** (AlphaZero-style Transformer + MCTS):
  - `transformer_model.py` — BattleTransformer policy + value heads
  - `train_transformer.py` — Transformer training loop
  - `mcts.py` — Monte Carlo Tree Search decision engine
  - `self_play.py` — Async self-play loop
  - `showdown_client.py` — 3-layer WebSocket client
- ✅ **Supported Formats**: 20 formats across Singles, Doubles, and Champions tiers
  (see `.github/workflows/train-models.yml` matrix for full list)
- ✅ **Documentation**: README.md, docs/COMMANDS.md, docs/DEPLOYMENT.md
- ✅ **GitHub**: All code synced to <https://github.com/NoChillModeOnline/NCLPDLB.git>
- ✅ **Standalone .exe**: PyInstaller spec at `src/bot/NCLPDLB.spec`

### Deployment

- ✅ **Standalone executable**: Build with `pyinstaller src/bot/NCLPDLB.spec`
- ✅ **No Docker or cloud infrastructure required**

---

## ✅ ML Training Environment

### Environment

- ✅ **PyTorch + stable-baselines3**: Installed via `.venv` (CPU wheel)
- ✅ **Showdown server**: Required at `ws://localhost:8000` for local training;
  ladder training uses `play.pokemonshowdown.com`
- ✅ **20 formats** in the CI training matrix
- ✅ **Models**: `src/ml/models/transformer_checkpoint.pt` (current active model)
- ⚠️ **Checkpoint break (ISS-007 + ISS-008)**: `OBS_DIM` changed 48 → 78 across
  `feat/obs-dim-53-stab-speed` and `feat/obs-ability-item`. Existing 48-dim and
  53-dim checkpoints are **incompatible** with the new observation space. One fresh
  78-dim training run covers both expansions.

See `docs/DEPLOYMENT.md` → *ML Training Environment* for full setup instructions.

---

## 📋 Next Steps

### 1. Run the Bot

**From source:**

```bash
python src/bot/main.py
```

**From exe:**

```bash
cd src/bot && pyinstaller NCLPDLB.spec
src/bot/dist/NCLPDLB.exe
```

### 2. ML Training (Optional — for /spar)

```bash
# Trigger via GitHub Actions (recommended — uses self-hosted Windows runner)
# Go to Actions → Train ML Models → Run workflow

# Or run locally:
python -m src.ml.run_training
```

Trains all 20 formats. Models saved to `src/ml/models/transformer_checkpoint.pt`.

---

## 📊 Feature Availability

| Feature | Status |
|---------|--------|
| Draft (Snake/Auction/Tiered) | ✅ |
| Team Management | ✅ |
| Analytics & Coverage | ✅ |
| ELO & Matchmaking | ✅ |
| Replay Parsing | ✅ |
| `/spar` (Battle AI) | ⏸️ Needs trained model at `src/ml/models/transformer_checkpoint.pt` |

---

## 📞 Support

- **Documentation**: `README.md`, `docs/COMMANDS.md`, `docs/DEPLOYMENT.md`
- **GitHub**: <https://github.com/NoChillModeOnline/NCLPDLB>
- **Spreadsheet**: set `GOOGLE_SHEETS_SPREADSHEET_ID` in `.env`
