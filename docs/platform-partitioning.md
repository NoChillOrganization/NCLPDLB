# Replay Table Partitioning Guide

Reference for converting the three replay tables to declarative range partitioning when volume
warrants it. The `0002_analytics.sql` migration does **not** apply partitioning — it only adds
`occurred_at TIMESTAMPTZ` to `replay_move` as the future partition key.

---

## When to partition

Do not partition prematurely. Partition `replay_move` first, only when either condition is met:

| Signal | Threshold |
|--------|-----------|
| Row count | > 50 million rows in `replay_move` |
| Query latency (date-bounded scan) | p95 > 500 ms on `WHERE occurred_at BETWEEN ...` after index tuning |

At typical tournament volume (~20k replays/year, ~100 moves/battle) you won't hit 50M for years.
Partition `replay` and `replay_battle` only if `replay_move` partitioning alone proves insufficient.

---

## Why not now

1. You **cannot** `ALTER` a populated table into a partitioned table in place. Migration requires
   rename → create parent → insert → swap → drop, which takes a full table lock during the swap.
2. Declarative partitioning adds operational complexity: `pg_partman` setup, partition pruning
   verification, index duplication across child partitions.
3. The `idx_replay_move_occurred` index added in `0002_analytics.sql` gives fast date-bounded
   scans without partitioning until the threshold above is reached.

---

## Partition key design

Postgres requires the partition key to be part of the primary key. The current `BIGSERIAL PRIMARY KEY`
must become `PRIMARY KEY (id, occurred_at)`. This affects:

- `replay_move` → partition on `occurred_at TIMESTAMPTZ` (monthly range)
- `replay_battle` → if partitioned, partition on `normalized_at TIMESTAMPTZ` (monthly range)
- `replay` → if partitioned, partition on `uploaded_at TIMESTAMPTZ` (monthly range)

`occurred_at` in `replay_move` is denormalized from `replay.uploaded_at` specifically to enable
partitioning without a join.

---

## Migration recipe (monthly range)

Run once per table, in a maintenance window or with `lock_timeout` set.

```sql
-- Step 1: rename the current table
ALTER TABLE replay_move RENAME TO replay_move_old;

-- Step 2: drop the old index (will be recreated per partition)
-- (named indexes must be dropped first)

-- Step 3: create the partitioned parent
CREATE TABLE replay_move (
    id               BIGSERIAL,
    replay_battle_id INTEGER      NOT NULL,
    turn             INTEGER      NOT NULL,
    occurred_at      TIMESTAMPTZ  NOT NULL,   -- NOT NULL required for RANGE partitioning
    player_slot      TEXT,
    actor_species_id INTEGER,
    move_name        TEXT,
    target_slot      TEXT,
    raw_text         TEXT,
    raw_json         JSONB,
    PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at);

-- Add FKs on parent (inherited by children):
ALTER TABLE replay_move
    ADD CONSTRAINT fk_rm_battle FOREIGN KEY (replay_battle_id)
        REFERENCES replay_battle(id),
    ADD CONSTRAINT fk_rm_species FOREIGN KEY (actor_species_id)
        REFERENCES canonical_species(id);

-- Step 4: create initial monthly partitions covering existing data range.
-- Replace date literals with your actual data range.
-- With pg_partman (recommended) this is automated — see below.
CREATE TABLE replay_move_2024_01 PARTITION OF replay_move
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
CREATE TABLE replay_move_2024_02 PARTITION OF replay_move
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');
-- ... continue for each month ...

-- Step 5: recreate indexes (Postgres does NOT inherit indexes from parent DDL)
CREATE INDEX ON replay_move (replay_battle_id, turn);
CREATE INDEX ON replay_move (move_name);
CREATE INDEX ON replay_move (actor_species_id);
CREATE INDEX ON replay_move (occurred_at DESC);

-- Step 6: copy data
INSERT INTO replay_move
    SELECT id, replay_battle_id, turn, occurred_at, player_slot,
           actor_species_id, move_name, target_slot, raw_text, raw_json
    FROM replay_move_old;

-- Step 7: verify row counts match, then drop old table
-- SELECT COUNT(*) FROM replay_move;
-- SELECT COUNT(*) FROM replay_move_old;
DROP TABLE replay_move_old;
```

> **Lock note**: `INSERT INTO ... SELECT` on step 6 holds no exclusive lock on `replay_move` since
> it's a new empty table. The brief exclusive lock only happens on `DROP TABLE replay_move_old` in
> step 7, which is a single fast DDL op.

---

## Automating partition creation with pg_partman

`pg_partman` handles rolling partition creation and retention automatically. Install via your
package manager (`postgresql-<ver>-partman` or the extension from PGXN).

```sql
-- Enable the extension (superuser required)
CREATE EXTENSION IF NOT EXISTS pg_partman SCHEMA partman;

-- Register replay_move for monthly management
SELECT partman.create_parent(
    p_parent_table   => 'public.replay_move',
    p_control        => 'occurred_at',
    p_interval       => '1 month',
    p_premake        => 4,              -- pre-create 4 future months
    p_start_partition => '2024-01-01'   -- earliest data date
);

-- Run maintenance manually (or schedule via pg_cron)
CALL partman.run_maintenance_proc();
```

Schedule `run_maintenance_proc()` to run nightly via `pg_cron` or an external cron job. It creates
future partitions (`p_premake` months ahead) and optionally drops old ones based on a retention
policy you configure in `part_config`.

> ponytail: don't hand-roll a partition-maker cron until pg_partman proves insufficient. It handles
> edge cases (DST transitions, leap months, default partition fallback) you'll waste days on.

---

## Retention policy

Add a retention window to `part_config` after registering with `create_parent`:

```sql
UPDATE partman.part_config
SET    retention = '2 years',
       retention_keep_table = false    -- actually drop, not just detach
WHERE  parent_table = 'public.replay_move';
```

Adjust `retention` to match your analytics horizon and storage budget.

---

## Verification checklist

After migration:

```sql
-- Partition map
SELECT nmsp_parent.nspname AS schema,
       parent.relname       AS parent,
       child.relname        AS partition
FROM   pg_inherits
JOIN   pg_class parent      ON pg_inherits.inhparent = parent.oid
JOIN   pg_class child       ON pg_inherits.inhrelid  = child.oid
JOIN   pg_namespace nmsp_parent ON parent.relnamespace = nmsp_parent.oid
WHERE  parent.relname = 'replay_move'
ORDER  BY child.relname;

-- Confirm partition pruning is active for a date-bounded query
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*) FROM replay_move
WHERE occurred_at BETWEEN '2024-06-01' AND '2024-07-01';
-- Look for "Partitions selected: 1" in the plan output.

-- Row count sanity check
SELECT tableoid::regclass AS partition, COUNT(*) FROM replay_move GROUP BY 1 ORDER BY 1;
```
