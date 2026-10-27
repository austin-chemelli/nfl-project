# ADR 0002: Parquet + in-process DuckDB under one data root

Status: accepted 2026-10-23, confirmed by the POC 2026-10-25.

## Context
Weekly batch workload, ~1M plays, solo developer, must run identically on a laptop, in a cloud job and later on a home server. No concurrent writers and no user data in 2026.

## Options
1. Parquet in layers (`raw/`, `curated/`, `marts/`) under a path, DuckDB in-process.
2. Postgres (Cloud SQL / Neon / Supabase) from the start.
3. BigQuery or MotherDuck.

## Decision
Option 1. `NFL_DATA_ROOT` is always a filesystem path: `./data` locally, a GCS bucket mounted with Cloud Storage FUSE on Cloud Run Jobs. Raw snapshots are immutable upstream bytes with a manifest; curated tables are rebuilt from raw; marts are the outputs (append-only where stated). Hive partitioning is disabled when reading raw because snapshot folder names look like partitions.

## Consequences
No API server and no accounts are possible on this alone; Postgres arrives with Approach C (2027). Local dev against hosted data is an `rsync` of the bucket. All parquet stays out of git.
