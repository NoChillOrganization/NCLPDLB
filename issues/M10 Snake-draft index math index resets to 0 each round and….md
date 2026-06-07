---
title: "M10: Snake-draft index math: index resets to 0 each round and…"
created: 2026-06-05
priority: medium
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M10</id>
  <title>M10: Snake-draft index math: index resets to 0 each round and…</title>
  <location>services/draft_service.py (models.py:237-248)</location>
  <description>Snake-draft index math: index resets to 0 each round and reversal keyed on `current_round % 2` does not give the end-of-round player back-to-back picks. Snake order wrong at every round boundary.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
