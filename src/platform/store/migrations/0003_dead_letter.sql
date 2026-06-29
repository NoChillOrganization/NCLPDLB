-- 0003_dead_letter.sql
-- Durable sink for unrecoverable failures: exhausted retries + parse errors.
-- Append-only by design — a dead letter is an audit fact, not a mutable state.
-- Operator workflow: query this table, fix the root cause, re-run the sync job;
-- land_raw's ON CONFLICT DO NOTHING means re-running the batch is safe.
-- # ponytail: add (natural_key, error) dedupe index if replay noise becomes a problem.

CREATE TABLE dead_letter (
    id            BIGSERIAL PRIMARY KEY,
    source_id     INT         REFERENCES source(id),
    route         TEXT        NOT NULL,
    natural_key   TEXT,
    payload       JSONB,              -- raw payload if available; NULL on fetch-level failure
    error         TEXT        NOT NULL,
    failed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ingest_run_id BIGINT      REFERENCES ingest_run(id)
);

CREATE INDEX idx_dead_letter_source ON dead_letter (source_id, failed_at DESC);
