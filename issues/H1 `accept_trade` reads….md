---
title: "H1: `accept_trade` reads…"
created: 2026-06-05
priority: high
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H1</id>
  <title>H1: `accept_trade` reads…</title>
  <location>services/team_service.py:181-206</location>
  <description>`accept_trade` reads `to_player_id`/`from_player_id`/`league_id`/`pokemon_given` keys; trade swap only runs **if both rosters already in `_roster_cache`** and is **never persisted** back to Sheets. After restart or cache miss → trade marked accepted, zero roster change (silent data loss).</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
