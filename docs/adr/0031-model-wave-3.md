# ADR 0031: Model wave 3: one Student, neutral sites level, every registry member decided

Status: accepted 2026-11-20 (model round 3; Austin asked for the round and for the design calls to be made and recorded, not asked). Supersedes the "Student v2 beside the Student" part of ADR 0026 (D23) and its refit timing, ADR 0018's Venue & weather and neutral-site handling, and ADR 0028's D28 (edges only through a separate approach). Measurement: `.notes/hub/plans/approaches-audit.md`, scripts `scripts/approaches_audit.py` and `scripts/approaches_gap.py`, module `nfl.approaches.shadow`.

## Context
Austin asked to re-evaluate the approaches: one Student instead of two, weights re-checked, the data added since October used where it helps, and the matchup numbers the Preview shows reflected in the scoring where they earn it. He lifted the "wait for the offseason refit" rule: the new Student goes public mid-season once it beats today's in the backtest (paired Δ log loss, 2016 onward, 90% CI), with a new `model_version` and a marker on the tracker. Old rows stay (append-only).

Found by the audit:
- The two Students differed only in calibration (`platt`, a no-op on a `public: fitted` line, against `shift_10`).
- The Student's gap to the market lives in the 42% of games where they disagree by 6+ points of win chance. Weeks 1-4 and 15+ carry 75% of it and road favorites 67%. The final injury report closes 7-10% of it.
- 24 registry members were never stored and silently skipped, among them the weather the store already had under other names.
- Venue & weather's fitted modifiers (domes, turf, division games, primetime) cost accuracy since 2016. The Sharp had no venue group, so it gave a designated home team its full home field at neutral sites (+7 points).
- No decomposition, luck, player-value or weather candidate beat the Student in shadow. The net matchup edge did.

## Options
1. **Keep both Students** and add features to v2. Austin didn't want two, and v2 alone carried only 0.0003.
2. **One Student from the audit:** every fitting choice and candidate measured one at a time against today's Student; adopt only what clears the shadow gate (CI below 0, 2016 onward), and fix the structural bugs (neutral sites) for every approach.
3. **A broader refit** (season decay, phase-specific fits, flat ridge without groups). Measured: decay −0.0002 (ns), phase fits +0.0029 (worse), flat −0.0014 (ns, and it loses the groups the site explains).

## Decision
Option 2.
- **One Student** (`configs/student.yaml`): `calibration: shift_10`; no Venue & weather group; the net matchup edge in Offense. `student_v2.yaml` is deleted. Its rows stay in `predictions.parquet`, and the site, README, strong calls and tracker stop listing it.
- **Neutral sites are level by rule** (`engine.NEUTRAL`, `Model.neutral_gate`): every fitted model multiplies its home-field term (intercept and calibration offset) by 1 − `environment.neutral_site`, in fitting and in scoring. The member `environment.neutral_site` leaves the registry, since a member would count it twice. Venue & weather's game-level members only shift home field, so they are gated the same way (`engine.venue_gate`), and the global fit drops the flag (`ensemble.EXCLUDED_FEATURES`).
- **Registry v7:** every member is built or removed on purpose.
  - Weather: the planned `environment.temp_c` and `wind_kph` are removed. The store's `weather.temp_f` and `wind_mph` stay out of every fit: training would see observed kickoff weather, while a lock only has a forecast. They wait for archived forecasts (M23.14) (review finding).
  - FTN charting: the drop, contested-catch and risky-throw rates are built but left out of the groups (together +0.0013 [+0.0002, +0.0023] since 2022). The RPO, screen, under-center and no-huddle rates are built (context).
  - Coaching: tenure, first-year coach, pace, penalty yards, and pass rate over expected when ahead or behind are built (context). `decisions.hc_ats_career` (a spread record: the market's number, doesn't repeat) is removed. So is `front.pass_rushers_5plus_rate` (identical to the blitz rate in FTN's charting).
  - Matchups: the seven planned interactions are replaced by the matchup engine's edges. `matchup.net_edge_pg` joins Offense, and the seven per-situation edges stay context-only.
- **The ledger's fourth gate runs in code:** `nfl candidates run` backtests each feature candidate in shadow (`nfl.approaches.shadow`; columns `shadow_delta`, `shadow_lo`, `shadow_hi`, `shadow_n`, `shadow_from`; verdict `model` when the CI is below 0). Feature-store candidates (`frame="features"`) get the residual gates on their home-minus-away value. A candidate that clears the gate joins a group at the next registry bump, mid-season if it beats the public line (Austin, 2026-11-20).
- **Personas** keep their characters and weights. The Analyst drops Venue & weather, the venue modifiers the evidence says don't add. The Traditionalist keeps it. The Sharp gains nothing but the neutral rule. Each persona's diagnostic ("what history would change") fits toward zero instead of toward the persona (`fit: {shrink_to_persona: false}`), so it shows what history alone supports. The public lines are unchanged by this (they are still the light fit toward the persona, λ = 0.22·n).
- **Fitting plumbing for later:** `fit.DECAY_HALF_LIFE` (season weights, off) and per-row weights in `fit_ridge`/`fit_platt`.
- **The tracker** marks where each line's config hash changed (`tracker.json.model_changes`). The Preview marks each matchup and second-level number "in the line" or "shown, not scored" from the registry.

## Consequences
- Every config hash changed: every fit, backfill row and lock artifact is new, and `nfl lock` refuses the old fits. It deploys by the runbook's model-wave cutover (refit and backfill on a fresh bucket copy, upload right after the merge). The first public lock on wave 3 is the first lock after the upload.
- Since 2016 the Student's log loss is 0.6270 (was 0.6286; −0.0016 [−0.0028, −0.0005], 8 of 11 seasons), the Analyst's 0.6260 (−0.0013), the Sharp's 0.6276 (−0.0003, ns) and the Traditionalist's 0.6366 (+0.0001, ns). On 2005-2015 the venue change costs the Student +0.0004 (ns): it is a bet that the last decade's home field is the one that matters now.
- The gain is under a tenth of the gap to the market (0.017). The remaining gap is in the big disagreements early and late in the season, and that is what the news work (ADR 0032) and better priors would target.
- About 25 candidates were tested at 90%, so two or three chance passes are expected. The net edge counts because it passed two independent gates (shadow, and the market residual +0.63 [+0.27, +0.92]) as the pre-registered matchup candidate. The play-action edge passed against an earlier draft and not against the final Student (−0.0001 [−0.0003, +0.0002]).
- News ratings are unchanged in this wave: ADR 0032 moves them into a bounded adjustment.
- `approaches/diy.py` scores its own composites without the neutral rule. The Your-own-approach track takes that up when Build comes back.
