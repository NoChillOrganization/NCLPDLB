# NCLPDLB — Apply Audit Fixes
# Run this from inside F:\Claude Code\projects\pokemon-draft-bot
# (or wherever your local clone of the master branch lives)

$repoPath = $PSScriptRoot  # run from repo root, or change this path
Set-Location $repoPath

# Create fix branch
git checkout master
git pull origin master
git checkout -b fix/audit-all-issues

# Apply the patch
git apply audit-fixes.patch

# Commit
git add -A
git commit -m "fix: full audit — bid tracking, stellar type, logging, escape fixes"

# Push
git push origin fix/audit-all-issues

Write-Host ""
Write-Host "Done! Branch pushed: fix/audit-all-issues"
Write-Host "Open a PR at: https://github.com/NoChillModeOnline/NCLPDLB/compare/fix/audit-all-issues"
