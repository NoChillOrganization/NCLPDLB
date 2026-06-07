---
title: "M11: Auction: `place_bid` records bids but there is no method to…"
created: 2026-06-05
priority: medium
status: done
tags: [audit, nclpdlb-code-review]
---
<issue>
  <id>M11</id>
  <title>M11: Auction: `place_bid` records bids but there is no method to…</title>
  <location>services/draft_service.py:393-426</location>
  <description>Auction: `place_bid` records bids but there is **no** method to close a nomination, decrement `budget`, or award the Pokémon. Auction drafts cannot complete.</description>
  <priority>MEDIUM</priority>
  <status>open</status>
  <created>2026-06-05</created>
  <source>NCLPDLB Code Audit Report (Read-Only)</source>
</issue>
