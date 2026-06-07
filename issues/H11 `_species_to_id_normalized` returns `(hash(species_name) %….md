---
title: "H11: `_species_to_id_normalized` returns `(hash(species_name) %…"
created: 2026-06-05
priority: high
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>H11</id>
  <title>H11: `_species_to_id_normalized` returns `(hash(species_name) %…</title>
  <location>ml/feature_extractor.py:351</location>
  <description>`_species_to_id_normalized` returns `(hash(species_name) % 10000)/10000.0`. Python `str.hash()` is salted per-process (PYTHONHASHSEED) → **different feature values every run**. battle_env.py:56 deliberately uses MD5 (`_stable_species_id`) to avoid exactly this. Trained-vs-inference feature drift. **(verified)**</description>
  <priority>HIGH</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
