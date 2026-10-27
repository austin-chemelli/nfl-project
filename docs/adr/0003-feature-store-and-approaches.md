# ADR 0003: Feature store + approaches replace "model philosophies"

Status: accepted 2026-10-25. Supersedes the brief's "Elo / EPA / Monte Carlo / market / ensemble" model list and the 2026-10-23 "four model lines" decision.

## Context
The product goal shifted (2026-10-25) from a betting-flavored predictor to an educational preview tool: several lenses that weigh the same evidence differently, like different fans would, an ensemble, and divergence from the market as the interesting signal. Separate model families (Elo, EPA ratings, drive sim) cannot share features or explain *why* they disagree.

## Options
1. Keep independent model families and present them as lenses.
2. One long, as-of stamped feature store; each approach is a config over the same features; a linear scoring engine produces probability, spread and per-feature contributions.
3. Option 2 with non-linear learners (GBMs) per approach.

## Decision
Option 2. Features are `(season, week, game_id, side, feature, value, known_as_of, source, version)`; the engine builds a standardized home-minus-away vector per game; an approach is YAML (families it emphasizes, weights, calibration). Elo, the market baseline and the naive baseline survive as features and reference lines. Approaches in 2026: Traditionalist, Analyst, Sharp on the public scorecard; Narrative captured live in shadow; Matchup in the offseason. Each approach may carry weight on every family; the name says what it weighs most.

## Consequences
Contributions are additive and explainable, which the game page depends on. Linear-in-features limits accuracy, which is acceptable because the fitted flavors and the market remain the honest references (ADR 0004). Adding a feature is a builder plus a line in a YAML. Monte Carlo and non-linear models become offseason experiments that must emit the same prediction rows.
