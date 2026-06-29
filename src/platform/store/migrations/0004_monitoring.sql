-- 0004_monitoring.sql
-- Read-only monitoring views for the ingest pipeline health dashboard.
-- No new stored state — all views derive from ingest_run and dead_letter.
-- Apply after 0001_init.sql + 0003_dead_letter.sql.
--
-- Dashboard queries:
--   SELECT * FROM source_health;
--   SELECT * FROM recent_dead_letters;

-- source_health: per-source 30-day summary + stale detection
CREATE OR REPLACE VIEW source_health AS
SELECT
    s.name                                                                         AS source,
    MAX(r.finished_at) FILTER (WHERE r.status = 'ok')                             AS last_success_at,
    ROUND(
        EXTRACT(EPOCH FROM (now() - MAX(r.finished_at) FILTER (WHERE r.status = 'ok'))) / 86400
    , 1)                                                                           AS days_since_success,
    COUNT(*)       FILTER (WHERE r.started_at > now() - INTERVAL '30 days')       AS runs_30d,
    COUNT(*)       FILTER (WHERE r.status = 'ok'
                               AND r.started_at > now() - INTERVAL '30 days')     AS ok_30d,
    COUNT(*)       FILTER (WHERE r.status = 'error'
                               AND r.started_at > now() - INTERVAL '30 days')     AS error_30d,
    ROUND(AVG((r.stats->>'landed')::int)
          FILTER (WHERE r.status = 'ok'
                      AND r.started_at > now() - INTERVAL '30 days'))             AS avg_landed_30d,
    ROUND(AVG(EXTRACT(EPOCH FROM (r.finished_at - r.started_at)))
          FILTER (WHERE r.status = 'ok'
                      AND r.started_at > now() - INTERVAL '30 days'))             AS avg_duration_secs,
    COUNT(dl.id)   FILTER (WHERE dl.failed_at > now() - INTERVAL '30 days')       AS dead_letters_30d
FROM source s
LEFT JOIN ingest_run  r  ON r.source_id  = s.id
LEFT JOIN dead_letter dl ON dl.source_id = s.id
GROUP BY s.name;

-- recent_dead_letters: last 7 days grouped by error prefix — spot error patterns fast
CREATE OR REPLACE VIEW recent_dead_letters AS
SELECT
    s.name              AS source,
    dl.route,
    LEFT(dl.error, 120) AS error_prefix,
    COUNT(*)            AS occurrences,
    MAX(dl.failed_at)   AS last_seen
FROM dead_letter dl
JOIN source s ON s.id = dl.source_id
WHERE dl.failed_at > now() - INTERVAL '7 days'
GROUP BY s.name, dl.route, LEFT(dl.error, 120)
ORDER BY occurrences DESC;

-- Indexes for alert query performance (alert queries filter by source_id + status + time)
CREATE INDEX IF NOT EXISTS idx_ingest_run_source_status_started
    ON ingest_run (source_id, status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_ingest_run_source_finished
    ON ingest_run (source_id, finished_at DESC);
