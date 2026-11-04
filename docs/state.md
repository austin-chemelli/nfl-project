# State of the project

Where the project is right now. Chats keep it current as they work ([state-maintenance.md](state-maintenance.md)); `scripts/state_check.py` checks the mechanical parts at every session start, before every PR and in CI. How we got here: [journal.md](journal.md). What's next: [tasks.md](tasks.md). Why: [adr/](adr/). How we work: [../CLAUDE.md](../CLAUDE.md).

## Bottom line (as of 2026-11-04)

The numeric pipeline and the public site run on schedules with nobody touching them. Locks went live on 2026-11-04 (PR #6): the first public lock is Thursday 2026-11-05 at 09:00 ET. The desktop's scheduled task was registered the same day, and its first real pass is 2026-11-04 at 18:00 ET. This week shipped the site's v2 layout (one answer first, ADR 0017), fixed three number bugs a cross-check of production found (market consensus near even money, an Elo leak in after-the-fact scoring, Week 8 missing from the tracker), and put the desktop research on a Wednesday and Saturday schedule. Next: watch the first live locks, then the narrative's previews and evals (M6.3, M6.4).

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
| ui | `ui-next` | `~/dev/nfl-project-ui` | round 2: games first, approaches second (`.notes/ui-round2.md` §3–4: game page Preview tab, retro reorder, slate cards, tracker) | U1 (ensemble off the site, Student headline) built 2026-11-04, web-only; U2 game page next; parallel to model-wave2 (§8) | |
| model-wave2 | `model-wave2`, `qb-charted-starter` | `~/dev/nfl-project-model` | `.notes/ui-round2.md` §6: line-move cap, scheme groups zeroed, pressure rate into Defense, special-teams group, ensemble demoted (the QB fix ships ahead on its own branch); one `model_version` for the Week 10 Thursday lock. Runs parallel to ui (§8) | started 2026-11-04 | |
| project-state | `project-state` | removed | this hub, the board, the maintenance checklist, hooks and CI guard | merged 2026-11-04, hooks registered in `.claude/settings.json` | #7 |
| hooks | `hooks-dev-folder`, `hooks-log` | removed | the state hooks at the `~/dev` level, executable bit, run log | merged 2026-11-04; hooks verified firing on resume | #8, #9 |
| narrative | `narrative-m6.2u`, `desktop-task-fix`, `locks-live` | removed | desktop narrative schedule, the desktop task fixes, locks live | merged 2026-11-04; worktrees and branches removed; task registered on the desktop, first pass 2026-11-04 18:00 ET | #1, #5, #6 |

## Milestones

| Milestone | Status |
|---|---|
| M0–M3 hygiene, feature store, approaches, odds + ledger | done 2026-10-27 |
| M4 first public lock (`nfl lock`, refresh, runbook) | built 2026-10-27; first live cloud lock Thu 2026-11-05 |
| M5 Streamlit pages, hypotheses, DIY, coaches | done 2026-10-28 (local explorer only) |
| M6 LLM layer | M6.1, M6.1b, M6.2L (v1–v5), M6.2e, M6.2u done by 2026-11-03; desktop task registered 2026-11-04; **next: M6.3 previews + faithfulness, M6.4 evals, M6.5 Narrative approach in shadow**. After Week 9's passes: recompose the 9B-only matchup on the same facts to compare with v5 |
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

- D4 Preview bars are scaled by the Global fit (Austin, 2026-11-04).
- D5 The Student stays as the data-only public line; the ensemble is demoted to a diagnostic like Global and leaves the site, README and tiles (Austin, 2026-11-04). Its lock rows keep being written until wave 2 drops it.
- D6 Model wave 2 scoped (Austin, 2026-11-04; `.notes/ui-round2.md` §6): quarterback-group fix, line move winsorized and given to the Student and Analyst, coaching and both scheme groups zeroed in every line, special teams promoted to its own group, ensemble stops locking. One `model_version` at the Week 10 Thursday lock.
- D7 folded into D6.
- D8 Retro names: "Swing plays" and "Pure luck" (Austin, 2026-11-04).

- Who locks Week 9: the cloud (`locks_paused = false`, PR #6, merged 2026-11-04), without the planned shadow week, to find the problems on the first live weekend. The laptop is the fallback.
- Narrative timing: two passes, Wednesday evening for every game and Saturday morning for the Sunday and Monday games; the newer record supersedes with no reconciliation code (journal 2026-11-03).
- Narrative models: `qwen3.5:9b` plus `qwen3:14b` for the matchup job, thinking off; gemma4 and gpt-oss dropped (journal 2026-11-03).
- Site layout: tabs plus a summary strip, thin team-color accent, matchup cards, retro as the default tab (ADR 0017, 2026-11-03).
- Branch and worktree cleanup after a merge happens without asking (CLAUDE.md, 2026-11-04).
- The live coordination board stays uncommitted in `.notes/` (journal 2026-11-04).
- Docs maintenance is automatic at boundaries, not a weekly audit (journal 2026-11-04).

## Known issues and risks

- **Upcoming games priced the previous starter, not the named one** (Baltimore on Lamar Jackson's career with Tyler Huntley charted; Arizona likewise). Fixed on `qb-charted-starter`: upcoming games follow the depth chart's QB1. Not live until that PR merges and its image builds. Huntley missed Wednesday's practice, so the chart may change again; the lock follows whatever nflverse has at 09:00.
- **First live locks** Thu 2026-11-05 09:00 and Sat 2026-11-07 12:00: watch the executions and the lock commits; the laptop fallback is `uv run nfl lock --slot thu` in the primary checkout. Thursday's is the first push from the cloud: dry runs don't push, so the deploy key's write access is confirmed but the push itself is untested.
- **First desktop pass** 2026-11-04 18:00 ET: the task's environment is tested (entry `desktop setup test` in Cloud Logging), a full scheduled run isn't. The 08:30 check on 2026-11-05 emails if it didn't upload.
- **Production retros are v1 until the 07:00 run on 2026-11-05** rebuilds all 2026 retros with the league bands, the Elo fix and the Week 8 backfill rows. Until then 28 Week 8 retros show a graded Elo that differs from the game page.
- A correction to an earlier game doesn't mark later retros stale (accepted 2026-11-03; the daily job only rehashes each game's own inputs).
- NO @ NYG Week 6: the books' spread and moneyline disagree on the favorite at a coin flip. Real market data, not a bug.
- The GCP free trial ends about late January 2027: upgrade the billing account before then (`docs/hosting.md` §3.1).
- M8 leftovers: no uptime check on `meta.json`, no data-freshness alert.
- README scorecard CIs change between `nfl readme` runs: on 2026-11-03 only the bootstrap CI digits moved (point estimates and counts identical), although `grade.py` seeds its RNG. Cause unverified; that run's README change was discarded.
- "Most misread" is hidden in the week recaps: it is built on the ensemble in `retro/week.py`. Moves to the Student with U3's retro schema bump; wave 2's ensemble stop would leave it empty for new weeks until then.
- Flaky web test: `web/src/pages/build/build.test.tsx` ("Blank (equal weights)" button not found) failed once on PR #6, which doesn't touch `web/`, and passed on rerun. Not investigated; UI track.
- gcsfuse logs ERROR `BufferedWriteHandler.OutOfOrderError` on curated parquet writes in cloud jobs (seen in dry run `nfl-lock-thu-5mqhw`, 2026-11-04). The job succeeded; the effect on the written files wasn't checked.

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
| [desktop-llm-setup.md](desktop-llm-setup.md) | the desktop's models, Ollama, SearXNG, Tailscale | 2026-11-04 |
| [local-llm-narrative.md](local-llm-narrative.md) | what the local model can and can't do; prompt and model experiments | 2026-11-04 |
| [feature-groups.md](feature-groups.md) | adding a feature to a group or a group to a persona | 2026-10-28 |
| [PROJECT_BRIEF.md](PROJECT_BRIEF.md) | the original scope; historical, ADRs win on conflict | 2026-10-27 |
| `.notes/` (uncommitted) | `board.md` live tracks; `audit_site.py` the production number audit; `backtest-2025.md`, `feature-dictionary.md`, `data-walkthrough.md`, `local-llm-limits.md` reference; `project-state-plan.md` this system's plan; `archive/` notes that were true once | 2026-11-04 |

## Maintenance

- Chats update this file at track boundaries and whenever a decision or finding changes direction; the checklist is [state-maintenance.md](state-maintenance.md). Austin never has to edit it by hand.
- Each hook run appends a line to `~/.claude/nfl-hooks.log` (when it ran, from which cwd). Check it when a session seems to have started without the hub.
- `scripts/state_check.py` runs at session start (`scripts/hooks/session-start.sh`, which also injects this file, the board and the journal tail), before `gh pr create` / `git push` (`scripts/hooks/pr-guard.sh`) and in CI (`docs` job). The hooks are registered in the repo's `.claude/settings.json` and in `~/dev/.claude/settings.json` (sessions start in the `~/dev` workspace; `scripts/hooks/dev-folder-settings.json`): links, the schedule table, workstream rows vs worktrees and PRs, docs-map dates, the bottom line's age.
- A code PR that changes neither this file nor the journal is blocked by the hook and by CI (label `docs-not-needed` to override).
