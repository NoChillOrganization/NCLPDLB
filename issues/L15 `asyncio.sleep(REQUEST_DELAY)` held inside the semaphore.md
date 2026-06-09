---
title: "L15: `asyncio.sleep(REQUEST_DELAY)` held inside the semaphore"
created: 2026-06-05
priority: low
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>L15</id>
  <title>L15: `asyncio.sleep(REQUEST_DELAY)` held inside the semaphore</title>
  <location>ml/replay_scraper.py:140</location>
  <description>`asyncio.sleep(REQUEST_DELAY)` held **inside** the semaphore → serializes delay into concurrency budget, ~halves throughput.</description>
  <priority>LOW</priority>
  <status>done</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
