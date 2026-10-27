# ADR 0005: Point-in-time regimes, append-only rows, two lock points

Status: accepted 2026-10-23, extended 2026-10-26.

## Context
Backtests leak unless every input is dated; live predictions are only credible if they are provably pre-kickoff. Historical nflverse data is not bitemporal.

## Decision
- Backtest as-of = game-week filter on the current snapshot, stamped `known_as_of = kickoff − 2h` (synthetic), strictly before the `kickoff − 1h` synthetic lock. Live as-of = ingestion snapshot timestamp. A lock may use only rows with `known_as_of < lock_ts`.
- Fits used in season S are trained through S−1 and frozen; any in-season refit is a new `model_version` with new rows.
- Prediction and bet rows are append-only; grading uses the last lock before kickoff.
- Two lock points per week: Thursday ~9am ET (TNF) and Saturday noon ET (after the Friday injury report). Pre-game inactives re-lock is offseason work.
- Each lock writes `public/predictions/<season>/week_<w>_<slot>.json` and its SHA-256 to git; the commit timestamp is the public proof.
- Leakage guards are pytest tests, run in CI.

## Consequences
Historical features are "as good as the final data", which overstates what was knowable (injuries, late line moves); the docs say so. The live system is strictly honest. Two locks per week means the Saturday run must not overwrite Thursday rows.
