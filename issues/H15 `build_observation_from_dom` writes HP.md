---
title: "H15: `build_observation_from_dom` writes HP"
created: 2026-06-05
priority: high
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H15</id>
  <title>H15: `build_observation_from_dom` writes HP</title>
  <location>ml/browser_trainer.py:94-124</location>
  <description>`build_observation_from_dom` writes HP→obs[0], turn→obs[2], moves→obs[3..6], but real 78-dim layout has species_id at [0], HP at [1], etc. Policy is fed semantically wrong observations (garbage).</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
