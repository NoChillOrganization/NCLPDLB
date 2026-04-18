<!-- Generated: 2026-04-17 | Files scanned: ~25 | Token estimate: ~800 -->

# Backend / Services

## Cog → Service Mapping

```
/draft *        → draft_service.DraftService
/team  *        → team_service.TeamService
/elo   *        → elo_service.EloService
/stats *        → analytics_service.AnalyticsService
/spar           → showdown_player.BotChallenger
/admin *        → various (direct sheet/config ops)
/sheet *        → sheets.py (direct)
```

## draft_service.py

Core state machine for draft sessions.

```
DraftService
  start_draft(guild_id, config)        → Draft; persists to SQLite
  make_pick(guild_id, player_id, mon)  → DraftPick; persists to SQLite
  ban_pokemon(guild_id, mon)           → persists to SQLite
  reset_draft(guild_id)                → deletes from SQLite
  restore_active_drafts()              → loads all SQLite rows into _active_drafts

_timer_tasks: dict[str, asyncio.Task]  — per-guild pick timers
  _start_timer(guild_id)               → asyncio.get_running_loop().create_task(...)
  _advance_pick(guild_id)              → auto-advance + SQLite cleanup on completion
```

Formats supported: snake, auction, tiered, ban-phase.

## elo_service.py

```
EloService
  record_match(guild_id, winner_id, loser_id, ...) → MatchResult
    - Updates _elo_cache
    - _save_player() → Sheets upsert
    - _save_player_to_db() → SQLite upsert (raises on failure)
  get_standings(guild_id) → list[PlayerElo]
  restore_ratings_from_db() → populates _elo_cache from SQLite

_elo_cache: dict[guild_id, dict[player_id, PlayerElo]]
K factor: 32, default rating: settings.elo_default_rating (1000)
```

## analytics_service.py

```
AnalyticsService
  team_coverage(team) → type coverage report
  weakness_report(team) → exploitable weaknesses
  threat_score(team, opponent) → heuristic matchup score
  archetype(team) → playstyle classification
```

## notification_service.py

Discord embed helpers; no persistent state. Used by cogs to build consistent embeds.

## Key Async Patterns

- All service methods are `async def`
- Sheets calls wrapped: `await asyncio.get_event_loop().run_in_executor(None, sheets_fn)`
- SQLite calls: `async with aiosqlite.connect(DB_PATH) as conn:` (db.py handles this)
- Timer tasks: `asyncio.get_running_loop().create_task(...)` — requires active event loop
