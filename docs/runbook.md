# Weekly runbook

How to operate the live pipeline by hand until Cloud Scheduler runs it (step 5, M7.2). Every command runs from the repo root. Times are US Eastern (Daylight Time until Nov 1, 2026, then Standard). The Odds API free tier allows 500 credits a month; `nfl odds status` shows usage, and the code refuses past a soft cap of 400.

## The week

| When (ET) | Command | Why | Credits |
|---|---|---|---|
| Tue ~10:00 | `uv run nfl weekly refresh` then `uv run nfl readme` (refresh rebuilds the site JSON; view with `uv run nfl ui`) | Ingest last week's results, grade, settle paper bets, refresh features and the README scorecard; Tuesday opening line | 3 |
| Wed and Fri (optional) | `/nfl-narrative <season> <week>` in Claude Code | Narrative research records (dev producer until the API job, M6.2) | 0 |
| **Thu 09:00** | `uv run nfl lock --slot thu --commit --push` | Lock Thursday-night games (and any Wed/Fri game) | 3 |
| Thu ~20:05 | `uv run nfl odds snapshot` | Closing line for the Thursday game (closing-line value) | 3 |
| **Sat 12:00** | `uv run nfl lock --slot sat --commit --push` | Lock every Saturday–Monday game, after Friday's injury report | 3 |
| Sun ~09:20 (international weeks) | `uv run nfl odds snapshot` | Closing line for the London/Germany game | 3 |
| Sun ~12:50, ~16:00, ~20:10; Mon ~20:05 | `uv run nfl odds snapshot` | Closing lines for each kickoff window | 3 each |

About 24 credits a week, ~105 a month. Closing snapshots only feed closing-line value; skipping one just falls back to nflverse's line for those games.

## What a lock does

`nfl lock --slot thu|sat` (see `src/nfl/lock.py`):
1. Ingests current-season nflverse data (only changed files are written), takes an odds snapshot, rebuilds curated tables and every feature family stamped with the current time.
2. Scores the slot's games that haven't kicked off with the frozen fits trained through last season: every approach in both flavors, the global fit, the ensemble, and the market, Elo and naive reference lines.
3. Appends the prediction rows (never edits) and opens paper bets at the lock's odds.
4. Writes `public/predictions/<season>/week_<ww>_<slot>_<lock time>.json` and its `.sha256`.
5. With `--commit`, commits only those two files (refuses if anything else is staged). With `--push`, pushes only if every unpushed commit is a lock commit. Lock-only pushes are pre-approved; anything else waits for Austin.

Takes about 30 seconds.

## Rules

- **Never lock late.** A lock refuses games that have kicked off, and there is no backfilling the live record. A missed lock is a missed lock; note it in the journal.
- **Re-running is safe.** A second lock of the same slot appends new rows and a new file; grading uses the last lock before each kickoff. Re-lock if something was wrong (e.g. a QB ruled out after the Thursday lock doesn't matter for Sunday games, which the Saturday lock covers anyway).
- **Push code first.** The lock's push guard refuses while code commits are unpushed. Push them (or ask Austin) before Thursday.
- **No refits mid-season.** Fits are frozen at the start of the season (ADR 0005). Persona edits during the season need a new `model_version` and are announced in the journal.

## Rehearsing

`uv run nfl lock --slot sat --dry-run` does steps 1–2 and writes the artifact under `data/marts/dryrun/` only. Use it for the dry-run week and whenever the code changed since the last lock. `--no-refresh` skips step 1 (fast, uses the data on disk); `--no-odds` skips the snapshot.

## If something breaks

- **nflverse download fails:** rerun; ingest is idempotent. If it's still down, `--no-refresh` locks on the data from the last successful ingest (features are stamped with what was actually known).
- **Odds API fails or is out of credits:** `--no-odds`; the market features then come from the latest snapshot on disk, or nflverse's line.
- **Missing fit artifacts:** `uv run nfl fit` (only between seasons, or after an announced persona change).
- **Push refused:** read the listed commits; push code commits yourself, then `git push` the lock.

## In the cloud (step 5, from 2026-10-28)

The same commands run as Cloud Run jobs in `nfl-project-prod` (`docs/hosting.md`), on the schedule above, with the data root at `gs://nfl-project-prod-data`. The lock schedules are paused until the shadow week passes (`infra/variables.tf`, `locks_paused`).

```
gcloud run jobs list --region us-central1                      # the four jobs
gcloud run jobs execute nfl-lock-thu --region us-central1 --args="lock,thu,--dry-run,--no-odds" --wait
gcloud run jobs executions list --job nfl-weekly-refresh --region us-central1
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="nfl-lock-thu"' --limit 50 --freshness 1d
gcloud scheduler jobs list --location us-central1               # ENABLED / PAUSED
gcloud storage rsync -r gs://nfl-project-prod-data ./data       # pull the cloud's data root down (never push)
```

- A failed execution emails Austin (alert policy). Fix the cause, rerun the job by hand.
- `nfl readme` is laptop-only (a README commit from the cloud would be a non-lock commit).
- Go live: set `locks_paused = false` in `infra/terraform.tfvars`, `terraform apply`, and stop locking from the laptop.
