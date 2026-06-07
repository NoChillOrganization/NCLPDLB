---
title: "M12: `int(record.get('elo', 1000))` raises `ValueError` on…"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M12</id>
  <title>M12: `int(record.get("elo", 1000))` raises `ValueError` on…</title>
  <location>services/elo_service.py:83-85,162-166</location>
  <description>`int(record.get("elo", 1000))` raises `ValueError` on non-numeric Sheets cells (blank `""`, "1000 pts", "5-2" visual template).</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
