---
title: "M29: `settings = Settings()` at import time with required…"
created: 2026-06-05
priority: medium
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M29</id>
  <title>M29: `settings = Settings()` at import time with required…</title>
  <location>src/config.py:86</location>
  <description>`settings = Settings()` at import time with required no-default fields → `pydantic.ValidationError` on import if `.env` incomplete; breaks tooling/tests that merely import a service.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
