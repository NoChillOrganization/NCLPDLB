---
title: "M33: Monkey-patches private `google.auth._helpers.utcnow`…"
created: 2026-06-05
priority: medium
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M33</id>
  <title>M33: Monkey-patches private `google.auth._helpers.utcnow`…</title>
  <location>scripts/setup_google_sheet.py:33-37; setup_ml_sheet.py:33-36</location>
  <description>Monkey-patches private `google.auth._helpers.utcnow` (removed/changed in recent google-auth) → `AttributeError` swallowed; mixed aware/naive datetime handling between the two scripts.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
