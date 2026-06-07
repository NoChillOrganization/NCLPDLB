---
title: "M21: `predict`/`policy_probs` do `masked_fill(mask, -inf)` then…"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M21</id>
  <title>M21: `predict`/`policy_probs` do `masked_fill(mask, -inf)` then…</title>
  <location>ml/transformer_model.py:260,290</location>
  <description>`predict`/`policy_probs` do `masked_fill(mask, -inf)` then softmax; all-illegal mask → all `-inf` → NaN → undefined argmax/sampling.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
