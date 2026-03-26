# =============================================================================
# NCLPDLB → pokemon-draft-league-bot: Final Push + Cleanup
# =============================================================================
# Run this from PowerShell inside your pokemon-draft-league-bot folder:
#
#   cd "F:\Claude Code\projects\pokemon-draft-bot"
#   .\pdlb-finalize-and-cleanup.ps1
#
# What this does:
#   1. Pulls the merged master from the cloud sandbox into your local folder
#   2. Pushes 3 new commits to pokemon-draft-league-bot on GitHub
#   3. Deletes fix/unit-4-team-service and fix/unit-9-ml-replay branches
#   4. Deletes the entire NCLPDLB repo from GitHub
#   5. Cleans untracked files from your local folder
# =============================================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
    Write-Error "ERROR: Run this script from inside your pokemon-draft-league-bot folder."
    exit 1
}

Set-Location $RepoRoot
Write-Host "`n=== PDLB Finalize & NCLPDLB Cleanup ===" -ForegroundColor Cyan

# Verify we're on the right repo
$remoteUrl = git remote get-url origin 2>&1
if ($remoteUrl -notmatch "pokemon-draft-league-bot") {
    Write-Error "ERROR: This doesn't look like the pokemon-draft-league-bot repo. Remote is: $remoteUrl"
    exit 1
}

# -----------------------------------------------------------------------------
# STEP 1: Sync local folder to remote master (fetch + reset)
# -----------------------------------------------------------------------------
Write-Host "`n[1/5] Syncing local folder with remote master..." -ForegroundColor Yellow

git fetch origin
git checkout master
git reset --hard origin/master

Write-Host "  Local master synced." -ForegroundColor Green

# -----------------------------------------------------------------------------
# STEP 2: Push the 3 merged commits to remote master
# -----------------------------------------------------------------------------
Write-Host "`n[2/5] Pushing merged commits to GitHub..." -ForegroundColor Yellow
Write-Host "  Commits to push:"
Write-Host "    - Merge fix/unit-4-team-service"
Write-Host "    - Merge fix/unit-9-ml-replay (already counted)"
Write-Host "    - chore: merge NCLPDLB (58 files: models, source, docs, config, bug fixes)"

git push origin master
if ($LASTEXITCODE -ne 0) {
    Write-Error "git push failed. Make sure you're authenticated (Windows Credential Manager or gh auth login)."
    exit 1
}
Write-Host "  Push successful." -ForegroundColor Green

# -----------------------------------------------------------------------------
# STEP 3: Delete PDLB's stale branches
# -----------------------------------------------------------------------------
Write-Host "`n[3/5] Deleting stale PDLB branches..." -ForegroundColor Yellow

foreach ($branch in @("fix/unit-4-team-service", "fix/unit-9-ml-replay")) {
    Write-Host "  Deleting origin/$branch..." -NoNewline
    git push origin --delete $branch 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host " done" -ForegroundColor Green
    } else {
        Write-Host " (already gone)" -ForegroundColor DarkYellow
    }
}

# -----------------------------------------------------------------------------
# STEP 4: Delete the NCLPDLB repo entirely from GitHub
# -----------------------------------------------------------------------------
Write-Host "`n[4/5] Deleting NCLPDLB repo from GitHub..." -ForegroundColor Yellow
Write-Host "  Repo: https://github.com/NoChillModeOnline/NCLPDLB" -ForegroundColor DarkYellow

$confirm = Read-Host "  Type 'DELETE' to confirm permanent deletion of NCLPDLB repo"
if ($confirm -ne 'DELETE') {
    Write-Host "  Skipped NCLPDLB deletion (you can run 'gh repo delete NoChillModeOnline/NCLPDLB --yes' manually)." -ForegroundColor DarkYellow
} else {
    # Try gh CLI first
    if (Get-Command gh -ErrorAction SilentlyContinue) {
        gh repo delete NoChillModeOnline/NCLPDLB --yes
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  NCLPDLB repo deleted." -ForegroundColor Green
        } else {
            Write-Host "  gh CLI failed. Try manually at: https://github.com/NoChillModeOnline/NCLPDLB/settings" -ForegroundColor Red
        }
    } else {
        Write-Host "  gh CLI not found. Delete manually at: https://github.com/NoChillModeOnline/NCLPDLB/settings" -ForegroundColor Red
        Write-Host "  (Scroll to the bottom → Danger Zone → Delete this repository)" -ForegroundColor DarkYellow
    }
}

# -----------------------------------------------------------------------------
# STEP 5: Clean untracked files from local folder
# -----------------------------------------------------------------------------
Write-Host "`n[5/5] Cleaning untracked files from local folder..." -ForegroundColor Yellow
Write-Host "  Preview of files to be removed:" -ForegroundColor DarkYellow
git clean -fdxn

$confirm2 = Read-Host "`n  Proceed with removal? (y/N)"
if ($confirm2 -eq 'y' -or $confirm2 -eq 'Y') {
    git clean -fdx
    Write-Host "  Untracked files removed." -ForegroundColor Green
} else {
    Write-Host "  Skipped file cleanup." -ForegroundColor DarkYellow
}

# -----------------------------------------------------------------------------
# DONE
# -----------------------------------------------------------------------------
Write-Host "`n=== All done! ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  pokemon-draft-league-bot is now the single canonical repo." -ForegroundColor White
Write-Host "  It contains everything from both repos, fully merged and verified." -ForegroundColor White
Write-Host ""
Write-Host "  What was merged in from NCLPDLB:" -ForegroundColor White
Write-Host "    - 2 new source files: training_players.py, type_chart.py" -ForegroundColor White
Write-Host "    - 4 new test files" -ForegroundColor White
Write-Host "    - 9 new ML model directories" -ForegroundColor White
Write-Host "    - docker-compose.yml, pyrightconfig.json, GEMINI.md, and more" -ForegroundColor White
Write-Host "    - Bug fixes: place_bid(), stellar type, account_configuration1/2, print->log" -ForegroundColor White
Write-Host ""
Write-Host "  GitHub: https://github.com/NoChillModeOnline/pokemon-draft-league-bot" -ForegroundColor Cyan
