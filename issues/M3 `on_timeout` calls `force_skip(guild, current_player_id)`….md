---
title: "M3: `on_timeout` calls `force_skip(guild, current_player_id)`…"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M3</id>
  <title>M3: `on_timeout` calls `force_skip(guild, current_player_id)`…</title>
  <location>bot/views/draft_view.py:22-31,86-95</location>
  <description>`on_timeout` calls `force_skip(guild, current_player_id)` with no check the pick is still pending; select callback never calls `self.view.stop()` after a successful pick → timer fires later and skips the **wrong** player. Race condition.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
