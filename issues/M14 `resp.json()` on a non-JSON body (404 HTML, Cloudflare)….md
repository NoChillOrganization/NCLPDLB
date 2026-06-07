---
title: "M14: `resp.json()` on a non-JSON body (404 HTML, Cloudflare)…"
created: 2026-06-05
priority: medium
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M14</id>
  <title>M14: `resp.json()` on a non-JSON body (404 HTML, Cloudflare)…</title>
  <location>services/battle_sim.py:153-154</location>
  <description>`resp.json()` on a non-JSON body (404 HTML, Cloudflare) raises `json.JSONDecodeError` (a `ValueError`), which is **not** caught by `except aiohttp.ClientError` → escapes `parse_replay`.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
