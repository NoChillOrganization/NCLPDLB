---
title: "M9: `make_pick` `await`s (`to_thread(save_pick)`,…"
created: 2026-06-05
priority: medium
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M9</id>
  <title>M9: `make_pick` `await`s (`to_thread(save_pick)`,…</title>
  <location>services/draft_service.py:25-30,283-310</location>
  <description>`make_pick` `await`s (`to_thread(save_pick)`, `_persist_draft`) between the `current_player_id == player_id` check and the append/advance → TOCTOU; double-click can double-pick / corrupt index. No per-guild lock (elo_service has one).</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
