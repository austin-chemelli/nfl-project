# NFL Matchup Predictor — Project Brief

Handoff from planning conversations (Oct 2026). Source of truth for scope and goals. Decisions are recorded in [adr/](adr/) and the plan in [architecture.md](architecture.md) and [tasks.md](tasks.md); where this brief and an ADR disagree, the ADR records the resolution.

**Reframed 2026-10-25 (ADR 0003):** educational preview tool first, betting as a scoring lens. "Model philosophies" became a shared feature store plus persona-style *approaches* (Traditionalist, Analyst, Sharp; later Matchup, Narrative), each with a persona and a fitted flavor, plus an ensemble, odds-weighted paper bets, divergence-from-market analysis, and a Hypotheses page.

## Why this project
- A **public, shipped, live** project showing strategic, effective use of LLMs/agents.
- Skills not shown elsewhere: hosting/deployment, IaC, CI/CD, frontend (TypeScript), real-world data.
- Real measurements (accuracy, calibration, cost, latency) and evals, not a feature list.
- One polished project beats several half-built ones.

## The product
A weekly NFL **matchup breakdown and predictor**, built in two phases:
- **Approach A (first):** no user input. Every week: ingest new data, update team tendency profiles, predict every game (win prob, spread, total, score distribution), publish matchup breakdowns, and score last week's predictions publicly.
- **Approach C (later):** "predict the tendencies" game. Users read the breakdown + enrichment and forecast team behavior (e.g., early-down pass rate, blitz rate, 4th-down attempts); reality scores them (Brier/log loss); compare against the model.

LLM/agent role: an **explanatory and enrichment layer** — general football-concept explanations, a web research agent (coordinator trends, scheme notes, injuries), and possibly structured features fed to models.

## Data (nflverse — verify fields with a null-rate audit before designing around them)
- Play-by-play back to 1999 (EPA, win probability, etc.), updated nightly in-season.
- Participation: offense formation/personnel, defense personnel, defenders in box, number of pass rushers, man/zone coverage flag. No specific coverage shells or play names confirmed.
- FTN charting (2022+): QB location, no-huddle, motion, play-action, screen, RPO, trick play, QB out of pocket, etc. License CC-BY-SA 4.0 — check share-alike implications for published derived data.
- Schedules include betting lines (useful for history/market baseline).
- Injury data: believed available — verify in-season freshness.
- Gap: no coordinator table; build a coaching-staff mapping manually or via LLM extraction.
- Attribution: nflverse is CC-BY; credit in README. Fan-made, not affiliated with the NFL disclaimer; no logos.

## Workstreams
1. **Data platform** — idempotent scheduled ingestion, 2022+ backfill, null-rate audit, Parquet + DuckDB. Every record carries a "known as of" timestamp for point-in-time correctness.
2. **Tendency store** — per team × situation bucket (down, distance, field zone, score state), offense and defense. Blend league prior + coordinator history + current season with exponential recency decay and beta-binomial shrinkage. Handle discontinuities (coordinator change, QB change). Later: player-availability splits.
3. **Prediction models ("philosophies")** — *Superseded by ADR 0003/0004:* feature store + approaches (persona and fitted flavors, shrink-to-persona ridge) + ensemble. Elo and the market baseline remain as features and reference lines; the Monte Carlo drive sim is an offseason experiment.
4. **Backtest + tournament** — walk-forward (predict week w using data through w-1). Tune on 2022–2024, select on 2025, run top performers live for rest of 2026. Metrics: log loss, Brier, spread MAE, calibration, ATS, CLV. Automated leakage guards.
5. **LLM enrichment** — three separate jobs:
   a. General concept explanations (model knowledge, labeled as general).
   b. Research agent → structured, timestamped, cited facts (claim, source, date, confidence); verify checkable claims against tendency store and flag conflicts.
   c. Feature extraction for models (most rigor needed).
   **Key problem:** web search can't be fairly backtested on past games (hindsight leakage). Options: evaluate LLM features live only; restrict historical enrichment to point-in-time data; date-filtered sources. **Headline experiment:** does enrichment improve forecasts vs. the same model without it?
6. **Matchup breakdown generator** — per-game report; every number verified against data before publishing; enrichment shown with citations. Evals: numeric faithfulness, citation validity, human-rated usefulness.
7. **Odds + paper ledger** — model probs → fair odds; edge vs. market; fractional Kelly sizing; immutable timestamped paper bets at real odds; track P&L and **closing-line value** (CLV is the primary edge metric; season P&L is mostly noise). Real-money betting deferred: sports betting is not legal in Texas (as of 2026); sportsbooks generally lack bet-placement APIs and prohibit automation.
8. **Approach C game** — auto-generated prompts where model is uncertain or tendencies shift; lock at kickoff; scoring, streaks, leaderboard vs. model.
9. **Frontend** — TypeScript/React: weekly slate, matchup pages, team pages, model scorecard, ledger, later the C game.
10. **Platform/infra** — NFL-week schedule (Tue refresh + model run; Wed–Fri injury enrichment; pre-game inactives update; post-game grading). Docker, IaC (Terraform), CI, deploy to cloud (GCP familiar), secrets. Observability: pipeline freshness, LLM traces with cost/latency, failure alerts.
11. **Writing** — README with architecture diagram + results; posts on recency weighting, enrichment impact, a season of paper bets + CLV. Document how AI coding tools were used (CLAUDE.md, what worked/failed, how output was verified).

## Draft tiers (to be finalized)
- **Core:** data platform, tendency store, 2–3 model philosophies, backtest harness, weekly pipeline deployed live.
- **Core AI:** verified matchup breakdowns, research agent with cited structured facts, enrichment-vs-no-enrichment experiment.
- **Next:** odds + paper ledger with CLV, frontend, observability dashboards.
- **Later:** Approach C game, accounts/leaderboard, availability splits, full Monte Carlo sim.
- **Defer/cut:** real-money betting, polished UI before data is solid, individual player modeling.

## Open decisions (all resolved, Oct 2026)
1. Number of model philosophies in v1 — **decided:** three approaches (Traditionalist, Analyst, Sharp) in persona + fitted flavors, plus ensemble and reference lines; Narrative in shadow; Matchup offseason. [ADR 0003](adr/0003-feature-store-and-approaches.md), [ADR 0004](adr/0004-persona-and-fitted-flavors.md).
2. Enrichment explain-only vs. feeding models — **decided:** narrative features are captured live from launch and feed only the shadow Narrative approach in 2026; previews are explain-only with a faithfulness check. [ADR 0007](adr/0007-llm-layer.md).
3. Live-first vs. backtest-first — **decided:** both on the same code path; first public lock once the approaches exist (no calendar target), walk-forward backtest 2015–2025 graded by the same code. [ADR 0005](adr/0005-point-in-time-and-locks.md), [ADR 0010](adr/0010-first-live-lock-with-approaches.md).
4. Frontend depth before playoffs — **decided:** Streamlit locally through P1; React + TS static site on Firebase Hosting in P2; no API or accounts in 2026. [ADR 0009](adr/0009-frontend-timing.md).
5. Hosting + LLM/search budget — **decided:** local runs until P2, then Terraform'd GCP (Cloud Run Jobs, Scheduler, GCS, Secret Manager, WIF) + Firebase; LLM on an API key, $10–15/week target, $25 cap, Sonnet/Opus/Haiku 5.5 by job, built-in web search. [ADR 0008](adr/0008-hosting-path.md), [ADR 0007](adr/0007-llm-layer.md).

Also decided: free data only ([ADR 0001](adr/0001-open-data-only.md)); Parquet + DuckDB under one data root ([ADR 0002](adr/0002-storage-parquet-duckdb.md)); scoring and odds-weighted bets ([ADR 0006](adr/0006-scoring-and-odds-weighted-bets.md)); licensing ([ADR 0011](adr/0011-licensing.md)).

## Principles
- LLM stays out of the numeric core; it explains and enriches. All published numbers are verified against data.
- Point-in-time correctness everywhere; suspect leakage when results look too good.
- Ship something live early — live, publicly scored predictions can't be backfilled.
- State limitations honestly (observational data, small samples, market efficiency).
