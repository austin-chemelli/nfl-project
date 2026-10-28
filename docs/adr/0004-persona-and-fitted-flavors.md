# ADR 0004: Two flavors per approach; persona weights proposed by Claude, reviewed by Austin

Status: accepted 2026-10-25; **amended 2026-10-27** (one public flavor per approach, see below).

## Context
Hand-weighted personas are the educational product but will lose to the market on accuracy. The scorecard must stay honest without discarding the personas.

## Options
1. Personas only, uncalibrated.
2. Personas only, calibrated.
3. Persona and fitted flavors per approach, where the fit is a ridge logistic regression shrunk toward the persona's weights (`λ‖w − w_persona‖²`), λ chosen walk-forward; plus one unconstrained global fit.

## Decision
Option 3. Persona flavor: YAML weights, Platt-calibrated walk-forward so the character's *ranking* stands but its confidence is honest. Fitted flavor: shrink-toward-persona ridge; the distance between the two weight vectors is the educational payload ("the Traditionalist weighs rest three times more than history supports"). Global fit feeds the Hypotheses page and is a reference line. Ensemble = mean of fitted-flavor logits, equal weights in 2026. Persona weights are proposed by Claude with a one-line rationale per feature and reviewed/tweaked by Austin in the YAML.

## Consequences
Every approach contributes two scorecard lines; the UI labels the persona line as the character's record. Fitting is ~50 lines of numpy/scipy, no sklearn dependency for the core. FTN-era features are missing before 2022 and are treated as league-average (0 after standardization), which the Hypotheses page must disclose per feature.

## Amendment 2026-10-27: one public line per approach

Showing a persona and a fitted flavor for every approach doubled every table and chart and was too confusing to follow (Austin, after the first click-through). The approaches exist to show how a kind of fan's biases match reality, so the biases must stay visible.

- **Each approach has one public model, `<approach>`** (no flavor suffix): the persona's group weights, **lightly fitted** (ridge toward the persona with a strong, fixed λ so the persona keeps most of its budget; the drift per group is reported), Platt-calibrated. This is what the slate, tracker, ledger and lock artifacts show.
- **The fully fitted version is a diagnostic, not a scorecard line.** It lives in the tracker's "what history would change" comparison (persona weight vs. fitted weight per group, the educational payload) and in the DIY page's `fit_toward`.
- **Calibration stays.** Confidence is learned from history for every persona so the records are comparable; the persona's ranking of games is its own.
- The Student is unchanged: its identity *is* the fitted weights.
- The ensemble is the mean of the four approaches.
