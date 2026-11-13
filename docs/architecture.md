# Architecture

Status: current, verified 2026-11-13 for the Players section as built (M24.7 team health), the rest 2026-11-09 (§3.8 the candidates ledger live, ADR 0026; §3.9 matchups and paths to an upset, ADR 0028, planned); the live state is [state.md](state.md).

Planned 2026-10-26 after the local POC. Scope and goals: [PROJECT_BRIEF.md](PROJECT_BRIEF.md). Decisions and their reasons: [adr/](adr/). Work breakdown: [tasks.md](tasks.md). This file says what the system *is*; it does not repeat why.

## 1. Overview

A weekly NFL preview tool that is educational first and market-aware second. Every game is predicted by several **approaches**: personas (the Traditionalist, the Analyst, the Sharp, later the Matchup and the Narrative) that weigh the *same* shared features differently, the way different kinds of fans do. Each approach has two flavors: **persona** weights (hand-reviewed, the character) and **fitted** weights (regression shrunk toward the persona, walk-forward on history). An **ensemble** averages the fitted flavors. Every approach is scored publicly against the market and a naive baseline on forecast quality, on odds-weighted paper bets, and on how often it was right when it disagreed with the market. A **Hypotheses** page shows what history says about each feature. An LLM extracts the week's narrative into structured, cited features (live only) and writes previews whose numbers are checked against the data.

Principles (from the brief, unchanged): the LLM stays out of the numeric core; point-in-time correctness everywhere; ship live early; be honest about limits.

## 2. Components

```mermaid
%%{init: {'themeVariables': {'signalColor': '#999', 'signalTextColor': '#999', 'lineColor': '#999'}}}%%
flowchart LR
    subgraph src[Sources]
        NV[nflverse parquet<br/>incl. player tables]
        OA[The Odds API]
        OM[Open-Meteo]
        WEB[Public web]
    end
    subgraph data[Data platform]
        RAW[raw/ snapshots]
        CUR[curated/ tables]
        FS[(feature store)]
    end
    subgraph num[Numeric core]
        AP[approaches<br/>persona + fitted]
        ENS[ensemble]
        PRED[(predictions<br/>append-only)]
        LED[(bets + CLV)]
        SC[scorecards<br/>hypotheses]
    end
    subgraph llm[LLM layer]
        NAR[narrative extraction]
        PRE[preview text]
        FC{faithfulness check}
    end
    subgraph pub[Publish]
        JSON[marts/site/*.json]
        LOCK[public/predictions/<br/>JSON + sha256 in git]
        UI[Streamlit P1 /<br/>React P2]
    end
    NV & OA & OM --> RAW --> CUR --> FS
    WEB --> NAR --> FS
    FS --> AP --> ENS --> PRED
    OA --> LED
    PRED --> LED & SC
    FS & PRED --> PRE --> FC --> JSON
    PRED & LED & SC --> JSON --> UI
    PRED --> LOCK
```

| Component | Module(s) | Responsibility |
|---|---|---|
| Ingest | `nfl/ingest.py`, `nfl/odds.py`, `nfl/weather.py` | Download upstream bytes into immutable snapshots with manifests. nflverse by URL; Odds API JSON; Open-Meteo JSON. |
| Curate | `nfl/curate.py` | DuckDB builds `games`, `plays` (pbp ⋈ FTN), `injuries`, `depth_charts`, `lines`, `weather` from the latest snapshots. Deterministic. |
| Catalog | `nfl/catalog.py` | One DuckDB view per table (curated, features, marts as one file or parts) plus `features_asof(ts)` and `game_vectors(ts)`, built per process, never written; `nfl sql` (ADR 0025). |
| Audit | `nfl/audit.py` | Null rates per column per season; freshness per dataset. |
| Tendencies | `nfl/tendencies.py` | Team × situation × metric rates with shrinkage and recency decay. Feeds features and the game page. |
| Feature store | `nfl/features/` | One long as-of table of every input any approach uses. Builders per family. |
| Approaches | `nfl/approaches/` | YAML configs, scoring engine, walk-forward fitting, calibration, ensemble, per-feature contributions. |
| Reference models | `nfl/models/` | `market`, `elo`, `naive` stay as scorecard reference lines and as feature sources. |
| Lock | `nfl/lock.py` | Live prediction run at a lock point; writes prediction rows and the public JSON + hash. |
| Grade and ledger | `nfl/grade.py`, `nfl/ledger.py` | Scores predictions, settles paper bets, computes CLV and divergence buckets. |
| Retrospective | `nfl/retro/` | Post-game: efficiency vs season to date, luck factors priced in points against league expectations, predictions graded per game, group attribution (ADR 0016). Daily job. |
| League | `nfl/league/` | Division map, standings and the real tiebreak procedure, Monte Carlo playoff odds with a team-strength shock, game leverage, similar seasons, the per-team feature table (`teams.json`, also the source of the game page's bands). Built inside every site build; snapshots on refresh and lock (ADR 0019). |
| Hypotheses | `nfl/hypotheses.py` | Per-feature coefficients, CIs, verdicts from the global fit. |
| LLM | `nfl/llm/` | Narrative extraction, preview text, faithfulness check, call log. Separate entrypoints, versioned prompts. |
| Site | `nfl/site.py` | Writes the JSON contract the UI reads. |
| UI | `nfl/ui/app.py` (P1), `web/` (P2) | Streamlit explorer, then React + TS static site. |
| CLI | `nfl/cli.py` | Every job is a subcommand; the container runs the same commands everywhere. |

## 3. Data model

### 3.1 Storage layers (unchanged from the POC)

One data root, `NFL_DATA_ROOT`, always a filesystem path (local `./data`, GCS via Cloud Storage FUSE in P2).

```
raw/<source>/<dataset>/snapshot_ts=<ts>/ + manifest.json   immutable upstream bytes
curated/<table>/season=YYYY/                                rebuildable from raw
marts/                                                      features, fits, predictions, bets, scorecards, llm_calls, site/
```

Git holds code, prompts, approach configs, `public/predictions/` lock artifacts, and `docs/`. Never parquet.

### 3.2 Curated tables

| Table | Grain | Key columns |
|---|---|---|
| `games` | game | `game_id, season, week, game_type, kickoff_utc, home_team, away_team, location, roof, surface, spread_line, total_line, home_moneyline, away_moneyline, home_rest, away_rest, div_game, result, home_score, away_score, home_coach, away_coach, home_qb_name, away_qb_name` |
| `plays` | play | POC 37-column pbp subset + FTN flags, `has_ftn`; from M15.2 also `vegas_home_wp`, `vegas_home_wpa` and the `fixed_drive*` / `drive_*` columns (ADR 0020) |
| `injuries`, `depth_charts` | report row | as POC |
| `lines` (new) | game × book × market × snapshot | `game_id, snapshot_ts, book, market ('h2h','spreads','totals'), side, price_american, point` |
| `weather` (not curated; ADR 0024) | game | forecasts stay raw: `raw/open_meteo/snapshot_ts=<ts>/forecasts.json` (`game_id, kickoff_utc, temp_f, wind_mph, gusts_mph, precip_pct`), read by `nfl.weather.load_snapshots` |
| `stadiums` (new, from CSV in repo) | stadium | `stadium, team, lat, lon, tz, altitude_m, roof` incl. international venues |

### 3.3 Feature store

`marts/features/season=YYYY/*.parquet`, long format:

| column | type | meaning |
|---|---|---|
| `season, week, game_id` | | target game |
| `side` | `home` / `away` / `game` | team-level value, or a game-level value |
| `feature` | str | `<family>.<name>`, e.g. `environment.rest_days`, `market.p_home_vigfree` |
| `value` | float | null allowed |
| `known_as_of` | timestamp | backtest (game kicked off before the build): synthetic `kickoff − 2h`, strictly before the `kickoff − 1h` synthetic lock; upcoming games: the build time |
| `source` | str | `pbp`, `schedules`, `ftn`, `odds_api`, `open_meteo`, `llm_narrative`, `elo`, `tendencies` |
| `version` | str | builder version; narrative features carry the prompt version |

Storage: `marts/features/season=YYYY/<family>.parquet`, written by `nfl.features.store.write_features` as an upsert on `(game_id, side, feature, known_as_of)`; a later row repeating the latest stored value is skipped. **Builder contract:** each `nfl/features/<family>.py` exposes `SOURCE`, `VERSION` and `build(paths, games, build_ts) -> DataFrame` of store rows, made with `store.from_team_values` / `store.from_game_values` (which apply the stamping rule). Builders never write; `nfl features` (M1.9) does. Season-to-date values for a game use only games that kicked off strictly before it.

The engine turns rows into one **game vector** per game: for `team` features `home − away`, for `game` features the value. Vectors are standardized with the scaler saved in the fit (mean/sd over the training window); missing values become 0 after standardization (league average). This is what lets FTN-era features coexist with 2010+ features.

Families and first features (builders in `nfl/features/<family>.py`):

| Family | Features (side) | Source |
|---|---|---|
| `strength` | `elo_pre` (team), `epa_off`, `epa_def`, `success_off`, `success_def`, `point_diff_pg` (team, season-to-date, shrunk toward prior season / league) | elo, pbp |
| `environment` | `rest_days`, `travel_km`, `tz_shift` (team); `is_dome`, `is_turf`, `div_game`, `primetime`, `neutral_site`, `temp_c`, `wind_kph` (game) | schedules, stadiums, weather |
| `weather` (ADR 0024) | `temp_f`, `wind_mph`, `precip_pct` (game; open-air only; played games from nflverse, upcoming from each forecast at its fetch time). Read by the total and the swing list only, never an approach | schedules, Open-Meteo |
| `form` | `last3_win_pct`, `last3_margin`, `streak` (team) | games |
| `decisions` | `fourth_go_rate_oe`, `pass_rate_oe`, `early_down_pass_rate`, `explosive_rate`, `turnover_margin_pg` (team) | pbp (`xpass`/`pass_oe` precomputed), tendencies |
| `front` | `blitz_rate`, `box_8plus_rate`, `motion_rate`, `play_action_rate` (team; 2022+) | ftn via tendencies |
| `market` | `p_home_vigfree`, `spread_line`, `total_line`, `line_move_pts` (game) | schedules (backtest), odds_api (live) |
| `narrative` | `injury_impact` (0–3), `sentiment` (−1..1), `upset_buzz` (0–1), `qb_status` (0–2), `revenge`, `lookahead` (team; live only) | llm_narrative |

### 3.4 Approaches and fits

Config: `src/nfl/approaches/configs/<id>.yaml`.

```yaml
id: traditionalist
name: The Traditionalist
blurb: Trusts rest, travel, weather, the run game and who's hot.
emphasis: [strength, environment, form]        # families with the heaviest weights; every family may appear
calibration: platt
weights:                                        # on standardized home-minus-away features
  strength.elo_pre:      {w: 1.0, why: "Still believes in the better team"}
  environment.rest_days: {w: 0.6, why: "Rest wins games"}
  form.last3_win_pct:    {w: 0.7, why: "Momentum is real to him"}
  decisions.pass_rate_oe: {w: 0.1, why: "Hears about it, doesn't buy it"}
fit:
  shrink_to_persona: true
  lambda_grid: [1, 10, 100, 1000, 10000]   # on the summed log loss; ~700 ≈ persona as strong as 3,000 games
  train_from: 2010
```

Scoring: `logit = b + Σ w_f · z_f`, `p_home = σ(logit)`, `spread_home = Φ⁻¹(p_home) · 13.5`, `total = market total` (totals are not modeled in 2026). Contributions `w_f · z_f` are stored per prediction for the UI.

**Groups (ADR 0012, M2.8).** Features belong to groups (`docs/feature-groups.md`); a group's composite is `c_g = Σ v_{g,f} z_f` with inner weights `v` taken from the walk-forward global fit and normalized to unit variance, shared by every approach. Personas and the DIY page weigh the ~10 composites; overrides of `v` are allowed and re-normalized. Flat `weights:` on features remain valid as one-feature groups.

**One public line per approach (ADR 0004 amendment, 2026-10-27):** `model_id = <approach>` is the persona lightly fitted and calibrated; `<approach>.fitted` is kept as a diagnostic. **The market's forecast is never an input (ADR 0013):** the Market group holds market *behavior* only, capped at 20% of a persona's budget.

Flavors as originally designed (`model_id = <approach>.<flavor>`; superseded by the amendment above):
- **persona**: weights from YAML; Platt calibration `σ(a·logit + b)` fitted walk-forward so the persona's *ranking* is the character's while its confidence is honest.
- **fitted**: L2-regularized logistic regression with the penalty `λ‖w − w_persona‖²` (shrinks toward the persona, not zero), `λ` chosen per approach on validation seasons.
- **global**: one unconstrained ridge fit on all features; not an approach, but the source for the Hypotheses page and a reference line.
- **ensemble**: mean of the fitted flavors' logits (equal weights in 2026).

Fit artifacts: `marts/fits/<model_id>/<trained_through>.json` with scaler, weights, calibration, λ, training window, git sha. Walk-forward: fit on seasons `< S`, score season `S`, for S in 2015–2025. 2022–2024 pick `λ`; 2025 is the holdout; 2026 is live.

### 3.5 Predictions, bets, scorecards

`marts/predictions.parquet` (append-only; POC schema plus): `model_id, model_version (git sha + config hash), lock_ts, slot ('backfill'|'thu'|'sat'), data_snapshot_ts, p_home, spread_home, total, sd_margin, contributions (json), is_backfill`.

`marts/bets.parquet` (append-only, immutable): `bet_id, model_id, game_id, lock_ts, market ('h2h'|'spreads'), side, price_american, point, model_p, market_p_vigfree, edge, stake_units (1.0), book, closing_price, closing_point, clv, result ('win'|'loss'|'push'|null), units_net`. A bet exists when `|model_p − market_p_vigfree| > 0.05` at lock.

`marts/previews.parquet` (append-only, ADR 0024): `game_id, model_id, scored_at, p_home, spread_home` from the daily pass with the locked artifacts; never graded. `marts/strong_calls.parquet` (append-only, ADR 0024): per approach-game 10+ points from the market at lock: `game_id, model_id, lock_ts, side, p_home, market_p, spread_home, market_spread, top_groups (json), assumption (json), what_if_p_home, sentence`. Graded on the fly by the site and `nfl grade` (`strong_calls.grade_all`: `result, log_loss, market_log_loss, closing_toward`); `nfl grade` also writes the derived `strong_calls_graded.parquet`. A relocked game counts once, at its last lock.

`marts/totals.parquet` (append-only, ADR 0024): `game_id, season, week, model_id ('student_total'), model_version, lock_ts, slot, total, sd_total, market_total`, one row per game per lock; graded on the fly by the site, never in the scorecard. Artifacts under `marts/fits/student_total/<trained_through>.json`, refitted by the lock when missing or stale.

`marts/graded.parquet`, `marts/scorecard.parquet` (per model × season × week + cumulative: n, log_loss, brier, spread_mae, ece, ats_pct, units, clv_avg), `marts/divergence.parquet` (per model × bucket of |model_p − market_p|: n, hit_rate, log_loss).

### 3.6 LLM artifacts

`marts/llm_calls.parquet` (one row per request, retries included; written by `nfl.llm.client`): `run_id, job, model, prompt_version, game_id, attempt, ok, error, input_tokens, output_tokens, cache_read_tokens, energy_wh (estimate: latency × LLM_LOCAL_WATTS), latency_ms, ts`. No cost column: every call is local (ADR 0014). Each machine keeps its own log; the desktop's goes up with its records (M6.2L upload path).
`marts/narrative/season=YYYY/`: structured extraction per game × team: the features above plus `claims` (list of `{claim, source_url, published_at, confidence}`), `summary`, `prompt_version`, `known_as_of`.
`marts/previews/`: per game text + the faithfulness report (`numbers_checked, numbers_matched, unmatched[]`). A preview with unmatched numbers is not published.

### 3.6a Narrative records

`marts/narrative/season=YYYY/week=WW/<game_id>_<ts>.json`, one per game per research run, validated by `nfl.llm.narrative.GameNarrative` (claims dated ≤ `known_as_of`, record stamped before kickoff, teams match). `producer` is `claude_code` (the `/nfl-narrative` skill, development) or `api` (the Sonnet job, production); the pipeline treats both identically. Features come from `nfl.features.narrative`, stamped with the record's `known_as_of`.

### 3.6b DIY approach matrix (planned, M5.8)

`marts/diy/matrix.parquet` and `site/diy_matrix.json`: per scored game, the standardized vector (scaler trained through season − 1), outcome, market p, spread and context flags. Scoring any weight vector is a matrix product plus walk-forward Platt calibration, so the build-your-own page needs no server: Streamlit in P1, TypeScript on the same JSON in P2.

### 3.6c Retrospectives (ADR 0016, M9)

- `marts/retro/expectations.json`: league tables fit on 2015–2025 plays (3rd/4th-down conversion by distance bucket, FG make rate by distance, XP rate, fumble-lost share, EPA value per event, the "played like" logistic), with `version` and training window.
- `marts/retro/season=YYYY/<game_id>.json`: one per finished game, validated by `nfl.retro.schema.RetroGame`; stamps `pbp_snapshot_ts`, `pbp_hash` (that game's plays) and `expectations_version`; rebuilt only when the hash or the expectations version changes. Derived: overwritten when nflverse corrects a game.
- `marts/retro/season=YYYY/recap_<ww>.json`: `WeekRecap` aggregated from the week's game retros.

```mermaid
%%{init: {'themeVariables': {'signalColor': '#999', 'signalTextColor': '#999', 'lineColor': '#999'}}}%%
flowchart LR
    P[curated plays<br/>2015-2025] --> X[expectations.json]
    G[curated plays<br/>this season] --> R[game retro]
    X --> R
    PR[predictions + contributions<br/>site.py selection] --> R
    R --> W[week recap]
    R & W --> S[site/retro/*.json<br/>site/recap_*.json]
```

Game retro sections: `result`; `predictions[]` (per approach: status, pick, right, log loss, spread error, best); `played_like` (home win % from the logistic); per team `efficiency[]` (metric, game, season to date, league) and `luck[]` (factor, actual, expected, swing points, sentence) with `luck_net`; `attribution` (per approach, per group: pp, drop-one log-loss value); `headlines[]` (template sentences).

### 3.6d League artifacts (ADR 0019, M14)

- `site/similar.json`: each team's 25 nearest past team-seasons, its seven-measure profile and its flag cards (ADR 0019).
- `site/teams.json`: every team's latest season-to-date value, league percentile and rank for every team-level feature, from each team's next-game row as of the last feature build (`nfl.league.teams.team_latest`), plus conference, division, record and games. `feature_bands` reads the same table.
- `site/league.json`: standings with "seed today", playoff odds per team for two variants (Student, market), game leverage and odds history (ADR 0019); since M26.2 also the played results and each variant's playoff ratings, so the browser can rerun the simulation for the playoff what-if (ADR 0029; engine in `web/src/lib/league/`, kept in parity with the Python by fixtures from `scripts/league_parity.py`).
- `marts/league/season=YYYY/snapshots.parquet`: append-only odds snapshots (as_of, kind refresh|lock, variant, team, outputs, model_version, n_sims, seed), written on the Tuesday refresh and after each real lock, never backfilled.

### 3.7 Site JSON (the UI contract)

| File | Content |
|---|---|
| `site/meta.json` | data freshness per dataset, last lock, git sha, approach list with blurbs |
| `site/slate_<season>_<week>.json` | per game: kickoff, teams, market line, every model's `p_home`/`spread`, divergence flags, `card` (the slate card's edges, injuries, QB context, weather concern and tendencies contrast) |
| `site/game_<game_id>.json` | everything the game page needs: per-approach contributions, tendency matchup rows, narrative claims + sentiment, preview text, injuries |
| `site/scorecard.json`, `site/tracker.json` | scorecard rows; per model cumulative units, CLV, calibration bins, divergence buckets, weekly series |
| `site/hypotheses.json` | per feature: coefficient, CI, n, verdict, sentence, approaches that lean on it |
| `site/audit.json` | null rates, freshness |
| `site/retro/<game_id>.json` | game retrospective (ADR 0016); only for finished 2026 games; 404 = not built yet; `wp_series` and `drives` from M15 (ADR 0020), nullable |
| `site/teams.json`, `site/league.json`, `site/similar.json` | per-team feature table; standings, playoff odds, leverage; similar seasons and flag cards (ADR 0019, §3.6d) |
| game and slate files, additive (ADR 0024) | `market_history[]` (pre-kickoff consensus path), `market_moves`, `events[]` (what changed in each window), `swings[]` (what could move the game, with what-ifs), `strong_calls[]`, `today` (the preview score), `expected_score`, `books` (each book at the latest pre-kickoff snapshot, with disagreement flags); `tracker.json.strong_calls`, `tracker.json.totals` |
| `site/recap_<season>_<week>.json` | week recap: per-approach week record and log loss, best approach, best call and costliest miss, biggest upsets, luckiest/unluckiest teams, most misread games |

Streamlit reads these in P1; React reads the same files in P2. The contract is versioned with `schema_version` in `meta.json`.

### 3.8 Candidates ledger and the gates (ADR 0026, M23)

A second-level feature is a split of something a group already measures (EPA without turnovers, takeaways, fumble luck), not a matchup product: every measurement found interaction features to be noise. Every candidate, passing or failing, is defined once in `nfl/candidates.py` and screened by `nfl candidates run` into `marts/candidates.parquet` (append-only: one row per candidate per `screen_version`, every gate's numbers, a verdict, Austin's `interesting` flag and note). The site's History page shows the whole ledger under "Tested, not used". Derived aggregates the screen and the builders share are SQL models (`src/nfl/sql/models/*.sql` → `marts/derived/`, `nfl models build`), each with a leakage test.

```mermaid
%%{init: {'themeVariables': {'signalColor': '#999', 'signalTextColor': '#999', 'lineColor': '#999'}}}%%
flowchart LR
    C[candidate] --> S{stable?<br/>split-half r ≥ 0.3}
    S -- no --> L[luck term or readout]
    S -- yes --> F{predicts the 2nd half<br/>beyond what we have?}
    F -- no --> X[context, labeled]
    F -- yes --> R{residual vs Student<br/>and market, CI ≠ 0}
    R -- no --> X
    R -- yes --> M[member in a shadow approach]
    M --> G{paired Δ log loss < 0,<br/>90% CI, 2016+}
    G -- yes --> P[public Student at a refit]
    G -- no --> X
```

The first three gates are cheap and high-powered (team-seasons); the last is ADR 0018's bar for a public line. The Student's calibration (a home shift inherited from pooling 2002 onward) was fixed first, as the approach `student_v2` (a 10-season home-field offset beside the Student, live 2026-11-09).

### 3.9 Matchups, paths to an upset, market leans (ADR 0028, M25)

Situation splits are context first. `splits.py` registers each situation once (who chooses it, source, first season); the SQL model `derived/team_split_week` holds every unit's plays, EPA and success with and without each flag per game, as of nothing (consumers read `week < w`). `matchups.py` turns that into per-game edges: the opponent's habit minus the habit already faced, times this unit's gap shrunk toward the league-wide effect (k fitted on earlier seasons), times base plays, in points per game, each with a reliability badge from the candidates ledger. `paths.py` reads `derived/upset_conditions` (dogs' win rates by size and in-game condition since 2006) and says how the underdog wins as conditions and plausibility, never as a probability: pre-game team rates predict a game's turnover margin with r 0.00. `leans.py` sums the ledger's `use` candidates' slopes against the market times this game's gaps into one number in points, graded live. Nothing here is lock code; the headline chance never moves. Edges reach a line only through a separate `matchup` approach after the ledger's gates (phase 3, offseason).

```mermaid
%%{init: {'themeVariables': {'signalColor': '#999', 'signalTextColor': '#999', 'lineColor': '#999'}}}%%
flowchart LR
    PL[(plays)] --> SW[derived/team_split_week]
    SP[splits.py registry] --> SW
    SW --> ME[matchups.py<br/>shrunk gaps, edges in points]
    LG[candidates ledger] --> ME
    PL --> UC[derived/upset_conditions]
    UC --> PA[paths.py<br/>conditions and plausibility]
    LG --> LE[leans.py<br/>what the market misses]
    ME --> GJ[game JSON: matchups<br/>team JSON: splits<br/>retro: splits, paths]
    PA --> GJ
    LE --> GJ
    ME -. phase 3, gated .-> MA[matchup approach<br/>beside the Student]
```

## 4. Key flows

### 4.1 Weekly rhythm (in-season)

```mermaid
%%{init: {'themeVariables': {'signalColor': '#999', 'signalTextColor': '#999', 'lineColor': '#999'}}}%%
sequenceDiagram
    participant Tue as Tue refresh
    participant Wed as Wed-Fri enrich
    participant Thu as Thu 9am ET lock
    participant Sat as Sat noon ET lock
    participant Mon as Mon/Tue grade
    Tue->>Tue: ingest, curate, audit, tendencies, features, odds snapshot
    Tue->>Tue: grade last week, settle bets, closing lines, site JSON
    Wed->>Wed: narrative extraction (web search), previews + faithfulness
    Thu->>Thu: odds snapshot, features as-of now, all approaches, append predictions, bets
    Thu->>Thu: write public/predictions/<season>/week_<w>_thu.json + sha256, commit
    Sat->>Sat: same for Sun/Mon games (after Friday injury report)
    Mon->>Mon: grade, settle, tracker, hypotheses refresh
```

Until P2 these are commands Austin runs (`nfl weekly refresh`, `nfl lock --slot thu|sat`, `nfl weekly grade`). From P2 Cloud Scheduler triggers the same commands as Cloud Run Jobs.

Daily at 07:00 ET (`nfl-retro`, ADR 0016): ingest this season's pbp and schedules, curate this season's games and plays, build retrospectives for finished games without one (or with a newer pbp snapshot), publish. Thursday, Sunday and Monday games get theirs the next morning.

### 4.1a Daily pass (ADR 0024)

Wed, Fri and Sat 20:05 ET (`nfl daily`, the odds job): current-season ingest, one odds snapshot, curate, the Open-Meteo forecast, tendencies, features, preview scores of upcoming games with the locked artifacts, site JSON (line history, window events, swing factors, what-ifs), publish. Thursday, Sunday and Monday keep their snapshot times; Sunday and Monday snapshots are in-play lines for games under way and never count as movement.

### 4.2 Lock

`nfl lock --slot thu|sat` (implemented in `src/nfl/lock.py`; slots by Eastern weekday: thu = Wed–Fri, sat = Sat–Tue; artifact name `week_<ww>_<slot>_<lock ts>.json`): refresh current-season data, take an odds snapshot; build features as-of now for the slot's games; load the frozen fits (trained through `S−1`); score every approach and flavor; append prediction rows with `lock_ts = now`; open bets where the edge exceeds the threshold; write the public JSON and its SHA-256; commit with message `lock: S W<W> <slot>`. Re-running a lock appends new rows; grading uses the last lock before kickoff. Since ADR 0024 the lock also takes an Open-Meteo forecast in its refresh, puts each game's `student_total` (total, sd) in the public JSON, and after the commit records strong calls and appends the totals rows; none of those can block the lock.

### 4.3 Backtest and fit

`nfl fit`: build features for 2010–2025; for each approach run the walk-forward loop; pick λ; write fit artifacts; `nfl predict --backfill` writes one synthetic lock per historical game (`kickoff − 1h`, `is_backfill=true`) so the scorecard covers 2015–2025 under the same grading code as live rows. The leakage tests assert that every feature row used has `known_as_of < lock_ts` and every fit was trained on seasons before the scored season.

### 4.4 Grade and settle

Per (game, model): last lock before kickoff; log loss, Brier, spread error, ATS, calibration bin. Per bet: result from `games.result` against the line at lock; `clv` from the closing line: our latest Odds API snapshot within 3h before kickoff, else nflverse's schedule line (the Odds API historical endpoint is paid-only on the free plan; verified 2026-10-26). CLV is movement toward the bet (vig-free probability points for moneylines, points for spreads), null when bet and close are the same nflverse number. Divergence buckets: group graded rows by `|model_p − market_p|` in 0–2.5, 2.5–5, 5–10, 10+ points.

### 4.5 Narrative extraction (live only)

Per game, per team, Sonnet 5.5 with the built-in web search tool, output constrained to the narrative schema with citations. Prompt version frozen per week. Features land in the store with `known_as_of = run ts`, so a Thursday lock can only use Wednesday's extraction. Nothing from this flow is backfilled; the Narrative approach's record starts at its first live week and the UI says so.

## 5. Point-in-time rules

1. Backtest as-of is the game-week filter on the current nflverse snapshot, stamped `kickoff − 1h`. Historical data is not bitemporal; we don't pretend.
2. Live as-of is the ingestion snapshot timestamp. A lock may use only feature rows with `known_as_of < lock_ts`.
3. Fits used in season `S` are trained through `S−1` and frozen; refits during the season produce new `model_version`s and new rows, never edits.
4. Prediction and bet rows are append-only. Tests enforce 1–4.

## 6. Scoring

Primary: log loss, Brier, calibration (ECE + reliability bins), spread MAE, against `market_baseline` and `home_naive`. Secondary: ATS, odds-weighted units (flat 1 unit, 5-point threshold), CLV (primary *edge* metric), divergence buckets. Every scorecard states n and that ~180 live games cannot rank models; CIs are bootstrapped by season on the backtest.

## 7. Tech stack

Python 3.14 via uv; Polars + DuckDB (in-process, no DB server); numpy + scipy for fitting; pydantic + PyYAML for configs; Typer CLI; httpx; Anthropic Python SDK (structured outputs, web search tool, Batches API); Streamlit + Plotly (P1 UI); React + TypeScript + Vite (P2); Docker; Terraform; GitHub Actions (CI); GCP Cloud Run Jobs + Cloud Scheduler + GCS + Secret Manager + Workload Identity Federation; Firebase Hosting. pytest + ruff.

## 8. Deployment path

| Phase | Runs where | Data | UI |
|---|---|---|---|
| P0–P1 | Laptop, commands run by hand at lock times; CI on Actions | `./data` | Streamlit local |
| P2 | Cloud Run Jobs from one image, Cloud Scheduler, Terraform in `infra/` | GCS bucket via FUSE | React on Firebase Hosting |
| Self-hosting (separate project, after P2) | Desktop as primary runner, cloud as fallback | GCS stays source of truth | unchanged |

Portability rules: one image with CLI subcommands; config via env; data root is a path; no code knows where it runs.

## 9. Not in 2026

Matchup and Narrative approaches on the public scorecard (Narrative capture *does* run), Monte Carlo drive sim, player modeling, coordinator table and tendency discontinuities, participation-based coverage/personnel tendencies (data lands Feb 2027), Approach C (user predictions), API server, accounts, Langfuse, self-hosting.

## Team page (ADR 0022, M18)

`/team/:code` joins four site files in the browser: `team/<code>.json` (staff, evidence, situations, expected and observed tendencies; ADR 0021), and `teams.json`, `league.json`, `similar.json` (shared with the League page). Each failing only removes what needs it.

```mermaid
%%{init: {'themeVariables': {'signalColor': '#999', 'signalTextColor': '#999', 'lineColor': '#999'}}}%%
flowchart LR
    SP[(staff_spells.csv)] --> TF[team/CODE.json]
    BL[(coach_blend.json)] --> TF
    TD[(tendencies + scheme marts)] --> TF
    TF --> ST[Staff]
    TF --> TN[Tendencies]
    TJ[teams.json] --> OV[Overview]
    LJ[league.json] --> OV
    SJ[similar.json] --> OV
    TJ --> GM[Games]
    LJ --> GM
    TF --> GM
```

## Players (ADR 0027, M24)

As built through M24.5 (2026-11-12). Free nflverse player tables (weekly stats 1999+, snap counts 2013+, PFR advanced stats 2018+, contracts, draft picks, the id crosswalk `players`) are curated beside the team tables (`curate_players`, optional: a failure never stops a job) and queried through the catalog; the plays table keeps who caught, ran, sacked and defended each play.

- **Status to play** (`players/status.py`, M24.1): how often players listed Out, Doubtful or Questionable have played, by report position, 2016+, from our own history.
- **Value** (`players/value.py`, M24.2): every regular starter's worth in points of spread over a replacement, per (season, week), as of the start of the week (games before it only). A Python model through the catalog until M23's SQL runner takes it; output at `marts/derived/player_value.parquet`; `week_values` computes the upcoming week live.
- **Claims** (`players/claims.py`, M24.4): the daily pass records, per upcoming game and side, the three most valuable listed starters with value, P(play) and value at risk (`marts/player_claims*.parquet`, append-only); a change to Out before kickoff grades the last claim against the consensus line's move. Never read by a lock (tested).
- **Lineups** (`players/lineup.py`, M24.5): at each `nfl site`, each side's base-formation starters from the latest timestamped depth chart, with values and the game week's statuses, for the next two weeks' unplayed games. Its own chart reader (the top rank per formation slot), separate from `features/availability.py`'s lock lookup. Regular starters on the report whom the chart has moved down are listed beside it (`off_chart`); the team panel's statuses come from the same report rows.
- **Pages** (M24.5): the game's Injuries tab (formation map, key players, the report), the team's Availability tab, the tracker's Player claims. Site JSON fields `Game.lineups`, `Game.key_players`, `TeamFile.availability`, `Tracker.player_claims`, all nullable.
- **Team health** (`players/health.py`, M24.7): each team's full-strength lineup (at each base spot, the most valuable player the chart has had as the starter since March who is still on the weekly roster, `curated/rosters_weekly`, 2025+), each valued going into his last game, against this week's status: a reserve list (IR `R01` with its window, four games; designated to return `R48`; PUP), the report, inactive. Health = the share of full-strength value expected on the field, by group, for every game played and the next one, plus an outlook that brings IR players back when eligible. Site JSON `TeamFile.health`, `Game.health` (data only until the team page and map use it). Interior DL and linebackers are valued since M24.7.
- **Not yet** (M24.3, waits on M23's ledger): `availability.value_lost`, the value of who's missing weighted by status-to-play, as a ledger candidate before any approach may use it.

```mermaid
%%{init: {'themeVariables': {'signalColor': '#999', 'signalTextColor': '#999', 'lineColor': '#999'}}}%%
flowchart LR
    PS[(player weeks, snaps,\nPFR adv, contracts, draft)] --> PV[players/value\npoints per player-week]
    INJ[(injuries, daily snapshots)] --> STP[status_to_play rates]
    DC[(depth charts)] --> LU[players/lineup\nformation starters]
    DC --> HE[players/health\nfull strength vs now]
    RW[(weekly rosters, IR)] --> HE
    PV --> HE
    HE --> SITE
    PV --> CL[player_claims\ngraded by market moves]
    STP --> CL
    PV --> LU
    STP --> LU
    PV -.M24.3.-> VL[availability.value_lost\ncandidate]
    VL -.-> LEDGER[candidates ledger]
    CL --> SITE[Injuries tab, team Availability,\ntracker Player claims]
    LU --> SITE
```

