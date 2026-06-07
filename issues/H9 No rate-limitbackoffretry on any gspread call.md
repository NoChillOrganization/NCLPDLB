---
title: "H9: No rate-limit/backoff/retry on any gspread call"
created: 2026-06-05
priority: high
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H9</id>
  <title>H9: No rate-limit/backoff/retry on any gspread call</title>
  <location>data/sheets.py (all gspread calls) + every service caller</location>
  <description>No rate-limit/backoff/retry on any gspread call. Sheets quota is ~60 reads + 60 writes/min/user. A live draft (per-pick `save_pick` + `_persist_draft`) or `record_match` (4+ full-sheet round-trips, see H10) hits HTTP 429 and raises into the cog. `SheetsClient` methods don't even catch.</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
