-- Analytics schema extensions. Extends 0001_init.sql — do not apply without it.
-- Idempotent: ADD COLUMN uses IF NOT EXISTS; constraints use DO/EXCEPTION blocks;
-- CREATE TABLE/INDEX use IF NOT EXISTS. The db.py migration ledger prevents
-- re-runs in normal operation; these guards make the file safe for manual psql -f.

-- ============================================================
-- A. tournament_team_member — Pokémon build columns
-- ============================================================
-- 0001 has: item TEXT, ability TEXT, tera_type TEXT, moves JSONB
-- Add: nature, level, 6 named EV cols, 6 named IV cols.

ALTER TABLE tournament_team_member
    ADD COLUMN IF NOT EXISTS nature  TEXT,
    ADD COLUMN IF NOT EXISTS level   SMALLINT,
    ADD COLUMN IF NOT EXISTS ev_hp   SMALLINT,
    ADD COLUMN IF NOT EXISTS ev_atk  SMALLINT,
    ADD COLUMN IF NOT EXISTS ev_def  SMALLINT,
    ADD COLUMN IF NOT EXISTS ev_spa  SMALLINT,
    ADD COLUMN IF NOT EXISTS ev_spd  SMALLINT,
    ADD COLUMN IF NOT EXISTS ev_spe  SMALLINT,
    ADD COLUMN IF NOT EXISTS iv_hp   SMALLINT,
    ADD COLUMN IF NOT EXISTS iv_atk  SMALLINT,
    ADD COLUMN IF NOT EXISTS iv_def  SMALLINT,
    ADD COLUMN IF NOT EXISTS iv_spa  SMALLINT,
    ADD COLUMN IF NOT EXISTS iv_spd  SMALLINT,
    ADD COLUMN IF NOT EXISTS iv_spe  SMALLINT;

-- EV range checks (NULL passes; only populated values are validated).
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT chk_ttm_ev_hp  CHECK (ev_hp  BETWEEN 0 AND 252);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT chk_ttm_ev_atk CHECK (ev_atk BETWEEN 0 AND 252);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT chk_ttm_ev_def CHECK (ev_def BETWEEN 0 AND 252);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT chk_ttm_ev_spa CHECK (ev_spa BETWEEN 0 AND 252);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT chk_ttm_ev_spd CHECK (ev_spd BETWEEN 0 AND 252);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT chk_ttm_ev_spe CHECK (ev_spe BETWEEN 0 AND 252);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Total EV cap: coalesce so partial builds still validate.
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT chk_ttm_ev_total CHECK (
        (COALESCE(ev_hp,0) + COALESCE(ev_atk,0) + COALESCE(ev_def,0) +
         COALESCE(ev_spa,0) + COALESCE(ev_spd,0) + COALESCE(ev_spe,0)) <= 510
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- IV range checks.
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT chk_ttm_iv_hp  CHECK (iv_hp  BETWEEN 0 AND 31);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT chk_ttm_iv_atk CHECK (iv_atk BETWEEN 0 AND 31);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT chk_ttm_iv_def CHECK (iv_def BETWEEN 0 AND 31);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT chk_ttm_iv_spa CHECK (iv_spa BETWEEN 0 AND 31);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT chk_ttm_iv_spd CHECK (iv_spd BETWEEN 0 AND 31);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT chk_ttm_iv_spe CHECK (iv_spe BETWEEN 0 AND 31);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Level check.
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT chk_ttm_level CHECK (level BETWEEN 1 AND 100);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Natural key: enables ON CONFLICT (team_id, slot) upserts from normalize/tournament.py.
-- Safe to add as long as no duplicate (team_id, slot) rows exist in dev data.
DO $$ BEGIN
    ALTER TABLE tournament_team_member ADD CONSTRAINT uq_ttm_team_slot UNIQUE (team_id, slot);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ============================================================
-- B. replay_team — Pokémon build columns  (= "replay_pokemon")
-- ============================================================
-- 0001 has: canonical_species_id, brought BOOL, lead BOOL.
-- Showdown logs do not carry EV/IV/nature/item — all nullable.
-- Columns match tournament_team_member shape so analytics joins are uniform.

ALTER TABLE replay_team
    ADD COLUMN IF NOT EXISTS item     TEXT,
    ADD COLUMN IF NOT EXISTS ability  TEXT,
    ADD COLUMN IF NOT EXISTS tera_type TEXT,
    ADD COLUMN IF NOT EXISTS moves    JSONB,
    ADD COLUMN IF NOT EXISTS nature   TEXT,
    ADD COLUMN IF NOT EXISTS level    SMALLINT,
    ADD COLUMN IF NOT EXISTS ev_hp    SMALLINT,
    ADD COLUMN IF NOT EXISTS ev_atk   SMALLINT,
    ADD COLUMN IF NOT EXISTS ev_def   SMALLINT,
    ADD COLUMN IF NOT EXISTS ev_spa   SMALLINT,
    ADD COLUMN IF NOT EXISTS ev_spd   SMALLINT,
    ADD COLUMN IF NOT EXISTS ev_spe   SMALLINT,
    ADD COLUMN IF NOT EXISTS iv_hp    SMALLINT,
    ADD COLUMN IF NOT EXISTS iv_atk   SMALLINT,
    ADD COLUMN IF NOT EXISTS iv_def   SMALLINT,
    ADD COLUMN IF NOT EXISTS iv_spa   SMALLINT,
    ADD COLUMN IF NOT EXISTS iv_spd   SMALLINT,
    ADD COLUMN IF NOT EXISTS iv_spe   SMALLINT;

-- EV range checks.
DO $$ BEGIN
    ALTER TABLE replay_team ADD CONSTRAINT chk_rt_ev_hp  CHECK (ev_hp  BETWEEN 0 AND 252);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE replay_team ADD CONSTRAINT chk_rt_ev_atk CHECK (ev_atk BETWEEN 0 AND 252);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE replay_team ADD CONSTRAINT chk_rt_ev_def CHECK (ev_def BETWEEN 0 AND 252);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE replay_team ADD CONSTRAINT chk_rt_ev_spa CHECK (ev_spa BETWEEN 0 AND 252);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE replay_team ADD CONSTRAINT chk_rt_ev_spd CHECK (ev_spd BETWEEN 0 AND 252);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE replay_team ADD CONSTRAINT chk_rt_ev_spe CHECK (ev_spe BETWEEN 0 AND 252);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE replay_team ADD CONSTRAINT chk_rt_ev_total CHECK (
        (COALESCE(ev_hp,0) + COALESCE(ev_atk,0) + COALESCE(ev_def,0) +
         COALESCE(ev_spa,0) + COALESCE(ev_spd,0) + COALESCE(ev_spe,0)) <= 510
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- IV range checks.
DO $$ BEGIN
    ALTER TABLE replay_team ADD CONSTRAINT chk_rt_iv_hp  CHECK (iv_hp  BETWEEN 0 AND 31);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE replay_team ADD CONSTRAINT chk_rt_iv_atk CHECK (iv_atk BETWEEN 0 AND 31);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE replay_team ADD CONSTRAINT chk_rt_iv_def CHECK (iv_def BETWEEN 0 AND 31);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE replay_team ADD CONSTRAINT chk_rt_iv_spa CHECK (iv_spa BETWEEN 0 AND 31);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE replay_team ADD CONSTRAINT chk_rt_iv_spd CHECK (iv_spd BETWEEN 0 AND 31);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE replay_team ADD CONSTRAINT chk_rt_iv_spe CHECK (iv_spe BETWEEN 0 AND 31);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Level check.
DO $$ BEGIN
    ALTER TABLE replay_team ADD CONSTRAINT chk_rt_level CHECK (level BETWEEN 1 AND 100);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ============================================================
-- C. match — tournament per-game pairings and results
-- ============================================================
-- Schema-only. The Limitless adapter does not yet emit pairings;
-- population is follow-up normalizer work. winner_team_id NULL = result unknown/pending.

CREATE TABLE IF NOT EXISTS match (
    id               SERIAL PRIMARY KEY,
    event_id         INTEGER  NOT NULL REFERENCES tournament_event(id),
    round            INTEGER,
    table_number     INTEGER,
    player1_team_id  INTEGER  REFERENCES tournament_team(id),
    player2_team_id  INTEGER  REFERENCES tournament_team(id),
    winner_team_id   INTEGER  REFERENCES tournament_team(id),
    score            TEXT,                          -- e.g. "2-1"
    raw_text         TEXT,
    raw_json         JSONB,
    raw_ingest_id    BIGINT   REFERENCES raw_ingest(id),
    UNIQUE (event_id, round, player1_team_id, player2_team_id)
);

-- ============================================================
-- D. replay_move — per-move events (promoted from replay_battle.turns JSONB)
-- ============================================================
-- ponytail: turns JSONB still exists for backward compat and re-parse;
--           this table is populated lazily by a future explode job.
-- occurred_at is denormalized from replay.uploaded_at — required for future
-- RANGE partitioning without a join. See docs/platform-partitioning.md.
-- UNIQUE covers per-turn per-slot per-move; extremely rare doubles-mechanics
-- edge case (same slot, same move, same turn) will be handled by the writer
-- via ON CONFLICT DO NOTHING with a raw_text/json merge if ever encountered.

CREATE TABLE IF NOT EXISTS replay_move (
    id               BIGSERIAL PRIMARY KEY,
    replay_battle_id INTEGER      NOT NULL REFERENCES replay_battle(id),
    turn             INTEGER      NOT NULL,
    occurred_at      TIMESTAMPTZ,               -- partition key candidate
    player_slot      TEXT,                       -- 'p1a' | 'p1b' | 'p2a' | 'p2b'
    actor_species_id INTEGER      REFERENCES canonical_species(id),
    move_name        TEXT,
    target_slot      TEXT,
    raw_text         TEXT,                       -- original log line
    raw_json         JSONB,                      -- structured event from turns[].events[]
    UNIQUE (replay_battle_id, turn, player_slot, move_name)
);

-- ============================================================
-- E. raw_text columns on raw_ingest and replay
-- ============================================================
-- raw_ingest.payload JSONB already covers structured raw_json.
-- raw_text stores the verbatim replay log or HTML for re-parse without re-fetch.

ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS raw_text TEXT;
ALTER TABLE replay     ADD COLUMN IF NOT EXISTS raw_text TEXT;

-- ============================================================
-- F. Indexes
-- ============================================================

-- replay hot paths
CREATE INDEX IF NOT EXISTS idx_replay_format_uploaded
    ON replay (format_id, uploaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_replay_team_species
    ON replay_team (canonical_species_id);

CREATE INDEX IF NOT EXISTS idx_replay_move_battle_turn
    ON replay_move (replay_battle_id, turn);

CREATE INDEX IF NOT EXISTS idx_replay_move_name
    ON replay_move (move_name);

CREATE INDEX IF NOT EXISTS idx_replay_move_actor
    ON replay_move (actor_species_id);

-- replay_move occurred_at for future partition pruning / date-bounded queries
CREATE INDEX IF NOT EXISTS idx_replay_move_occurred
    ON replay_move (occurred_at DESC);

-- species alias — source-agnostic resolution and case-insensitive name probe
CREATE INDEX IF NOT EXISTS idx_species_alias_key
    ON species_alias (normalized_key);

CREATE INDEX IF NOT EXISTS idx_species_alias_raw_lower
    ON species_alias (lower(raw_name));
