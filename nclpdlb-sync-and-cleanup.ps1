# =============================================================================
# NCLPDLB — Sync Local Folder to Clean Master + Delete All Remote Branches
# =============================================================================
# Run this from PowerShell in the repo root:
#   cd "F:\Claude Code\projects\pokemon-draft-bot"
#   .\nclpdlb-sync-and-cleanup.ps1
#
# What this does:
#   1. Pulls the merged master from GitHub (all audit fixes + branch changes)
#   2. Removes any local files/folders not tracked by the clean master
#   3. Deletes all 21 remote branches, leaving only master
# =============================================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
    Write-Error "ERROR: Not a git repo. Run this script from inside F:\Claude Code\projects\pokemon-draft-bot"
    exit 1
}

Set-Location $RepoRoot
Write-Host "`n=== NCLPDLB Branch Consolidation Script ===" -ForegroundColor Cyan

# -----------------------------------------------------------------------------
# STEP 1: Fetch latest from origin and reset local master to match remote
# -----------------------------------------------------------------------------
Write-Host "`n[1/3] Syncing local master with remote..." -ForegroundColor Yellow

git fetch origin
if ($LASTEXITCODE -ne 0) { Write-Error "git fetch failed"; exit 1 }

git checkout master
if ($LASTEXITCODE -ne 0) { Write-Error "git checkout master failed"; exit 1 }

# Hard reset to exactly match remote master (includes all merged fixes)
git reset --hard origin/master
if ($LASTEXITCODE -ne 0) { Write-Error "git reset failed"; exit 1 }

Write-Host "  Local master is now synced to remote master." -ForegroundColor Green

# -----------------------------------------------------------------------------
# STEP 2: Clean untracked files/folders not in master
# -----------------------------------------------------------------------------
Write-Host "`n[2/3] Removing untracked files not in master..." -ForegroundColor Yellow

# -f = force, -d = remove untracked dirs, -x = remove ignored files too
# Dry run first so you can see what will be removed
Write-Host "  Preview of files to be removed:" -ForegroundColor DarkYellow
git clean -fdxn

$confirm = Read-Host "`n  Proceed with removal? (y/N)"
if ($confirm -ne 'y' -and $confirm -ne 'Y') {
    Write-Host "  Skipped file cleanup." -ForegroundColor DarkYellow
} else {
    git clean -fdx
    if ($LASTEXITCODE -ne 0) { Write-Error "git clean failed"; exit 1 }
    Write-Host "  Untracked files removed." -ForegroundColor Green
}

# -----------------------------------------------------------------------------
# STEP 3: Delete all remote branches except master
# -----------------------------------------------------------------------------
Write-Host "`n[3/3] Deleting remote branches..." -ForegroundColor Yellow

$branchesToDelete = @(
    "fix-vgc-item-clause",
    "fix-vgc-teampreview",
    "fix/account-config",
    "fix/audit-all-issues",
    "fix/drop-obtainable-and-dedup-moves",
    "fix/gen9zu-dedupe",
    "fix/remove-conda-workflow",
    "fix/revert-to-local-server",
    "fix/teams-and-browser-mode",
    "fix/train-models-workflow",
    "fix/unit-1-models-config",
    "fix/unit-10-integration-e2e",
    "fix/unit-2-draft-service",
    "fix/unit-3-elo-service",
    "fix/unit-4-team-service",
    "fix/unit-5-analytics-battle",
    "fix/unit-6-data-layer",
    "fix/unit-7-notifications-video",
    "fix/unit-8-phase9-guards",
    "fix/unit-9-ml-replay",
    "main"
)

$deleted = 0
$skipped = 0

foreach ($branch in $branchesToDelete) {
    Write-Host "  Deleting origin/$branch..." -NoNewline
    git push origin --delete $branch 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host " done" -ForegroundColor Green
        $deleted++
    } else {
        # Branch may already be deleted — not fatal
        Write-Host " (already gone or not found)" -ForegroundColor DarkYellow
        $skipped++
    }
}

Write-Host "`n  Deleted: $deleted   Already gone: $skipped" -ForegroundColor Green

# -----------------------------------------------------------------------------
# DONE
# -----------------------------------------------------------------------------
Write-Host "`n=== All done! ===" -ForegroundColor Cyan
Write-Host "  - Local folder is synced to clean master" -ForegroundColor White
Write-Host "  - Untracked files cleaned (if confirmed)" -ForegroundColor White
Write-Host "  - Remote branches deleted: $deleted" -ForegroundColor White
Write-Host "`n  Only 'master' remains on GitHub." -ForegroundColor Green
