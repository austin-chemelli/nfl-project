# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A weekly NFL **preview and prediction tool** that is educational first and market-aware second. Several **approaches** (personas: the Traditionalist, the Analyst, the Sharp, the Student; later the Matchup and the Narrative) weigh the same shared features differently, each as one public line (the persona's weights, lightly fitted and calibrated), plus an ensemble. The market is the reference everything is compared against, never an input. Every approach is scored publicly against the market and a naive baseline on forecast quality, odds-weighted paper bets, and how often it was right when it disagreed with the market. A Hypotheses page shows what history says about each feature. An LLM extracts the week's narrative into structured, cited features (live only) and writes previews whose numbers are checked against the data.

Public portfolio project. The goal is a **live, shipped** system with real measurements (accuracy, calibration, cost, latency) and evals, not a feature list.

## Docs (read these first)

- [docs/state.md](docs/state.md): **where the project is right now**: what runs where and when, links, workstreams, milestones, open decisions, known issues, the docs map. Injected into every session by the SessionStart hook; kept current by every chat as it works ([docs/state-maintenance.md](docs/state-maintenance.md)).
- [docs/architecture.md](docs/architecture.md): components, data model (feature store, approach configs, prediction and bet rows, site JSON contract), flows, point-in-time rules, deployment path.
- [docs/adr/](docs/adr/): one ADR per decision, with the reasons. Don't re-open an accepted ADR without new information; propose a new ADR instead.
- [docs/tasks.md](docs/tasks.md): the work sequence, progress, and agent-sized tasks with acceptance criteria. Work from it; update it when scope changes.
- [docs/feature-groups.md](docs/feature-groups.md): the group registry (ADR 0012): which features roll up into which high-level feature, with signs.
- [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md): original scope and goals. Where it conflicts with an ADR, the ADR wins (it records the resolution).
- [docs/hosting.md](docs/hosting.md): how step 5 works (two runners, one bucket; site data from a public bucket) and what Austin sets up by hand. [docs/desktop-llm-setup.md](docs/desktop-llm-setup.md): the desktop LLM server (ADR 0014).
- [docs/journal.md](docs/journal.md): the project's story so far (sessions, decisions, findings, bugs). **Append an entry at the end of any session that changes the plan, the data, or the results.**
- `.notes/` (gitignored, local): brainstorm decision log and working notes.

## Status

In [docs/state.md](docs/state.md) (bottom line, milestones, workstreams), updated as work happens. The story is [docs/journal.md](docs/journal.md). Repo is public; locks are live from 2026 Week 9; there are no calendar targets, only the sequence at the top of docs/tasks.md.

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
uv run nfl fit --only student_v2 && uv run nfl predict --backfill --only student_v2   # one new approach; the others' frozen fits and rows stay
uv run nfl predict           # reference models (market, Elo, naive) -> marts/predictions.parquet (append-only)
uv run nfl predict --backfill  # approaches + global + ensemble at synthetic locks; replaces ALL backfill rows of those models, whatever --seasons says
uv run nfl grade             # scorecard (+ECE), reliability, summary with CIs, divergence buckets, site JSON
uv run nfl odds snapshot     # Odds API lines now (3 credits) -> raw/odds_api + curated/lines
uv run nfl daily             # the Wed/Fri/Sat pass (ADR 0024, M20.1): current-season ingest, odds snapshot, curate, features, forecast, preview scores, site
uv run nfl odds status       # credits used, snapshots on disk (free)
uv run nfl ledger            # open paper bets at last lock, settle, CLV -> marts/bets*.parquet
uv run nfl narrative slate 2026 8   # games to research; `ingest <file>` validates+stores a record; `example`, `list`
uv run nfl narrative run 2026 8 [game_id...]   # local research on the desktop model -> producer 'local' (~13 min/game); without ids it skips games stored in this pass
uv run nfl narrative week | check   # "<season> <week>" of the next games; check = exit 1 if a game lacks a record from the last desktop pass (cloud job before each lock)
uv run nfl narrative recompose <run.debug.json> --tag X [--model M] [--think job=low,...] [--job-models matchup=qwen3:14b|none] [--rebuild]  # rerun only the writing jobs (or only the checks) on a saved run's facts -> raw/narrative_local/experiments/X/
uv run nfl narrative compare <record.json>...  # M6.2e side-by-side metrics and texts (--out .notes/...)
uv run nfl llm ping          # one schema-constrained call to the desktop model (LLM_BASE_URL); `llm calls` = log summary
uv run nfl retro build [--season S] [--week W] [game_id...]   # post-game retrospectives (ADR 0016) -> marts/retro/ + site files; `retro expectations` refits the league tables; `retro daily` = the 07:00 ET cloud job
uv run nfl lock --slot thu|sat [--dry-run] [--commit --push]   # the live lock (docs/runbook.md)
uv run nfl weekly refresh    # Tuesday job: current-season ingest, odds, curate, features, score unscored finished games (append-only backfill), grade, ledger
uv run nfl readme            # rewrite the README scorecard section
uv run nfl site              # UI JSON contract -> marts/site/ (auto after weekly refresh and real locks)
uv run nfl sql "select ..."   # SQL over every table (ADR 0025): views over the parquet, `--tables` lists them; point in time: features_asof(ts), game_vectors(ts)
uv run nfl models build [name]   # SQL models (src/nfl/sql/models/*.sql) -> marts/derived/<name>.parquet; unchanged output not rewritten (ADR 0026, M23.3)
uv run nfl candidates run [--only ID] [--season-from 2006]   # screen the candidates registry through the gates -> marts/candidates.parquet (append-only; unchanged rerun appends nothing)
uv run nfl candidates list [--interesting]   # latest ledger row per candidate
uv run nfl league [--snapshot refresh|lock]   # standings, simulated playoff odds, leverage -> site/league.json (auto at the end of every `nfl site`)
uv run nfl hypotheses        # per-feature coef + 90% CI + verdict -> site/hypotheses.json
uv run nfl diy-matrix        # group composites per game for the build-your-own page
uv run nfl run-all           # full historical rebuild (POC-era; prefer the individual commands)
uv run nfl ui                # Streamlit app: slate, game, tracker, hypotheses, build your own, method
uv run pytest -q             # unit tests + leakage guards (guards skip without local data)
python3 scripts/state_check.py   # is docs/state.md consistent (links, schedule vs infra, worktrees, doc dates); --strict in hooks and CI
uv run ruff check src tests && uv run ruff format src tests
```

Web (`web/`, Node 24 via `.nvmrc`; plan in docs/site.md):

```
npm ci                       # once
npm run dev                  # http://localhost:5173, reads ../data/marts/site via /data (no bucket)
npm run typecheck && npm run lint && npm test && npm run build
uv run python scripts/web_fixtures.py   # refresh test fixtures after a site-contract change
python3 scripts/firebase_deploy.py --dry-run   # what a deploy would upload (CI deploys on push to main, after the tests pass)
```



## Layout and conventions

- `src/nfl/config.py`: paths and dataset registry. `NFL_DATA_ROOT` (default `./data`, gitignored) is always a filesystem path. Layers: `raw/<source>/<dataset>/snapshot_ts=<ts>/` + `manifest.json` (immutable), `curated/<table>/season=YYYY/`, `marts/`. Read raw with `hive_partitioning=false`.
- `src/nfl/features/<family>.py`: one builder per feature family writing the long schema in architecture §3.3. Feature names are `<family>.<name>`; `side` is `home`/`away`/`game`. Missing values are null in the store and become 0 (league average) after standardization. Builders expose `SOURCE`, `VERSION`, `build(paths, games, build_ts)` returning rows via `store.from_team_values`/`from_game_values`; they never write (architecture §3.3).
- `src/nfl/approaches/configs/<id>.yaml`: an approach (group weights with a `why`, optional overrides). One public line per approach (ADR 0004 amendment): `model_id` is the approach id (`traditionalist`, `analyst`, `sharp`, `student`), plus `ensemble` and the diagnostic `global`; `<id>.persona` and `<id>.fitted` artifacts are internals and diagnostics, never scorecard lines. The market's forecast is never an approach input (ADR 0013; the schema rejects it). Fit artifacts under `marts/fits/<model_id>/<trained_through>.json`; `nfl lock` refuses artifacts whose config hash doesn't match the YAML, and refuses `--commit` from uncommitted code.
- Team codes: pbp prints current codes (LA, LAC, LV) for every season while games use historical ones (STL, SD, OAK). Join plays to games on the canonical franchise code (`TEAM_ALIASES`), never the printed code.
- Web: `web/src/data/contract.ts` (zod) mirrors `src/nfl/site.py`; change both together and rerun `scripts/web_fixtures.py`. Data publishes independently of site deploys (ADR 0015); on `main`, CI rebuilds the site data with a new image and checks this commit's contract against the live files before deploying the web (ADR 0023, `npm run test:live`), so a field may be required when the same PR makes the jobs write it. Removing or renaming a field the live page reads still breaks open tabs: keep those changes additive. Pages use the shared components/chart kit and colors from CSS tokens; numbers are human-readable (no log-odds). Layout follows ADR 0017: a summary strip first, detail behind URL-synced `Tabs`, one lede sentence per section, caveats in one `FinePrint` per page, values on a league band (`RangeRow`, `MatchupBand`). On a game, color means the team: `[data-matchup]` with `matchupVars` from `lib/teamColors.ts`, never a raw brand color (ADR 0017 amendment); the League scatter does the same per team with `teamDotVars` (ADR 0019 amendment). Motion is CSS through the `--dur-*` tokens, zeroed under `prefers-reduced-motion`, never an animation library (ADR 0020). Production data URL `VITE_DATA_URL` (default the public bucket).
- UI: pages in `src/nfl/ui/pages/` read only `marts/site/*.json` via `nfl.ui.data` (palette, labels, loaders); never parquet. `tests/test_ui.py` renders every page headlessly.
- `src/nfl/retro/`: post-game retrospectives (ADR 0016, M9). Descriptive, computed in code; sentences are templates filled from the record (no LLM). Luck swings are in points, positive = helped the named team; season-to-date baselines use only games that kicked off before. Retros are derived files (overwritten on nflverse corrections), not records; only 2026 is published (`site/retro/`, `site/recap_*`).
- `src/nfl/catalog.py` (ADR 0025): one DuckDB view per table in `TABLES`, built per process and never written; a new table or source is a line there. For point-in-time reads in SQL use `features_asof(ts)`, never the raw `features` view, and give anything derived from it a leakage test.
- New feature ideas go through the candidates ledger first (ADR 0026, M23): define the candidate in `src/nfl/candidates.py`, run `nfl candidates run`, and let the gates (stable, predicts the second half, explains a residual, wins in shadow) decide. A candidate that fails stays in the ledger and on the History page; never delete one. Nothing joins a group without a ledger row, and the public Student changes only at a refit after a shadow line beats it. Derived aggregates shared by the screen and the builders are SQL models under `src/nfl/sql/models/` (`nfl models build`), one leakage test each. Player-level features (injury value, the offensive line) belong to their own flight: don't add them here.
- Matchups and paths to an upset (ADR 0028, M25) are context, not lock code: situations are registered once in `src/nfl/splits.py` and aggregated by the SQL model `team_split_week`; `src/nfl/matchups.py` (edges in points, shrunk toward the league effect), `paths.py` (how the underdog wins, as conditions with their historical win rates and each team's rate of producing them, never a probability) and `leans.py` (the ledger's `use` candidates against the market, in points) are pure modules read by `site.py`, the team files and the retro. Every number they show carries a reliability badge or plausibility label from the ledger; sentences are templates. Edges reach a line only through a separate `matchup` approach after the ledger's gates (phase 3, offseason). Coverage and personnel splits wait for the 2026 participation file.
- `src/nfl/models/`: reference models only (`market.py`, `elo.py`, `naive.py`), numeric, no LLM.
- `marts/predictions.parquet` and `marts/bets.parquet` are append-only. Never edit rows; add rows with a new `lock_ts` or `model_version`. So are `marts/strong_calls.parquet` and `marts/previews.parquet` (ADR 0024); previews are never graded and never reach the tracker, the retro, the recap or the README.
- Odds snapshots taken after a game's kickoff are in-play lines (the Sunday and Monday jobs): market movement uses only snapshots before kickoff.
- Narrative records (`nfl.llm.narrative.GameNarrative`) are the contract between research and pipeline; `producer` is `claude_code` (the `/nfl-narrative` skill, dev only) or `local` (the desktop model via `nfl.llm.research`, production; ADR 0014). In local records the model never writes a URL, date or source count: it cites fact ids and code attaches the sources from pages it fetched; drafts, debug files (pages, facts, raw outputs) and run summaries are under `raw/narrative_local/`. Features from them are stamped with the record's `known_as_of`, never backfilled.
- `src/nfl/llm/`: separate entrypoints (`narrative.py`, `preview.py`, `faithfulness.py`), prompts versioned in `src/nfl/llm/prompts/<job>_v<N>.md`. Every model call goes through `nfl.llm.client.LLMClient.complete` (the desktop's Ollama; thinking off; JSON-schema output; retries), which logs one row per request to `marts/llm_calls.parquet`. **No paid LLM API anywhere in the app** (Austin, 2026-10-29; ADR 0014 amendment): if the desktop is down, LLM jobs fail and email; they never fall back to an API.
- `public/predictions/<season>/week_<ww>_<slot>_<lock ts>.json` + `.sha256`: committed lock artifacts (written by `nfl lock`; never edited). Commit message `lock: <season> W<w> <slot>`. Lock-only commits may be pushed without asking (Austin, 2026-10-27), but only when `git log origin/main..HEAD` contains nothing else. Docs-only commits to `main` (hub, journal, CLAUDE.md) may be pushed without asking too (Austin, 2026-11-04). Every other push asks first.
- DuckDB 2.0: use `con.sql(q).pl()`; quote generated identifiers (`desc` is reserved). Timestamps need `pytz`.
- Data conventions: `spread_line` > 0 means home favored, `result` = home − away; schedule lines are untimestamped (closing-ish); injuries have `week`, and `date_modified` only for 2010–2024 (live point-in-time comes from ingest snapshots); 1999 schedules have no gametime (kickoff imputed by slot, `kickoff_imputed`); depth charts from 2025 are timestamped (`dt`); FTN joins pbp on (`game_id`,`play_id`) = (`nflverse_game_id`,`nflverse_play_id`) for ~99% of pass/run plays; participation (coverage, personnel) is offseason-only.
- The Odds API key only works as a URL query param: never log URLs or raw httpx errors from `nfl/odds.py` (it redacts them). Historical odds are paid-only on our plan.
- Secrets in `.env` (gitignored) locally, Secret Manager hosted. Never use Claude Max/OAuth tokens in the app (ADR 0007).

## Working conventions

- **Every session starts informed.** The SessionStart hook (`scripts/hooks/session-start.sh`, registered in the repo's `.claude/settings.json` and in `~/dev/.claude/settings.json` since sessions start in the `~/dev` workspace) injects `docs/state.md`, `.notes/board.md`, the last two journal entries and `scripts/state_check.py`'s findings. Run `git fetch` before starting work. Keep those files current as you work, at the boundaries in [docs/state-maintenance.md](docs/state-maintenance.md) (track start, checkpoint before a PR or when a decision or finding changes direction, close after the merge). Austin never maintains them by hand.
- Work from `docs/tasks.md`; tasks are sized for the `implementer` agent. Run siblings marked **P** in parallel, then review the diffs.
- Tests for anything touching time boundaries (as-of joins, walk-forward splits, ledger immutability). Leakage guards run in CI.
- Prefer small, verifiable steps that move toward the live pipeline. In-season work is only what needs live games; everything else can wait for the offseason.
- Licensing: code MIT; published derived data CC-BY-SA 4.0 with nflverse + FTN credit; "fan-made, not affiliated with the NFL"; no logos (ADR 0011).
- Writing about how AI coding tools were used is part of the project. Note notable wins or failures and how output was verified when they come up.

## Parallel work (several chats on one repo)

- **One worktree per track.** `~/dev/nfl-project` is the primary checkout and stays on a clean `main`: lock commits (`nfl lock --commit --push`) and job runs happen there, nothing else. Every other chat works in its own `git worktree` on its own branch, in a sibling folder (`~/dev/nfl-project-<track>`, e.g. `nfl-project-ui` on `ui-next`). Never `git checkout` another branch in a folder a different chat is using.
- **New worktree setup:** `git worktree add ../nfl-project-<track> -b <branch>`, then in it `ln -s ../nfl-project/{data,.env,.notes} .`, `cp ../nfl-project/.claude/settings.local.json .claude/` (if one exists), `uv sync --group dev`, `cd web && npm ci`. The `data` and `.notes` symlinks are ignored through `.git/info/exclude` (shared by all worktrees; the `.gitignore` patterns end in `/` and don't match symlinks). `data/` is shared and unversioned: a rebuild in one worktree changes what the others' dev servers read. `core.fileMode` is false here, so `chmod` alone is never committed: use `git update-index --chmod=+x <file>`.
- **The board.** `.notes/board.md` (uncommitted, one file for every worktree through the symlink) has one row per active track: branch, worktree, areas claimed, what it is doing now. Add your row when a track starts, delete it after the cleanup. Don't edit an area another row claims; ask Austin. The durable version is the Workstreams table in `docs/state.md`.
- **PRs for code.** Anything under `src/`, `web/`, `infra/`, `scripts/` or `tests/` merges to `main` through a PR after CI is green (merging deploys). A code PR also changes `docs/journal.md` or `docs/state.md` (the checkpoint in docs/state-maintenance.md): the PreToolUse hook `scripts/hooks/pr-guard.sh` blocks `gh pr create` and `git push` otherwise, and CI's `docs` job fails (label `docs-not-needed` to skip). Rebase onto `origin/main` first; lock commits land there several times a week. Direct commits to `main` are for lock artifacts and docs-only changes. Job code can merge anytime except the last 10 minutes before a lock (docs/runbook.md, Merging job code).
- **Finish a track:** Austin merges the PR. Once it is merged, the chat that owns the track cleans up without asking: check the branch is in `git branch --merged origin/main` and the worktree is clean, then `git worktree remove ../nfl-project-<track>`, `git branch -d <branch>`, `git push origin --delete <branch>`. Keep a worktree that will be reused soon (e.g. `nfl-project-ui`): `git switch -c <new-branch> origin/main && git branch --unset-upstream` instead of removing it. Don't touch another chat's worktree while it may be in use; report what was removed. Then the close step in docs/state-maintenance.md: board row deleted, workstream row marked merged on `main`.
