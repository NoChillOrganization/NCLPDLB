---
title: "M19: New `aiosqlite.connect` per save/load call"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M19</id>
  <title>M19: New `aiosqlite.connect` per save/load call</title>
  <location>data/db.py:65-130</location>
  <description>New `aiosqlite.connect` per save/load call; per-pick + per-match writes → churn and "database is locked" risk (default journal mode, no WAL).</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
