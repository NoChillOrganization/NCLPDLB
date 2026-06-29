-- Competitive data platform schema. See plans/.../architecture design.
-- ponytail: plain numbered SQL migrations, add alembic if branching schema history appears.

CREATE TABLE source (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL CHECK (name IN ('smogon', 'pikalytics', 'limitless', 'showdown')),
    kind TEXT NOT NULL
);
INSERT INTO source (name, kind) VALUES
    ('smogon', 'usage'), ('pikalytics', 'usage'), ('limitless', 'tournament'), ('showdown', 'replay');

CREATE TABLE ingest_run (
    id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES source(id),
    route TEXT NOT NULL CHECK (route IN ('tournament', 'usage', 'replay')),
    mode TEXT NOT NULL CHECK (mode IN ('periodic', 'event', 'replay_targeted')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    stats JSONB
);

CREATE TABLE raw_ingest (
    id BIGSERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES source(id),
    route TEXT NOT NULL CHECK (route IN ('tournament', 'usage', 'replay')),
    natural_key TEXT NOT NULL,
    url TEXT,
    payload JSONB NOT NULL,
    payload_hash TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'normalized', 'error')),
    processed_at TIMESTAMPTZ,
    normalizer_version INTEGER,
    UNIQUE (source_id, natural_key, payload_hash)
);
CREATE INDEX idx_raw_ingest_pending ON raw_ingest (status) WHERE status = 'pending';

CREATE TABLE canonical_species (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    national_dex INTEGER,
    display_name TEXT NOT NULL,
    base_forme_slug TEXT,
    is_forme BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE species_alias (
    id SERIAL PRIMARY KEY,
    canonical_species_id INTEGER NOT NULL REFERENCES canonical_species(id),
    source_id INTEGER REFERENCES source(id),
    raw_name TEXT NOT NULL,
    normalized_key TEXT NOT NULL,
    UNIQUE (source_id, normalized_key)
);

CREATE TABLE canonical_format (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    label TEXT NOT NULL,
    generation INTEGER NOT NULL,
    game_type TEXT NOT NULL CHECK (game_type IN ('singles', 'doubles')),
    regulation TEXT
);

-- Route 1: tournament (Limitless)
CREATE TABLE tournament_event (
    id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES source(id),
    external_id TEXT NOT NULL,
    name TEXT NOT NULL,
    format_id INTEGER REFERENCES canonical_format(id),
    event_date DATE,
    level TEXT CHECK (level IN ('online', 'major', 'champions')),
    url TEXT,
    raw_ingest_id BIGINT REFERENCES raw_ingest(id),
    UNIQUE (source_id, external_id)
);

CREATE TABLE tournament_team (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES tournament_event(id),
    placement INTEGER,
    player_name TEXT,
    player_external_id TEXT,
    wins INTEGER,
    losses INTEGER,
    raw_ingest_id BIGINT REFERENCES raw_ingest(id),
    UNIQUE (event_id, placement, player_external_id)
);

CREATE TABLE tournament_team_member (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES tournament_team(id),
    canonical_species_id INTEGER REFERENCES canonical_species(id),
    slot INTEGER NOT NULL,
    item TEXT,
    ability TEXT,
    tera_type TEXT,
    moves JSONB
);

-- Route 2: usage (Smogon, Pikalytics)
CREATE TABLE usage_snapshot (
    id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES source(id),
    format_id INTEGER REFERENCES canonical_format(id),
    period DATE NOT NULL,
    elo_cutoff INTEGER,
    sample_size INTEGER,
    raw_ingest_id BIGINT REFERENCES raw_ingest(id),
    UNIQUE (source_id, format_id, period, elo_cutoff)
);

CREATE TABLE usage_entry (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES usage_snapshot(id),
    canonical_species_id INTEGER REFERENCES canonical_species(id),
    rank INTEGER,
    usage_pct NUMERIC,
    raw_count INTEGER,
    UNIQUE (snapshot_id, canonical_species_id)
);

CREATE TABLE usage_moveset (
    id SERIAL PRIMARY KEY,
    usage_entry_id INTEGER NOT NULL REFERENCES usage_entry(id),
    moves JSONB,
    items JSONB,
    spreads JSONB,
    abilities JSONB,
    teammates JSONB,
    checks JSONB
);

-- Route 3: replay (Showdown)
-- ponytail: turns stored as jsonb, not a replay_turn table. Promote to relational only if
-- per-turn SQL queries are actually needed.
CREATE TABLE replay (
    id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES source(id),
    replay_id TEXT UNIQUE NOT NULL,
    format_id INTEGER REFERENCES canonical_format(id),
    uploaded_at TIMESTAMPTZ,
    players JSONB,
    rating INTEGER,
    log_hash TEXT,
    raw_ingest_id BIGINT REFERENCES raw_ingest(id)
);

CREATE TABLE replay_battle (
    id SERIAL PRIMARY KEY,
    replay_id INTEGER NOT NULL REFERENCES replay(id),
    winner TEXT,
    turn_count INTEGER,
    turns JSONB,
    parser_version INTEGER NOT NULL,
    normalized_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (replay_id, parser_version)
);

CREATE TABLE replay_team (
    id SERIAL PRIMARY KEY,
    replay_battle_id INTEGER NOT NULL REFERENCES replay_battle(id),
    player_slot INTEGER NOT NULL,
    canonical_species_id INTEGER REFERENCES canonical_species(id),
    brought BOOLEAN NOT NULL DEFAULT false,
    lead BOOLEAN NOT NULL DEFAULT false
);
