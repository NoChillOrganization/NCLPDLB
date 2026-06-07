---
title: "M27: `SimpleHeuristicPlayer.choose_move` does…"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M27</id>
  <title>M27: `SimpleHeuristicPlayer.choose_move` does…</title>
  <location>ml/training_players.py:72</location>
  <description>`SimpleHeuristicPlayer.choose_move` does `battle.opponent_active_pokemon.damage_multiplier(...)`; `opponent_active_pokemon` is `None` during forced-switch → `AttributeError`.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
