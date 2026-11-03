# ADR 0016: Post-game retrospective: expectations from history, luck in points, a daily job

Status: accepted 2026-11-02 (plan; tasks M9.x). Scope decided with Austin: 2026 games only, template sentences (no LLM text), a daily cloud job, shown on the game page and in a week recap.

## Context
After a game, the site shows each approach's pick and whether it was right, and nothing else. The useful questions come after the final score: did the result follow from how the teams played, or from things that rarely repeat (fumble bounces, a missed 40-yarder, a 4th-and-2 stop)? Did a team play far above or below its season to date? Which approach read the game best, and which of its groups pulled in the right direction? nflverse refreshes play-by-play several times a day in season (verified 2026-11-02: the `Update PBP Related Data` workflow ran 7 times that day), so the data is there within hours of a game ending.

Constraints: principle 1 (no generated statistic that wasn't computed), principle 4 (be honest: one game is noise, and "luck" is an estimate), contract changes stay additive (ADR 0015), and the jobs share one data bucket.

## Options
1. **Box score only.** Game stats next to season averages. Cheap, but it can't say whether a gap was luck, and it leaves the reader to do the math.
2. **Expectations from history, swings in points (chosen).** Every "luck" factor gets an *expected* value from league rates over 2015–2025 for the same situations, so the gap between actual and expected can be priced in points with the EPA value of that event, also measured on history. Efficiency is compared with the team's own season to date. A simple logistic fit on history gives "teams that played this efficiently won X% of the time".
3. **An LLM writes the retrospective.** Readable, but the desktop 9B is unreliable at synthesis (M6.2e) and every number would need a faithfulness gate. It is deferred: a recap paragraph can be layered on the computed record later, under M6.3's check.

## Decision
- **Descriptive, not causal.** The retrospective states what happened against what was expected. Every number is computed in code, and every sentence is a template filled from the record.
- **Expectations** (`marts/retro/expectations.json`, versioned, fit on 2015–2025 regular-season plays, rebuilt in the offseason):
  - 3rd- and 4th-down conversion rates by distance bucket (1, 2–3, 4–6, 7–10, 11+). For 4th down, only plays where the offense went for it count.
  - Field-goal make rate by 5-yard distance bucket, and the extra-point make rate.
  - The share of fumbles the fumbling team loses.
  - The EPA value of each event (a conversion against a failure in its bucket, a lost fumble, an interception, a penalty yard).
  - The "played like" model: a logistic of home win on the difference in EPA per play without turnover plays, with an intercept for home field. Turnovers are left out on purpose, because they are mostly the luck being separated. Success rate was dropped after the first fit: it correlates 0.74 with EPA and its coefficient turned negative once EPA was in (the schema keeps `b_success`, fixed at 0).
- **Luck factors** (per team, swing in points, positive = helped that team):
  - fumble recoveries;
  - interceptions against the team's season-to-date rate per dropback, labeled "partly skill";
  - 3rd- and 4th-down conversions, against a rate adjusted for both teams. The league rate for the distance is shifted by the offense's season-to-date conversions over expected and by the opponent defense's, each shrunk with 50 pseudo-attempts. Amended 2026-11-02 after the first run: against league rates alone, a good offense's normal skill counted as luck (luck sd 9 points a team, correlation 0.62 with the margin);
  - kicking (field goals and extra points, made against expected by distance);
  - penalties (yards against the season-to-date average), labeled "partly skill";
  - special-teams big plays (return TDs, blocked kicks).

  Each factor carries actual, expected, swing points and one sentence. Every play counts in one factor only: a 3rd-down interception is a turnover, not a failed conversion, and a blocked field goal is a special-teams play, not a miss (fixed in review; expectations `retro_exp_v2`).
- **Net swing and pure luck.** The sum of all factors is the *net swing*. Only fumble recoveries, kicking and special-teams plays are close to pure luck; conversions, interceptions and penalties are marked partly skill. On 2026 Weeks 1–8 the net swing has sd 9.1 points a team and correlates 0.59 with the margin (home minus away), while pure luck has sd 3.3 and 0.32. The page shows both, the headline names both, and the week recap ranks the luckiest teams by pure luck.
- **Efficiency** (per team, offense and defense):
  - Metrics: EPA per play, success rate, EPA per dropback, EPA per rush, explosive-play rate, sack rate and pass rate over expected.
  - Each is compared three ways: in this game, over the team's season to date (only plays from games that kicked off before this one, the same as-of rule as the features), and against the league average.
- **Predictions graded per game.** The record uses the prediction the game page shows (the last lock before kickoff, else not locked, else backfill; the `site.py` selection). For each approach it gives the pick, whether it was right, the log loss and the spread error, plus the best approach in the game.
- **Group attribution by drop-one log loss.** A group's contribution in win-probability points is exact: `pp = σ(L) − σ(L − c_g)` (M5.10). So the probability without that group is `p − pp`. The group's value in this game is `LL(p − pp) − LL(p)`: positive means it helped. The most valuable group per approach is the one with the largest value. The values don't sum to the total, which the page says.
- **Publishing.**
  - Retros are new files, `site/retro/<game_id>.json` and `site/recap_<season>_<week>.json`, so existing contracts don't change.
  - The web app asks for a retro only when a game has a result, and treats a 404 as "not built yet".
  - Retros are derived data, not records: a rebuild overwrites them when nflverse corrects a game, and each one stamps the pbp snapshot it used and a hash of that game's plays. A game is rebuilt only when its own plays change, or the expectations are refit; nflverse republishes the whole season file several times a day, so the season snapshot alone would rebuild everything.
- **A daily cloud job**, `nfl-retro` at 07:00 America/New_York:
  1. ingest the current season's pbp and schedules;
  2. curate the current season's games and plays;
  3. build retros for finished games that have none, or whose pbp snapshot is newer than the one stamped;
  4. publish.

  It writes nothing a lock reads beyond what the Tuesday refresh already writes, and 07:00 doesn't overlap the locks (Thu 09:00, Sat 12:00), the refresh (Tue 10:00) or the odds snapshots.

## Consequences
- Thursday, Sunday and Monday games get a retrospective by the next morning.
- One more Cloud Run job and one more Scheduler entry in Terraform. The image workflow's job list gains `nfl-retro`. Cost is a few minutes of CPU a day.
- Curated plays gain about 15 pbp columns (a one-time re-curate).
- The swing values depend on league constants from history, so they shift slightly when the expectations are refit. The file is versioned, and each retro records the version it used.
- One game says little about a model. The recap and the game section say so, and they don't feed the scorecard.
- **Follow-ups (not in v1):**
  - historical seasons, since the CLI can build any season but only 2026 is published;
  - an LLM recap paragraph under the faithfulness check;
  - Streamlit parity (P1 UI is disposable).
