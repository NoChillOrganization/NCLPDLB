"""Ingest pipeline health checker.

Queries the DB for four alert conditions and emits JSON to stdout.
Exit 0 = no alerts, exit 1 = at least one alert fired.

Usage:
    python -m src.platform.monitoring          # print alerts + exit code
    python -m src.platform.monitoring --quiet  # exit code only (for CI gate)

Alert types
-----------
STALE_SYNC       No successful run within the source's expected cadence.
REPEATED_FAILURE Last 3 runs for the source all errored.
VOLUME_DROP      Last run landed < 50% of 30-day avg (only fires when avg >= 10).
PARSE_ERRORS     Dead-letter rows with a record key in the last 24 h > 5.

Thresholds are conservative — tuned to fire on genuine outages, not noise.
Monthly sources (smogon/pikalytics) have a 35-day window so a skipped month
does not trigger until the *second* miss.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import timezone

from src.platform.store.db import get_pool

# Days since last successful run before STALE_SYNC fires.
_STALE_DAYS: dict[str, int] = {
    "smogon": 35,       # monthly cadence; fire after second missed month
    "pikalytics": 35,
    "limitless": 2,     # daily cadence
    "showdown": 2,
}
_DEFAULT_STALE_DAYS = 7
_VOLUME_DROP_RATIO = 0.5    # alert when last run < 50% of rolling avg
_VOLUME_MIN_BASELINE = 10   # don't alert on sources that normally land < 10 records
_PARSE_ERROR_THRESHOLD = 5  # dead-letter records (with natural_key) in last 24 h


async def check_alerts(conn) -> list[dict]:
    """Return a list of alert dicts. Empty list = healthy."""
    alerts: list[dict] = []

    # 1. STALE_SYNC — last successful run older than threshold
    rows = await conn.fetch("""
        SELECT s.name, MAX(r.finished_at) AS last_ok
        FROM source s
        LEFT JOIN ingest_run r ON r.source_id = s.id AND r.status = 'ok'
        GROUP BY s.name
    """)
    from datetime import datetime as _dt
    now = _dt.now(timezone.utc)
    for row in rows:
        threshold = _STALE_DAYS.get(row["name"], _DEFAULT_STALE_DAYS)
        if row["last_ok"] is None:
            alerts.append({
                "type": "STALE_SYNC",
                "source": row["name"],
                "last_ok": None,
                "age_days": None,
                "threshold_days": threshold,
                "action": f"No successful run ever recorded for '{row['name']}'. Check runner config.",
            })
        else:
            age_days = round((now - row["last_ok"]).total_seconds() / 86400, 1)
            if age_days > threshold:
                alerts.append({
                    "type": "STALE_SYNC",
                    "source": row["name"],
                    "last_ok": row["last_ok"].isoformat(),
                    "age_days": age_days,
                    "threshold_days": threshold,
                    "action": f"Sync '{row['name']}' overdue by {age_days - threshold:.1f}d. Check sync-prod.yml run history.",
                })

    # 2. REPEATED_FAILURE — last 3 runs all errored (consecutive failures, not 3-of-any)
    rows = await conn.fetch("""
        WITH ranked AS (
            SELECT source_id, status,
                   ROW_NUMBER() OVER (PARTITION BY source_id ORDER BY started_at DESC) AS rn
            FROM ingest_run
        )
        SELECT s.name, COUNT(*) AS error_count
        FROM ranked r
        JOIN source s ON s.id = r.source_id
        WHERE r.rn <= 3 AND r.status = 'error'
        GROUP BY s.name
        HAVING COUNT(*) >= 3
    """)
    for row in rows:
        alerts.append({
            "type": "REPEATED_FAILURE",
            "source": row["name"],
            "consecutive_errors": int(row["error_count"]),
            "action": f"'{row['name']}' failed 3 consecutive runs. Check dead_letter and runner logs.",
        })

    # 3. VOLUME_DROP — last ok run landed < 50% of 30d rolling avg
    rows = await conn.fetch("""
        WITH ok_runs AS (
            SELECT source_id,
                   (stats->>'landed')::int AS landed,
                   started_at,
                   ROW_NUMBER() OVER (PARTITION BY source_id ORDER BY started_at DESC) AS rn
            FROM ingest_run
            WHERE status = 'ok' AND stats->>'landed' IS NOT NULL
        ),
        last_run AS (SELECT source_id, landed FROM ok_runs WHERE rn = 1),
        baseline AS (
            SELECT source_id, AVG(landed) AS avg_landed
            FROM ok_runs
            WHERE started_at > now() - INTERVAL '30 days' AND rn > 1
            GROUP BY source_id
            HAVING AVG(landed) >= $1
        )
        SELECT s.name, l.landed AS last_landed, ROUND(b.avg_landed) AS avg_30d
        FROM last_run l
        JOIN baseline b USING (source_id)
        JOIN source s ON s.id = l.source_id
        WHERE l.landed < b.avg_landed * $2
    """, _VOLUME_MIN_BASELINE, _VOLUME_DROP_RATIO)
    for row in rows:
        alerts.append({
            "type": "VOLUME_DROP",
            "source": row["name"],
            "last_landed": row["last_landed"],
            "avg_30d": int(row["avg_30d"]),
            "action": (
                f"'{row['name']}' landed {row['last_landed']} records vs 30d avg {int(row['avg_30d'])}. "
                "Possible upstream data gap or schema change."
            ),
        })

    # 4. PARSE_ERRORS — dead_letter rows with a natural_key (record-level failures) in last 24h
    rows = await conn.fetch("""
        SELECT s.name, COUNT(*) AS dl_count
        FROM dead_letter dl
        JOIN source s ON s.id = dl.source_id
        WHERE dl.failed_at > now() - INTERVAL '24 hours'
          AND dl.natural_key IS NOT NULL
        GROUP BY s.name
        HAVING COUNT(*) > $1
    """, _PARSE_ERROR_THRESHOLD)
    for row in rows:
        alerts.append({
            "type": "PARSE_ERRORS",
            "source": row["name"],
            "dead_letter_24h": int(row["dl_count"]),
            "action": (
                f"'{row['name']}' has {int(row['dl_count'])} parse failures in last 24h. "
                "Check dead_letter table. Possible upstream schema drift."
            ),
        })

    return alerts


async def _main(quiet: bool) -> int:
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            alerts = await check_alerts(conn)
    finally:
        await pool.close()
    if not quiet:
        print(json.dumps({"alerts": alerts}, indent=2, default=str))
    return 1 if alerts else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Check ingest pipeline health")
    p.add_argument("--quiet", action="store_true", help="Suppress JSON output; use exit code only")
    args = p.parse_args()
    sys.exit(asyncio.run(_main(args.quiet)))
