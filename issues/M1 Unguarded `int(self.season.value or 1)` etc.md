---
title: "M1: Unguarded `int(self.season.value or 1)` etc"
created: 2026-06-05
priority: medium
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M1</id>
  <title>M1: Unguarded `int(self.season.value or 1)` etc</title>
  <location>bot/cogs/draft.py:57-60,168-172</location>
  <description>Unguarded `int(self.season.value or 1)` etc. on free-text modal inputs → `ValueError` → "interaction failed" with no user feedback. Same at sheet.py:49 (`int(week)`).</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
