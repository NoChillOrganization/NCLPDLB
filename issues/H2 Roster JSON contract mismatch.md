---
title: "H2: Roster JSON contract mismatch"
created: 2026-06-05
priority: high
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H2</id>
  <title>H2: Roster JSON contract mismatch</title>
  <location>data/sheets.py:527-536 ↔ services/team_service.py:71-83</location>
  <description>Roster JSON contract mismatch. Writer stores comma-joined `name(tera)` string; reader does `json.loads(record.get("pokemon_list","[]"))`. Key `pokemon_list` is never written and value isn't JSON → `get_team` always returns empty roster. Breaks analysis/compare/export/trade.</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
