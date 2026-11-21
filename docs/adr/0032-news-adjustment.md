# ADR 0032: News reaches the lines as one bounded adjustment, sized by history, scored against a football-only twin

Status: accepted 2026-11-20 (model round 3, decision 1, recommendation (a); built while the decision was still formally open, as the round's working rule allows). Amends ADR 0012 (narrative members in groups), ADR 0018 and ADR 0031 (registry v8). Measurement: `.notes/hub/plans/approaches-audit.md` §1.

## Context
- Austin wants late news and "bad vibes" (the Houston vs Indianapolis kind of game) to count, but only a little.
- Today the narrative ratings sit inside the groups, at the group's average fitted magnitude, with no cap and no measurement. In the 2026 live rows they move the Student 0.7 points on average (up to 2.1) and the Sharp up to 4.4.
- Some of that weight has no evidence at all: a "revenge game" flag is worth 1.2 points, and so is a "look-ahead" flag.
- The audit found:
  - Late status information explains about a tenth of the gap to the market (the Friday report closes 7-10%).
  - The market weighs a new starting quarterback about 1.3 points more than the Student.
  - In the Student, a quarterback out on the depth chart is worth 1.6 points, a quarterback change 1.1, and each starter out 0.2.
- None of the news can be backtested, because the research can't be redone for past weeks.

## Decision
- **Narrative members leave the groups (registry v8):** `narrative.qb_status`, `injury_impact`, `motivation`, `revenge`, `lookahead` and `weather_concern`. Buzz (`sentiment`, `hype`) stays as a persona trait (the Traditionalist listens, the Sharp fades), and so does the Sharp's public-betting read (Market behavior). Neither is in the Student.
- **One news adjustment, in points, added to every line:** `adj = clip(Σ wₖ · (homeₖ − awayₖ), ±1.5)`, applied in logit space at the lock. Weights are declared in `nfl.approaches.news`, each sized by a historical proxy where one exists:

  | Input | Points per unit | Size from |
  |---|---|---|
  | Reporting confirms a different starting QB than the team's last game, not yet on the depth chart (a countable fact) | 1.1 | the Student's `availability.qb_change` (1.07) |
  | `qb_status` (0 / 1 / 2) for a team whose chart doesn't already flag the QB | 0.5 per step | half of `qb1_out` (1.59) per step |
  | Starters the research reports out, net of those the official report the lock reads already lists (`max(0, news.starters_ruled_out - availability.starters_out)`, worked out at the lock) | 0.2 each | `starters_out` (0.22) |
  | `injury_impact` (0-3), only while the official report lists no starter out and the QB isn't flagged | 0.2 per step | `starters_out`, one key starter per step |
  | `motivation` (−1..1) | 0.3 per unit | half of today's 0.59; no history |
  | `revenge`, `lookahead`, `sentiment`, `hype`, `weather_concern`, `coaching_turmoil` | 0 | no evidence that they predict sides |

  The cap of 1.5 points is about 5 points of win chance. With it, news can close a Houston-sized lag, which was about 1.2 points at the lock, but can't override the football.
- **Repeatability decides which ratings count.** Each week three games are researched twice (`nfl narrative repeat`, item A1). A rating whose two runs agree within one step on less than 70% of pairs, once at least 12 pairs exist, gets weight 0. Unmeasured ratings count under the cap. The agreement table is in `marts/narrative_repeat.parquet` and on the evals output.
- **Countable facts instead of moods:** research schema v3 adds `qb_named_starter`, `starters_ruled_out` and `coach_fired_this_week` (optional, cited). Code derives `news.qb_change_confirmed` (the named starter differs from last game's passer and from `availability.charted_qb1`; this is the A6 depth-chart disagreement) and `news.starters_ruled_out` (the record's own count; the net of the official report is taken at the lock, because rebuilds of the injury table would otherwise move a stored number). They are stored point-in-time from now on, so in a season or two they can be backtested like any feature.
- **A football-only twin:** the lock writes `student.core` (the Student without the adjustment, a diagnostic, never a scorecard line) beside `student`. The tracker shows what the news added: live games where it moved the line, and the paired log loss against the twin.
- **A late-status pass** (Thu 07:30 and Sat 10:30 ET, before each lock) re-researches status only: quarterback, injury designations, inactives. It updates the countable facts and `qb_status` / `injury_impact`. The lock never waits for it: `as_of` takes the latest record before the lock, so a missing pass changes nothing. Austin switches it on.

## Consequences
- The backfill doesn't change (narrative is null historically), so the new registry changes no historical number. Live lines change by at most 1.5 points from news, and revenge, look-ahead and buzz no longer move the Student.
- The weights are declared, not learned, and say so on the site. The twin and the repeat table are how they earn or lose their place. The adjustment's record is live-only and small for a season.
- The personas take the same news adjustment as the Student. News is information, not a persona trait. Their characters stay in their group weights and Buzz.
