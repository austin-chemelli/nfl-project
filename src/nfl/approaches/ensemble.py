"""Global fit and ensemble (architecture §3.4, ADR 0004).

global    one ridge fit toward zero on every non-market, non-narrative feature in the store. It is
          not an approach: it answers "what does history say each feature is worth?" for the
          Hypotheses page and is a reference line. Market features are excluded so a hypothesis
          reads "does rest predict wins", not "is rest already priced in" (a later, separate fit).
ensemble  retired (ADR 0018) before it ever locked: the mean of the four lines' logits. Nothing
          writes it any more. The Student is the headline line.
"""

from __future__ import annotations

from nfl.approaches.schema import Approach, FitSpec, Weight

GLOBAL_ID = "global"
ENSEMBLE_ID = "ensemble"
HEADLINE_ID = "student"
# weather (ADR 0024) is context: training would see observed kickoff weather and a lock only a
# forecast, so it stays out of every fit (ADR 0031, review finding)
EXCLUDED_FAMILIES = {"market", "narrative", "weather"}
# the neutral-site flag is a rule (engine.NEUTRAL), never a fitted member: it would count twice
EXCLUDED_FEATURES = {"environment.neutral_site"}


def global_approach(known_features: set[str]) -> Approach:
    feats = sorted(
        f
        for f in known_features
        if f.split(".", 1)[0] not in EXCLUDED_FAMILIES and f not in EXCLUDED_FEATURES
    )
    return Approach(
        id=GLOBAL_ID,
        name="Global fit",
        blurb="What history says each feature is worth, with no persona.",
        emphasis=[],
        calibration="none",
        intercept=Weight(w=0.0, why="Fitted home field"),
        weights={f: Weight(w=0.0, why="Fitted from history") for f in feats},
        fit=FitSpec(shrink_to_persona=False),
    )
