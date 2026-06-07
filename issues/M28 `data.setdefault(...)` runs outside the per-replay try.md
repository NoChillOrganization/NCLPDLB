---
title: "M28: `data.setdefault(...)` runs outside the per-replay try"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M28</id>
  <title>M28: `data.setdefault(...)` runs outside the per-replay try</title>
  <location>ml/replay_scraper.py:133-138</location>
  <description>`data.setdefault(...)` runs **outside** the per-replay try; non-dict JSON (list/null) → `AttributeError` aborts the whole `gather`.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
