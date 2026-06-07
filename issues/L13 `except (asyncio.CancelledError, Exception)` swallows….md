---
title: "L13: `except (asyncio.CancelledError, Exception)` swallows…"
created: 2026-06-05
priority: low
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>L13</id>
  <title>L13: `except (asyncio.CancelledError, Exception)` swallows…</title>
  <location>ml/showdown_client.py:133</location>
  <description>`except (asyncio.CancelledError, Exception)` swallows cooperative cancellation — re-raise `CancelledError`.</description>
  <priority>LOW</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
