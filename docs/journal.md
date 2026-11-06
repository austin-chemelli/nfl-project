# Project journal

How this project has evolved: what was tried, what was decided and why, what the data and the backtests showed. Chronological, one entry per working session or milestone. This is the raw material for the eventual write-ups (README results, posts, the "how AI coding tools were used" notes). Decisions themselves live in `docs/adr/`; this file is the story around them.

Conventions: date-headed entries, newest last. Each entry: **what happened**, **decisions** (link the ADR), **findings** (numbers with n), **open** (what was left unresolved). Keep it factual; opinions go in `.notes/`. Append at the end of every session that changes the plan, the data, or the results.

## 2026-10-23: brainstorm

**What happened.** Austin brought a project brief (`docs/PROJECT_BRIEF.md`) with five open decisions. Claude (Fable) reviewed it, verified data facts against nflverse, and kept a running decision log in `.notes/brainstorm.md`.

**Decisions.** Free, redistributable data only (ADR 0001): nflverse plus The Odds API free tier; paid charting sources (NFL Pro, PFF, FTN direct, Fantasy Points) tabled after checking prices and redistribution terms. Parquet + DuckDB under one data root (ADR 0002). Cloud-first hosting on GCP with Firebase Hosting, self-hosting on the spare desktop as a later project (ADR 0008). LLM spend on an API key, not the Max subscription (ADR 0007). Licensing: code MIT, derived data CC-BY-SA (ADR 0011). Two lock points per week (ADR 0005).

**Findings.** Participation data (coverage, personnel, man/zone) is published only after the season; FTN charting (box count, blitzers, motion, play-action, RPO, QB alignment) updates in-season, 2022+. An early draft of the log wrongly said box count was offseason-only; corrected. nflverse schedule lines are untimestamped and closing-ish. Claude Max subscription tokens may not power an application (enforced since ~Apr 2026).

**Open.** Model philosophies, enrichment feeding models or not, live-first vs backtest-first, frontend depth, budget: all resolved on 2026-10-25/26.

## 2026-10-24 to 10-25: local POC

**What happened.** Built a ~1,500-line local POC: ingestion of nflverse parquet into immutable snapshots with manifests, DuckDB-curated tables (games, plays joined to FTN, injuries, depth charts), a null-rate audit, raw team tendencies by situation, three reference models (market baseline, margin-of-victory Elo, naive home), append-only predictions with synthetic backfill locks, grading, and a Streamlit explorer. `nfl run-all` in ~10 s. 7 tests including the first leakage guards.

**Findings.** Market baseline log loss ≈ 0.60–0.62 per season (2022–2025, ~285 games each), Elo ≈ +0.02–0.03 worse, naive 0.69. 99% of pass/run plays join FTN on (game_id, play_id). Bugs found and fixed: `desc` is a DuckDB reserved word; DuckDB 2.0 connections have no `.pl()`; hive partitioning must be off when reading raw snapshot folders; an ATS bug scored "model spread equals the line" as a win. A data walkthrough (`.notes/data-walkthrough.md`) documented sample rows and what is precomputed by nflfastR (EPA, WP, success, CPOE, xpass) versus computed here.

## 2026-10-25: vision v2

**What happened.** Austin reframed the product: educational and insightful first, betting as a scoring lens; several "approaches" that weigh shared evidence differently, like different fans; an ensemble; a slate view, game pages with drill-ins, a season tracker; divergence from the market as the interesting signal; odds-weighted outcomes rather than win/loss.

**Decisions.** Feature store + approaches + calibration replaces "model philosophies" (ADR 0003). Each approach in a persona and a fitted flavor (ADR 0004). Odds-weighted paper bets with a 5-point threshold, flat 1 unit, CLV as the edge metric, divergence buckets (ADR 0006). A basic Hypotheses page is a first-class deliverable. Persona weights proposed by Claude, reviewed by Austin.

## 2026-10-26: plan, then M0–M3 built

**What happened.** `/plan-project` on Fable produced `docs/architecture.md`, ADRs 0001–0011, `docs/tasks.md`, and a rewritten CLAUDE.md. Austin chose: Streamlit through P1 and React in P2 (ADR 0009); first public lock waits for the approaches rather than locking Week 9 with the POC models (ADR 0010); the name stays `nfl-project`. Calendar targets were then removed from the plan at Austin's request: sequence only. Implementation moved to Opus with implementer agents in parallel: feature store (7 families), approach configs, scoring engine, shrink-to-persona ridge fitting with walk-forward λ selection, backfill 2015–2025, grading v2 (ECE, reliability, season-bootstrap CIs, divergence buckets), Odds API snapshots, live market features, and the paper ledger. 93 tests.

**Decisions.** No GitHub Actions cron scheduler; locks are laptop commands until Cloud Scheduler in P2 (ADR 0008 amendment). Backtest feature rows are stamped kickoff − 2h, strictly before the kickoff − 1h synthetic lock. The λ grid moved to 1–10,000 on the summed log loss after the original 0.3–10 proved effectively unregularized. The global fit excludes market features so hypotheses read "does X predict wins", not "is X priced in".

**Findings (backtest 2015–2025, 3,018 games, models never trained on the scored season).** Sharp fitted 0.612 log loss vs market 0.615 (CI on the difference crosses zero); ensemble 0.623; Traditionalist, Analyst and Elo ≈ 0.635; Traditionalist persona 0.642; naive 0.689. When the non-market approaches disagreed with the market by 10+ points (≈ 660 games each), the side they leaned toward won 38–41% of the time against a market expectation of 40–41%, i.e. the market was right. Persona vs fitted weights: the Traditionalist overrates momentum ~6× and rest ~3×; travel, time zones and turnover margin fit near zero; the Analyst overrates defensive EPA and 4th-down aggressiveness and underrates plain results. Platt scale 0.50 for the Traditionalist persona (twice as confident as warranted), 0.73 Analyst, 0.97 Sharp. Backfill paper ledger 2022+: every model loses into closing-ish lines, Sharp fitted −2.9% ROI, the rest −7% to −15%.

**Bugs.** Play-by-play prints current team codes (LA, LAC, LV) for every season while schedules use historical ones (STL, SD, OAK); the strength builder silently dropped those teams' plays. Fixed by joining on franchise codes, with a regression test. The Odds API historical endpoint turned out to be paid-only on the free plan (the brainstorm log had it as included); closing lines now come from our own pre-kickoff snapshots, else nflverse. The Odds API only takes the key as a URL parameter; one probe printed a URL with the key into session output, after which the module was made to redact URLs from every error (tested).

**Open.** Austin's review of the persona weights; the first commit.

## 2026-10-27: ideas, groups, sequence, narrative contract

**What happened.** Austin proposed a build-your-own approach page, asked for more features, and asked to get the LLM narrative research running for Week 8. Claude (Fable) wrote `.notes/ideas-diy-features-narrative.md` (DIY page design that needs no server; ~60 candidate features with calculations; the narrative agent plan), built the narrative record contract (`nfl.llm.narrative`, `nfl.features.narrative`, `nfl narrative slate|ingest|example|list`) and the `/nfl-narrative` Claude Code skill as the development-time producer of the same records the API job will produce. Then, on Austin's observation that 60 features cannot be hand-weighted, two-level features: groups with fitted inner weights, personas weigh groups (ADR 0012). Four grouping options were compared; Austin chose the tight-groups option with the scheme group split three ways (`docs/feature-groups.md`, 15 groups). The work sequence was fixed at the top of `docs/tasks.md`: model identity → live → UI → LLM API → hosting → next feature wave.

**Findings.** Injury reports carry `date_modified`, so availability features can be stamped at report time (the data walkthrough had said no report date). A 2024 participation file has personnel and pressure on 100% of plays and coverage type on ~49% (pass plays), from 2016: scheme priors attached to coordinators are feasible. pbp back to 1999 is ~14 MB per season, so a backfill to 1999 for 21 scored seasons is cheap.

**Open.** Persona weights re-proposed at the group level after M2.8; the Week 8 narrative run with the skill; the commit.

## 2026-10-27 (later): step 1 built (Opus)

**What happened.** Data: play-by-play backfilled to 1999, injuries and depth charts to 2009, new pbp columns (passer id, QB EPA, CPOE, sacks, special-teams flag). Three implementer agents in parallel built the availability family (QB1 out, QB change, starters out, position-weighted injury impact, OL out, report count), strength extras (opponent-adjusted EPA via a weekly ridge, pass/rush splits, early-down and non-garbage EPA, sack rates, Pythagorean win%, luck, strength of schedule, special-teams EPA, QB career EPA and CPOE that follow the quarterback), and schedule context (EPA trend, ATS last 3, bye, short week, road streak, lookahead, letdown, eliminated, clinched). The main session built the group machinery (ADR 0012): a 15-group registry, grouped persona configs with overrides, per-group inner weights, unit-variance composites, persona and fitted flavors on composites, stored as flat effective weights so scoring and artifacts didn't change. Personas re-proposed at group level, plus the Student (equal start, learns from results). Scored seasons are now 2005–2025 (5,684 games), training from 2002.

**Decisions.** Inner weights are per-group fits, not the joint global fit, and shrink toward each member's declared sign (ADR 0012 amendment). The market baseline is the vig-free moneyline (v0.2). 1999 kickoff times are imputed by slot and flagged.

**Findings.** Fitted approaches now trail the market by 0.016 log loss (was 0.021 with the flat design). The Sharp ties the market (Δ −0.0004, CI crosses 0). The data's group weights: Quality 0.35, Quarterback 0.22, Offense 0.21, Health 0.11, Defense 0.10, Stakes 0.10, Form 0.08, Venue 0.05, Rest & travel 0.05, scheme ≈ 0, Coaching −0.05. The Traditionalist overrates form and rest about 4× and underrates offense 4× and the QB 2×; the Analyst overrates coaching aggressiveness (fits to 0). Nobody wins when disagreeing with the market by 10+ points.

**Bugs and leaks caught.** (1) The QB "projected starter" was the passer with the most dropbacks in the game, which leaked in-game injuries and benchings in ~3% of team-games; the Sharp briefly "beat the market" with a CI below zero. Switched to the first passer, with a regression test. (2) The remaining Sharp edge was exactly the miscalibration of Φ(spread/13.5) (calibrated spread 0.6083 = Sharp persona 0.6083), hence the vig-free moneyline baseline. (3) 1999 schedules have no kickoff times, so Elo would have replayed 1999 after 2026. (4) Older injury files store season as a float (partitions named `season=2009.0`). (5) Injury `date_modified` exists only 2010–2024, not 2025+ as assumed in the morning. (6) Inner weights shrunk toward zero flipped signs within near-duplicate groups (12 flips), fixed by shrinking toward declared signs.

**Open.** Austin's review of the group-level personas; the coaching group's composition; the first commit.

**Later the same day.** Austin kept the personas as characters (the persona-vs-fitted gaps are the point) and moved turnover margin from Coaching to Quality; Coaching's fitted group weight went from −0.05 to 0.00, so turnover margin had been what made "coaching" look harmful. Registry v2. First build committed as `f7edd73` (91 files, 137 tests); not pushed.

**Before going public.** The original project brief carried a personal "About me" section (employer, job-search targets). It was moved to `.notes/about-me.md` (local, never committed) and stripped from every commit with `git filter-branch`; the brief now has a neutral "Why this project" section. The rewrite changed only that file (verified by diffing against a backup branch).

## 2026-10-27 (evening): the lock (step 2 begins)

**What happened.** The repo went public after the history rewrite. Built `nfl lock`: a refresh (current-season ingest, odds snapshot, curate, features), strict as-of scoring of the slot's unplayed games with the frozen 2025 fits plus market/Elo/naive reference lines, append-only prediction rows, paper bets, a deterministic public JSON with SHA-256, and guarded commit/push (commits only the lock files; pushes only when every unpushed commit is a lock commit, matching Austin's standing permission). Also `nfl weekly refresh`, `docs/runbook.md`, a README with a pipeline-written scorecard (`nfl readme`) and an MIT LICENSE.

**Cleanup.** `nfl predict` had been writing a "live" row per upcoming game on every run since the POC; grading would have treated those as real pre-game locks. 673 such rows (and 20 paper bets opened from them) were purged; none were public. `nfl predict` is now backfill-only, and live rows come only from `nfl lock`.

**Findings.** First dry run (Week 8 Thursday, CAR @ GB) end to end in ~30 s: market 0.64, Traditionalist and Analyst 0.68, Sharp 0.61, Student 0.68, ensemble 0.66, Elo 0.67. The Sharp sits below the market because it reads the spread (GB −3.5 ≈ 0.60) while the vig-free moneyline says 0.64: the two markets disagree slightly on this game.

**Open.** Dry-run week (Thu Oct 29, Sat Oct 31), first public locks in Week 9, pushing the code commits before then.

## 2026-10-27 (night): step 3 UI

**What happened.** The repo's code was committed and pushed (CI green on GitHub). Built the site JSON contract (`nfl site`: meta, weekly slates, per-game files, tracker, audit; statuses locked / backfill / preview, with a real lock always winning), a Streamlit navigation shell with a shared data/palette module (dataviz reference palette: each approach keeps one hue everywhere, personas dashed, references gray), and, via four parallel implementer agents, the Slate, Game, Season tracker, Method, Hypotheses and Build-your-own pages. Every page renders headlessly in tests; the real server serves them. The approach backfill now covers the current season's completed games.

**Findings.** Hypotheses (57 features, 2002–2025, season bootstrap): QB EPA, Elo, point differential, Pythagorean win%, success rate and QB CPOE lead; momentum predicts alone (0.19 logit/SD) but mostly vanishes after team strength (0.04). The build-your-own evaluator reproduces the backfill (Sharp within 0.0004, Student fitted 0.0001) in ~25 ms per evaluation, so the page needs no server.

**Bug caught.** `form.lookahead` (next opponent Elo − this opponent Elo) ranked 7th of 57 and fit with the wrong sign: it was mostly "this opponent is weak", a duplicate of team strength. Redefined as the next opponent's Elo vs an average team; it is now "weak" with an interval including zero.

**Open.** Clicking through the app in a browser (Austin); the dry-run week; weather at lock.

## 2026-10-27 (late): first click-through feedback

**What happened.** Austin ran the `/nfl-narrative` skill (on Sonnet, in a forked subagent) for CAR @ GB: one record, 7 claims, all sources resolve, visible on the game page. Then a full feedback pass on the UI, triaged in `.notes/ui-feedback.md`.

**Decisions.** (1) One public line per approach: the persona, lightly fitted and calibrated; the fully fitted version becomes a diagnostic (ADR 0004 amendment). (2) The market's forecast is never an input to an approach; a "Market behavior" group (line moves, public %, book disagreement) is a capped supplement; the Sharp is redefined around it (ADR 0013). (3) Every feature and group gets a description and a unit; nothing in log-odds reaches the UI: contributions in win-probability points, edges as percentiles, weights as budget shares. (4) Narrative record v2: per-team paragraph and bullet notes, scheme trends, matchup notes with a support count. (5) The coordinator/participation track moves into the in-season sequence, with a Coaches page.

**Findings.** The Sharp "tying the market" was an artifact of feeding it the market; with ADR 0013 every approach will trail the market by ~0.015, which is the honest picture.

**Open.** Narrative stamp should come from the ingest clock (M6.0); the step 3 UI code is uncommitted.

## 2026-10-28: model identity v2 and the feedback build (Opus)

**What happened.** Implemented the feedback decisions. One public line per approach: the persona's group weights ridge-shrunk toward the persona with a fixed strength (PUBLIC_RIDGE = 1.0, chosen so the Traditionalist moves ~25% of the way toward what history supports: 3.0 → 10%, 1.0 → 25%, 0.25 → 55%), then calibrated; the fully fitted flavor stays as a diagnostic. ADR 0013 enforced in the approach schema (the line's level can't be an input; Market behavior capped at 20%); the Sharp redefined around market behavior, quarterback and efficiency. New market-behavior feature: moneyline-vs-spread gap. Registry v3 with labels, descriptions and units for all ~100 members. Site contract v2: contributions in win-probability points, group edges as percentiles of all matchups 2005–2025, budget shares, league averages for tendencies. Narrative v2 schema and skill; ingest stamps records with its own clock (the v1 producer had stamped four minutes late). In parallel: participation data 2016–2025 ingested and curated with team-season scheme rates; the coordinator table 2016–2026 built by a research agent.

**Findings.** Honest backtest after ADR 0013 (2005–2026, ~5,790 games): every approach trails the market. Ensemble +0.0135, Student +0.0154, Sharp +0.0171, Analyst +0.0178, Elo +0.0200, Traditionalist +0.0209 (log loss vs market). Participation: coverage charting starts in 2018; the 2023 provider change shifts league man rate (0.29 → 0.42 → 0.49 → 0.31 in 2022–2025), so coordinator profiles compare within seasons. Coordinator table: OC/DC from Wikipedia team pages with ~10 news cross-checks; play-callers are the weakest column; PFR blocks automated fetching.

**Open.** Austin's validation of 20 sampled coordinator rows; UI readability agents in flight.

**Later (2026-10-28).** Five implementer agents rebuilt the pages on contract v2: slate and game (edges by group, tendency dumbbells against the league, narrative v2 panel), tracker and method (calibration as "when it says 70%, how often does that team win", divergence as plain sentences), hypotheses over time (any feature or group by season), build-your-own under ADR 0013 plus a season view linked from its best/worst seasons, and a Coaches page with coordinator profiles from participation data. Six scheme-prior features (each play-caller's history relative to each season's league average) joined the store. Full rebuild and 218 tests pass; every page serves. Coordinator profile example: Vic Fangio's defenses play more man coverage than 85% of the league; twenty 2026 coordinators have no participation history yet.

## 2026-10-28: code review before the first commit of the feedback build

**What happened.** Austin asked for a review pass before committing. The reviewer agent (read-only; it also simulated Week 8 scoring without writing) found ten issues; all but one were fixed the same session.

**Findings and fixes.**
1. *HIGH:* the Sharp's live-only market-behavior inputs entered in raw units (no history to standardize), and the override divided by a tiny composite sd inflated them: a 2-point line move was worth ~0.8 logit (~20 points of win probability). Fixed with declared scale priors for live-only features (`LIVE_PRIORS`) used by the Scaler; Week 8 simulation now tops out at 0.19 logit.
2. *HIGH, ADR 0013:* `market.ml_spread_gap` (moneyline p − Φ(spread/13.5)) carried ~45% of the spread's information (corr 0.63 with the spread), leaking the line's level into the Sharp and the DIY page. Removed from Market behavior and added to the forbidden set (ADR 0013 amendment). The Sharp now trails the market by 0.019 (was 0.017), behind the Analyst.
3. *HIGH:* `.gitignore`'s `data/` also matched `src/nfl/data/`, so the coordinator table would not have been committed and CI would fail. Anchored to `/data/`.
4. Narrative ingest now validates game id, season, week and teams against the schedule and uses the schedule's kickoff; the builder skips (with a warning) records overtaken by a flexed kickoff instead of breaking every build.
5. *Point-in-time:* scheme priors used the end-of-season play-caller for every week of seasons with a mid-season change (94 of 702 unit-seasons): look-ahead. Those unit-seasons now get no prior.
6. The lock now commits and pushes before rebuilding the site; a site failure only warns.
7. The lock refuses `--commit` from uncommitted code and refuses fit artifacts whose config hash doesn't match the YAML; the registry version is bumped (a formatter had silently defeated an earlier bump).
8–9. Stale model ids in the lock summary and a stale ensemble version label fixed.
10. *Deferred:* a locked game's page shows feature values and narrative "as of now" next to lock-time numbers (display only; tracked in docs/tasks.md).

**Lesson.** Two of the HIGH findings were invisible to the tests (they passed) and only showed up when the reviewer scored a real slate and measured correlations: worth doing before every first-of-its-kind lock.

## 2026-10-28: step 4 goes local (ADR 0014)

**What happened.** The feedback build was committed and pushed (`1afa8e5`, CI green) after the review fixes. Austin chose to run the LLM work on his desktop (GTX 1070 8 GB, Ryzen 3700X, 16 GB RAM, Windows) instead of paying for API credits. A research agent surveyed late-October-2026 options; its sourcing was thin, so the main session re-verified the load-bearing claims (model choice, Pascal/CUDA status, Ollama support, search-API terms).

**Decisions.** ADR 0014: Qwen3.5-9B Q4_K_M on Ollama (thinking off, 16k context), SearXNG for search, Tailscale between machines, Windows for now (Ubuntu stays in the self-hosting project). No free-form agent on the small model: code searches and fetches, the model does schema-constrained steps citing document ids, so URLs can't be fabricated. A producer-comparison eval against the Claude-skill records gates whether the local records feed the shadow Narrative approach; the Sonnet API job remains the fallback.

**Findings.** CUDA 13 dropped Pascal; the 580 driver branch and CUDA-12 builds keep the 1070 usable. Brave's free search tier is gone. The newest small models are from spring 2026; recent open releases are all large.

**Hosting plan (same day, Fable).** `docs/hosting.md` and ADR 0015: the cloud (Cloud Run Jobs + Scheduler, Terraform, one private bucket mounted as the data root) runs everything numeric and commits locks with a deploy key; the desktop runs only the LLM jobs and uploads records to the same bucket; the React site on Firebase fetches its JSON from a public bucket, so data changes never need a deploy. One shadow week before the cloud becomes the primary lock runner. Not started.

## 2026-10-28: step 5 goes live in GCP (phases 1 and 2)

**What happened.** The hosting walkthrough ran in a forked chat. Austin created the GCP free trial, logged gcloud in (WSL needs `BROWSER` pointed at the Windows Brave binary), and added the secrets and the GitHub deploy key by hand; everything else ran from the laptop: project `nfl-project-prod`, the state bucket, Terraform phase 1 (37 resources: APIs, buckets, registry, service accounts, empty secrets, Workload Identity for Actions), then phase 2 (four Cloud Run jobs, nine Scheduler entries, failure alert, budget). `./data` was rsynced to the private bucket (761 MB) and the first image pushed by hand.

**The wrapper.** `scripts/cloud-job.sh` is the in-container entry point: it reads the deploy key from a secret volume, shallow-clones `main`, refuses to run if the clone's HEAD isn't the sha the image was built from (so `code_version` in a lock artifact can't lie), runs `nfl lock --commit --push`, and copies `marts/site/*.json` plus `public/predictions/` to the public bucket mount. The same script ran a dry-run Thursday lock locally in Docker with the real deploy key before anything was applied.

**Decisions.** Lock schedules are created paused (`var.locks_paused`) until the shadow week passes; refresh and odds snapshots run live from the first Tuesday. `nfl readme` stays a laptop command: a README commit from the cloud would be a non-lock commit and trip the push guard. Firebase was added to the project with Analytics off; the Hosting site waits for the React build.

**Gotchas.** Three permission classifier denials shaped the session: editing `~/.zshrc`, writing secret versions, and `gcloud auth configure-docker` (a persistent Docker config). Secrets went in by Austin; the image push used a throwaway `DOCKER_CONFIG` in the scratchpad. Cloud Scheduler returned a 409 "tenant project creation" on one of nine entries created in parallel (transient; re-apply). The billing-budget API needs `user_project_override` + `billing_project` on the provider, and that in turn needs `iam.googleapis.com` enabled, which took minutes to propagate.

## 2026-10-28: the React site (M7.4, M7.5)

**What happened.** Plan in `docs/site.md`. The main session built the foundation in `web/`: Vite + React 19 + TypeScript, a zod contract for every site JSON file (parses all 318 real files; caught the coaches `sides`/`qb` shapes on the first run), TanStack Query hooks, formatters mirroring `nfl.ui.data.fmt`, shared components, a small SVG chart kit (diverging bars, dot-and-whisker, dumbbell), the app shell and routes, and trimmed checked-in fixtures (`scripts/web_fixtures.py`). Four implementer agents then built the pages in parallel on disjoint files (slate + game; tracker + method; hypotheses + coaches; build-your-own + season + the TypeScript DIY evaluator). The evaluator matches Python's `evaluate` to 1e-6 on log loss and per-game probabilities across 12 weight sets (bootstrap intervals can't share numpy's random stream; tested loosely). Deploy is `scripts/firebase_deploy.py` on the Hosting REST API from `.github/workflows/site.yml` (keyless WIF), chosen over the Firebase CLI because of open reports of it ignoring Workload Identity credentials.

**Review.** No wrong numbers or team attribution. Fixed before deploy: the Build sliders wrote `?w=` on every input event (Safari and Firefox throw past ~100 `replaceState` calls in a few seconds, which would have frozen the sliders mid-drag; the URL and the evaluation now follow once a drag pauses); no route error element, and the SPA rewrite would have answered a stale `/assets/` chunk with `index.html` under the one-year immutable header (assets now 404 and the error page reloads once). Also fixed: slate showed "no slate yet" for any error, nullable season columns, a stale team filter across seasons, tooltip overflow on phones, a dev-server crash on directory requests. Site JSON is now published gzipped (the 1.3 MB build-your-own matrix becomes 270 KB).

**Found by checking the live bucket.** The published `meta.json` predates the tendency labels the contract required, so the first deploy would have shown an error on every page. The fields now default to empty, and CLAUDE.md records the rule: data publishes independently of the site, so contract changes stay additive.

**Lesson.** The cache-header question (which of two matching Firebase header rules wins) is undocumented; making the rules disjoint removed the question instead of guessing.
## 2026-10-29: the desktop LLM server is up (M6.1b)

**What happened.** Fable walked the desktop through `docs/desktop-llm-setup.md` from the desktop's own WSL, alongside a system cleanup (C: went from 23 GB free to 247 GB; the old Windows copy of the repos moved to H:). Austin stepped in for the UAC prompts, the Ollama tray launch and the Tailscale sign-in. Everything in the doc was re-verified against the real machine and the doc rewritten to match.

**Findings.**
- The 9B fits: `qwen3.5:9b` at 16k context with q8_0 KV cache runs 100% on the GTX 1070 using 6.9 of 8 GB VRAM, 23 tok/s generation, 206 tok/s prompt eval. `qwen3.5:4b` (4.5 GB, 39 tok/s) stays as the fallback. ADR 0014's "~5.6 GB" was the weights only; the pull is 6.6 GB on disk.
- Ollama's OpenAI-compatible `/v1` endpoint ignores `think: false`; thinking stays on and a 25-token JSON answer costs 312 completion tokens. `reasoning_effort: "none"` on `/v1` (or `think: false` on the native `/api/chat`) brings it to 19. The M6.1 client must send that on every call.
- Windows 10 has no WSL mirrored networking, but calling the desktop's Tailscale IP from WSL works anyway (outbound through Windows' Tailscale adapter), including from the desktop's own WSL. The WSL NAT gateway path is blocked by the per-app Block rule Windows auto-created when Ollama first listened on the network; those auto rules also allow Ollama from any Private-network address, so they get deleted in favor of the rule scoped to the tailnet.
- The Ollama tray app only serves when started from an interactive session; every launch from a WSL shell or script left it running without a listener.
- Driver 582.28 is the actual last Pascal build (R580 branch, security-only); SearXNG's config lives in the WSL home because Docker Desktop's engine runs there.

**State.** Ollama 0.40.12 and SearXNG answer over Tailscale from WSL; `.env` holds the URLs; `.env.example` documents them with placeholders. Left: the smoke test from the laptop (Tailscale not installed there yet), the admin pass that deletes the auto-created firewall rules, a reboot for the driver.

**Tooling note.** The session ran Windows checks and fixes from WSL through `powershell.exe` with ASCII-only scripts saved with a BOM and parse-checked first; PowerShell 5.1 read BOM-less UTF-8 as CP1252 and an em dash broke a script. Elevated steps were staged as files and launched with one UAC click each.

## 2026-10-29: laptop to desktop, and the LLM client (M6.1)

**What happened.** Tailscale went on the laptop (Windows 11; WSL stays in NAT mode and reaches the desktop through the Windows adapter), and the §7 smoke test passed from the laptop's WSL, closing M6.1b. M6.1 followed: `nfl.llm.client.LLMClient` is the single path for model calls. It posts to Ollama's OpenAI-compatible `/v1` with `reasoning_effort: "none"` and a strict `json_schema` response format (checked live first: the 9B returns schema-valid JSON, including a nested list-of-facts schema with an enum). Every request, retries included, is one row in `marts/llm_calls.parquet` with tokens, latency and an energy estimate. `nfl llm ping` answers from the desktop in about a second warm, 8 s cold.

**Decision: no API fallback.** The first version also had an Anthropic adapter (SDK, priced cost, weekly cap), following ADR 0014's "API as a measured fallback". It was never automatic (it needed `LLM_PROVIDER=anthropic` and a key), but Austin doesn't want a paid API in the app at all, so it was removed the same day along with the SDK dependency, and ADR 0014 is amended: if the desktop fails, LLM jobs fail and Austin gets an email. The email (for failed runs and for runs that never happen because the desktop is off) is task M6.2u.

**Design notes.** Retries split two ways: transient failures (connection, timeout, 429, 5xx) back off; a reply that fails validation is retried with the error shown to the model, since at temperature 0 a plain resend would repeat the same output. Truncated replies fail at once but still log their tokens. In the extract check the model dropped "expected to start" from a sentence it otherwise split correctly, the kind of gap M6.2e should measure.

## 2026-10-29 (late): local narrative research works end to end (M6.2L)

**What happened.** `nfl narrative run` researches a game with no paid service: code builds the skill's searches as templates, queries SearXNG on the desktop, fetches pages politely (robots.txt, per-domain delay, trafilatura for main text and publish date), and keeps pages dated within 9 days. The 9B extracts facts from one page per call, then writes each team block and the game block citing fact ids; code attaches every URL, date and `support` count, so a fabricated URL is impossible by construction. An implementer agent (Sonnet) built the search and fetch modules in parallel with the pipeline. BAL @ BUF was stored from the laptop: 20 pages, 136 facts, 30 claims, 7.4 minutes and ~25 Wh, about 2 hours for a 16-game week.

**Found on the live runs (three runs of the same game).**
- Pages were taken query by query, so injury, QB and news searches used the whole page budget and matchup, betting and weather searches never ran. Now every query runs first and pages are picked round-robin.
- Page dates lie on live hub pages (ESPN's Packers injury page carried Oct 1); the newer of the page and search-engine dates wins. The page cache had no expiry, which would have served last week's injury page next week; it now expires after 12 hours.
- The model swapped home and away in the game summary and wrote fact ids as "Fact 45" (dropping every Buffalo note); prompts now name home and away outright and ids are parsed leniently.
- The schedule's QB is the last game's starter, so a prompt that called it "the starting quarterback" made the model list Tyler Huntley at status 2 while its own notes said Lamar Jackson would start. Relabeled; the next run had Jackson at status 1.
- The guards fired as intended: a public betting share with no percentage in any fact was dropped, and so was a note stating a number its facts didn't contain.

**Open.** Scheme facts are thin (scheme searches mostly return form and stats pieces), and ratings like sentiment are rough; M6.2e compares these records with the skill's on the same games.

## 2026-10-30: narrative v2: analysis survives, sentences are grounded (`local_v2`, skill `narrative_v3`)

**What happened.** Reading the first stored BAL @ BUF record, Austin saw that everything past injuries and basics was missing. The debug file showed the pipeline had extracted good analysis ("3 keys to a Bills win": Bills 31st against the pass and last in defensive EPA/play, 16 Ravens offensive-line combinations, the Bills' interior rush against it) and then lost it: there was no scheme or matchup category, so analysis was filed as "form" or even "injury"; every page repeats the injury report, so injury facts took 48 of the game prompt's 80 slots; and summaries were only checked for numbers, so one gave Josh Allen a "history of back issues" that no page mentioned.

**Changes.** Extraction gets `scheme` and `matchup` categories and names the player each fact is about; injury and QB facts are deduped per player and capped at 25 per prompt (freshest first); the game prompt gets no injury facts; summary and consensus sentences cite facts; one check drops any item whose numbers, two-word names or injury words aren't in what it cites; matchup notes and scheme trends must rest on a matchup or scheme fact; claims rotate categories; a plain-wording rule ("basement of the AFC North" was true but not neutral). The `/nfl-narrative` skill now states the same rules, so M6.2e compares like with like.

**Found on three live runs.**
- The first v2 run had the analysis back but named Tyler Huntley as Baltimore's starter (status 2) with 15 facts dated that day saying Lamar Jackson was cleared; "Huntley started the last three games" and the schedule hint won. The starter is now its own small call per team over QB facts only, newest first, checked against what it cites; the team prompt gets the pick with its reports. Jackson came back at status 1 on both later runs.
- A matchup note moved Baltimore's reshuffled line to Buffalo; fact lines now carry their team (`F12 [matchup, BAL]`).
- The second run dropped all six Baltimore notes: the 9B cited the fact *next to* the right one (F24 for F1, F28 for F29), and a trailing period ("Highmark Stadium.") broke name lookups. Items whose ids are off are now re-cited to the one fact that backs them on their own (nearest id first, only for text with a number, name or condition in it) and counted; replaying the saved outputs recovered all six with the right sources.
- Final run: 20 pages, 162 facts, 10.3 minutes; nothing dropped or re-cited; 7 BAL and 5 BUF notes across injury, form, scheme and coaching; 2 scheme trends per team; 3 matchup notes with support 2 to 3 (shootout expected, Jackson's return against a defense allowing 29+ in five of six). Still weak: matchup notes are generic next to the source analysis, and a Week 1 grade (Kyle Hamilton, C+) slipped in as current form.

**Cost.** v2 extracts ~20% more facts and adds two QB calls: about 10–11 minutes a game, ~3 hours for a 16-game week.

## 2026-11-02: first skill-vs-local comparison (M6.2e, CHI @ SEA)

**What happened.** With Week 8's Sunday games played, Monday night's Bears @ Seahawks was the first game researched both ways before kickoff: the `/nfl-narrative` skill (Sonnet 5.5, web search) and the local pipeline (`local_v2`, the desktop 9B). Both records stored. Comparison in `.notes/m6.2e-chi-sea-comparison.md`.

**Findings.** The structured fields mostly agree (both QBs at status 0, Seattle's injury impact 2, the main absences). The text does not: the skill's record has 8 notes a team, multi-source scheme trends built on unit stats (EPA, explosive plays allowed, run and blitz rates) and 5 matchup notes with support 2–4; the local one had 5 notes, weak trends, and one matchup note. Three local errors had pipeline causes, and were fixed in `local_v3`:
- *The wrong favorite.* The consensus said the Bears were favored. The Yahoo betting page quotes a sportsbook director saying "We opened this Bears -3", contradicting its own header (Seattle −3); the 9B took the quote, and grounding passed because a fact said it. Records now never state the line in text: the site shows the market from our odds data, line facts stay out of the compose prompts, and any item stating one is dropped. The skill follows the same rule (`narrative_v4`).
- *Cut-off text.* Both matchup notes were exactly 300 characters and ended mid-word: Ollama enforces a JSON schema's `maxLength` by stopping the string, not by making the model write less. Prompts ask for under 220 characters, and code trims to the last whole sentence or drops the item.
- *Motivation 1.0 for a Week 8 game.* Now anchored (0 ordinary, 0.3 division or playoff race, 0.7 must-win, 1 elimination; prime time is hype, not motivation).

v3 also adds the skill's stat-driven searches (EPA ranks, blitz and pressure, betting previews) and 24 pages a game; scheme facts went from 40 to 79. On the re-run those errors were gone and motivation matched the skill; the remaining gap is synthesis: 2 matchup notes, mostly single-source trends, and "the Bears will deploy a heavy blitz package against Seattle's top-ranked pass defense" (a defense against a defense). That is the 9B, and the lever for it is a bigger model, which 8 GB of VRAM limits. Narrative only feeds site text and the shadow Narrative approach, so v3 runs weekly while comparisons accumulate.

**Also.** The skill run rebuilt the site JSON, which exposed a crash in the old Streamlit game page for games without approach forecasts (fixed with a guard). A full local week is now about 13 minutes a game, ~3.5 hours.

## 2026-11-02: game pages were never published; every game shows what exists

Austin found every game page on the live site saying "No detail file for this game yet", and the Week 8 slate showing only the market for most games. Two causes. `nfl publish` uploaded `marts/site/*.json` with a non-recursive glob, so the 272 per-game files in `site/game/` never reached the bucket (since hosting went live); it now uploads subfolders. And a game shows approach forecasts only from a lock, a backfill (Tuesday's refresh) or a preview (upcoming games at site-build time): Week 8 had no real locks, the last site build ran after the Sunday kickoffs, so played games had nothing until Tuesday. New status `pregame`: a game that kicked off with neither a lock nor a backfill is scored as of an hour before kickoff, with the same models and only data known then, and labeled as not part of the live record. On the site, sections without data now say so (no approach forecasts yet, no group edges yet) instead of disappearing.

## 2026-11-02: deploys wait for the tests; the lock job's image check fixed

Deploys used to start in parallel with CI on every push to `main`, so a commit that failed its tests could already be live. `site.yml` and `image.yml` are now reusable workflows that `ci.yml` calls only after both test jobs pass, when the push changed the web app or the job code respectively (Austin chose this over PR preview channels for now). Reading the lock job for this turned up a latent bug: it refused to run unless `main`'s HEAD *was* the image's commit, but the image only rebuilds on code changes, so Saturday's Week 9 lock would have refused after Thursday's lock commit (and any docs-only push before a lock did the same). It now refuses only if job code changed after the image's commit; tested against a scratch repo (lock commit after the image: runs; code change: refuses; unknown commit: refuses).

## 2026-11-02: post-game retrospective (M9, ADR 0016)

**What.** Austin asked for a view of each finished game that compares the forecasts with what happened: the teams' season form against their play in the game, the "lucky" factors (3rd/4th downs, turnovers, penalties, kicks), and which approach and which of its groups read the game best. Planned on Fable (ADR 0016, M9.1–M9.8), built on Opus with implementer agents in two parallel tracks (Python and web) against a contract fixed first (pydantic and zod validating the same example files), then reviewed by a reviewer agent. 2026 only; template sentences, no LLM; a daily cloud job at 07:00 ET (`nfl-retro`), since nflverse republishes play-by-play several times a day in season.

**How "luck" is priced.** Each factor's expected value comes from league rates in the same situations over 2015–2025 (conversion by distance, field goals by distance, the share of fumbles lost), and the gap is priced in points with that event's EPA value from the same history. "Played like" is a logistic of winning on non-turnover EPA per play. A group's value to a forecast is the drop-one log-loss change, computed from the raw contributions.

**What the numbers forced.**
- Success rate went into the played-like fit and came out with a negative coefficient (it correlates 0.74 with EPA); the fit is EPA-only.
- `return_touchdown` includes pick-sixes and fumble returns (661 of 834 in 2015–2025), so special-teams big plays first came out 3x too common; they are now kick and punt returns plus blocks.
- Against league rates, luck had sd 9 points a team and correlated 0.62 with the margin: a good offense converting third downs counted as lucky. Adjusting the expectation for both teams' form barely moved it, because ~13 third downs a game carry ~5.5 points of binomial noise. The honest answer was labeling: conversions, interceptions and penalties are "partly skill", the total is a *net swing*, and *pure luck* (fumble recoveries, kicks, return plays) is shown separately: sd 3.3, correlation 0.32.

**Review caught three real bugs before anything shipped.** The first cloud run would have failed, because DuckDB binds a parquet glob to the first file's schema and the bucket's older seasons lacked the new columns (the daily job now re-curates plays once when it sees that). Rebuilds would have dropped approach forecasts from games that were never locked, once the pregame window passed, because every nflverse refresh marked every retro stale (staleness is now a hash of the game's own plays, and unlocked games are scored on demand). Turnovers on 3rd/4th down were counted twice. Earlier, the implementer found that `curate(seasons=...)` deleted every other season's curated data, which the daily job would have done to the bucket on its first run.

**Checks.** Kicking and interceptions for CHI @ GB (Week 5) match the published box score (FG 0/1 and 1/3, XP 1/1 and 2/3, 3 and 0 interceptions); third downs, fumbles and penalties could not be checked externally (the box-score sites refuse scripted fetches). 301 Python and 697 web tests.

## 2026-11-03: narrative v4: smaller jobs beat a bigger model (`local_v4`)

**What.** After the CHI @ SEA comparison, Austin asked to push the desktop model further and document it (it is the project's most interesting constraint to talk about): examples, thinking where it helps, one job per call, structured inputs and outputs, and a bigger model, measured against the old results. Write-up: `docs/local-llm-narrative.md`.

**How it was measured.** `nfl narrative recompose` reruns only the writing stage of a saved run on its saved facts, so every variant sees identical input; `--rebuild` reruns only the code checks on saved outputs. Two Week 8 games (BAL @ BUF, CHI @ SEA), read side by side (`nfl narrative compare`).

**Findings.**
- *Structure moved the 9B most.* Splitting the team call into notes, trends and summary, making unit matchup notes name the offense and the (different) defense, reading the two best analysis pages whole, and adding examples from an invented game: CHI @ SEA matchup notes went from 1 (cut off) to 4, correctly paired and backed by 1–3 sites, at ~3 minutes a game for the writing stage.
- *Thinking didn't pay.* Ollama's Qwen ignores the effort level (any effort is "on", with no budget): 23.6 vs 3.1 minutes for a game, a trends call past 13,000 tokens, Buffalo's summary dropped for unsupported numbers; on the matchup job alone, fewer and vaguer notes. Off by default; a thinking call gets a fixed budget and is redone without thinking if it runs out.
- *Bigger models were more fluent, not more faithful.* gpt-oss:20b (MoE, ~3.6B active; ~7 min a game) contradicted its sources (a safety listed as a tackle; "missing Lamar Jackson" the week he returned). qwen3:14b (~15.5 min) had the most specific matchup ideas but put real stats on the wrong team. gemma4:26b was the cleanest but took 98 minutes for one game (18.7 GB against 8 GB of VRAM). qwen3.5:27b took 11.6 minutes for one QB call and was stopped. Memory, not model quality, is the binding limit on this desktop. Kimi K3-class open models (2.8T parameters) are out of reach of any home machine.

**The errors became checks.** A stat whose owner in the sentence (the nearest team name, or a player's when the sentence says "his" or "X's") isn't the team of a cited fact with that number; a matchup note setting a team's offense against its own defense without naming the opponent; fact ids ("(F27)") stripped before the checks. First versions also dropped four correct sentences (records like "5-1"; "blitz Sam Darnold on 41.1% of plays") and were tightened until a rebuild over all seven saved outputs dropped exactly the three known errors. They catch two of the 14B's ~6 errors; the rest (offense vs defense stats for the same team, superlatives, a QB-vs-QB "matchup") need a better writer, not a regex.

**Next.** Austin chose to split jobs between models: the 9B where it is reliable and the 14B where it adds something (v5).

## 2026-11-03: narrative v5: the matchup job on the 14B (`local_v5`)

The v4 comparison was per job, so Austin chose to split jobs between models instead of picking one: the 9B keeps the QB, notes, trends, summaries and game block (correct note kinds, faithful trends, a fifth of the 14B's time), and qwen3:14b writes the matchup notes, where it had the sharpest ideas. The 14B's good v4 notes had been written with thinking on, so v5 was tried both ways on the same two games. With thinking on it reproduced its v4 output exactly, errors included, at 8.6 minutes a game; with thinking off it wrote 5 and 3 matchup notes with cleaner offense-against-defense pairings and no known errors, at 5.3 minutes a game (the model swap included), about 35 minutes more a week. Two of those notes set one defense against the other (the v2 mistake again), so the pairing check now drops that as well; a check-only rerun over every saved output dropped nothing else. On two games the gain over the 9B is small (the 9B named more specifics), so v5 runs in production from Week 9 and the 9B-only version is recomposed on the same facts for a bigger sample.

## 2026-11-03: narrative runs on a schedule (M6.2u)

**The timing question.** Research too early misses the injury news; too late and nobody reads the preview before kickoff. Austin's answer: two passes. Wednesday evening covers every game (the Thursday game's final designations are out by then, and the rest get an early preview), and Saturday morning covers the Sunday and Monday games again after Friday's designations, finishing before the 12:00 lock. The Monday game misses Saturday's designations; a third pass can be added if that shows.

**No reconciliation code.** Records were already append-only, one file per run stamped with `known_as_of`. The site shows a game's newest record, and features and locks use the newest before their own time, so the Saturday pass simply supersedes Wednesday's for anything after it, and Wednesday's stays on disk.

**How it runs.** Windows Task Scheduler on the desktop starts `scripts/desktop-narrative.sh` in WSL. It pulls `main`, downloads the schedule and lines from the bucket, researches every game not yet kicked off, uploads the records and starts a new `nfl-site` cloud job to rebuild and publish. Any failure writes an ERROR to Cloud Logging, which emails Austin. A pass that never happens (desktop asleep, signed out) is caught by `nfl-narrative-check`, a cloud job half an hour before each lock that fails if an upcoming game has no record since the pass started. The pass times live in one place (`PASSES`) so the check and the docs agree. Built in its own worktree and merged by PR, per the new parallel-work convention.

## 2026-11-03: site v2, one answer first (M10), and a number audit

**Why.** With the retrospective added, a finished game's page was 21 stacked sections, each with a paragraph, hover help, a chart and a table. Austin found it overwhelming and some charts hard to read (the efficiency dumbbells auto-scaled, so numbers bunched together and only spoke on hover), and asked to be guided through the design choices, so the plan (Fable) offered three flows with wireframes: tabs with a summary strip, a guided one-screen-at-a-time story, or a dashboard of tiles. Austin picked tabs (ADR 0017), plus thin team-color accents, slate cards and the retro as a finished game's default tab.

**What changed.** Every page opens with up to five tiles that each state one thing and link to the tab that explains it; detail sits behind URL-synced tabs; ledes are one sentence and caveats collapse into one "fine print" per tab. Efficiency is drawn on the league's typical range (the 10th–90th percentile of teams' season-to-date values, added to the retro as schema v2), with the number printed at the row end. The slate became matchup cards with a compact dots-against-the-market strip and one computed sentence. Built by implementer agents in parallel (kit, contract, slate, tracker), with the game page in the main session to set the pattern; a reviewer pass found no blocking bugs and several misleading-wording cases, all fixed.

**Iteration.** Austin's first look: the tiles were the right idea with the wrong content (they restated numbers). The second version answers questions instead: upset or not, how many approaches were right, did the play match the result, which way the swing plays went, the biggest surprise against a team's season; before kickoff, the pick, how it sits against the market, the approaches' split, the biggest factor, the key absence. Near a coin flip, tiles say "toss-up" rather than "upset".

**The audit.** Austin noticed JAX @ BAL showing Baltimore favored after the Ravens' QB news. That was stale local data (the dev server read the laptop's Oct 27 odds; production had JAX −9.5), but it prompted a scripted cross-check of every published number: market internals, slate vs game files, every retro's grading against its result, every recap against its retros, the tracker. Most of it lined up exactly. It found three real production bugs:
- *Week 8 missing from the tracker.* It was played after the Oct 27 backfill and before the first locks, so nothing stored existed to grade; Week 7 also lacked market/Elo/naive rows for 13 games. The weekly refresh now scores finished games that have no prediction, append-only (PR #2). `predict --backfill` was not usable: for one season it would have deleted every other season's backfill rows.
- *The market consensus near even money.* Books were combined with a median of American odds, which jump from −100 to +100: +105 and −104 gave +0.5, a 99.5% favorite, so CAR @ NO showed NO 65% while every book had CAR favored. Now taken in decimal odds (PR #3), two days before the first public lock.
- *An Elo leak when scoring after the fact.* Elo replayed every finished game, including the one being scored, so pregame rows and retros showed an Elo that knew the result (ARI @ DAL: DAL 62% instead of 69%). Live locks were never affected (PR #3).

**Lesson.** Unit tests checked each computation against itself; only a cross-check of the published output against the books and against the other published files found these. The audit script is worth keeping as a CI or post-publish check.

## 2026-11-04: a living state of the project, kept by the chats (docs/state.md)

**Why.** Several chats work on the repo at once, each writing plans and notes, and Austin couldn't tell which file was current, where things were, or what the other chats were doing. The journal was the one doc that stayed true because it is append-only. The previous standard (a markdown note per decision, linked in chat) produced 27 notes in `.notes/`, two of them snapshots of "the state" that were stale within a week, and a CLAUDE.md status paragraph frozen on 2026-10-27.

**What changed.** One committed hub, `docs/state.md`: bottom line, what runs where (one schedule table across the cloud, the desktop and GitHub, with console links), workstreams, milestones, open decisions with what closed them, known issues, and a docs map with verified dates. Every doc now has one job and a status line; the tasks.md progress table is frozen; `.notes/ui-direction.md` became the design-language section of `docs/site.md`; 20 notes moved to `.notes/archive/`. A live board, `.notes/board.md`, uncommitted so every worktree sees the same file instantly, says who is working on what and which areas are claimed. Maintenance is automatic at boundaries (`docs/state-maintenance.md`): a SessionStart hook injects the hub, the board, the journal tail and `scripts/state_check.py`'s findings into every chat; a PreToolUse hook blocks `gh pr create` and `git push` on a branch that changes code without a journal or hub change, or when the hub is inconsistent; CI's `docs` job applies the same rule. The check is mechanical only: links, the schedule table against `infra/jobs.tf` and `PASSES`, workstream and board rows against `git worktree list` and open PRs, docs-map dates against each doc's status line and git log.

**Decisions.** No weekly audit and nothing Austin runs by hand (Austin asked for it to happen as work happens). The board stays uncommitted: one laptop, several chats; a knowledge-base tool can replace it later (hub decision D3). Branch and worktree cleanup after a merge needs no asking (CLAUDE.md, earlier the same day).

**Lesson.** The journal survived because appending is cheap and never conflicts; the hub copies that (each chat edits only its rows) and adds a check so the facts that can drift silently (schedules, links, dates) can't.

## 2026-11-04 (later): the hooks must live where the session starts

**Finding.** After the hooks were registered in the repo's `.claude/settings.json`, a reloaded session showed no injected state. Claude Code reads project settings from the folder the session starts in, and Austin's VS Code workspace is `~/dev`, the parent of every checkout, so the repo's settings never applied. The nested CLAUDE.md and skills do load for files under the repo; hooks don't.

**What changed.** The same two hooks are also registered in `~/dev/.claude/settings.json` (`scripts/hooks/dev-folder-settings.json`, absolute paths to the primary checkout's scripts). The scripts now find the checkout from the session's `cwd` in the hook's stdin JSON (and a leading `cd <dir> &&` in the command for the PR guard), so they work for every worktree; a session with no checkout in its cwd gets main's copy from `~/dev/nfl-project` with a note saying so.

**Addendum.** A resumed session after the `~/dev` registration still showed nothing, and there was no way to tell whether the hook ran at all. Each hook now appends one line to `~/.claude/nfl-hooks.log` (time, script, cwd, project dir), so the question has an answer. The log then showed the real cause at once: the scripts were committed without the executable bit (`core.fileMode` is false in this repo, so git never recorded the `chmod`), so every run ended with exit 126, permission denied, and Claude Code dropped the empty output. Fixed by storing the bit in git and by invoking the scripts through `bash` in both settings files, so the mode can never matter again.

## 2026-11-04 (later): the desktop is set up and locks go live (PRs #5, #6)

**Why.** Austin got to the desktop and asked for the setup steps in a form they could follow there, then decided to start locks in Week 9 without the planned shadow week: "even if it's not perfect", the first live weekend is where the problems will show.

**What changed.** Austin ran a one-time checklist on the desktop: uv, the repo, `.env`, gcloud, and the Task Scheduler task `nfl-narrative` (Wed 5:00 PM and Sat 6:00 AM Central). Its environment test reached Cloud Logging at 16:34 UTC. PR #5 stored the executable bit on `scripts/desktop-narrative.sh` and fixed the runbook's setup. PR #6 set `locks_paused = false`; the plan changed only the two lock schedules, and both are ENABLED.

**Findings.** The script had been committed as 100644, so the runbook's task, which ran it by path, would have failed with "Permission denied" on its first real run. The checklist ran it through `bash`, and the task on the desktop does too. A cloud dry run of the Thursday lock passed on 2026-11-04 (execution `nfl-lock-thu-5mqhw`). JAX @ BAL's market number looked wrong at 19% for the home team but is right: the books had JAX -10 and BAL +400. The hooks PRs changed `scripts/` after that run; the deployed image was rebuilt from `0fe3ddc`, and job code hasn't changed since, so the lock's image check still passes. Three small things went to the hub's known issues: README CI digits that move between runs despite a seeded RNG, a flaky Build page test, and gcsfuse write errors in a job that still succeeded.

**Lesson.** This is the same missing executable bit that silently stopped the hooks. Scheduled entry points should be called through their interpreter, so the file mode can't matter. Dry runs don't cover the last step: Thursday's lock is the first real push from the cloud.

## 2026-11-04: upcoming games priced last week's quarterback (`qb-charted-starter`)

**Why.** Austin asked why the Sharp sat so far from the other approaches in JAX @ BAL, with Baltimore down to its backups. Checking that showed the quarterback group netting to zero in every approach: the "new starter" penalty was cancelled by stats rating Baltimore's quarterback above Trevor Lawrence.

**What was wrong.** For a game without plays, `strength.qb_epa` and `strength.qb_cpoe` used the starter of the team's previous game. Lamar Jackson started Week 8 (one dropback before leaving), so Week 9 priced Baltimore on his career while the depth chart had Tyler Huntley, and `availability.qb_change` flagged a new starter on top of the wrong stats. My first diagnosis, a composite collapsing on null stats, was wrong; the published values were real numbers for the wrong player.

**What changed.** Upcoming games take the depth chart's QB1 as of the build (`availability.charted_qb1`), then the previous starter. A played game always keeps its actual first passer. `strength` VERSION 3.

**Findings.** Old and new logic on identical data, all 7,548 games 1999-2026: 0 differences in played games, so no fit, backtest or grade moves. Only Baltimore and Arizona change, from Week 9 on. Dry-run Week 9 locks on a copy of production: 2 of 15 games moved. JAX @ BAL home win chance (market 19.1%): Traditionalist 31.1 to 28.6, Analyst 38.1 to 32.4, Student 35.2 to 30.5, Sharp 17.4 to 13.1. Baltimore's QB EPA goes from 0.100 to -0.116 and CPOE from +1.50 to -0.66.

**Lesson.** Comparing feature files needs a noise baseline: two identical runs differed in 30,765 rows at exact equality and in none at 1e-9, and joining live rows without `known_as_of` crosses snapshots.

## 2026-11-04: the ensemble leaves the site, the Student is the headline (U1)

**Why.** D5: the Student stays as the public line and the ensemble becomes a diagnostic. The backend can't stop locking the ensemble until the site no longer needs it (H1 in `.notes/ui-round2.md` §8).

**What changed.** Web only, so it can merge during a lock window. `web/src/data/hideEnsemble.ts` runs in the zod contract on the slate, game, retro, recap and tracker files, so no page sees the ensemble whether or not the data has it. `HEADLINE` in `lib/models.ts` names the Student, and the pick tile, vs-the-market tile, biggest factor, recap's picks right and the tracker's tiles read it. `gameStatus` no longer falls back to the first key of `models`: Student, the other approaches, then the references. The tracker's headline sentence moves from the Analyst to the Student.

**Findings.** Retros and recaps are ranked with the ensemble in them: in the dev copy it is the best read of 1 retro of 121 and none of the 8 recaps, so the filter hands the flag to the best approach and closes the ranks. "Most misread" in the recap is built on the ensemble in `retro/week.py`, and its sentences say so, so those rows are hidden until the retro rebuild moves them to the Student. That is a job-code change that needs a schema bump to reach weeks 1 to 8 (only stale weeks are rewritten), so it goes with U3 rather than in a PR that would be blocked by tonight's lock window.

**Lesson.** A display rule that has to hold across every page belongs at the data boundary: 13 routes rendered against the dev copy with no mention of it, and rendered again from a copy with the ensemble deleted from the files.

## 2026-11-04: model wave 2 (M11, ADR 0018), before the first public lock

**Why.** Austin's first week with the live site: scheme and coaching moved predictions with no evidence, one line move swung the Sharp 24 points, and the ensemble and the Student were hard to tell apart.

**What changed.** `coaching`, `off_scheme`, `def_scheme` and `matchups` are context-only: shown, never weighted, and the schema refuses them. Line moves are capped at ±4.5 points inside the model; the stored feature stays raw. The Student and the Analyst read line moves at half the Sharp's weight, declared rather than learned, because the feature exists live only. Special teams is a group (overall, kicking, punt unit, kickoff unit). Pressure rate moved to Defense. The ensemble stops locking and its backfill rows go; `fill_unscored` now keys on the Student.

**Findings.** Backtest 2005-2026, 5,804 games, log loss: Analyst 0.6278 to 0.6250, Student 0.6256 to 0.6247, Traditionalist 0.6303 to 0.6294, Sharp unchanged at 0.6288, market 0.6095. Nothing got worse and nothing got near the market. Line moves barely appear in that backtest because they exist only for recent weeks, so it says nothing about the cap. The retired ensemble was 0.6239, so the Student as headline gives up 0.0008. JAX @ BAL (market 19.1%): Sharp 13.1 to 24.2, Student 30.5 to 26.3, Analyst 32.4 to 28.8, Traditionalist 28.6 to 28.0.

The 13 coaching and scheme features with no hypotheses row were never built, and neither was any matchup feature, so those groups carried weight on nothing. Special teams came out weaker once split: the overall feature falls from "matters" (+0.033) to "weak" (+0.023) because its parts share its credit; kickoff unit +0.028 weak, punt unit +0.015 weak, kicking -0.004 no evidence.

**Lesson.** Scale a live-only feature from what it does, not from a guess: the declared SD of 1.5 was fine for a normal week and useless for the one game that mattered.

**Cutover (evening of 2026-11-04).** Austin moved it up from Week 10 to before the first public lock, because production had no live rows: the whole public record starts on this model and the ensemble never locked. U1 merged first, PR #12 followed, and the marts went up. The first `nfl-site` run failed on a config-hash mismatch for the Analyst: 28 of the 308 fit files in the bucket were still their October versions after the upload. The cause isn't established. Their sizes all differed, so rsync had no reason to skip them; the upload's output was piped into `grep -c`, which hid any errors and its exit status, and the network dropped at least once around then, so failed copies are the likely explanation. An MD5 comparison of every file found them, they were copied individually, and all 308 fits were then checked by checksum. Then the site job and a cloud dry-run lock passed on `2bdcf05`. The hash guard did its job: it refused to publish mixed weights. Nothing wrong reached the public site. The runbook now requires reading the upload's exit status and a second pass that must find nothing to copy.

## 2026-11-04: the game page leads with the game (U2)

**Why.** Austin's feedback F2 to F4: everything above the fold was the approaches, the tale of the tape gave no way to tell whether a gap was big, and Tendencies was buried. D4 scales the bars by the Global fit.

**What changed.** Tabs are now Preview, Approaches, Tendencies, Details, Injuries & news, with What happened still first on finished games. Preview (`pages/game/Preview.tsx`) is one bar per group sized by the Global fit, with the edge percentile under each name and a picker that outlines one approach on the same rows. Selecting the Sharp adds a chip with the raw line move. Details draws both teams on the league's band (`charts/MatchupBand.tsx`), with right always the better side. Gaps wider than the league's interquartile range stand out and the rest are muted. `site.py` adds `feature_bands` to `meta.json`: additive, and older files fall back to plain tables. The approaches tile left the pregame strip. Coaching and the scheme groups are out of the bars, the edge list and the Biggest edge tile through one helper, `isContextOnly`, until `context_only` ships from wave 2.

**Findings.** One scale for every overlay, the rule on the Approaches tab, doesn't work here: the Sharp's −23 market row flattened every other bar to slivers on a phone, so the scale fits what's on screen. JAX @ BAL's "Who's better" reads 7 of 22 gaps standing out. Bands are one per feature for the season, on today's league, so an old game sits on the current range; that's display only, and the fine print says so. The hub's flaky Build test was never about Build: under full CPU load, whole page suites failed at random (41 tests in one run) because `findBy*`'s 1 second default raced the lazily loaded routes. Raising it to 5 seconds exposed vitest's own 5 second test limit, now 15. After that, 775 tests passed in three runs under 16 busy loops on 12 cores.

**Lesson.** Regenerating fixtures from the dev copy broke the tests that need Week 8 to be pregame, so `scripts/web_fixtures.py` depends on the week it runs in; `feature_bands` went into `fixtures/site/meta.json` by hand. Screenshots from a headless browser found five problems in a page whose tests all passed.

## 2026-11-04 (later): team colors, and some color for the site (U2, Austin's first look)

**Why.** Austin liked the structure and had four notes. A push toward the left team read as a negative. Red and blue made him check the legend for who was who, and the overlay outlines changed color for no reason he could see. The range bars didn't show where teams bunch up, and the hover was a plain text box. And the whole site felt bland in dark mode.

**What changed.** Pushes are always a plus, with position or a team code saying whose they are. On a game, color now means the team: `lib/teamColors.ts` fits each brand color to each theme and picks a pair per matchup, running through the bars, dots, a banner wash, tile edges and slate cards. Overlays are one neutral outline. `feature_bands` gains the quartiles and median, so the band is faint from p10 to p90 and solid over the middle half. `useChartTip` is a real hover card on Details, Preview and Tendencies. Surfaces take a slight cool tint, with one brand gradient under the header. ADR 0017 is amended: team colors were a thin accent only.

**Findings.** Brand colors fail as marks: Ravens purple and Bears navy vanish on a dark page, and four teams share `#002244`. Of 992 matchups, fitting alone left 86 failures under red-green colorblind simulation and two Saints games that nothing could separate, until the pair picker scored colorblind distance too and the Saints and Raiders got an ink neutral. JAX @ BAL first came out as Jacksonville gold: teal and purple sit at one lightness. Splitting them by a lightness step before reaching for a secondary color kept both teams recognizable; that needed the target at 18 rather than 20, still above the hard floor of 15.

**Lesson.** Red-and-blue was a default nobody chose. Asking what a color means on each page separated what should become a team (toward JAX) from what shouldn't (helped, hurt, better than the market).

## 2026-11-04 (later): the retro leads with the game (U3)

**Why.** Austin's F10: make the retro game-first, explain "played like", untangle the swing tile ("GB +12.4" next to "pure luck about even"), and read one team's miss as the other's gain.

**What changed.** Tiles run result, played like, swing plays, biggest surprise, approaches right, and headlines no longer mention approaches. `PlayedLike` gains the inputs (`home_epa`, `away_epa`, `home_success`, `away_success`, `p_base`): additive, with retro schema 3 so the daily job rebuilds everything, which also moves "Most misread" to the Student for weeks 1 to 8. Swing plays become one bar per factor, home's swing minus away's, split into Variance and Pure luck on one scale. The swing tile's sub-line gives the two parts that add up to the headline. Global is off the retro and recap tables. `RangeRow` gets the hover card, and the `context_only` fallback is gone now that production has the field.

**Findings.** The plan said played-like uses EPA and success rate. It doesn't: `expectations.py` fits EPA alone, because success rate correlates 0.74 with EPA and its coefficient turns negative once EPA is in, so the page calls EPA what decides it and success rate context. On real data CAR @ GB checks by hand: home start 59.1%, EPA gap 0.251, 93.1%. Two bugs showed up only on real records in a browser: Packers green rendered gray, because its chroma sat under the threshold for a neutral (a U2 bug), and the Variance and Pure luck charts scaled separately, so 2.5 points looked longer than 11.9.

**Phase by phase.** Austin found EPA alone limiting, so 14 other measures were tested on about 2,760 games from 2015 to 2025 (`.notes/ui/played-like-factors.md`). EPA already contains most of them: success rate, explosive plays, sacks, red zone and third downs each add under 0.01 log loss. Field position looked strong but is mostly turnovers (correlation −0.50). Filtering to plays while the game was in doubt gave the biggest gain, but it selects on the score, and a first-three-quarters filter did worse than all plays. So the verdict stays as it is and a descriptive scorecard goes beside it: the `phases` field, on the same schema bump. On real data, the team that won more phases won the game 97 of 107 times.

**Lesson.** A plan describing code is a claim to check before building on it. The dev copy needed production's wave 2 fits before `nfl retro build` would run, and that guard did its job. Real records also caught what unit tests couldn't: "9 of 16" third downs against the headline's 9 of 14, and a special-teams number that charged field goals to both teams. New rows should read the record's existing counts and definitions rather than recompute them.

## 2026-11-05: the first desktop pass failed twice, so search became the last resort (narrative-sources)

**Why.** The first scheduled pass stopped at `git pull` on a local edit in the desktop clone. The rerun stored 8 of 15 games, then failed the other 7 in about 20 seconds. Austin asked how to fix the cause, not just space calls out.

**What changed.** Injuries and team news come from RSS feeds and weather from Open-Meteo (`src/nfl/llm/feeds.py`). Tavily is the first search backend when `TAVILY_API_KEY` is set, with SearXNG as the fallback. Queries per game fell from 17 to 7, and 5 on Saturday with film results reused. Blocked engines are now a real error (`EnginesBlocked`): the pass waits and retries, up to 80 minutes, rather than writing thin records. Rerunning a pass skips games already stored. The failure email names each game and error. `scripts/desktop-narrative.sh` resets to `origin/main`, saving any local edit as a patch. ESPN's undocumented API was tested and left out because of its terms (ADR 0014 amendment).

**Findings.** SearXNG answers 200 with an empty list when its engines are blocked, so nothing flagged it. `qwen3:14b` was still loaded after the failure, which showed games 9 to 15 never reached the model. Reproducing it from the laptop gave 0 pages in 11 seconds, with Brave and Google CSE on "too many requests". Brave blocked after about 5 test queries over a few minutes, so spacing alone wouldn't have been enough. The desktop's own log wasn't available, so the 7 errors are inferred. In a live check, 29 of 30 teams had injury items in their feeds.

**Lesson.** A self-hosted metasearch has no quota, which also means no promise. Questions with a known home shouldn't go through search, and a status code of 200 doesn't mean a search worked.

## 2026-11-04 (later): slate cards lead with the game (U4)

**Why.** Austin's F1: the approaches strip is great, but the card says nothing about the game itself.

**What changed.** Each card now gives the line and total, a "why this game" line, a tendencies contrast when it's stark, then the approaches strip, smaller. Slate rows had no edges, injuries or tendencies, so `site.py` adds an additive `card` block, which makes this job code rather than the web-only change first assumed. Built by two implementer agents in parallel from one spec with a fixed contract, then checked on production data and reviewed by reviewer agents in three rounds. The third found that the first round's fix stopped working at kickoff.

**Findings.** Every line on a card is a public claim, and most of the problems were claims rather than crashes. Neither QB source is reliable alone: replayed days out, 2 of 6 schedule lines named the wrong player (Tyler Huntley days before Lamar Jackson started in Week 8), and depth charts three days out had 20 of 242 game-teams wrong, 2 of 5 lines. So the card needs both, says "listed" when they agree and "starter unclear" when they don't. In Week 9 they disagree for BAL, CLE, PHI and SEA; which is right isn't known. Neutral sites read as large edges for the nominal away team in Venue & weather and Rest & travel (9 of 9 in 2026; the cause wasn't traced through the composites), so `countsAsEdge` excludes them and the card names the stadium. "Usually" named stand-ins on one start or a tie, so it now needs three starts and a clear lead. Absences fired on 119 of 121 games and named backups and long snappers, so a card names only a charted starter, matched by player id, who wasn't Out or Doubtful at the team's last game: 140 of 550 rows in Weeks 1 to 8. That check compares game to game, because two calendar weeks would have hidden Lamar Jackson, out in Week 7 and back in Week 8. Temperature and wind are empty for all of 2026, so the weather note rests on the narrative's score. `blitz_rate` and `pass_rushers_5plus_rate` correlate 0.99998 in 2026 against about 0.9 before, so they count as one stat in the contrasts. Mutation testing was the reviewers' sharpest tool: 9 of 13 data mutants survived the first pass's tests, all of them green.

**Lesson.** Reviewers given real data and told to attack claims rather than code found what a spec-following build couldn't. The spec itself said "starts for". Season test timeouts also came back after the earlier fix: role queries over a 284-row table take about 2 seconds alone, so that file now has its own limit.

## 2026-11-04 (later): job code can merge almost anytime (U4)

**Why.** Austin asked why merges felt so restricted, with a lock most of a day away. The round 2 plan said no job-code merges from Wednesday evening until Thursday's lock, and every chat kept repeating it.

**Findings.** Nothing enforced that. `check_image_matches` in `scripts/cloud-job.sh` only refuses a lock when the image is behind `main` at run time, and an image builds in 3 to 4 minutes, so the rule was about 10 hours wider than the mechanism. A refused lock emails and reruns safely, with 11 hours to spare on Thursday.

**What changed.** The rule is now the real one, in `docs/runbook.md` and the hub: merge job code anytime except the last 10 minutes before a lock. Dry-runs are for risky changes, not every merge. Model changes still ship with their refit, because the lock checks each fit against its config. A backup lock run is open as D9.

**Lesson.** Check what a process rule enforces before repeating it. A cautious line in a plan turned into a freeze because nobody tested it against the code.

## 2026-11-05: first pass on feeds and first public lock (#15)

**Why.** Confirm the merged source changes on a real desktop pass before Saturday, and that the Thursday lock ran.

**What changed.** Nothing in code. The desktop stored the 7 games the 2026-11-04 run lost, the 08:30 check passed, and `nfl-lock-thu` committed `lock: 2026 W09 thu` (`c8d8103`, JAX @ BAL) from the cloud at 14:07Z.

**Findings.** 15 of 15 records in the bucket at 06:32Z. All 7 new records used the 4 feed pools and 7 queries; 5 outdoor games also used the forecast. All 7 reached 30 claims from 10 to 14 pages, and team sites and NBC Sports rose among the cited sources, with 15 claims citing Open-Meteo. Games took 26.5 minutes on average (n=7), against about 16 for the four cleanest gaps of the search-only pass. Timing 8 feed pages from one game on the desktop gave about 32 seconds a page and 10 facts, against 21 seconds and about 7 facts in Week 8; at 25 pages against 20 that is about 6 of the 10 extra minutes. Tavily's dashboard showed 51 credits used, so it served the 49 queries. The two `pass started` entries were a manual start, Ctrl+C, and a second start. Quality against the search-only records is not compared yet.

**Lesson.** Resuming worked, but a resume keeps thin records: LA @ WAS stayed at 14 claims until the next pass. Pass length now matters on Saturdays, when the check runs 4.5 hours after the start and uploads come last.

## 2026-11-05: two future plans for narrative research (M6.6, M6.7)

**Why.** Austin asked why the research is a fixed pipeline, and what would make it smarter.

**What changed.** Parked two plans in `docs/tasks.md`, with decision D3 in the hub: one follow-up search per game in the local pipeline (M6.6), or a hosted free-roaming agent on API credits (M6.7), which would need the no-paid-API rule reversed. Nothing built.

**Findings.** A throwaway prompt on 2 Week 8 games proposed 4 distinct follow-up queries: 2 useful, 2 weak status checks, with real citations and the same output on a second run. No searches were run, so whether they find anything is unknown. Credits: one follow-up per game fits (about 885 of 1,000 a month), two don't.

**Lesson.** ADR 0014 ruled out an agent on the 9B by reasoning, not by test; the only agent comparison is the Claude skill, which also uses a far larger model.

## 2026-11-05: the tracker says which way is good (U5, M12)

**Why.** Austin's F5, F7 and F8: too much overlap, a season chart that didn't say which direction was good, bland tabs, a scoring rule the site never explained, and History opening on its hardest view.

**What changed.** The season chart plots each line's gap to the market, with a too-close-to-call band. Tabs go from five to four: log loss by season and disagreements move to Backtest, which is the period they cover, and disagreements becomes one table. The recap names the week's best call and costliest miss, and says the score pays for confidence both ways (retro schema 4). History opens on Over time. References read as dashed rings in tables and toggles. `hideEnsemble.ts` is gone, and test fixtures no longer carry ensemble rows. Planned on Fable as M12, built by three implementer agents in parallel, then integrated and reviewed.

**Findings.** Checking the plan against production changed it. Bold calls per approach would have been four copies of one line: in Week 8 all four share the same best and worst call, so they're per week. The market and every line score the same games, so a gap is a fair comparison, but gaps are ±0.03 and move week to week, so the noise band is required. After wave 2 the Student sits about even with the market after 120 backfilled games, and the Traditionalist leads by 0.006. A paired bootstrap puts every line's 90% range across zero, about ±0.025 wide, so the chart's band is that wide rather than the 0.005 first planned: at ±0.005 the Traditionalist sat in the green, contradicting this paragraph. A list built from whatever the file holds showed `ensemble` on a dev rebuild from stale marts, so those lists now filter with `isPublicLine`.

**A record bug found in review.** `predict()` skipped only games with a backfill row, so Tuesday's refresh would have added a backfill row for every game with a live reference lock, and `graded_frame` kept the latest row. Thursday's locked market, Elo and home-baseline rows would have stopped counting as live, and the append-only file would have kept the extra rows. Approaches were safe only because `fill_unscored` is keyed on the Student. Fixed before the first refresh: `predict()` skips any game already holding a row for that model, and `graded_frame` prefers a live lock, the rule `site.best_rows` already had.

**Paper bets.** The tab was one table, so Austin asked for visuals, and the backtest didn't need to wait for live bets: it has 21 seasons. It now leads with a verdict, then a bankroll curve, return per bet with a range, and a season grid, all read against what the same bets return with no edge. Every approach is down and none has beaten no edge by more than the noise. Building it turned up three things. The table's CLV averaged spread points with probability points over nine bets, which is how the Analyst showed +5.95%, so CLV is now live moneyline only. The tab called every bet a moneyline bet, and over a fifth of the approaches' bets are spreads. And the cut in our price data jumps from under 3% to about 4% on the moneyline and 4.5% on spreads in 2023, so older seasons are easier on every line; the page says so.

**Lesson.** A plan's line such as "per approach" is a guess until it meets real rows, and five minutes with the data beats building it.


## 2026-11-05: site walk fixes, all of review §10 (M13)

**Why.** Four simulated test users walked the site and left 9 bugs and 18 small changes (`.notes/project-review-2026-11.md` §10). Austin asked for all of them, plus a last-week line on the slate.

**What changed.** Preview Elo replays every season (`site.py`), as the lock does. Every "?" works on touch and stays on screen. The tracker has one too-close-to-call threshold, 0.025, so the Best approach tile no longer crowns a winner inside the noise. Slate cards name the Student's pick, the home page says what the site is, the slate shows last week's record, and the Disagreement sort is now Gap to market. The Sharp's negative shares are drawn. Retro swing sentences are rewritten, so `SCHEMA_VERSION` is 5. The rest is copy: periods, units, labels, page titles, a nav fade, and History renamed Evidence in the nav.

**Findings.** Replaying Week 9 on real data, all 15 previews differed from the full-history Elo by at least 0.5 points, up to 14.8 (ARI @ SEA 68% against 83%). Display only: locks and grades already used full history. Two bugs were hiding behind others. The Sharp's budget looked short because `sortedShares` dropped negatives, not because of the way shares are counted. And once a tap opened the "?", the tip ran off the left edge of a phone (left −126 on a 390-wide screen), which no test user could have seen, so tips are now fixed to the screen. Paper bets start in 2006 because prices do: none of 2005's 267 games has one.

**Review.** It caught claims the plan itself had wrong. A schedule line's `as_of` is a synthetic stamp, so printing it as a market time was false on 108 finished games; only snapshots print a time now. "Models trained only on earlier seasons" overclaimed: Elo updates game by game, and a few settings were chosen on 2022-24 and apply to every season. "Hurt both teams" was false on 2 games with a team at exactly 0.0. A re-walk by two personas found that the new last-week line read like a live record, when Week 8 was backfill, and that `hover:no-underline` had never worked, because unlayered `a:hover` beats every Tailwind layer.

**Lesson.** Rebuilding `.data-prod` with local marts mixes stale predictions into production files. Check code changes on the rebuild, then sync back from the bucket before anyone walks the site. And copy written into a plan is a claim like any other: check it against the data the same way.


## 2026-11-05: two flights planned: the league page (M14) and the retro's win-probability chart (M15)

**Why.** After the project review, Austin picked six ideas for a deeper look. Six research agents, one per idea, each read the code and measured the data, and wrote a plan in `.notes/plans/`. Austin then chose the two flights to start: a league page with team charts and the playoff picture, and the retro's win-probability chart with a motion pass, drives and a story layout. Planned on Fable as ADR 0019 and ADR 0020, tasks M14 and M15, two chats in parallel.

**What changed.** ADR 0019 settles the league page: the real tiebreak procedure through strength of schedule (D9 closed), a calibrated team-strength shock in the simulation, Student and market variants side by side, playoffs through the Super Bowl, append-only snapshots from launch, and the team scatter as the Teams tab of `/league` rather than its own page. ADR 0020 settles the retro chart on nflfastR's spread-adjusted win probability, "Turning points" as the name for the chart's marked plays, and a motion policy: CSS through tokens, zeroed under reduced motion, no animation library. The boldness view is parked.

**Findings.** The research changed the review's advice in three places. Team-level splits against the blitz, play action and box count do not repeat year to year (split-half and year-to-year r about 0), so the interaction features stay a context view with model work gated on a one-day spike. A gradient-boosted model fit on the same matrix loses to the Student by 0.0033 log loss (worse in 15 of 22 seasons) and a "Student plus trees" variant ties, so no learned line is built now; a shadow season could not even detect a gap that size. And `feature_bands` took each team's last-kickoff row, a Week 18 pregame row, so six rate features and every per-game feature showed stale values on the game page; phase 1 of M14 fixes it. Smaller facts worth keeping: `curated/plays` drops `vegas_home_wp`, whose first value is 1.9 points from the site's market on average where plain `wp` is 13.9 off; a scratch tiebreak engine reproduced 48 of 48 conference-seasons' real seeds since 2002, and no real tie went past strength of victory; the repo has no division or conference map anywhere; the Student is not Platt-calibrated (its calibration is the identity), contrary to the review's wording; `.data-prod` in the UI worktree was stale, so the Student experiment ran on the wave 2 snapshot.

**Lesson.** A research agent that must measure before it recommends can overturn a confident plan in an afternoon, and the overturned items (interactions, a learned Student) were the two the review had called the offseason's main projects. Plan the measurement first and the milestone after.

## 2026-11-05: the retro shows how the game unfolded, and the site starts to move (M15 phase 1)

**Why.** The retro is the site's best idea and read as text and tables, and nothing on the site moved. ADR 0020 settled the shape; this built it in one evening: M15.1 in the main chat, four implementer agents in parallel, then real data, a review and a site walk.

**What changed.** Seven more play columns are curated, and the retro carries `wp_series` and `drives` at schema 6. `WpChart` opens the retro tab under the headlines, with numbered turning points and a text list. Kit motion runs from CSS tokens that reduced motion zeroes: the curve draws, dots slide from the market, bars grow, a tile's panel scrolls in and flashes. `ProbStrip` and `DotWhisker` lost `<title>` for tips that work on touch. The game page, slate and tracker load as their own shape.

**Findings.** Three things the plan had wrong or missed, all found by looking at real data. `play_id` isn't game order around timeouts: an icing timeout sorts after the kick and repeats the old probability, which would have bounced the curve at the end of every close game; taking only rows with a non-zero wpa leaves one 2.6-point break in 19,449 rows. The task's elapsed-time formula was wrong (`game_seconds_remaining` counts the whole game down). And marks at `p_after` would have floated off a curve drawn from pre-snap values, so the curve now holds post-play values. A rehearsal of the real `retro daily` path on a private root rebuilt 121 games in about a minute, with every existing field byte-equal to production's files, which is what proves the `_luck` refactor changed no number. The tile's scroll and flash passed every test and didn't work: the router applies a tab change as a transition, so the panel mounted after the retries ran out, and `ScrollRestoration` would have cancelled the scroll anyway. Only a browser showed it. Site walk: both personas named the chart as the page's best part; the hiring engineer called "falling to 2% in Q3" a contradiction, which was a misread, but it showed the sentence didn't say whose 2% it was, so the caption now says "its win chance" and the number sits on the chart. The swing tile against the headline bullet confused both personas and is still open: `.notes/site-walk/2026-11-05-5/report.md`.

**Lesson.** Tests that can't run the thing they describe pass quietly: jsdom ignores CSS and has no router timing, so anything about motion or scroll needs a browser check before it counts. And a plan's number is worth rechecking against the raw rows when a formula is about to be built on it.

## 2026-11-05: the League page's Teams tab (M14 phase 1)

**Why.** Austin wanted any two features on a chart of all 32 teams, as the first piece of a league page (ADR 0019). It ships first because it needs nothing new from the model, and it gives the page a shell for the playoff picture.

**What changed.** `/league` with a Teams tab: a hand-rolled SVG scatter, eight presets with corner captions, team colors with a division highlight, "Find a team", a team panel with every game, and a numbers table. `site/teams.json` holds every team's value, percentile and rank for 45 features (183 KB, 29 KB gzipped). `feature_bands` reads the same table, so the game page's bands stop using Week 18 pregame rows. `src/nfl/league/` starts with the division map. Built by three implementer agents against a contract and stubs committed first, then integrated.

**Findings.** The review caught what the plan had wrong. The plan said a team's season-to-date numbers are the same in every future row, which holds for most features and not for `form.epa_trend`: its window averages only the played games, so the row after next averages three. Picking "next game" from `now` then moved a team onto that row at kickoff, and on Sundays 28 teams changed by up to 0.203, one by 23 rank places, with no new data, because the odds snapshots rebuild the site between feature builds. "Next" now means next after the last feature build; a replay of Thursday against Monday moves 0 of 2,129 values. The auditor persona checked all 8 presets and found every rank, direction and caption consistent, and every shared number equal to the game page's.

**Team colors.** The plan chose conference colors because one color per team collides: 107 of 496 pairs on dark look alike and three are identical. Austin asked why not team colors anyway, and the answer was that the plan had only tried one color. A ring in each team's second color brings the look-alikes down to 21, and the rest share real colors and have labels.

**Lesson.** Anything keyed to the clock on a file rebuilt by several jobs has to ask which job's clock. A value should change when its inputs do, and a test that advances `now` with nothing else changed is cheap.

## 2026-11-05: who had the ball, and where it went (M15 phase 2)

**Why.** Phase 1 published the drives without drawing them. The curve says how the game swung; drives say what the teams did with the ball.

**What changed.** `PossessionStrip` runs under the curve on the same time axis, and "Drive by drive" draws every drive on one field: a bar from start to end and a glyph for how it ended. Web only. The time scale moved to `charts/wpScale.ts` so both charts read it.

**Findings.** A drive's `end_yl` is the last snap, so a touchdown stops a yard or more short of the goal line; the chart takes touchdowns to the line. Drive results reconcile with the final score in all 242 team-games of 2026 (touchdowns, field goals, defensive scores and safeties, with conversions the only gap), which is the check that says the data is tagged right. Field orientation is a choice: the away team always drives right, which isn't how teams switch ends in a real game, and the help text says so.

**Lesson.** When a new chart only redraws published data, a reconciliation against a number the reader already trusts, here the score, is worth more than more unit tests.

## 2026-11-05: the result stays on screen (M15 phase 3)

**Why.** With the curve and the drives in, a finished game's page runs several screens on a phone, and the result scrolls away with the summary strip.

**What changed.** ADR 0017 is amended first, as ADR 0020 required: the retro's order is written down, Drive by drive placed after the curve, and a finished game gets a pinned result. `Condensed` shows one line under the site header (the score, OT, the verdict) once the full strip has left through the top. The scroll-driven story stays rejected.

**Findings.** The reorder the plan expected was already done by building phases 1 and 2 in that order. The observer has to tell "left through the top" from "still below the fold", since neither is intersecting. Measuring the header at runtime keeps this free of the league track's `Layout.tsx`.

**Lesson.** A sticky element with no height is a cheap way to add a pinned line without moving anything: page height was identical with it on and off, which is the check that matters.

## 2026-11-05: the playoff picture: standings, simulated odds, leverage (M14 phase 2)

**Why.** The League page could compare teams but not say who is making the playoffs. Austin asked for playoff odds with game leverage, which needs real standings and tiebreakers, a simulation of the rest of the season, and honest inputs for it (ADR 0019).

**What changed.** `src/nfl/league/` gains `standings.py`, `tiebreak.py`, `simulate.py`, `inputs.py` and `build.py`, and `nfl league`. `site/league.json` is written last in every site build, in its own try/except; snapshots append only from the Tuesday refresh and real locks. `/league` gains a summary strip and the Playoff odds, Standings and Games that matter tabs, and slate cards get a stakes line. Built by five implementer agents on new files, against one signature fixed in their prompts, then integrated by hand.

**Findings.** The tiebreakers match the real qualifiers, byes and wild-card pairings in 48 of 48 conference-seasons from 2002 to 2025, with or without the points steps. A full build, 10,000 runs for each variant, takes about 6 s. σ = 0.4 improves the Student proxy by an amount too small to tell from noise, and Elo clearly: the Student proxy was already calibrated at the top. The biggest finding came from the first real file: a tile said the Student and the market differ most on TB, 58% to 23%. Eight of TB's nine games had no line, so that "market" was our own fit. Tested on the 29 real lines it hadn't seen, the fit misses by 6.9 points of win chance a game, and the Student by 5.8. The tile is gone and the Market view says how much of it is an estimate. Also caught: closing lines aged by the clock, so every rebuild would have jittered the odds.

A reviewer pass then checked the numbers independently (records, seeds and the simulation reproduced exactly; nothing can touch a lock) and found what the tests couldn't. Scores arrive up to a day after a game ends, so a finished game could headline the page; the page now keeps only games with a kickoff still ahead. Ratings for playoff games shrank to nothing by Week 18, because they fit remaining games only, and with one game left the home term became that game's logit; played games now anchor the fit. `through_week` moved on a Thursday score, which would have mislabelled Saturday snapshots for good. The σ comparison wasn't paired at 0; paired, the gain stops being significant even at the 12-game cut.

**Lesson.** A number with a source label is a claim about the source. Most of "market" was a model, and only holding out real lines showed it was no closer to the market than the thing it was compared with. And fixtures hide scale: 34 fixture games looked fine, 151 real ones ran past 20,000 pixels on a phone.

## 2026-11-06: context for the League page: similar seasons, compare, ranks (M14 phase 3)

**Why.** Odds say what a simulation expects. A fan also asks what happened to teams like this one, and how two teams compare on everything we publish (ADR 0019).

**What changed.** `src/nfl/league/similar.py` finds each team's nearest past team-seasons since 2002, aligned by games played, and `league.json` carries the ten nearest and a summary of 25. `/league` gains a Similar seasons tab. The Teams tab gains Compare (`?team=&vs=`, every published measure on the league band, grouped) and a sortable rank table. Playoff odds has a sparkline, hidden until two Tuesdays are in the mart.

**Findings.** Leave-one-season-out Brier 0.134 at k = 25 against 0.238 for the base rate. The current team's row had to come from `team_latest`: counting games from the clock would have brought back the Sunday drift phase 1 fixed, and all 192 rows match `teams.json` on game and value. All 30 neighbours checked for BUF, CHI and LAC match `curated/games`.

Austin's first look: it showed who was similar and not why. So the tab gained a finish grid, a chart of where a team and its 25 neighbours overlap on seven measures, and cards for red flags, things that look bad and weren't, and real strengths. The study behind the cards tested 32 measures among teams on the same record. Weak offense, expected win rate and QB play cost 5 to 6 points of playoff chance; a cold last three games, a streak and turnovers showed no penalty; and the strongest "looks bad" was a record that undersells the team (+7.1). A split-half check threw out EPA trend, which flipped sign, and the idea that rushing doesn't matter. Measuring the quarter against all of history gave BUF a "bottom-quarter defense" at 21st, because EPA levels drift; within each season the list held.

The last review recounted all 62 cards exactly and still found the page claiming more than the numbers did. Peers "within a win" made gaps that were mostly the record: CLE's −35 points was really −13. "Looks bad, wasn't" sat on counts that said it did, 4 of 46 against 14 of 99, because the tolerance was absolute. The Defense card used the friendliest of several defense measures; on the adjusted one the chart uses there's a mild penalty, so the card went, and with it a line saying the offense "earned" the record, which nothing measured. Effects fade or flip after 12 games, so cards stop there. 62 cards became 32, and every one now says what its counts say.

**Lesson.** Reusing the one function that already answers "which row is current" is worth more than a test that a second answer agrees with it. And an insight on a page is a claim: test it the way the sentence will read, on data it wasn't chosen on.

## 2026-11-06: Coaches and Build come off the live site for now (M16 parked)

**Why.** Austin wants both pages better before the public sees them again, and wanted them hidden, not removed.

**What changed.** `web/src/lib/hiddenPages.ts` lists them. On the live site they leave the nav, their URLs answer like pages that don't exist, and the League panel's "Scheme profile" and the Season page's "Back to Build your own" links go. `npm run dev` still shows everything, and the code, routes and data files all stay. M16 is parked until Austin picks it up: Coaches needs an accuracy and visuals pass, and Build comes back with the work that puts a custom approach on other pages.

**Findings.** Neither page had ever been in a site walk, and both date from before team colors, UI round 2 and wave 2. Build overflows by 14 px on a phone and runs 7,418 px tall; Coaches has no charts at all. `/season/:year` is only linked from Build, so it's orphaned while Build is hidden.

**Lesson.** A page nobody re-tests falls behind quietly while the rest of the site moves. Site walks need a goal that sends someone to every page.

## 2026-11-06: Staff spells and verification (M17.1, M17.2 and M17.3 partial, M17.5, M17.6 backend)

**Why.** Play-callers were the weakest column, and the one Austin cares most about: `coordinators.csv` was Wikipedia titles plus general knowledge, flattened to one row per team-season.

**What changed.** `data/staff_spells.csv` replaces it: one row per spell, with weeks, an evidence grade and a source. `load_coordinators()` is now a derived view (it reproduced all 352 old rows before any data changed). Research agents checked 2016–2026; `.notes/staff-verification/changes.md` lists each change. `staff_context.py` labels each unit (same caller, new QB, moved, first-time) and writes `site/team/<code>.json` through the site build, with expected values from `coach_blend.json`, which `scripts/coach_prior_study.py` generates.

**Findings.** The table had 55 of 64 current units with no play-caller, and three 2026 changes nobody had recorded: Wash replaced Evero at CAR (Week 9), Payton took Denver's calls back from Webb (Week 5), Ryans took Houston's defense from Burke (Week 5). "General knowledge" was wrong often: 2025 PHI (Patullo, not Sirianni), 2025 NYG (Kafka, not Daboll), 2025 SEA (Macdonald, not Durde). The study: a moved offensive caller's past clearly beats the team's last season on personnel, shotgun and time to throw, the team's wins on pass rate, moved defensive callers barely beat guessing, and first-time callers can't be predicted from the team's past. nflverse's schedule coach field is stale from 2024.

The table's head coaches now match the nflverse schedule on all 256 team-seasons through 2023, apart from one nflverse typo; that check is a test.

**Lesson.** My first spot check called HC, OC and DC "probably mostly fine", and I gave Austin a wrong count (23 of 64) and made-up ranks in a worked example (McDaniel's motion): an example in a plan reads as a measurement, so measure it or don't print a number. Research agents hit a shared search limit well short of their budgets, so a verification plan needs to ask how many lookups it can really make. A finding from a half-corrected table moved when the table was finished (time to throw): rerun before writing conclusions down. The review then caught what tests hadn't: "New here" on a head coach who'd been there for years, a name and a confirmation taken from different rows, and a public file with no evidence filter, which I'd just told Austin was harmless.

