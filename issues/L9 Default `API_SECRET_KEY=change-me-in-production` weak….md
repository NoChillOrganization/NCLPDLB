---
title: "L9: Default `API_SECRET_KEY='change-me-in-production'` weak…"
created: 2026-06-05
priority: low
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>L9</id>
  <title>L9: Default `API_SECRET_KEY="change-me-in-production"` weak…</title>
  <location>setup.py:159</location>
  <description>Default `API_SECRET_KEY="change-me-in-production"` weak static default — use `secrets.token_urlsafe(32)`.</description>
  <priority>LOW</priority>
  <status>done</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
