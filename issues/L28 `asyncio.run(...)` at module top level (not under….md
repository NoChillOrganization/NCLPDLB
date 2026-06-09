---
title: "L28: `asyncio.run(...)` at module top level (not under…"
created: 2026-06-05
priority: low
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>L28</id>
  <title>L28: `asyncio.run(...)` at module top level (not under…</title>
  <location>scripts/{sync_commands,force_sync}.py</location>
  <description>`asyncio.run(...)` at module top level (not under `__main__`) → importing runs the bot; `force_sync.on_ready` re-loads extensions on reconnect → `ExtensionAlreadyLoaded`.</description>
  <priority>LOW</priority>
  <status>done</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
