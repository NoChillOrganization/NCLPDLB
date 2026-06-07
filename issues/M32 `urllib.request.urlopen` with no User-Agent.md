---
title: "M32: `urllib.request.urlopen` with no User-Agent"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M32</id>
  <title>M32: `urllib.request.urlopen` with no User-Agent</title>
  <location>scripts/prepare_competitive_data.py:129</location>
  <description>`urllib.request.urlopen` with no User-Agent → Smogon 403; broad `except` → silent empty stats.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
