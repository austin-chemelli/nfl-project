# State of the project

Where the project is right now. Chats keep it current as they work ([state-maintenance.md](state-maintenance.md)); `scripts/state_check.py` checks the mechanical parts at every session start, before every PR and in CI. How we got here: [journal.md](journal.md). What's next: [tasks.md](tasks.md). Why: [adr/](adr/). How we work: [../CLAUDE.md](../CLAUDE.md).

## Bottom line (as of 2026-11-06)

The pipeline, the public site and the desktop narrative passes run on schedules; the first public lock landed Thursday 2026-11-05 at 09:07 ET (`c8d8103`), on model wave 2 (ADR 0018). Wave 2 is football features only, line moves capped at 4.5 points, special teams as a group, the Student as the headline line and the ensemble retired. UI round 2 finished 2026-11-05 (#17), and the site walk fixes followed (#18). The League page is finished and live (M14, #20, #23, #24): playoff odds on two variants, standings, leverage, team charts, similar seasons and slate stakes lines. The retro's win-probability chart, motion, drives and pinned result are live too (M15, #19, #21, #22). Coaches and Build are hidden from the live site until they're better (M16): nothing removed, both still in `npm run dev`. Next: the narrative's previews and evals (M6.3, M6.4).

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

About 24 Odds API credits a week. A failed cloud execution and a failed desktop pass each email Austin; nothing retries by itself. The lock job refuses to run if `main` has job-code commits newer than its image. An image builds in 3 to 4 minutes, so job code can merge anytime except the last 10 minutes before Thu 09:00 and Sat 12:00; a refused lock emails and can be rerun by hand (`docs/runbook.md`, Merging job code).

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
| league | `league-teams`, `league-playoffs`, `league-context` | removed | M14 league page in three phases (ADR 0019): Teams tab with scatter charts and the `feature_bands` fix; standings, simulated playoff odds, leverage, slate stakes line; similar seasons, compare, ranks | merged 2026-11-06, all three phases live and checked in production. The first real snapshot lands with Saturday's lock: check the job log for `SNAPSHOT NOT SAVED` | #20, #23, #24 |
| pop | `retro-wp`, `retro-drives`, `retro-story` | removed | M15 (ADR 0020): win-probability chart with turning points, motion tokens and kit motion, skeletons, touch tips; drives; pinned result | merged 2026-11-05, all three phases live; `nfl-retro` run by hand on d969ab3, retros on schema 6; worktree and branches removed. M15.10 route crossfades optional, not built | #19, #21, #22 |
| ui | `ui-next` | `~/dev/nfl-project-ui` | Coaches and Build hidden from the live site, merged 2026-11-06 (#25); earlier: M13 site walk fixes (#18), round 2; later items in `.notes/ui-round2.md` §9 (tendencies across situations, H4 injuries and news tab, open-bets list once live bets exist) | U1 to U5 merged and live (#11, #13, #14, #16, #17); `nfl-retro` and `nfl-site` run by hand on 041a83a, 2026-11-05 | #11, #13, #14, #16, #17 |
| model-wave2 | `model-wave2`, `qb-charted-starter` | removed | `.notes/ui-round2.md` §6: line-move cap, scheme groups zeroed, pressure rate into Defense, special-teams group, ensemble demoted (the QB fix ships ahead on its own branch); one `model_version`, live before the first public lock | merged and cut over 2026-11-04; worktree kept until the first lock passes (rollback backup) | #12 |
| project-state | `project-state` | removed | this hub, the board, the maintenance checklist, hooks and CI guard | merged 2026-11-04, hooks registered in `.claude/settings.json` | #7 |
| hooks | `hooks-dev-folder`, `hooks-log` | removed | the state hooks at the `~/dev` level, executable bit, run log | merged 2026-11-04; hooks verified firing on resume | #8, #9 |
| narrative-sources | `narrative-sources` | removed | fix the 2026-11-04 pass failures: feeds and Tavily before search, resumable passes, failure detail, reset instead of pull | merged 2026-11-05, image `c12c6a5`; worktree and branch removed; first desktop pass on it finished 2026-11-05 06:32Z with 15 of 15 games | #15 |
| narrative | `narrative-m6.2u`, `desktop-task-fix`, `locks-live` | removed | desktop narrative schedule, the desktop task fixes, locks live | merged 2026-11-04; worktrees and branches removed; task registered on the desktop, first pass 2026-11-04 18:00 ET | #1, #5, #6 |

## Milestones

| Milestone | Status |
|---|---|
| M0–M3 hygiene, feature store, approaches, odds + ledger | done 2026-10-27 |
| M4 first public lock (`nfl lock`, refresh, runbook) | built 2026-10-27; first live cloud lock Thu 2026-11-05 |
| M5 Streamlit pages, hypotheses, DIY, coaches | done 2026-10-28 (local explorer only) |
| M6 LLM layer | M6.1, M6.1b, M6.2L (v1–v5), M6.2e, M6.2u done by 2026-11-03; desktop task registered 2026-11-04; **next: M6.3 previews + faithfulness, M6.4 evals, M6.5 Narrative approach in shadow**. After Week 9's passes: recompose the 9B-only matchup on the same facts to compare with v5; parked: M6.6 follow-up searches, M6.7 hosted agent (D3) |
| M7 hosting (container, Terraform, buckets, cloud locks, React site) | done 2026-10-29; locks live from Week 9 |
| M8 observability | alerts done; uptime check on `meta.json` and a data-freshness alert still open |
| M9 game retrospective (ADR 0016) | done 2026-11-02 |
| M10 site v2, one answer first (ADR 0017) | done 2026-11-04 (PR #4) |
| M11 model wave 2 (ADR 0018) | done 2026-11-04 (PR #12), live before the first public lock |
| M13 site walk fixes (review §10) | done 2026-11-05 (PR #18), live; retros on schema 5 |
| M14 league page (ADR 0019) | done 2026-11-06 (#20, #23, #24), live; odds history starts with Tuesday's refresh |
| M15 retro win probability, motion, drives, story (ADR 0020) | done 2026-11-05 (#19, #21, #22), live; retros on schema 6; M15.10 route crossfades optional, not built |
| M16 Coaches and Build back on the site | Coaches picked up 2026-11-06 as M17 (ADR 0021): staff table, study and team data files merged (#26), 2026 verified; team page next (M18); both pages still hidden. Build: with the custom-approach work |
| M19 site name and custom domain | parked 2026-11-07: researched, waiting on Austin's calls (domain, display name, repo rename). Plan: `.notes/plans/rename-and-domain.md` |
| Feature wave (M1.13 FTN extras and matchup interactions, Matchup approach) | parked for the offseason |

## Open decisions

| Id | Question | Options | Waiting on | Raised |
|---|---|---|---|---|
| D1 | Keep the production number audit (`.notes/audit_site.py`, uncommitted) as a CI or post-publish check? | (a) a step after `nfl publish` that fails the job; (b) a CI check against the public bucket; (c) leave it manual | Austin's call; a chat can build (a) in a day | 2026-11-03 |
| D2 | Tendencies on the league band too (`RangeRow` over `tendencies.parquet`), the follow-up ADR 0017 left out? | (a) next UI round; (b) not worth it | the next UI look | 2026-11-03 |
| D3 | How should narrative research get smarter? Plans in `docs/tasks.md` (M6.6, M6.7) | (a) M6.6: one model-proposed follow-up search per game in the local pipeline, a few hours, free; (b) M6.7: hosted free-roaming agent on API credits, better writing and no desktop dependence, but reverses the no-paid-API rule; (c) leave it as it is | Austin; both parked, neither scheduled | 2026-11-05 |
| D3 | A better knowledge-base tool for cross-chat tracking than `.notes/board.md`? | later; revisit when the board stops being enough | nothing yet | 2026-11-04 |
| D10 | Betting integration (§5): which venue is lawful where Austin lives; then read-only prices only, or execution with a fixed small stake? | legal check first; read-only / execute | Austin | 2026-11-05 |
| D11 | GPU for the desktop (§6): a 24 GB card to run 27–32B models, or stay on the 1070 with prompts and evals only? | buy / stay | Austin's money | 2026-11-05 |
| D12 | Learned Student (§3.1): a fifth line in shadow (recommended) or a replacement for the Student? | shadow / replace | Austin | 2026-11-05 |
| D13 | Player-level data (§2.2): injury weighting plus four position groups, or wider? | narrow / wide | Austin | 2026-11-05 |
| D14 | A backup lock run 30 minutes after each lock that acts only if the first didn't, so a badly timed merge fixes itself? | (a) build it, about an hour, plus an "already locked?" check; (b) leave reruns manual | Austin, after the first public lock | 2026-11-04 |
| D15 | Coaches refinement (ADR 0021): where the per-team view lives | **decided 2026-11-06: a team page `/team/:code`, linked from game previews and wherever a team is named** | Austin | 2026-11-06 |
| D16 | Staff verification depth | **decided 2026-11-06: 2016–2026 (where scheme data exists), full bar 2022+, light bar before; five research agents launched 2026-11-06** | Austin | 2026-11-06 |

**Recently closed** (kept two weeks; the ADR or journal entry holds the record):

- D9 League page tiebreaks: the real procedure through strength of schedule, then a seeded coin flip (Austin, 2026-11-05, ADR 0019). A scratch engine reproduced 48 of 48 conference-seasons' seeds, so it is M, not L.
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

- **A league build failure is silent** (M14): `site.build` prints and carries on, so the job stays green with no email, and a lost snapshot can't be backfilled. Grep `league.json failed` or `SNAPSHOT NOT SAVED` in the job logs until there is a log-based alert. Snapshots are one read-modify-write file, so a manual run overlapping a scheduled one can lose rows.
- **Baltimore's Week 9 starter is uncertain.** Tyler Huntley missed Wednesday's practice and Joe Fagnano took full reps. The lock uses the depth chart nflverse has at 09:00.
- **First live locks** Thu 2026-11-05 09:00 and Sat 2026-11-07 12:00: watch the executions and the lock commits; the laptop fallback is `uv run nfl lock --slot thu` in the primary checkout. Thursday's is the first push from the cloud: dry runs don't push, so the deploy key's write access is confirmed but the push itself is untested.
- **Desktop passes** 2026-11-05: the pass on #15 stored the 7 missing games (15 of 15 in the bucket, 06:32Z), Tavily served its queries (51 credits used), the 08:30 check passed and the first public lock landed (`c8d8103`, JAX @ BAL). Open: (1) games took 26.5 minutes each, against about 16 for full games on the search-only pass. Feed pages take about 32 seconds each against 21 in Week 8 (n=8, one game), because they yield more facts, which accounts for about 6 of the 10 extra minutes. At that rate Saturday's 14 games end about 13:10 ET, after the 11:30 check, which would email a false failure because uploads come last; the lock doesn't depend on it, and Saturday's fewer queries won't shorten the model time. (2) `push_locks` tries once and the job has no retries, so a GitHub push error fails the lock job; rerun it before kickoff. A docs push failed that way twice on 2026-11-05 (`fatal error in commit_refs_rules`) and passed 28 minutes later. (3) LA @ WAS (14 claims, 2 pages) and NYG @ PHI (4 pages) are thin leftovers from the blocked run; Saturday's pass replaces them.
- Game page, from the League site walk (`.notes/site-walk/2026-11-05-4/report.md`): "JAX, 48th pct" is the size of the edge among matchups, and reads as a contradiction beside a rank-3 offense; a scheme label loses its closing parenthesis; Details rows print equal rounded values with dots far apart. Small; the pop track owns those files.
- The learned-Student experiment (2026-11-05, `.notes/plans/learned-student.md`): a GBM on the same matrix loses to the Student by 0.0033; "Student + trees" ties. Not building it now. Also found: `.data-prod` in the UI worktree is stale (features from Oct 28); `schema.py` defines a `shadow` flag no code reads.
- Follow-up to wave 2: the retro's kicking luck should read against the kicker's own season rate (`src/nfl/retro/game.py`, after the UI retro PR).
- A correction to an earlier game doesn't mark later retros stale (accepted 2026-11-03; the daily job only rehashes each game's own inputs).
- NO @ NYG Week 6: the books' spread and moneyline disagree on the favorite at a coin flip. Real market data, not a bug.
- The GCP free trial ends about late January 2027: upgrade the billing account before then (`docs/hosting.md` §3.1).
- M8 leftovers: no uptime check on `meta.json`, no data-freshness alert.
- README scorecard CIs change between `nfl readme` runs: on 2026-11-03 only the bootstrap CI digits moved (point estimates and counts identical), although `grade.py` seeds its RNG. Cause unverified; that run's README change was discarded.
- gcsfuse logs ERROR `BufferedWriteHandler.OutOfOrderError` on curated parquet writes in cloud jobs (seen in dry run `nfl-lock-thu-5mqhw`, 2026-11-04). The job succeeded; the effect on the written files wasn't checked.

## Docs map

Current docs, what each is for, and when it was last verified against the code or the console (`scripts/state_check.py` warns when a doc changed after its verified date or the date is older than 30 days).

| Doc | Read it when | Verified |
|---|---|---|
| [architecture.md](architecture.md) | changing components, the data model, flows or point-in-time rules | 2026-11-06 |
| [adr/](adr/) | before re-opening a decision; ADR 0020 is the newest (0019 league page, 0020 retro win probability and motion) | 2026-11-05 |
| [tasks.md](tasks.md) | picking up planned work; progress lives in the journal and here, not in its frozen table | 2026-11-07 |
| [journal.md](journal.md) | understanding why something is the way it is | 2026-11-06 |
| [hosting.md](hosting.md) | touching `infra/`, the buckets, deploys or the desktop upload path | 2026-11-04 |
| [runbook.md](runbook.md) | operating the week by hand, rerunning a job, the desktop setup | 2026-11-05 |
| [site.md](site.md) | working in `web/`: pages, the design language, the kit, deploy | 2026-11-06 |
| [state-maintenance.md](state-maintenance.md) | updating this file, the journal or the board (every chat, at track boundaries) | 2026-11-04 |
| [desktop-llm-setup.md](desktop-llm-setup.md) | the desktop's models, Ollama, SearXNG, Tailscale | 2026-11-05 |
| [local-llm-narrative.md](local-llm-narrative.md) | what the local model can and can't do; prompt and model experiments | 2026-11-05 |
| [feature-groups.md](feature-groups.md) | adding a feature to a group or a group to a persona | 2026-11-04 |
| [PROJECT_BRIEF.md](PROJECT_BRIEF.md) | the original scope; historical, ADRs win on conflict | 2026-10-27 |
| `.notes/` (uncommitted) | `board.md` live tracks; `audit_site.py` the production number audit; `backtest-2025.md`, `feature-dictionary.md`, `data-walkthrough.md`, `local-llm-limits.md` reference; `project-state-plan.md` this system's plan; `project-review-2026-11.md` the 2026-11-05 review and next directions (D9–D13); `plans/` one research plan per enhancement (2026-11-05: interaction features, learned Student, boldness view, league page, team scatter, WP chart and motion), each ending in decisions for Austin; `plans/pop-chat-prompt.md` starts the M15 chat; `archive/` notes that were true once | 2026-11-04 |

## Maintenance

- Chats update this file at track boundaries and whenever a decision or finding changes direction; the checklist is [state-maintenance.md](state-maintenance.md). Austin never has to edit it by hand.
- Each hook run appends a line to `~/.claude/nfl-hooks.log` (when it ran, from which cwd). Check it when a session seems to have started without the hub.
- `scripts/state_check.py` runs at session start (`scripts/hooks/session-start.sh`, which also injects this file, the board and the journal tail), before `gh pr create` / `git push` (`scripts/hooks/pr-guard.sh`) and in CI (`docs` job). The hooks are registered in the repo's `.claude/settings.json` and in `~/dev/.claude/settings.json` (sessions start in the `~/dev` workspace; `scripts/hooks/dev-folder-settings.json`): links, the schedule table, workstream rows vs worktrees and PRs, docs-map dates, the bottom line's age.
- A code PR that changes neither this file nor the journal is blocked by the hook and by CI (label `docs-not-needed` to override).
