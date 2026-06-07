---
title: "H6: `record_match` updates `elo`/`wins`/`losses` but never…"
created: 2026-06-05
priority: high
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H6</id>
  <title>H6: `record_match` updates `elo`/`wins`/`losses` but never…</title>
  <location>services/elo_service.py:123-135</location>
  <description>`record_match` updates `elo`/`wins`/`losses` but **never updates `streak`**, yet `streak` is persisted (`_save_player_to_db`) and shown in standings. Streaks frozen forever. **(verified)**</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
