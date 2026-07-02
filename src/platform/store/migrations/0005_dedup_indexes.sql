-- NULL-safe dedup indexes for tournament_team and match.
--
-- The bare UNIQUE constraints added in 0001_init.sql / 0002_analytics.sql use columns
-- that are NULLable (placement, player_external_id, round, player1_team_id,
-- player2_team_id).  Postgres NULL != NULL, so two rows with the same event_id
-- but NULL placement were not considered duplicates — they both pass the old
-- constraint and accumulate on every re-run.
--
-- Fix: drop the plain UNIQUE constraints, replace with COALESCE-based functional
-- unique indexes.  The sentinel values (-1 for integers, '' for text) are outside
-- valid data ranges, so they never collide with real data.
--
-- db_upserts.py ingest_tournament_batch is updated in the same commit to use
-- ON CONFLICT (event_id, COALESCE(...)) expression form matching these indexes.
--
-- Idempotent: DROP IF EXISTS + CREATE UNIQUE INDEX IF NOT EXISTS.
-- Depends on: 0001_init.sql, 0002_analytics.sql.

-- ─── tournament_team ──────────────────────────────────────────────────────────

ALTER TABLE tournament_team
    DROP CONSTRAINT IF EXISTS tournament_team_event_id_placement_player_external_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_tournament_team_coalesce
    ON tournament_team (
        event_id,
        COALESCE(placement, -1),
        COALESCE(player_external_id, '')
    );

-- ─── match ────────────────────────────────────────────────────────────────────

ALTER TABLE match
    DROP CONSTRAINT IF EXISTS match_event_id_round_player1_team_id_player2_team_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_match_coalesce
    ON match (
        event_id,
        COALESCE(round, -1),
        COALESCE(player1_team_id, -1),
        COALESCE(player2_team_id, -1)
    );
