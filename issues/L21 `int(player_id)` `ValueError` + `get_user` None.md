---
title: "L21: `int(player_id)` `ValueError` + `get_user` None"
created: 2026-06-05
priority: low
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>L21</id>
  <title>L21: `int(player_id)` `ValueError` + `get_user` None</title>
  <location>services/notification_service.py:99,108</location>
  <description>`int(player_id)` `ValueError` + `get_user` None → `AttributeError`, both caught by broad `except Exception` with noisy stack traces for benign bad input.</description>
  <priority>LOW</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
