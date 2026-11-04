# Weekly runbook

How to operate the live pipeline by hand until Cloud Scheduler runs it (step 5, M7.2). Every command runs from the repo root. Times are US Eastern (Daylight Time until Nov 1, 2026, then Standard). The Odds API free tier allows 500 credits a month; `nfl odds status` shows usage, and the code refuses past a soft cap of 400.

## The week

| When (ET) | Command | Why | Credits |
|---|---|---|---|
| Tue ~10:00 | `uv run nfl weekly refresh` then `uv run nfl readme` (refresh rebuilds the site JSON; view with `uv run nfl ui`) | Ingest last week's results, grade, settle paper bets, refresh features and the README scorecard; Tuesday opening line | 3 |
| **Wed 18:00** (desktop) | `scripts/desktop-narrative.sh` (Windows Task Scheduler) | Narrative research for every game of the week on the desktop models, uploaded, site rebuilt (~4 h) | 0 |
| Thu 08:30 | `nfl narrative check` (cloud job) | Emails if Wednesday's pass left a game without a record | 0 |
| **Sat 07:00** (desktop) | `scripts/desktop-narrative.sh` | Narrative research again for the Sunday and Monday games, after Friday's injury designations (~3.5 h) | 0 |
| Sat 11:30 | `nfl narrative check` (cloud job) | Emails if Saturday's pass left a game without a record | 0 |
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
gcloud run jobs list --region us-central1                      # the five jobs
gcloud run jobs execute nfl-lock-thu --region us-central1 --args="lock,thu,--dry-run,--no-odds" --wait
gcloud run jobs executions list --job nfl-weekly-refresh --region us-central1
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="nfl-lock-thu"' --limit 50 --freshness 1d
gcloud scheduler jobs list --location us-central1               # ENABLED / PAUSED
gcloud storage rsync -r gs://nfl-project-prod-data ./data       # pull the cloud's data root down (never push)
```

- **Retrospectives** (ADR 0016) run daily at 07:00 ET (`nfl-retro`). By hand, locally: `uv run nfl retro daily` (fetches nflverse, curates the current season only, builds what is missing or stale) or `uv run nfl retro build [--season S] [--week W] [game_id...] [--force]` on the data already on disk (then `uv run nfl publish --bucket nfl-project-prod-site` to ship). In the cloud: `gcloud run jobs execute nfl-retro --region us-central1 --wait`. If it says the expectations file is missing, `uv run nfl retro expectations` (the daily job builds it itself when absent). Retros are derived and safe to rebuild; only 2026 is published.
- A failed execution emails Austin (alert policy). Fix the cause, rerun the job by hand.
- `nfl readme` is laptop-only (a README commit from the cloud would be a non-lock commit).
- `uv run nfl publish --bucket nfl-project-prod-site` pushes the laptop's `marts/site/*.json` and `public/predictions/` to the public bucket (5-minute cache); the cloud jobs do this themselves.
- Infra changes: edit `infra/*.tf`, open a PR (the `infra` workflow posts the plan in the run summary), merge to apply.
- Go live: set `locks_paused = false` in `infra/terraform.tfvars`, `terraform apply`, and stop locking from the laptop.

## Narrative on the desktop (M6.2u, from Week 9)

Two passes a week on the desktop, which has the models (docs/desktop-llm-setup.md): Wednesday 18:00 ET for every game (the Thursday game's final reports are out by then; the rest get an early preview) and Saturday 07:00 ET for the Sunday and Monday games (after Friday's injury designations, done before the 12:00 lock). Each pass stores new records; nothing is overwritten. The site shows a game's newest record, and features and locks use the newest one from before their own time (`known_as_of`). The pass times are `PASSES` in `src/nfl/llm/narrative.py`; the cloud check uses them, so change both together.

`scripts/desktop-narrative.sh` does one pass:
1. `git pull` and `uv sync`.
2. Download `curated/games` and `curated/lines` from the bucket (the schedule, starting QBs and lines the research reads).
3. `nfl narrative run <season> <week>` for every game not yet kicked off.
4. Upload `marts/narrative/season=S/week=WW/` to the bucket (rsync, never deletes) and start `nfl-site` (rebuild and publish).

Failures go to Cloud Logging (log `nfl-desktop-narrative`, ERROR) and email Austin. A pass that never runs (desktop off, asleep, signed out) is caught by `nfl-narrative-check` at 08:30 Thursday and 11:30 Saturday, which fails, and so emails, if an upcoming game has no `local` record since the last pass started. The check never touches the locks.

**One-time desktop setup** (WSL Ubuntu on the desktop):
```
curl -LsSf https://astral.sh/uv/install.sh | sh                    # uv, if missing
git clone https://github.com/austin-chemelli/nfl-project.git ~/dev/nfl-project   # public repo: pulls need no key
cd ~/dev/nfl-project && uv sync
# .env: LLM_BASE_URL=http://<desktop-tailscale-ip>:11434/v1, SEARX_URL=http://<desktop-tailscale-ip>:8080, LLM_MODEL=qwen3.5:9b
# gcloud CLI (https://cloud.google.com/sdk/docs/install#deb), then:
gcloud auth login && gcloud config set project nfl-project-prod
uv run nfl llm ping                                                # model reachable
for t in games lines; do gcloud storage rsync -r gs://nfl-project-prod-data/curated/$t data/curated/$t -q; done
uv run nfl narrative week                                          # prints "<season> <week>"
```
Then register the task from an admin PowerShell. Times are the desktop's local time (`Get-TimeZone`): 18:00 and 07:00 ET are 17:00 and 06:00 Central. Set `$distro` to the Ubuntu distro's name from `wsl -l -v`.
```
$distro = "Ubuntu"
$a = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-d $distro -- bash -lc 'bash ~/dev/nfl-project/scripts/desktop-narrative.sh'"
$t = @((New-ScheduledTaskTrigger -Weekly -DaysOfWeek Wednesday -At 5:00PM), (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At 6:00AM))
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 8)
Register-ScheduledTask -TaskName "nfl-narrative" -Action $a -Trigger $t -Settings $s
```
The task runs when Austin is signed in, which Ollama needs anyway (docs/desktop-llm-setup.md §6). Check the task's environment without a full pass (uv and gcloud on the login shell's PATH): `wsl -d <distro> -- bash -lc "cd ~/dev/nfl-project && uv run nfl narrative week && echo OK"`. Run a pass by hand: `Start-ScheduledTask nfl-narrative`, or `bash scripts/desktop-narrative.sh` in WSL. Logs: `data/raw/narrative_local/passes/` on the desktop, and `gcloud logging read 'logName="projects/nfl-project-prod/logs/nfl-desktop-narrative"' --limit 20`.

