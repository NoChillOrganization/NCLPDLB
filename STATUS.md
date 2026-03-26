# Pokemon Draft League Bot - Setup Status

**Last Updated:** 2026-03-23

---

## ✅ Completed

### Data & Configuration

- ✅ **Pokemon Database**: 1,025 Gen 1-9 Pokemon seeded in `data/pokemon.json`
- ✅ **Google Sheets**: 17 tabs created and configured
  - Setup, Rules, Cover, Draft, Draft Board, Pool A/B Boards
  - Schedule, Match Stats, Standings, Pokemon Stats, MVP Race
  - Transactions, Playoffs, Pokédex (populated with all 1,025 Pokemon), Team Template, Data
- ✅ **Configuration Files**: `.env` and `credentials.json` in place
- ✅ **Spreadsheet ID**: `16F9FP5wkyzDdF8C7vD9xwY2j2JkcWYR1EUK_MtRt7zs`

### Tests

- ✅ **Unit Tests**: All 41 tests in `test_analytics.py` and `test_battle_sim.py` pass
  - `analytics_service.py`: type chart, coverage, weakness, archetype, threat score, role detection
  - `battle_sim.py`: replay parsing, team comparison, matchup scoring

### Code & Documentation

- ✅ **ML Infrastructure**:
  - BattleEnv (singles) and BattleDoubleEnv (doubles/VGC)
  - train_policy.py with team-based training
  - train_all.py for sequential format training
  - teams.py with 5 pre-built teams × 10 formats
  - RotatingTeambuilder for custom team formats
- ✅ **Supported Formats**: gen9randombattle, gen9ou, gen9nationaldex, gen9monotype,
  gen9anythinggoes, gen9doublesou, gen9vgc2026regi, gen9vgc2026regf, gen7randombattle,
  gen6randombattle
- ✅ **Documentation**: README.md, docs/COMMANDS.md, docs/DEPLOYMENT.md
- ✅ **GitHub**: All code synced to <https://github.com/NoChillModeOnline/NCLPDLB.git>
- ✅ **Standalone .exe**: PyInstaller spec updated (`src/bot/NCLPDLB.spec`)

### Deployment

- ✅ **Standalone executable**: Build with `pyinstaller src/bot/NCLPDLB.spec`
- ✅ **No Docker or cloud infrastructure required**

---

## ⏸️ Blocked

### ML Training

- ⏸️ **PyTorch + stable-baselines3**: Cannot install on ARM64 Windows natively
- ⏸️ **All 10 format training**: Requires a Linux or x86 environment
- ⏸️ **Models**: None trained yet (requires ~8-12 hours once environment set up)

**Solution:** Run training on an x86 machine or a cloud VM with Python 3.11.

---

## 📋 Next Steps

### 1. Run the Bot

**From source:**

```bash
python src/bot/main.py
```

**From exe:**

```bash
# Build first
cd src/bot && pyinstaller NCLPDLB.spec

# Then run
src/bot/dist/NCLPDLB.exe
```

### 2. ML Training (Optional — for /spar)

```bash
# On x86 Linux/Windows with Python 3.11
pip install torch stable-baselines3
python -m src.ml.train_all
```

This trains all 10 formats sequentially:

- gen9randombattle (500k steps)
- gen9ou (500k steps)
- gen9doublesou (500k steps)
- gen9nationaldex (500k steps)
- gen9monotype (500k steps)
- gen9anythinggoes (500k steps)
- gen7randombattle (500k steps)
- gen6randombattle (500k steps)
- gen9vgc2026regi (500k steps)
- gen9vgc2026regf (500k steps)

Models saved to: `data/ml/policy/<format>/final_model.zip`

---

## 📊 Feature Availability

| Feature | Status |
|---------|--------|
| Draft (Snake/Auction/Tiered) | ✅ |
| Team Management | ✅ |
| Analytics & Coverage | ✅ |
| ELO & Matchmaking | ✅ |
| Replay Parsing | ✅ |
| `/spar` (Battle AI) | ⏸️ Needs trained models |

**49 out of 50 commands work without ML training.**

---

## 📞 Support

- **Documentation**: `README.md`, `docs/COMMANDS.md`, `docs/DEPLOYMENT.md`
- **GitHub**: <https://github.com/NoChillModeOnline/NCLPDLB>
- **Spreadsheet**: <https://docs.google.com/spreadsheets/d/16F9FP5wkyzDdF8C7vD9xwY2j2JkcWYR1EUK_MtRt7zs>
