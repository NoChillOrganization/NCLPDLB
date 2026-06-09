---
title: "L2: `socket.create_connection(...)` result never closed"
created: 2026-06-05
priority: low
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>L2</id>
  <title>L2: `socket.create_connection(...)` result never closed</title>
  <location>bot/cogs/admin.py:375-377</location>
  <description>`socket.create_connection(...)` result never closed → fd leak per check.</description>
  <priority>LOW</priority>
  <status>done</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
