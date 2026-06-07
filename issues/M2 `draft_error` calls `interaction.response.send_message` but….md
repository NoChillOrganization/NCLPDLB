---
title: "M2: `draft_error` calls `interaction.response.send_message` but…"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M2</id>
  <title>M2: `draft_error` calls `interaction.response.send_message` but…</title>
  <location>bot/cogs/draft.py:561-565</location>
  <description>`draft_error` calls `interaction.response.send_message` but `draft_create` already `defer()`s (line 321) → `InteractionResponded` (40060) masks the real error. Should check `is_done()` + use `followup` (sheet.py:325-338 does this correctly).</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
