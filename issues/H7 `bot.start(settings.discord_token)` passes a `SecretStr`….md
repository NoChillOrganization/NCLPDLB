---
title: "H7: `bot.start(settings.discord_token)` passes a `SecretStr`…"
created: 2026-06-05
priority: high
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H7</id>
  <title>H7: `bot.start(settings.discord_token)` passes a `SecretStr`…</title>
  <location>scripts/force_sync.py:47</location>
  <description>`bot.start(settings.discord_token)` passes a `SecretStr` (config field type) to discord.py which expects `str` → login fails. `sync_commands.py` correctly uses `.get_secret_value()`. **(verified)**</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
