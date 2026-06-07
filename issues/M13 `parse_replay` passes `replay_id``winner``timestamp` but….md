---
title: "M13: `parse_replay` passes `replay_id`/`winner`/`timestamp` but…"
created: 2026-06-05
priority: medium
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M13</id>
  <title>M13: `parse_replay` passes `replay_id`/`winner`/`timestamp` but…</title>
  <location>services/battle_sim.py:164-173 ↔ sheets.py:336-343</location>
  <description>`parse_replay` passes `replay_id`/`winner`/`timestamp` but `save_replay` only uses `match_id`(=="")/`url`/`p1_team`/`p2_team`/`turns` and writes to the **Schedule** tab keyed on blank `match_id` → every replay overwrites the same row; winner/timestamp dropped.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
