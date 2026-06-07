---
title: "M23: `evaluate()` uses `poke_env.battle1` — version-dependent…"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M23</id>
  <title>M23: `evaluate()` uses `poke_env.battle1` — version-dependent…</title>
  <location>ml/train_policy.py:1056</location>
  <description>`evaluate()` uses `poke_env.battle1` — version-dependent attribute on the SinglesEnv wrapper; `AttributeError` per eval iteration if absent.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
