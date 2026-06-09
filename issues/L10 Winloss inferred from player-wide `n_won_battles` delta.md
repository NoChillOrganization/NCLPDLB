---
title: "L10: Win/loss inferred from player-wide `n_won_battles` delta"
created: 2026-06-05
priority: low
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>L10</id>
  <title>L10: Win/loss inferred from player-wide `n_won_battles` delta</title>
  <location>ml/self_play.py:350-361</location>
  <description>Win/loss inferred from player-wide `n_won_battles` delta → misattribution across concurrent battles; read `Battle.won/.lost` instead.</description>
  <priority>LOW</priority>
  <status>done</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
