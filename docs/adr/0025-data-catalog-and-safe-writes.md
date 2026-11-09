# ADR 0025: A SQL catalog over the parquet files, and safe writes, instead of a database server

Status: accepted 2026-11-08 (Austin). Keeps ADR 0015's storage (parquet in one private bucket, Cloud Run Jobs as the primary writer) and ADR 0005's point-in-time rules; adds a query layer and write rules on top.

## Context
Austin asked whether the project should use a real database: every question means writing Polars and glob code, cross-source joins are hand-written per module, PR diffs look huge, and the planned second-level (interaction) features join plays, FTN charting, participation, depth charts and injuries. The review (`.notes/data-storage-review.md`, 2026-11-08) measured:

- Size: the production bucket holds raw 691 MB, curated 146 MB, marts 61 MB; the feature store is 920k rows in 5.5 MB. DuckDB reads over any table take 1 to 80 ms. Size and speed aren't the problem.
- The big diffs are regenerated test fixtures and reference data (35k of 113k added lines), not data: parquet never enters git.
- Real gaps: no query surface; append-only marts rewritten whole on every append (`predict.py`, `ledger.py`, `previews.py`, `strong_calls.py`, `totals.py`); every feature file rewritten even with nothing new (`store.write_features`); in-place writes that a crash can leave half-written; no lock between jobs; most marts without a declared schema.

## Options
1. **A catalog over the files.** DuckDB views over the existing parquet, built per process, plus SQL models for derived data. No server, no cost, nothing migrated; writes stay as they are unless changed on purpose.
2. **DuckLake** (DuckDB's table format, 1.0 since 2026-04-13: parquet data plus a catalog database, with transactions and time travel). Real tables and safe concurrent writers, but every writer changes, and multi-writer needs a Postgres catalog (another service).
3. **A database server** (Postgres on Cloud SQL from about $9-11/month, or Neon/Supabase free tiers). Strong constraints and concurrency, but a row store is the wrong engine for 1.3M-row play scans, every reader and writer is rewritten, and local work needs the network.
4. **MotherDuck or BigQuery.** Excellent SQL, but a vendor and credentials for every run, and cost risk, for 0.2 GB of working data.

## Decision
Option 1, in phases, with DuckLake held for a trigger:

- **Phase 0, fixtures:** `.gitattributes` marks fixtures and lockfiles `linguist-generated`, so GitHub collapses them in PR diffs; `git diff` still shows them.
- **Phase 1, the catalog:** `nfl.catalog.connect(paths)` returns an in-memory DuckDB connection with one view per table in `catalog.TABLES` (curated tables by season, the feature store, every mart as one file or a folder of parts), and the macros `features_asof(ts)` and `game_vectors(ts)`, held equal to `store.as_of` and `store.game_vectors` by tests. `nfl sql` runs a query or lists the views. The catalog is built per process and never written, so it can't drift from the files.
- **Phase 2, safe writes:** one write helper (declared schema, temp file then rename); append-only marts as one file per append, so an append never rewrites history; feature writes skip files with nothing new and live jobs build the current season; a job lock in the data bucket for the jobs that write marts.
- **Phase 3, SQL models** for derived, cross-source data, with a leakage test per model, when the interaction-feature work starts (after its validation spike).
- **Phase 4, DuckLake**, only if one of these happens: two writers really contend, rewrite time shows in job minutes, a table needs time travel beyond `known_as_of`, or data passes 5-10 GB.

## Consequences
- Every question about the data is one SQL query, including point-in-time ones; new sources are one line in `catalog.TABLES`.
- Nothing about storage, the bucket, the site contract, the lock artifacts or the long feature schema changes in phases 0 and 1; phase 2 changes how marts are written, one at a time, with append-only tests.
- Two implementations of the as-of rule now exist (Polars and SQL); the parity tests are what keep them one rule. A SQL model that skips `features_asof` can leak the future: every model gets a leakage test.
- Views list a table's files when the connection opens; a long-lived connection won't see files written after that.
