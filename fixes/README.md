# NCLPDLB Audit Fixes

## How to apply

### Option A — Apply the patch (fastest)
```bash
cd F:\Claude Code\projects\pokemon-draft-bot
git checkout master && git pull
git checkout -b fix/audit-all-issues
git apply audit-fixes.patch
git push origin fix/audit-all-issues
```

### Option B — Run the PowerShell script
```powershell
# Copy audit-fixes.patch to your repo root first, then:
.\apply-fixes.ps1
```

### Option C — Copy files manually
Copy each .py file from this folder directly into your repo at the matching path.

## What's changed
| File | Fix |
|---|---|
| src/services/draft_service.py | Auction bid tracking implemented |
| src/ml/feature_extractor.py | stellar type added; /18→/19; comment fixed |
| src/ml/train_policy.py | 17x print() → log.info() |
| src/ml/train_all.py | 10x print() → log.info() |
| src/data/smogon.py | 4x print() → log |
| src/ml/replay_parser.py | 1x print() → log.warning() |
| src/ml/replay_scraper.py | 2x print() → log.info() |
| tmp/check_obs.py | f-string → rf-string |
| scripts/sync_commands.py | Backslash → forward slash in docstring |
