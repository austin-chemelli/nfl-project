# ADR 0012: Two-level features: groups with fitted inner weights, personas weigh groups

Status: accepted 2026-10-27.

## Context
The feature list is heading toward 60+ (ADR 0003 families, the 2026-10-27 ideas note). Hand-setting 60 persona weights is not feasible, the DIY page cannot ask users for 60 sliders, and most low-level features are noise on their own. Austin's proposal: group features into a small number of high-level ones, weigh the groups by hand, and let the backfill learn the weights *inside* each group.

## Decision
Each feature belongs to exactly one **group**. A group's value for a game is a composite:

```
c_g = Σ_{f ∈ g} v_{g,f} · z_f        (z = standardized home − away feature; v normalized so Var(c_g) = 1 on the training window)
logit = b + Σ_g W_g · c_g
```

- **Inner weights `v` belong to the data, not the persona.** *Amended 2026-10-27 during M2.8:* each group's `v` is a walk-forward ridge fit of the outcome on **that group's members only**, shrunk toward each member's declared sign × 0.05 with λ = 3000 (validation 2022–24: toward 0 at λ 100 gave 0.6280 and 12 sign flips; toward sign at 3000 gave 0.6231 and 1 flip; equal weights 0.6265), rescaled to unit composite variance; members with fewer than 200 non-null training games (narrative, live-only) get their declared sign at the group's mean fitted magnitude. The original text used the joint global fit's coefficients restricted to the group; in the joint fit, overlapping features trade weight between groups (e.g. the Sharp's fitted defensive EPA flipped sign), so composites would not mean what their names say. Overlap between groups is handled one level up, by the group weights. Original wording: they are the walk-forward global fit's coefficients restricted to the group's features (same training window rules as ADR 0005), rescaled to unit composite variance. Before a fit exists they default to equal magnitudes with the group's declared signs. All personas and the DIY page share the same `v`; the same composite means the same thing everywhere.
- **Personas and users weigh groups** (`W`, about ten numbers). The persona flavor is `W` from the YAML with Platt calibration; the fitted flavor is ridge on the composites, shrunk toward the persona's `W` (ADR 0004 unchanged, one level up).
- **Overrides are allowed, not default.** A YAML or the DIY page may override `v` for a group; overrides are re-normalized to unit variance so `W` keeps its meaning.
- **The Student** (`configs/student.yaml`) is the data-only baseline: every non-market, non-buzz group starts at the same weight and the fitted flavor lets history move them. *(The original claim that all-ones group weights reproduce the global fit no longer holds after the amendment above; the global fit stays as the Hypotheses source.)*
- The low-level fit (ridge on all features) stays as the source for the Hypotheses page and for `v`.

Groups (chosen 2026-10-27 after comparing four options, full membership in `docs/feature-groups.md`): Quality, Offense, Defense, Quarterback, Health, Form, Stakes, Rest & travel, Venue & weather, Coaching, Offensive scheme, Defensive scheme, Matchups, Market, Buzz. Fifteen, each with one meaning; the UI may show them under six headings that carry no weights.

## Options considered
1. Flat features, persona weights on each (today). Rejected: does not scale past ~20 features.
2. Groups with inner weights fitted *per persona* (bilinear, alternating least squares). Rejected: composites would mean different things per persona, and the DIY page would need its own fit per user.
3. Groups with shared, data-fitted inner weights (chosen).
4. A learned nonlinear model (small MLP, GBM) per approach. Deferred: this design is a two-layer linear network with a frozen, interpretable first layer; a learned first layer or a nonlinearity is the offseason ML extension, scored by the same harness and the same leakage tests.

## Consequences
Persona YAMLs move to group weights plus optional overrides; the three personas get re-proposed at the group level and re-reviewed. The engine and the fitter gain a composition step; contributions are reported per group and, on drill-in, per feature. The DIY page becomes ten sliders. Changing a group's membership changes its composite, so group membership is versioned with the fit artifact and a change makes a new `model_version`. Game-level features (dome, primetime) sit in groups like any other, as standardized values rather than differences.
