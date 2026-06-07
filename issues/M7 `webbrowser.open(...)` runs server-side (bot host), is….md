---
title: "M7: `webbrowser.open(...)` runs server-side (bot host), is…"
created: 2026-06-05
priority: medium
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M7</id>
  <title>M7: `webbrowser.open(...)` runs server-side (bot host), is…</title>
  <location>bot/cogs/admin.py:383</location>
  <description>`webbrowser.open(...)` runs server-side (bot host), is synchronous/blocking, and almost never the intended behavior.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
