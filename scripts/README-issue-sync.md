# Issue Sync — Closing Workflow

Every closed issue gets a `ISS-NNN-SOLUTION.md` at the repo root (matching `ISS-002-SOLUTION.md` / `ISS-003-SOLUTION.md`).

## Closing an Issue

1. Move the row from the **Open** table to the **Closed** table in `issues.md`.
2. Run the sync script — it stamps `status: done` + `closed:` date into the issue note and scaffolds a solution skeleton if missing:
   ```bash
   python scripts/sync_closed_issues.py
   ```
3. Fill the scaffolded `ISS-NNN-SOLUTION.md` (Analysis → Approach → Code Changes → Verification → Related) from the actual diffs — the "ISS-002 way."
4. Commit everything:
   ```bash
   git add issues.md issues/ISS-NNN-*.md ISS-NNN-SOLUTION.md
   git commit -m "close(ISS-NNN): <title>"
   ```

## Going-Forward Automation (git hook)

The post-commit hook in `scripts/hooks/post-commit` runs `sync_closed_issues.py` automatically whenever `issues.md` is part of a commit. Install once per clone:

```bash
git config core.hooksPath scripts/hooks
```

The hook is **advisory** — post-commit cannot amend the triggering commit. If it scaffolds a new solution, commit the scaffold separately.

## CI / Check Mode

```bash
python scripts/sync_closed_issues.py --check   # exits 1 if any closed issue missing solution
python scripts/sync_closed_issues.py --verbose  # full per-issue detail
```

## Solution File Format

Match the existing `ISS-002-SOLUTION.md` structure:

```
---
id: ISS-NNN
title: …
status: done
phase: "05" | "06" | backlog
closed: YYYY-MM-DD
---

# ISS-NNN Solution — <title>

## Analysis
## Approach
## Code Changes
## Verification
## Related
```

End with `## Related` wikilinks to the issue note and adjacent solutions so the Obsidian graph connects solution ↔ issue.
