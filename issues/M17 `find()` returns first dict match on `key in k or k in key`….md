---
title: "M17: `find()` returns first dict match on `key in k or k in key`…"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M17</id>
  <title>M17: `find()` returns first dict match on `key in k or k in key`…</title>
  <location>data/pokeapi.py:62-65</location>
  <description>`find()` returns first dict match on `key in k or k in key` (plain substring). `"mew"` can return `"mewtwo"`; order-dependent → user can draft the wrong Pokémon.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
