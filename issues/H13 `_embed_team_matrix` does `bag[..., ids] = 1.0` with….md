---
title: "H13: `_embed_team_matrix` does `bag[..., ids] = 1.0` with…"
created: 2026-06-05
priority: high
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H13</id>
  <title>H13: `_embed_team_matrix` does `bag[..., ids] = 1.0` with…</title>
  <location>ml/train_matchup.py:65-71,112</location>
  <description>`_embed_team_matrix` does `bag[..., ids] = 1.0` with `vocab_size` defaulting to 512 when `species_vocab.json` is missing, but feature IDs can exceed 512 → `IndexError: index N out of bounds for axis 1 with size 512`.</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
