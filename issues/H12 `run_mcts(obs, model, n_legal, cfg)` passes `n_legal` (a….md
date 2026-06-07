---
title: "H12: `run_mcts(obs, model, n_legal, cfg)` passes `n_legal` (a…"
created: 2026-06-05
priority: high
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H12</id>
  <title>H12: `run_mcts(obs, model, n_legal, cfg)` passes `n_legal` (a…</title>
  <location>ml/showdown_player.py:177-183 → ml/mcts.py:246-249</location>
  <description>`run_mcts(obs, model, n_legal, cfg)` passes `n_legal` (a **count**) as the `n_actions` arg and drops `legal_mask`. MCTS then expands only actions `0..n_legal-1` as raw IDs (real space is 26) and never masks illegal moves → wrong/illegal move selection.</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
