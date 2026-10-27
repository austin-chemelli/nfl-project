# ADR 0004: Two flavors per approach; persona weights proposed by Claude, reviewed by Austin

Status: accepted 2026-10-25.

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
