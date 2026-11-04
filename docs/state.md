# State of the project

Where the project is right now. Chats keep it current as they work ([state-maintenance.md](state-maintenance.md)); `scripts/state_check.py` checks the mechanical parts at every session start, before every PR and in CI. How we got here: [journal.md](journal.md). What's next: [tasks.md](tasks.md). Why: [adr/](adr/). How we work: [../CLAUDE.md](../CLAUDE.md).

## Bottom line (as of 2026-11-04)

The numeric pipeline, the public site and the desktop narrative passes run on schedules with nobody touching them; the first public lock is Thursday 2026-11-05 at 09:00 ET. This week shipped the site's v2 layout (one answer first, ADR 0017), fixed three number bugs a cross-check of production found (market consensus near even money, an Elo leak in after-the-fact scoring, Week 8 missing from the tracker), and put the desktop research on a Wednesday and Saturday schedule. Next: watch the first live locks, then the narrative's previews and evals (M6.3, M6.4).

## What runs where

```mermaid
%%{init: {'themeVariables': {'signalColor': '#999', 'signalTextColor': '#999', 'lineColor': '#999'}}}%%
flowchart LR
    subgraph GH[GitHub]
        REPO[(main)]
        ACT[Actions<br/>ci · image · site · infra]
    end
    subgraph GCP[GCP nfl-project-prod, us-central1]
        SCHED[Cloud Scheduler]
        JOBS[Cloud Run Jobs<br/>refresh · lock-thu · lock-sat · odds<br/>retro · site · narrative-check]
        DATA[(nfl-project-prod-data<br/>private: raw · curated · marts)]
        PUB[(nfl-project-prod-site<br/>public: site/*.json · predictions/)]
        SM[Secret Manager<br/>Odds key · deploy key]
    end
    FB[Firebase Hosting<br/>nfl-project-prod.web.app]
    DESK[Desktop, Windows + WSL<br/>Ollama qwen3.5:9b + qwen3:14b · SearXNG<br/>narrative passes Wed 18:00, Sat 07:00]
    LAP[Laptop<br/>dev · worktrees · nfl readme]
    V((Visitor))

    SCHED --> JOBS
    JOBS <--> DATA
    JOBS -- publish --> PUB
    SM --> JOBS
    JOBS -- lock commits --> REPO
    REPO --> ACT
    ACT -- image --> JOBS
    ACT -- deploy --> FB
    DESK -- records, then starts nfl-site --> DATA
    LAP -. rsync down, never up .-> DATA
    LAP -- PRs --> REPO
    V --> FB
    V -. JSON .-> PUB
```

| Machine | Runs | Never runs |
|---|---|---|
| Cloud Run Jobs | refresh, odds snapshots, locks, retros, site rebuilds, the narrative check; `nfl publish` after each | anything LLM; `nfl readme` |
| Desktop | narrative research on the local models (ADR 0014), uploads to the data bucket | locks, grading, the site |
| Laptop | development in worktrees, `nfl readme`, hand reruns, `rsync` of the bucket down | odds snapshots (credits), locks (cloud is primary; laptop is the fallback) |
| Firebase | the static React app | data (the app reads the public bucket, 5-minute cache) |

### Schedule (ET)

The cloud rows are checked against `infra/jobs.tf` by `scripts/state_check.py`; the desktop rows against `PASSES` in `src/nfl/llm/narrative.py`.

| When | What | Where | Cron | Writes | Check it ran |
|---|---|---|---|---|---|
| Tue 10:00 | `nfl-weekly-refresh`: ingest, odds, curate, features, score unscored finished games, grade, ledger, site, publish | cloud | `0 10 * * 2` | marts, site JSON | `gcloud run jobs executions list --job nfl-weekly-refresh --region us-central1` |
| Wed 18:00 | desktop narrative pass, every game of the week; uploads records, starts `nfl-site` | desktop | `wed 18:00` | `marts/narrative/` | `gcloud logging read 'logName="projects/nfl-project-prod/logs/nfl-desktop-narrative"' --limit 5` |
| Thu 08:30 | `nfl-narrative-check`: fails (emails) if an upcoming game has no `local` record since the last pass | cloud | `30 8 * * 4` | nothing | executions list |
| Thu 09:00 | `nfl-lock-thu`: lock the Thursday games, commit + push the artifact | cloud | `0 9 * * 4` | predictions, bets, `public/predictions/` on `main`, site | `git log origin/main -1`; executions list |
| Thu 20:05 | `nfl-odds-snapshot`: closing lines for CLV, publish | cloud | `5 20 * * 4` | `curated/lines`, site | executions list |
| Sat 07:00 | desktop narrative pass, Sunday and Monday games (after Friday's designations) | desktop | `sat 07:00` | `marts/narrative/` | desktop log |
| Sat 11:30 | `nfl-narrative-check` | cloud | `30 11 * * 6` | nothing | executions list |
| Sat 12:00 | `nfl-lock-sat`: lock every Saturday to Monday game | cloud | `0 12 * * 6` | as Thursday | as Thursday |
| Sun 09:20, 12:50, 16:00, 20:10 | `nfl-odds-snapshot` | cloud | `20 9 * * 0`, `50 12 * * 0`, `0 16 * * 0`, `10 20 * * 0` | lines, site | executions list |
| Mon 20:05 | `nfl-odds-snapshot` | cloud | `5 20 * * 1` | lines, site | executions list |
| Daily 07:00 | `nfl-retro`: ingest the current season, build missing or stale retros and week recaps, publish | cloud | `0 7 * * *` | `marts/retro/`, `site/retro/`, `site/recap_*` | executions list |
| On demand | `nfl-site`: rebuild and publish the site JSON (started by the desktop after an upload) | cloud | none | site JSON | executions list |
| Push to `main` | `ci` (ruff, pytest, web typecheck/lint/test/build), then `image` when job code changed and `site` when `web/` changed; `infra` plans on PRs and applies on `main` | GitHub | none | Artifact Registry, Firebase, GCP | [Actions](https://github.com/austin-chemelli/nfl-project/actions) |

About 24 Odds API credits a week. A failed cloud execution and a failed desktop pass each email Austin; nothing retries by itself. The lock job refuses to run if `main` has job-code commits newer than its image, so code merges must finish their image build before Thu 09:00 and Sat 12:00.

### Links

- Site: <https://nfl-project-prod.web.app>. Data freshness: <https://storage.googleapis.com/nfl-project-prod-site/site/meta.json>.
- GitHub: [repo](https://github.com/austin-chemelli/nfl-project), [PRs](https://github.com/austin-chemelli/nfl-project/pulls), [Actions](https://github.com/austin-chemelli/nfl-project/actions).
- GCP (`nfl-project-prod`): [Cloud Run jobs](https://console.cloud.google.com/run/jobs?project=nfl-project-prod), [Scheduler](https://console.cloud.google.com/cloudscheduler?project=nfl-project-prod), [Logs](https://console.cloud.google.com/logs/query?project=nfl-project-prod), [data bucket](https://console.cloud.google.com/storage/browser/nfl-project-prod-data?project=nfl-project-prod), [site bucket](https://console.cloud.google.com/storage/browser/nfl-project-prod-site?project=nfl-project-prod), [Artifact Registry](https://console.cloud.google.com/artifacts?project=nfl-project-prod), [Secret Manager](https://console.cloud.google.com/security/secret-manager?project=nfl-project-prod), [Alerts](https://console.cloud.google.com/monitoring/alerting?project=nfl-project-prod), [Billing](https://console.cloud.google.com/billing?project=nfl-project-prod).
- Firebase: [Hosting](https://console.firebase.google.com/project/nfl-project-prod/hosting).
- Odds API: `uv run nfl odds status` (credits used); account at <https://the-odds-api.com/>.
- Desktop: `docs/desktop-llm-setup.md`; Task Scheduler task `nfl-narrative`; logs in `data/raw/narrative_local/passes/` on the desktop.

## Workstreams

Live view, with the areas each chat has claimed: `.notes/board.md` (uncommitted, shared by every worktree). This table is the durable version: one row per track, updated when a track starts, opens a PR and finishes.

| Track | Branch | Worktree | Goal | Status (date) | PR |
|---|---|---|---|---|---|
| ui | `ui-next` | `~/dev/nfl-project-ui` | next round of site changes after v2 (tendencies on the league band; whatever Austin's next look finds) | idle, waiting for direction (2026-11-04) | |
| project-state | `project-state` | removed | this hub, the board, the maintenance checklist, hooks and CI guard | merged 2026-11-04, hooks registered in `.claude/settings.json` | #7 |
| narrative | `narrative-m6.2u`, `desktop-task-fix` | `~/dev/nfl-project-narrative`, `~/dev/nfl-project-desktop-fix` | desktop narrative schedule and the desktop task fixes | merged (#1, #5, #6 locks live); worktrees still present, that chat cleans up (2026-11-04) | #1, #5, #6 |

## Milestones

| Milestone | Status |
|---|---|
| M0–M3 hygiene, feature store, approaches, odds + ledger | done 2026-10-27 |
| M4 first public lock (`nfl lock`, refresh, runbook) | built 2026-10-27; first live cloud lock Thu 2026-11-05 |
| M5 Streamlit pages, hypotheses, DIY, coaches | done 2026-10-28 (local explorer only) |
| M6 LLM layer | M6.1, M6.1b, M6.2L (v1–v5), M6.2e, M6.2u done by 2026-11-03; **next: M6.3 previews + faithfulness, M6.4 evals, M6.5 Narrative approach in shadow** |
| M7 hosting (container, Terraform, buckets, cloud locks, React site) | done 2026-10-29; locks live from Week 9 |
| M8 observability | alerts done; uptime check on `meta.json` and a data-freshness alert still open |
| M9 game retrospective (ADR 0016) | done 2026-11-02 |
| M10 site v2, one answer first (ADR 0017) | done 2026-11-04 (PR #4) |
| Feature wave (M1.13 FTN extras and matchup interactions, Matchup approach) | parked for the offseason |

## Open decisions

| Id | Question | Options | Waiting on | Raised |
|---|---|---|---|---|
| D1 | Keep the production number audit (`.notes/audit_site.py`, uncommitted) as a CI or post-publish check? | (a) a step after `nfl publish` that fails the job; (b) a CI check against the public bucket; (c) leave it manual | Austin's call; a chat can build (a) in a day | 2026-11-03 |
| D2 | Tendencies on the league band too (`RangeRow` over `tendencies.parquet`), the follow-up ADR 0017 left out? | (a) next UI round; (b) not worth it | the next UI look | 2026-11-03 |
| D3 | A better knowledge-base tool for cross-chat tracking than `.notes/board.md`? | later; revisit when the board stops being enough | nothing yet | 2026-11-04 |

**Recently closed** (kept two weeks; the ADR or journal entry holds the record):

- Who locks Week 9: the cloud (`locks_paused = false`, PR #6, merged 2026-11-04). The laptop is the fallback.
- Site layout: tabs plus a summary strip, thin team-color accent, matchup cards, retro as the default tab (ADR 0017, 2026-11-03).
- Branch and worktree cleanup after a merge happens without asking (CLAUDE.md, 2026-11-04).
- The live coordination board stays uncommitted in `.notes/` (journal 2026-11-04).
- Docs maintenance is automatic at boundaries, not a weekly audit (journal 2026-11-04).

## Known issues and risks

- **First live locks** Thu 2026-11-05 09:00 and Sat 2026-11-07 12:00: watch the executions and the lock commits; the laptop fallback is `uv run nfl lock --slot thu` in the primary checkout.
- **Production retros are v1 until the 07:00 run on 2026-11-05** rebuilds all 2026 retros with the league bands, the Elo fix and the Week 8 backfill rows. Until then 28 Week 8 retros show a graded Elo that differs from the game page.
- A correction to an earlier game doesn't mark later retros stale (accepted 2026-11-03; the daily job only rehashes each game's own inputs).
- NO @ NYG Week 6: the books' spread and moneyline disagree on the favorite at a coin flip. Real market data, not a bug.
- The GCP free trial ends about late January 2027: upgrade the billing account before then (`docs/hosting.md` §3.1).
- M8 leftovers: no uptime check on `meta.json`, no data-freshness alert.
- The other chat's two merged worktrees (`narrative`, `desktop-fix`) still exist; that chat removes them.

## Docs map

Current docs, what each is for, and when it was last verified against the code or the console (`scripts/state_check.py` warns when a doc changed after its verified date or the date is older than 30 days).

| Doc | Read it when | Verified |
|---|---|---|
| [architecture.md](architecture.md) | changing components, the data model, flows or point-in-time rules | 2026-11-02 |
| [adr/](adr/) | before re-opening a decision; ADR 0017 is the newest | 2026-11-03 |
| [tasks.md](tasks.md) | picking up planned work; progress lives in the journal and here, not in its frozen table | 2026-11-04 |
| [journal.md](journal.md) | understanding why something is the way it is | 2026-11-04 |
| [hosting.md](hosting.md) | touching `infra/`, the buckets, deploys or the desktop upload path | 2026-11-04 |
| [runbook.md](runbook.md) | operating the week by hand, rerunning a job, the desktop setup | 2026-11-04 |
| [site.md](site.md) | working in `web/`: pages, the design language, the kit, deploy | 2026-11-04 |
| [state-maintenance.md](state-maintenance.md) | updating this file, the journal or the board (every chat, at track boundaries) | 2026-11-04 |
| [desktop-llm-setup.md](desktop-llm-setup.md) | the desktop's models, Ollama, SearXNG, Tailscale | 2026-10-29 |
| [local-llm-narrative.md](local-llm-narrative.md) | what the local model can and can't do; prompt and model experiments | 2026-11-03 |
| [feature-groups.md](feature-groups.md) | adding a feature to a group or a group to a persona | 2026-10-28 |
| [PROJECT_BRIEF.md](PROJECT_BRIEF.md) | the original scope; historical, ADRs win on conflict | 2026-10-27 |
| `.notes/` (uncommitted) | `board.md` live tracks; `audit_site.py` the production number audit; `backtest-2025.md`, `feature-dictionary.md`, `data-walkthrough.md`, `local-llm-limits.md` reference; `project-state-plan.md` this system's plan; `archive/` notes that were true once | 2026-11-04 |

## Maintenance

- Chats update this file at track boundaries and whenever a decision or finding changes direction; the checklist is [state-maintenance.md](state-maintenance.md). Austin never has to edit it by hand.
- `scripts/state_check.py` runs at session start (`scripts/hooks/session-start.sh`, which also injects this file, the board and the journal tail), before `gh pr create` / `git push` (`scripts/hooks/pr-guard.sh`) and in CI (`docs` job): links, the schedule table, workstream rows vs worktrees and PRs, docs-map dates, the bottom line's age.
- A code PR that changes neither this file nor the journal is blocked by the hook and by CI (label `docs-not-needed` to override).
