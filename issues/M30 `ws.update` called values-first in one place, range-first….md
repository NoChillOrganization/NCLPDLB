---
title: "M30: `ws.update` called values-first in one place, range-first…"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M30</id>
  <title>M30: `ws.update` called values-first in one place, range-first…</title>
  <location>data/sheets.py:148 vs 164,176,463</location>
  <description>`ws.update` called values-first in one place, range-first in others — gspread v6 signature is `update(range_name, values)`; one form is wrong for the installed version.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
