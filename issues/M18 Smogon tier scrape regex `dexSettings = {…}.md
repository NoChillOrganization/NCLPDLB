---
title: "M18: Smogon tier scrape regex `dexSettings = {…}"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M18</id>
  <title>M18: Smogon tier scrape regex `dexSettings = {…}</title>
  <location>data/smogon.py:36-47; data/showdown.py:54-58,82</location>
  <description>Smogon tier scrape regex `dexSettings = {…};` + non-greedy `\{.*?\}` cannot capture nested JSON at that path; name normalization (`replace(" ","").replace("-","")`) won't match seed Title-case names. Tier pipeline effectively non-functional / silently empty.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
