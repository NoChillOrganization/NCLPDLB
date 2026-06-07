---
title: "M4: `report = svc.analyze_pokemon_list(...)` called without…"
created: 2026-06-05
priority: medium
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M4</id>
  <title>M4: `report = svc.analyze_pokemon_list(...)` called without…</title>
  <location>bot/views/team_view.py:42-44</location>
  <description>`report = svc.analyze_pokemon_list(...)` called **without `await`** in an async handler. If the method is a coroutine → `AttributeError` on `report.coverage_summary`; if sync+heavy → blocks event loop. (stats.py uses `await analytics.analyze_team`, so async methods exist on the service — verify signature.)</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
