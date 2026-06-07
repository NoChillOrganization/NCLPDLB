---
title: "H5: `get_team` filters `record.get('guild_id') != guild_id`,…"
created: 2026-06-05
priority: high
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H5</id>
  <title>H5: `get_team` filters `record.get("guild_id") != guild_id`,…</title>
  <location>services/team_service.py:67-72</location>
  <description>`get_team` filters `record.get("guild_id") != guild_id`, but `upsert_team_page` never writes a `guild_id` column → always `None` → returns None for every user (compounds H2).</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
