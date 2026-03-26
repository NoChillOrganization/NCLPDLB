# =============================================================================
# PDLB Final Push + NCLPDLB Cleanup
# Run from EITHER repo folder — the script finds both automatically.
# Usage: Right-click → "Run with PowerShell"  OR  open PowerShell and run:
#   powershell -ExecutionPolicy Bypass -File "F:\Claude Code\projects\pokemon-draft-bot\pdlb-push-and-cleanup.ps1"
# =============================================================================

$ErrorActionPreference = "Continue"   # don't hard-stop on non-fatal errors

Write-Host ""
Write-Host "=== PDLB Final Push + NCLPDLB Cleanup ===" -ForegroundColor Cyan
Write-Host ""

# --- Find the repo root (works from any subfolder too) ----------------------
$startDir = $PSScriptRoot
if (-not $startDir) { $startDir = Get-Location }

$repoRoot = $startDir
while ($repoRoot -and -not (Test-Path (Join-Path $repoRoot ".git"))) {
    $repoRoot = Split-Path $repoRoot -Parent
}
if (-not $repoRoot) {
    Write-Host "ERROR: Can't find a git repo. Place this script inside your pokemon-draft-bot folder." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Set-Location $repoRoot
Write-Host "Repo root: $repoRoot" -ForegroundColor DarkGray

# Confirm this is the right repo
$remote = & git remote get-url origin 2>&1
if ($remote -notmatch "pokemon-draft-league-bot") {
    Write-Host "ERROR: This doesn't look like pokemon-draft-league-bot." -ForegroundColor Red
    Write-Host "Remote URL: $remote" -ForegroundColor DarkGray
    Read-Host "Press Enter to exit"
    exit 1
}

# --- Check gh CLI is available ----------------------------------------------
$ghAvailable = $false
try {
    $null = & gh --version 2>&1
    if ($LASTEXITCODE -eq 0) { $ghAvailable = $true }
} catch {}

# --- STEP 1: Pull latest from remote ----------------------------------------
Write-Host "[1/4] Pulling latest from GitHub..." -ForegroundColor Yellow
& git fetch origin
& git checkout master
# Use merge (not reset) so we don't lose any local changes you may have
& git merge --ff-only origin/master 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Fast-forward failed — your local master has commits not on remote (that's fine, we'll push them)." -ForegroundColor DarkYellow
}
Write-Host "  Done." -ForegroundColor Green

# --- STEP 2: Push to remote master ------------------------------------------
Write-Host ""
Write-Host "[2/4] Pushing merged commits to GitHub..." -ForegroundColor Yellow
Write-Host "  This pushes 56 new/changed files (models, source, bug fixes, docs)." -ForegroundColor DarkGray

& git push origin master
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  Push failed. Trying to fix credentials..." -ForegroundColor Red
    if ($ghAvailable) {
        Write-Host "  Running: gh auth login" -ForegroundColor DarkYellow
        & gh auth login
        & git push origin master
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "  Still failed. Try running this manually and then re-run the script:" -ForegroundColor Red
        Write-Host "    git config --global credential.helper manager" -ForegroundColor White
        Write-Host "    git push origin master" -ForegroundColor White
        Read-Host "Press Enter to exit"
        exit 1
    }
}
Write-Host "  Push successful." -ForegroundColor Green

# --- STEP 3: Delete stale PDLB branches -------------------------------------
Write-Host ""
Write-Host "[3/4] Deleting stale branches from pokemon-draft-league-bot..." -ForegroundColor Yellow

foreach ($branch in @("fix/unit-4-team-service", "fix/unit-9-ml-replay")) {
    Write-Host "  Deleting $branch..." -NoNewline
    $result = & git push origin --delete $branch 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host " done" -ForegroundColor Green
    } else {
        Write-Host " (already gone or not found — OK)" -ForegroundColor DarkYellow
    }
}

# --- STEP 4: Delete the NCLPDLB repo ----------------------------------------
Write-Host ""
Write-Host "[4/4] Delete the NCLPDLB repo from GitHub" -ForegroundColor Yellow
Write-Host "  Repo: https://github.com/NoChillModeOnline/NCLPDLB" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Type DELETE (all caps) and press Enter to permanently delete it." -ForegroundColor DarkYellow
Write-Host "  Press Enter without typing anything to skip." -ForegroundColor DarkGray
$confirm = Read-Host "  > "

if ($confirm -eq "DELETE") {
    if ($ghAvailable) {
        Write-Host "  Deleting NCLPDLB repo..." -NoNewline
        & gh repo delete NoChillModeOnline/NCLPDLB --yes 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host " done" -ForegroundColor Green
        } else {
            Write-Host " failed (see below). Delete manually:" -ForegroundColor Red
            Write-Host "  https://github.com/NoChillModeOnline/NCLPDLB/settings" -ForegroundColor White
            Write-Host "  Scroll to bottom → Danger Zone → Delete this repository" -ForegroundColor DarkGray
        }
    } else {
        Write-Host "  gh CLI not found. Delete manually:" -ForegroundColor DarkYellow
        Write-Host "  https://github.com/NoChillModeOnline/NCLPDLB/settings" -ForegroundColor White
        Write-Host "  Scroll to bottom → Danger Zone → Delete this repository" -ForegroundColor DarkGray
    }
} else {
    Write-Host "  Skipped. You can delete it later at:" -ForegroundColor DarkYellow
    Write-Host "  https://github.com/NoChillModeOnline/NCLPDLB/settings" -ForegroundColor White
}

# --- Done -------------------------------------------------------------------
Write-Host ""
Write-Host "=== Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  pokemon-draft-league-bot is now the single canonical repo." -ForegroundColor White
Write-Host "  GitHub: https://github.com/NoChillModeOnline/pokemon-draft-league-bot" -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter to close"
