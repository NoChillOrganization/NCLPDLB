---
title: "L7: `json.loads(manifest.read_text())` unguarded"
created: 2026-06-05
priority: low
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>L7</id>
  <title>L7: `json.loads(manifest.read_text())` unguarded</title>
  <location>data_pipeline.py:125,175</location>
  <description>`json.loads(manifest.read_text())` unguarded → corrupt manifest aborts pipeline.</description>
  <priority>LOW</priority>
  <status>done</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
