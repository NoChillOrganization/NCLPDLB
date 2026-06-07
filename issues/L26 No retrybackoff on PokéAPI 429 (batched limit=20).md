---
title: "L26: No retry/backoff on PokéAPI 429 (batched limit=20)"
created: 2026-06-05
priority: low
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>L26</id>
  <title>L26: No retry/backoff on PokéAPI 429 (batched limit=20)</title>
  <location>scripts/seed_pokemon_data.py:23-63</location>
  <description>No retry/backoff on PokéAPI 429 (batched limit=20); failed species silently dropped, default gen 1.</description>
  <priority>LOW</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
