---
title: "L3: `match_upload` claims 'max 25MB' but never checks…"
created: 2026-06-05
priority: low
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>L3</id>
  <title>L3: `match_upload` claims "max 25MB" but never checks…</title>
  <location>bot/cogs/stats.py:197-216</location>
  <description>`match_upload` claims "max 25MB" but never checks `video.size` (team.py:110 checks logo size — be consistent).</description>
  <priority>LOW</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
