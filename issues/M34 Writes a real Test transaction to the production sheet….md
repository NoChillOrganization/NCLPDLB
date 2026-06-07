---
title: "M34: Writes a real 'Test' transaction to the production sheet…"
created: 2026-06-05
priority: medium
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M34</id>
  <title>M34: Writes a real "Test" transaction to the production sheet…</title>
  <location>scripts/test_sheets_integration.py:163-193,85-147</location>
  <description>Writes a real "Test" transaction to the **production** sheet and never deletes it; asserts schema keys (`coaches`,`record`,`coach_name`) the current `sheets.py` doesn't produce (confirms H2-H5 drift).</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
