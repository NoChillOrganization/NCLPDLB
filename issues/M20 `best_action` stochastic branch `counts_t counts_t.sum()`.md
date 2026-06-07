---
title: "M20: `best_action` stochastic branch: `counts_t / counts_t.sum()`"
created: 2026-06-05
priority: medium
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M20</id>
  <title>M20: `best_action` stochastic branch: `counts_t / counts_t.sum()`</title>
  <location>ml/mcts.py:202-205</location>
  <description>`best_action` stochastic branch: `counts_t / counts_t.sum()` → NaN when all visit counts 0 (e.g. `n_simulations=0`) → `np.random.choice` `ValueError`.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
