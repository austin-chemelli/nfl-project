# ADR 0021: Coaching staff ground truth, tendency context and a team page

Status: accepted 2026-11-06 (Austin): team page, verification 2016–2026 (hub decisions D15, D16). Plan: `.notes/plans/coaches-refinement.md`. Tasks: M17.

## Context
The coordinator table (`src/nfl/data/coordinators.csv`, 352 rows, 2016–2026) was built from Wikipedia season pages through a summarizer, with play-callers from general knowledge. The play-caller column is the one the profiles and the game page hang on, and it is wrong in the current season (CAR 2026 names Canales; Idzik has called plays since February 2026) and unverified elsewhere. The table flattens mid-season changes to the end-of-season person. Profiles use participation data, which nflverse publishes once per offseason, so every 2026 unit shows "no tendencies yet" while weekly FTN and pbp tendencies already exist through the latest played week. The nflverse schedule's coach field is stale for 2024+ (NYJ 2024 shows Saleh all season; 2026 shows three replaced head coaches), so it cannot be the ground truth. Austin's direction: accurate data first, play-callers labelled as play-callers only when they are, recent tendencies weighted over old ones, context for callers who moved teams, changed quarterbacks or have never called plays, and a place on the League side for a per-team evaluation. No paid API; open data only (ADR 0001); additive contracts (ADR 0015).

## Options
1. **Ground truth.** (a) Keep one row per team-season and fix names by hand. (b) A spells table (person, role, start and end week) with an evidence grade per row, verified by web-research agents against primary sources, with a public rule that a play-caller shows as one only with official, news or roundup evidence. (c) Extract staffs with the local LLM from the web each week and trust it. (c) is what produced today's errors at one remove; (a) cannot show interims or handoffs.
2. **Tendency context.** (a) Fixed heuristics (halve the prior when the caller moves, and so on). (b) Measure on 2017–2025 how well a caller's prior and the team's previous season predict the next season under each situation (caller moved, new quarterback, first-time caller, HC calling) and use the measured blend, with an equal blend labelled as the fallback where cells are thin. (c) Nothing: show history and this season side by side with no "expected" line.
3. **Current-season tendencies.** (a) Wait for participation each spring. (b) A second profile set on the FTN and pbp metrics (2022+), the same metrics for history and for this season through the latest week, so "expected vs so far" is drawable; the participation set stays as last charted season context.
4. **Placement.** (a) Grow the League team panel. (b) A team page `/team/:code` with state, staff, tendencies and games, absorbing the Coaches page's team view; the Coaches page keeps the coach view. (c) The Coaches page as today with charts.

## Decision
- 1(b): `staff_spells.csv` with roles HC, OC, DC, OFF_PC, DEF_PC, start and end weeks, evidence ∈ official · news · roundup · wiki · inferred, and a source URL per row; empty means not established. `load_coordinators()` becomes a derived view so nothing downstream breaks. Verification by `general-purpose` agents on Sonnet, one per season band, at a full bar for 2022–2026 and a light bar for 2016–2021; the main chat reconciles and records every change. A test enforces the public rule for 2022+ play-callers.
- 2(b) with 3(b): a prior study picks the decay and the blend weights per situation and publishes the table here; live profiles on the FTN set carry "expected vs so far"; the charted set (personnel, coverage, time to throw, pressure) is shown in season as a prediction from the same blend, kept on the chart when the spring drop adds the observed value (Austin, 2026-11-06). Coaching lineage is sourced text for first-time callers, never a model input. The quarterback is not modelled per person; the new-QB flag and the team-previous-season term carry it, and backup-QB weeks are flagged from pbp starters.
- 4(b): the team page, built after the data is verified; linked from League, Similar, the slate and game headers. The Coaches page returns as the coach view under M16.3.
- In-season changes: a weekly staff check on the desktop pass writes candidates with quotes and URLs; a person confirms; the change ships in a PR. Nothing edits the table automatically.

## Consequences
- The honest labels get stricter: a unit without a confirmed play-caller shows the coordinator with "not confirmed".
- Profiles become week-aware (phase 2), which fixes the known limit in `features/scheme.py`; the scheme features' values will move for team-seasons with a mid-season change, which is fine because every approach zeroes them (M11.3) and only the Hypotheses page reads them.
- Four seasons at most of FTN history: the live profile says so. Participation-only measures (personnel, coverage, time to throw, pressure) stay a year behind in season, and the page says that too.
- Ongoing cost: a weekly confirm step for staff changes, minutes a week; agent runs once now and a smaller pass each offseason.
- Risks: agent over-confidence (mitigated by the quoted-sentence rule and the reconcile step), thin cells in the prior study (equal blend fallback), and the team page growing into a rebuild (it ships after data, with the design language's caps).

## Measured (2026-11-06)
`scripts/coach_prior_study.py` on 2017–2025, unit-seasons with no mid-season change; first-time cells from 2020, since the table starts in 2016 and an older career would look first-time. Typical miss in percentile points of the within-season rank, every column on the same cases (always guessing the league middle: 23 to 28). Weights and misses live in `data/coach_blend.json`, written by the study and read by the team files. A cell needs 25 unit-seasons. The table behind this is partly verified: 56% of 2016–2021 play-caller rows are unconfirmed.

| Situation | Unit-seasons | Caller's past | Team's last season | League middle | Blend, held out |
|---|---|---|---|---|---|
| Offense, same caller (charted) | 93 | 18.0 | 17.7 | 26.3 | 17.4 |
| Offense, same caller, new QB (charted) | 51 | 20.5 | 22.9 | 25.6 | 20.5 |
| Offense, caller moved (charted) | 27 | 21.2 | 29.6 | 26.0 | 21.5 |
| Defense, same caller (charted) | 164 | 20.1 | 20.4 | 25.2 | 19.9 |
| Defense, caller moved (charted) | 36 | 28.4 | 30.4 | 26.5 | 25.2 |
| Offense, first-time caller from outside (charted) | 26 | – | 24.1 | 24.7 | – |

Consequences for the page: when a caller moves, personnel, shotgun and time to throw lean on him and pass rate leans on the team (23 vs 34); a moved defensive caller is a weak read; a first-time caller's "expected" is labelled weak. Recency matters little: decay from 0.5 to 1.0 moves the same-caller miss from 17.9 to 18.6, so 0.7 stays. Week-by-week QB changes come from the schedule's starter names, measured from the Week 1 starter, not from pbp.

**Review changes.** `took_over` splits callers already on the staff from those who moved. Everything about a unit follows the person in force at the file's week, and only when confirmed. `coaches.json` stays out of the site build until M17.9, because it has no evidence filter. A role whose last spell ended early with no successor is null in the view, so the unit falls back to its coordinator. A 32-team who-calls-plays list counts as `roundup` evidence on its own.
