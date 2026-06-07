---
title: "M8: `asyncio.get_event_loop()` inside a coroutine is deprecated…"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M8</id>
  <title>M8: `asyncio.get_event_loop()` inside a coroutine is deprecated…</title>
  <location>bot/cogs/ml.py:79</location>
  <description>`asyncio.get_event_loop()` inside a coroutine is deprecated (3.12+); project targets 3.14. Use `get_running_loop()`.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
