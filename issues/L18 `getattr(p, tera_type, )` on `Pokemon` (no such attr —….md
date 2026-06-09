---
title: "L18: `getattr(p, 'tera_type', '')` on `Pokemon` (no such attr —…"
created: 2026-06-05
priority: low
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>L18</id>
  <title>L18: `getattr(p, "tera_type", "")` on `Pokemon` (no such attr —…</title>
  <location>services/team_service.py:116</location>
  <description>`getattr(p, "tera_type", "")` on `Pokemon` (no such attr — it's on `DraftPick`) → always `""`.</description>
  <priority>LOW</priority>
  <status>done</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
