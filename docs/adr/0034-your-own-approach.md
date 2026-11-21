# ADR 0034: Your own approach: a line the reader builds, scored in the browser, never in the record

Status: accepted 2026-11-20 (model round 3, track 3; Austin asked for the feature and for the design calls to be made and recorded, not asked). Builds on ADR 0012 (groups), ADR 0013 (the market is never an input), ADR 0015 (data published independently of the site), ADR 0029 (visitor state in the browser) and ADR 0031 (neutral sites level by rule). Closes M16.2 (Build comes back with this work).

## Context
Austin: a reader builds their own approach from the features we have by weighing groups, sees how it would have done, saves it, and then sees it in every view that compares approaches, and as the default line if they choose. The site is static (Firebase Hosting plus public JSON, no accounts). Build has scored weights in the browser since M5.8 (`web/src/diy/`), but only over history, from its own composites that ignored the neutral-site rule, and it was hidden (M16).

Constraints: the market's forecast is never an input (ADR 0013); every published number is checked against the data; live predictions can't be backfilled, and a reader's line must never look like part of the public record; slate and game files are fetched by every visitor.

## Options
1. **Where a custom line is scored.** (a) In the browser from published per-game group composites. (b) A server job per saved approach (needs accounts and storage per reader). (c) Only on Build, never elsewhere.
2. **How its record this season is made.** (a) From the composites as of each game's graded lock (the same moment the Student was graded at), rebuilt by `nfl site` from the point-in-time feature store. (b) Only from saves forward (a record that starts empty and lives in localStorage). (c) From the current composites (leaks: later information).
3. **What "default" means.** (a) A browser preference that swaps the line pages lead with, with a visible mark and a one-click way back. (b) Server-side headline change (impossible without accounts, and wrong: the public headline is the Student).

## Decision
1(a), 2(a) with the "since you saved" split shown beside it, 3(a).

**The line.** Signed points per weighted group, normalized (Σ|W| = 1, Market behavior at most 20%), then

    p_home = σ(a · Σ_g W_g c_g + c · g),   g = 1 at a home game, 0 at a neutral site

- `c_g` are the engine's group composites: each group's members standardized and weighed by the inner weights of the persona artifacts trained through S − 1 (`student.persona`, then `traditionalist.persona` for Venue & weather and Buzz, then `sharp.persona`). Inner weights don't depend on the approach, so these are the numbers every published line is built from; Venue & weather's members are zero at a neutral site (`engine.venue_gate`). The one difference: Market behavior is line movement only (the Student's and the Analyst's override); the Sharp's own reading also fades the public's side.
- `(a, c)` is a Platt calibration with the same neutral-site gate, fitted on every Build-matrix season before the scored season (2002–2025 for 2026). It is fitted in the browser when the reader saves and stored with the matrix key (`<registry>-<last season>-<hash of the source artifacts>`, `meta.custom.key`, read back from the published matrix so a failed rebuild publishes no key rather than one nobody can refit to); when the key changes (a refit, a registry bump) the browser refits it in the background from `diy_matrix.json`, the only time a non-Build page loads that file.
- The context-only groups carry no weight in a custom line either. Market behavior and Buzz are live only: they can't move the backtest, but count in the line this season (the page says so). Because the calibration's slope is fitted where they are zero and then applied to the whole lean, together they hold at most 30% of a custom line's budget (`LIVE_CAP`); without it a line that is 95% Buzz got a slope twenty times too steep and showed 100% picks (review finding). A line with no weight on a group with history can't be saved.
- Parity: a published line scored through the browser's path (its group weights, intercept and calibration on the published composites) equals the engine's `p_home` to 1e-16 in Python (`tests/test_diy.py`) and to the composites' 4 decimals in TypeScript (`web/src/you/you.test.ts`, fixture `fixtures/diy/lines.json`), on the Student, the Analyst and the Traditionalist, neutral sites included.

**The data (additive, `site.py` section "your own approach").** Every slate and game row carries `composites` (`as_of`, `neutral`, `c{group}`) as of the lock_ts of the headline row the page shows (lock, backfill, preview or pregame), so "You" reads what the Student read beside it; about 200 bytes a game. `site/custom_<season>.json` holds every graded game with the composites at the Student's graded lock and the Student's and the market's graded p (about 65 KB, read only by the tracker, last week's line and the recap). `meta.custom` names the registry, key and groups. `diy_matrix.json` v2: the weighted groups only, a `neutral` column, Venue & weather active.

**The browser.** `web/src/you/`: the store (`nfl-you-v1`, one approach per browser: name, points, registry and groups it was saved under, calibration, saved_at, default flag; validated on load, synced across tabs), the maths (`line.ts`), a provider that resolves it once for the app and adds `models.you` and `contributions.you` to the slate and game data as they load, so every view that lists the approaches shows it. A saved approach from an older registry keeps the groups that still exist and the page says which were dropped or are new. Shareable by `?w=` (the weights, not the line).

**Never in the public record.** Nothing server-side scores, locks, grades or bets a custom line; the README, the public tracker rows, the ledger and the strong calls don't know it exists. Every number from it is labelled unofficial. Its record this season is computed in the browser from `custom_<season>.json`, and shown with "since you saved" apart, because weights set after seeing results have been tuned on them.

**Default.** `useHeadline()` is the reader's line when they made it the default, else the Student; the server's headline stays the Student. A bar under the site header says pages lead with the reader's line, with "Lead with the Student". The playoff odds are not recomputed: rerunning the season simulation in the browser is out of scope, and the League page says the odds are the Student's and the market's.

## Consequences
- The record is honest only as far as the feature store is point-in-time (ADR 0005): composites at a past lock are rebuilt from rows with `known_as_of` before it, with this season's groups (v7). For weeks 9–11 the Student's graded line was wave 2 while the reader's uses v7 groups at the same moments; the tracker's fine print says so. Weeks 1–8 were backfill for both.
- `nfl site` computes the composites twice (the pages' rows and the graded rows), a few seconds; both are wrapped so a failure costs only "You".
- When news moves into a bounded adjustment (ADR 0032), its narrative members leave the groups at a registry bump and the composites follow; whether "You" gets the adjustment is that PR's call, at the seam `you/line.ts` (`scoreLine`).
- A cleared browser loses the approach; accounts stay a later milestone (ADR 0029).
