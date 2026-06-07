---
title: "H10: N+1 full-sheet reads"
created: 2026-06-05
priority: high
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H10</id>
  <title>H10: N+1 full-sheet reads</title>
  <location>data/sheets.py:166-203</location>
  <description>N+1 full-sheet reads. `upsert_row` does `row_values(1)` + `get_all_records()` (full read) on **every** write; `find_row` reads the whole sheet and returns first match. `EloService.record_match` → ~4 full-sheet reads/match.</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
