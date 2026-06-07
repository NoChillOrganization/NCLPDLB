---
title: "M25: `asyncio.Event()` constructed in `__init__` (before loop…"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M25</id>
  <title>M25: `asyncio.Event()` constructed in `__init__` (before loop…</title>
  <location>ml/showdown_client.py:374</location>
  <description>`asyncio.Event()` constructed in `__init__` (before loop runs, via pool ctor) — on Python &lt;3.10 binds to wrong loop.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
