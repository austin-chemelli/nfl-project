# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A weekly NFL **preview and prediction tool** that is educational first and market-aware second. Several **approaches** (personas: the Traditionalist, the Analyst, the Sharp; later the Matchup and the Narrative) weigh the same shared features differently, each in a hand-reviewed *persona* flavor and a *fitted* flavor, plus an ensemble. Every approach is scored publicly against the market and a naive baseline on forecast quality, odds-weighted paper bets, and how often it was right when it disagreed with the market. A Hypotheses page shows what history says about each feature. An LLM extracts the week's narrative into structured, cited features (live only) and writes previews whose numbers are checked against the data.

Public portfolio project. The goal is a **live, shipped** system with real measurements (accuracy, calibration, cost, latency) and evals, not a feature list.

## Docs (read these first)

- [docs/architecture.md](docs/architecture.md): components, data model (feature store, approach configs, prediction and bet rows, site JSON contract), flows, point-in-time rules, deployment path.
- [docs/adr/](docs/adr/): one ADR per decision, with the reasons. Don't re-open an accepted ADR without new information; propose a new ADR instead.
- [docs/tasks.md](docs/tasks.md): the work sequence, progress, and agent-sized tasks with acceptance criteria. Work from it; update it when scope changes.
- [docs/feature-groups.md](docs/feature-groups.md): the group registry (ADR 0012): which features roll up into which high-level feature, with signs.
- [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md): original scope and goals. Where it conflicts with an ADR, the ADR wins (it records the resolution).
- [docs/journal.md](docs/journal.md): the project's story so far (sessions, decisions, findings, bugs). **Append an entry at the end of any session that changes the plan, the data, or the results.**
- `.notes/` (gitignored, local): brainstorm decision log and working notes.

## Status

2026-10-27: sequence decided (top of docs/tasks.md); ADR 0012 adds two-level features (groups with fitted inner weights). 2026-10-26: plan written (architecture, ADRs 0001–0011, tasks). M0, M1 (feature store, 7 families), M2 (approaches, fitting, backfill 2015–2025, grading v2) and M3 (Odds API snapshots, live market features, paper ledger with CLV) are built but uncommitted; progress table at the top of docs/tasks.md, backtest findings in `.notes/backtest-2025.md`. Step 1 done 2026-10-27 (groups, availability/QB/schedule features, history from 1999, personas at group level, review in `.notes/persona-review-groups.md`). Next: step 2, the lock. The first public lock waits for the approaches (ADR 0010); there are no calendar targets, only the sequence.

## Non-negotiable principles

1. **The LLM stays out of the numeric core.** Models produce the numbers; LLMs explain and enrich. Every published number is checked against the data first. Generated text never introduces a statistic that wasn't computed.
2. **Point-in-time correctness everywhere.** Every feature row carries `known_as_of`; a lock may only use rows with `known_as_of < lock_ts`; fits used in season S are trained through S−1. When backtest results look too good, assume leakage before skill. Rules in ADR 0005.
3. **Ship live early.** Live, publicly scored predictions can't be backfilled. Prefer a working end-to-end pipeline over polishing one component.
4. **Be honest about limitations**: observational data, small samples, efficient markets, ~180 live games can't rank models. Say so in output and docs.

## Stack

- Python 3.14 via **uv**; Polars + **DuckDB** in-process (no DB server); numpy + scipy for fitting; pydantic + PyYAML for configs; Typer CLI; httpx; Anthropic Python SDK; pytest; ruff (line length 100).
- UI: Streamlit + Plotly through P1 (disposable); React + TypeScript + Vite static site in P2 (`web/`), both reading `marts/site/*.json`.
- Infra (P2): Docker, Terraform (`infra/`), GitHub Actions for CI and deploys, GCP Cloud Run Jobs + Cloud Scheduler + GCS + Secret Manager + Workload Identity Federation, Firebase Hosting.
- Data: nflverse parquet by URL, The Odds API (free tier), Open-Meteo. Free, redistributable sources only (ADR 0001).

## Commands

`uv sync --group dev` once, then:

```
uv run nfl ingest            # nflverse parquet -> raw snapshots (idempotent)
uv run nfl curate            # DuckDB builds curated/{games,plays,injuries,depth_charts,...}
uv run nfl audit             # null-rate audit -> marts/audit.parquet
uv run nfl tendencies        # team x situation x metric rates -> marts/tendencies.parquet
uv run nfl features          # feature families -> marts/features/season=YYYY/<family>.parquet (upsert)
uv run nfl fit               # λ selection + walk-forward fits -> marts/fits/<model_id>/<trained_through>.json
uv run nfl predict           # reference models (market, Elo, naive) -> marts/predictions.parquet (append-only)
uv run nfl predict --backfill  # approaches + global + ensemble on 2015-2025 at synthetic locks (replaces backfill rows)
uv run nfl grade             # scorecard (+ECE), reliability, summary with CIs, divergence buckets, site JSON
uv run nfl odds snapshot     # Odds API lines now (3 credits) -> raw/odds_api + curated/lines
uv run nfl odds status       # credits used, snapshots on disk (free)
uv run nfl ledger            # open paper bets at last lock, settle, CLV -> marts/bets*.parquet
uv run nfl narrative slate 2026 8   # games to research; `ingest <file>` validates+stores a record; `example`, `list`
uv run nfl run-all           # all of the above (replaced by `nfl weekly` in M4)
uv run nfl ui                # Streamlit explorer
uv run pytest -q             # unit tests + leakage guards (guards skip without local data)
uv run ruff check src tests && uv run ruff format src tests
```

Planned (see tasks.md for the milestone): `nfl lock --slot thu|sat [--commit]`, `nfl weekly refresh|grade`, `nfl site`, `nfl narrative`, `nfl hypotheses`.

## Layout and conventions

- `src/nfl/config.py`: paths and dataset registry. `NFL_DATA_ROOT` (default `./data`, gitignored) is always a filesystem path. Layers: `raw/<source>/<dataset>/snapshot_ts=<ts>/` + `manifest.json` (immutable), `curated/<table>/season=YYYY/`, `marts/`. Read raw with `hive_partitioning=false`.
- `src/nfl/features/<family>.py`: one builder per feature family writing the long schema in architecture §3.3. Feature names are `<family>.<name>`; `side` is `home`/`away`/`game`. Missing values are null in the store and become 0 (league average) after standardization. Builders expose `SOURCE`, `VERSION`, `build(paths, games, build_ts)` returning rows via `store.from_team_values`/`from_game_values`; they never write (architecture §3.3).
- `src/nfl/approaches/configs/<id>.yaml`: an approach. Persona weights carry a `why`. `model_id` is `<approach>.<persona|fitted>`, plus `global` and `ensemble`. Fit artifacts under `marts/fits/<model_id>/<trained_through>.json`.
- Team codes: pbp prints current codes (LA, LAC, LV) for every season while games use historical ones (STL, SD, OAK). Join plays to games on the canonical franchise code (`TEAM_ALIASES`), never the printed code.
- `src/nfl/models/`: reference models only (`market.py`, `elo.py`, `naive.py`), numeric, no LLM.
- `marts/predictions.parquet` and `marts/bets.parquet` are append-only. Never edit rows; add rows with a new `lock_ts` or `model_version`.
- Narrative records (`nfl.llm.narrative.GameNarrative`) are the contract between research and pipeline; `producer` is `claude_code` (the `/nfl-narrative` skill, dev only) or `api` (production). Features from them are stamped with the record's `known_as_of`, never backfilled.
- `src/nfl/llm/`: separate entrypoints (`narrative.py`, `preview.py`, `faithfulness.py`), prompts versioned in `src/nfl/llm/prompts/<job>_v<N>.md`, every call logged to `marts/llm_calls.parquet`. Weekly cost cap `LLM_WEEKLY_CAP_USD` (default 25).
- `public/predictions/<season>/week_<w>_<slot>.json` + `.sha256`: committed lock artifacts. Commit message `lock: <season> W<w> <slot>`.
- DuckDB 2.0: use `con.sql(q).pl()`; quote generated identifiers (`desc` is reserved). Timestamps need `pytz`.
- Data conventions: `spread_line` > 0 means home favored, `result` = home − away; schedule lines are untimestamped (closing-ish); injuries have `week`, and `date_modified` only for 2010–2024 (live point-in-time comes from ingest snapshots); 1999 schedules have no gametime (kickoff imputed by slot, `kickoff_imputed`); depth charts from 2025 are timestamped (`dt`); FTN joins pbp on (`game_id`,`play_id`) = (`nflverse_game_id`,`nflverse_play_id`) for ~99% of pass/run plays; participation (coverage, personnel) is offseason-only.
- The Odds API key only works as a URL query param: never log URLs or raw httpx errors from `nfl/odds.py` (it redacts them). Historical odds are paid-only on our plan.
- Secrets in `.env` (gitignored) locally, Secret Manager hosted. Never use Claude Max/OAuth tokens in the app (ADR 0007).

## Working conventions

- Work from `docs/tasks.md`; tasks are sized for the `implementer` agent. Run siblings marked **P** in parallel, then review the diffs.
- Tests for anything touching time boundaries (as-of joins, walk-forward splits, ledger immutability). Leakage guards run in CI.
- Prefer small, verifiable steps that move toward the live pipeline. In-season work is only what needs live games; everything else can wait for the offseason.
- Licensing: code MIT; published derived data CC-BY-SA 4.0 with nflverse + FTN credit; "fan-made, not affiliated with the NFL"; no logos (ADR 0011).
- Writing about how AI coding tools were used is part of the project. Note notable wins or failures and how output was verified when they come up.
