# ADR 0018: Model wave 2: football features only, line moves capped, the Student is the headline

Status: accepted 2026-11-04 (Austin). Amends ADR 0012 (groups), ADR 0013 (market behavior) and ADR 0004 (the ensemble).

## Context
Austin's first week with the live site raised four problems. Scheme and coaching tendencies moved win probabilities with no evidence that they predict wins. The Sharp sat 24 points from its own football read in JAX @ BAL because of one feature. The ensemble and the Student were hard to tell apart, and there were too many lines to follow. Special teams, which can decide a game, had no group of its own.

The evidence: 13 of the 26 coaching and scheme features exist, and none reaches "matters" on the Hypotheses page (3 weak, 10 no evidence). The other 13 and all 7 matchup features were never built. Line moves across 44 live games run a median of 0.5 points and 2.5 at the 95th percentile, and the declared scale is 1.5, so JAX @ BAL's 12.5 entered the model at -8.3 SD.

## Decision
- **Context-only groups.** `coaching`, `off_scheme`, `def_scheme` and `matchups` are `context_only`: they carry no weight in any public line, and the schema rejects them in an approach. They stay on the site as things to look at. Global keeps them: it is not a public line, and the Hypotheses page reads its verdicts from it. A group earns its way back through interaction research (offense style against defense style), as a new ADR.
- **Line moves are capped at ±4.5 points** inside the model (`FEATURE_CAPS`), applied to the raw value before standardizing. It passes every move seen so far except JAX @ BAL. The stored feature and the site keep the real number.
- **The Student and the Analyst read line moves too**, at half the Sharp's weight. This reverses ADR 0013's "the Student stays market-free". The rule that matters stands: no approach sees the market's forecast. The weight is declared, not learned, because line moves exist live only. The public split stays the Sharp's. The Traditionalist has no market input, for character.
- **Special teams is a group**: overall value (moved from Quality), kicking, punt unit and kickoff unit, all season-to-date EPA per game, demeaned by play type. Kicking uses EPA, which already accounts for distance, so no new expectation table is needed.
- **Pressure rate moves to Defense.** This is a football judgment: its verdict is "no evidence".
- **The ensemble is retired.** It never locks and leaves the site, the README and the tiles. The Student is the headline line. Its backfill rows are derived and go.

## Consequences
- The composites changed, so `REGISTRY_VERSION` is 6 and every fit is new. It lands before the first public lock (Thu 2026-11-05), so no live row exists on the old model and the public record starts on one version.
- The Student's "learns only from results" is no longer quite true, and its description says so.
- Removing weak groups leaves less for the approaches to disagree about.
- Special teams adds little predictive signal: overall value ranks 20th of the 21 features that reach "matters". It is in the model because it belongs in the picture of a game.
