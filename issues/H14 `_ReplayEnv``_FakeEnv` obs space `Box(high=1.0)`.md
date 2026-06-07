---
title: "H14: `_ReplayEnv`/`_FakeEnv` obs space `Box(high=1.0)`"
created: 2026-06-05
priority: high
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H14</id>
  <title>H14: `_ReplayEnv`/`_FakeEnv` obs space `Box(high=1.0)`</title>
  <location>ml/browser_trainer.py:205,296-298 vs battle_env.py:453</location>
  <description>`_ReplayEnv`/`_FakeEnv` obs space `Box(high=1.0)`; real env is `Box(high=2.0)`. `PPO.load(latest.zip)` + `set_env` → SB3 observation-space-mismatch error on resume.</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
