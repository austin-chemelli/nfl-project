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
