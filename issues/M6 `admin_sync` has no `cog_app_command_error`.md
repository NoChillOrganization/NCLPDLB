---
title: "M6: `admin_sync` has no `cog_app_command_error`"
created: 2026-06-05
priority: medium
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M6</id>
  <title>M6: `admin_sync` has no `cog_app_command_error`</title>
  <location>bot/cogs/admin.py:113-137</location>
  <description>`admin_sync` has no `cog_app_command_error`; a non-`HTTPException` (e.g. `copy_global_to` raising) becomes an unhandled interaction failure.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
