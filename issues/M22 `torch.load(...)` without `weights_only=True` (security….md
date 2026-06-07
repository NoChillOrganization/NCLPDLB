---
title: "M22: `torch.load(...)` without `weights_only=True` (security:…"
created: 2026-06-05
priority: medium
status: open
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M22</id>
  <title>M22: `torch.load(...)` without `weights_only=True` (security:…</title>
  <location>ml/train_policy.py:278; pretrain weights load</location>
  <description>`torch.load(...)` without `weights_only=True` (security: arbitrary code exec on malicious `.pt` via `--pretrain`). Inconsistent with `transformer_model.load_model`.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
