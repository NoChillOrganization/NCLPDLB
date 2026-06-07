---
title: "H4: `get_tab` auto-creates a 1000×26 worksheet on…"
created: 2026-06-05
priority: high
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H4</id>
  <title>H4: `get_tab` auto-creates a 1000×26 worksheet on…</title>
  <location>data/sheets.py:119-126</location>
  <description>`get_tab` **auto-creates** a 1000×26 worksheet on `WorksheetNotFound` — called by read paths (`read_all`/`find_row`). A typo'd `Tab` constant or transient miss spawns junk tabs in the production sheet and masks real errors. Reads mutate state.</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
