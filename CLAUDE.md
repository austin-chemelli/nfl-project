# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A weekly NFL **matchup breakdown and predictor**. Every week it ingests new data, updates team tendency profiles, predicts every game (win probability, spread, total, score distribution), publishes matchup breakdowns, and publicly scores last week's predictions. Later, a "predict the tendencies" game lets users forecast team behavior and get scored against reality and the model.

This is a public portfolio project. The goal is a **live, shipped** system with real measurements (accuracy, calibration, cost, latency) and evals, not a feature list.

Full scope, workstreams, draft tiers and open decisions: [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md). That brief is the source of truth; if something here conflicts with it, the brief wins. Don't treat an open decision in the brief as settled. Ask.

## Status

Early setup (late Oct 2026). No code yet. About 10 regular-season weeks plus playoffs remain in the 2026 season, so a crude live pipeline ships early and the backtest harness is built alongside it.

## Non-negotiable principles

1. **The LLM stays out of the numeric core.** Models produce the numbers; LLMs explain and enrich. Every number that gets published is checked against the data first. Never let generated text introduce a statistic that wasn't computed.
2. **Point-in-time correctness everywhere.** Every record carries a "known as of" timestamp. A prediction for week `w` may only use data known before week `w` kicks off. When backtest results look too good, assume leakage before assuming skill.
3. **Ship live early.** Live, publicly scored predictions can't be backfilled. Prefer a working end-to-end pipeline over polishing one component.
4. **Be honest about limitations**: observational data, small samples, efficient markets. Say so in output and docs.

## Planned stack

- **Backend / pipelines:** Python (primary). Parquet + DuckDB for storage and queries.
- **Frontend:** TypeScript + React (comes after the data is solid).
- **Infra:** Docker, Terraform, CI, deploy to GCP. Scheduled jobs follow the NFL week: Tuesday refresh and model run, Wed–Fri injury enrichment, a pre-game inactives update, post-game grading.
- **Observability:** pipeline freshness, LLM traces with cost and latency, failure alerts.

Commands, layout and tooling go here once they exist. Don't invent them.

## Domain notes

### Data (nflverse)
- Play-by-play back to 1999 (EPA, win probability), updated nightly in-season. Participation data (formation, personnel, box count, pass rushers, man/zone flag). FTN charting 2022+ (motion, play-action, RPO, screen, etc.). Schedules include betting lines.
- **Verify before designing around a field**: run a null-rate audit first. Coverage-shell or play-name fields haven't been confirmed. Injury data freshness in-season isn't confirmed either.
- No coordinator table exists; the coaching-staff mapping has to be built by hand or by LLM extraction.
- **Licensing:** nflverse is CC-BY (credit in README). FTN charting is CC-BY-SA 4.0, so check the share-alike implications before publishing derived data. Include the "fan-made, not affiliated with the NFL" disclaimer. No team or league logos.

### Ingestion
Idempotent and scheduled. Re-running a job must not duplicate or corrupt data. Backfill starts at 2022.

### Tendency store
Per team × situation bucket (down, distance, field zone, score state), offense and defense. Blend league prior + coordinator history + current season with exponential recency decay and beta-binomial shrinkage. Handle discontinuities such as coordinator or QB changes explicitly.

### Models and evaluation
- Model "philosophies": Elo-style, opponent-adjusted EPA, tendency-matchup Monte Carlo drive sim, market-anchored, ensemble. Each has a parameter grid (decay half-life, HFA, shrinkage).
- Walk-forward backtest only: predict week `w` with data through `w-1`. Tune on 2022–2024, select on 2025, run the winners live for 2026.
- Metrics: log loss, Brier, spread MAE, calibration, ATS, CLV. Leakage guards are automated tests, not manual checks.

### LLM enrichment
Three separate jobs. Keep them separate in code too:
- **Concept explanations:** general football knowledge, labeled as general.
- **Research agent:** structured, timestamped, cited facts (`claim`, `source`, `date`, `confidence`). Check verifiable claims against the tendency store and flag conflicts.
- **Feature extraction for models:** needs the most rigor. Web search can't be fairly backtested (hindsight leakage), so evaluate LLM features live or restrict to point-in-time sources.

Headline experiment: does enrichment improve forecasts compared with the same model without it? Keep both paths runnable.

### Odds and paper ledger
Model probabilities → fair odds → edge vs. market → fractional Kelly sizing. Paper bets are immutable and timestamped at real odds. **Closing-line value is the primary edge metric**; season P&L is mostly noise. No real-money betting and no sportsbook automation.

## Working conventions

- Prefer small, verifiable steps that move toward a live pipeline.
- Tests for anything touching time boundaries (as-of joins, walk-forward splits, ledger immutability).
- LLM calls log model, prompt version, tokens, cost and latency.
- Writing about how AI coding tools were used is part of the project. Note notable wins or failures and how output was verified when they come up.
