---
title: "H3: `upsert_row` matches header by name but writes the caller's…"
created: 2026-06-05
priority: high
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H3</id>
  <title>H3: `upsert_row` matches header by name but writes the caller's…</title>
  <location>data/sheets.py:166-178</location>
  <description>`upsert_row` matches header by name but writes the caller's **positional** list starting at column A, ignoring documented per-tab layouts (Setup col H, Standings 2-row template, Transactions start row 6 col D). Overwrites wrong cells / templates.</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
