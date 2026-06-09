---
title: "L27: New aiohttp session per probe × ~130 concurrent"
created: 2026-06-05
priority: low
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>L27</id>
  <title>L27: New aiohttp session per probe × ~130 concurrent</title>
  <location>scripts/scrape_all_formats.py:183,222</location>
  <description>New aiohttp session per probe × ~130 concurrent → socket exhaustion / rate-limit; bound with a semaphore + shared session. Also `:42` `gen9doubleou` typo (should be `gen9doublesou`).</description>
  <priority>LOW</priority>
  <status>done</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
