---
title: "H16: `policy.learn(total_timesteps=n_trans)` on `_ReplayEnv`…"
created: 2026-06-05
priority: high
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H16</id>
  <title>H16: `policy.learn(total_timesteps=n_trans)` on `_ReplayEnv`…</title>
  <location>ml/browser_trainer.py:418-443</location>
  <description>`policy.learn(total_timesteps=n_trans)` on `_ReplayEnv` does **not** train on recorded transitions — PPO samples its own actions against a canned-observation env. "Policy updated from N transitions" is misleading; no offline learning occurs.</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
