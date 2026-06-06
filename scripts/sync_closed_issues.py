#!/usr/bin/env python3
"""
sync_closed_issues.py — keep per-issue SOLUTION notes in sync with issues.md.

Behaviour
---------
1. Parse the **Closed** table in issues.md to get every closed issue ID + slug.
2. For each closed issue:
   a. Locate its note (issues/ISS-NNN-slug.md) and ensure frontmatter has
      ``status: done`` and a ``closed:`` date (opt 1 — auto-sync).
   b. If no ISS-NNN-SOLUTION.md exists at SOLUTION_DIR, scaffold a skeleton
      (never overwrites an existing solution file).
3. Warn about reconcile drift: issue notes with ``status: done`` that are NOT
   in the Closed table (opt 4 — detect but don't auto-fix).
4. ``--check`` mode: read-only; exits 1 if any closed issue is missing a
   solution or has a frontmatter mismatch.

Usage
-----
  python scripts/sync_closed_issues.py            # sync + scaffold
  python scripts/sync_closed_issues.py --check    # CI / hook dry-run
  python scripts/sync_closed_issues.py --verbose  # extra detail
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

REPO_ROOT    = Path(__file__).parent.parent
ISSUES_MD    = REPO_ROOT / "issues.md"
ISSUES_DIR   = REPO_ROOT / "issues"
SOLUTION_DIR = REPO_ROOT  # ISS-NNN-SOLUTION.md lives at repo root (matches ISS-002/003)

TODAY = date.today().isoformat()

# ── Frontmatter helpers ───────────────────────────────────────────────────────

def _parse_frontmatter(text: str) -> dict[str, str]:
    """Return key→value dict from YAML frontmatter (--- block), stdlib only."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm


def _update_frontmatter(path: Path, updates: dict[str, str]) -> bool:
    """
    Write ``updates`` into the frontmatter of ``path``.
    Returns True if the file was changed, False if already correct.
    """
    text  = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return False  # no frontmatter — skip

    # Find closing ---
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return False

    fm_lines = lines[1:end]
    changed = False

    for key, val in updates.items():
        pattern = re.compile(rf"^{re.escape(key)}\s*:.*", re.MULTILINE)
        matched = False
        new_fm_lines = []
        for fl in fm_lines:
            m = pattern.match(fl.rstrip("\n\r"))
            if m:
                new_line = f"{key}: {val}\n"
                if fl != new_line:
                    fl = new_line
                    changed = True
                matched = True
            new_fm_lines.append(fl)
        fm_lines = new_fm_lines
        if not matched:
            fm_lines.append(f"{key}: {val}\n")
            changed = True

    if not changed:
        return False

    new_text = "".join(["---\n"] + fm_lines + ["---\n"] + lines[end + 1 :])
    path.write_text(new_text, encoding="utf-8")
    return True

# ── issues.md parser ──────────────────────────────────────────────────────────

# Matches: | [[ISS-006-ml-training-environment|ISS-006]] | ...
_CLOSED_ROW_RE = re.compile(
    r"\[\[(?P<slug>ISS-\d{3}-[^\]|]+)\|(?P<id>ISS-\d{3})\]\]"
)
_OPEN_ROW_RE = re.compile(
    r"\[\[(?P<slug>ISS-\d{3}-[^\]|]+)\|(?P<id>ISS-\d{3})\]\].*?(?:in-progress|open)",
    re.IGNORECASE,
)


def _parse_closed_issues(issues_md: Path) -> list[tuple[str, str]]:
    """Return list of (issue_id, slug) from the Closed table."""
    text = issues_md.read_text(encoding="utf-8")
    # Find the Closed section
    closed_section = ""
    in_closed = False
    for line in text.splitlines():
        if re.match(r"^##\s+Closed", line):
            in_closed = True
        elif re.match(r"^##\s+", line) and in_closed:
            break
        if in_closed:
            closed_section += line + "\n"

    results = []
    for m in _CLOSED_ROW_RE.finditer(closed_section):
        results.append((m.group("id"), m.group("slug")))
    return results


def _parse_open_issues(issues_md: Path) -> set[str]:
    """Return set of issue IDs from the Open table."""
    text = issues_md.read_text(encoding="utf-8")
    open_section = ""
    in_open = False
    for line in text.splitlines():
        if re.match(r"^##\s+Open", line):
            in_open = True
        elif re.match(r"^##\s+", line) and in_open:
            break
        if in_open:
            open_section += line + "\n"

    ids: set[str] = set()
    for m in re.finditer(r"\[\[ISS-\d{3}-[^\]|]+\|(?P<id>ISS-\d{3})\]\]", open_section):
        ids.add(m.group("id"))
    return ids


# ── Scaffold ──────────────────────────────────────────────────────────────────

_SOLUTION_SKELETON = """\
---
id: {issue_id}
title: {title}
status: done
phase: {phase}
closed: {closed}
---

# {issue_id} Solution — {title}

## Analysis

<!-- What was broken or missing, and why? -->

## Approach

<!-- Per-file breakdown of changes made. -->

## Code Changes

```diff
# paste relevant diffs here
```

## Verification

```bash
# commands to confirm the fix
```

## Related

- [[{slug}]] — source issue
"""


def _scaffold_solution(
    issue_id: str,
    slug: str,
    fm: dict[str, str],
    solution_path: Path,
) -> None:
    title  = fm.get("title", issue_id)
    phase  = fm.get("phase", "backlog")
    closed = fm.get("closed", TODAY)
    content = _SOLUTION_SKELETON.format(
        issue_id=issue_id,
        title=title,
        phase=phase,
        closed=closed,
        slug=slug,
    )
    solution_path.write_text(content, encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def run(check: bool = False, verbose: bool = False) -> int:
    """
    Execute the sync.  Returns exit code (0 = clean, 1 = issues found in --check).
    """
    if not ISSUES_MD.exists():
        print(f"ERROR: {ISSUES_MD} not found", file=sys.stderr)
        return 1

    closed = _parse_closed_issues(ISSUES_MD)
    open_ids = _parse_open_issues(ISSUES_MD)

    synced    = 0
    scaffolded = 0
    warnings  = 0
    check_failures = 0

    for issue_id, slug in closed:
        # ── Locate the issue note ──────────────────────────────────
        note_glob = list(ISSUES_DIR.glob(f"{issue_id}-*.md"))
        if not note_glob:
            print(f"  WARN  {issue_id}: no note found in issues/ (expected {slug}.md)")
            warnings += 1
            continue
        note_path = note_glob[0]
        fm = _parse_frontmatter(note_path.read_text(encoding="utf-8"))

        # ── Sync frontmatter (opt 1) ───────────────────────────────
        needed: dict[str, str] = {}
        if fm.get("status") != "done":
            needed["status"] = "done"
        if not fm.get("closed"):
            # Use issues.md header `closed:` date as fallback, else today
            issues_fm = _parse_frontmatter(ISSUES_MD.read_text(encoding="utf-8"))
            needed["closed"] = issues_fm.get("closed", TODAY)

        if needed:
            if check:
                print(f"  FAIL  {issue_id}: frontmatter needs update {needed}")
                check_failures += 1
            else:
                did_change = _update_frontmatter(note_path, needed)
                if did_change:
                    print(f"  SYNC  {issue_id}: updated frontmatter {list(needed.keys())}")
                    synced += 1
                elif verbose:
                    print(f"  OK    {issue_id}: frontmatter already correct")
        elif verbose:
            print(f"  OK    {issue_id}: frontmatter already correct")

        # ── Scaffold solution (if missing) ────────────────────────
        solution_path = SOLUTION_DIR / f"{issue_id}-SOLUTION.md"
        if not solution_path.exists():
            if check:
                print(f"  FAIL  {issue_id}: missing {solution_path.name}")
                check_failures += 1
            else:
                _scaffold_solution(issue_id, slug, fm, solution_path)
                print(f"  NEW   {issue_id}: scaffolded {solution_path.name}")
                print(f"        -> Fill in Analysis/Approach/Code Changes/Verification")
                scaffolded += 1
        elif verbose:
            print(f"  OK    {issue_id}: {solution_path.name} exists")

    # ── Reconcile drift (opt 4) ────────────────────────────────────────────────
    # Issue notes with status:done that are NOT in the Closed table
    for note_path in sorted(ISSUES_DIR.glob("ISS-*.md")):
        fm = _parse_frontmatter(note_path.read_text(encoding="utf-8"))
        nid = fm.get("id", "")
        if fm.get("status") == "done" and nid and nid not in {i for i, _ in closed}:
            if nid in open_ids:
                print(
                    f"  WARN  {nid}: note says status=done but still in Open table "
                    f"in issues.md — move row to Closed manually"
                )
            else:
                print(
                    f"  WARN  {nid}: note says status=done but not found in any "
                    f"issues.md table — check issues.md"
                )
            warnings += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    if check:
        status = "CLEAN" if check_failures == 0 else "NEEDS WORK"
        print(
            f"\n[sync_closed_issues --check] {status} — "
            f"{len(closed)} closed · {check_failures} failures · {warnings} warnings"
        )
        return 1 if check_failures else 0
    else:
        print(
            f"\n[sync_closed_issues] done — "
            f"synced {synced} notes · scaffolded {scaffolded} solutions · {warnings} warnings"
        )
        if scaffolded:
            print(
                "  Reminder: fill scaffolded SOLUTION files, then:\n"
                "    git add ISS-*-SOLUTION.md && git commit"
            )
        return 0


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Sync closed issue notes and scaffold SOLUTION files from issues.md"
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="Read-only mode: exit 1 if any closed issue is missing a solution or has stale frontmatter",
    )
    ap.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print a line for every issue, not just changes and warnings",
    )
    args = ap.parse_args()
    sys.exit(run(check=args.check, verbose=args.verbose))


if __name__ == "__main__":
    main()
