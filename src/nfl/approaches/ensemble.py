"""Global fit and ensemble (architecture §3.4, ADR 0004).

global    one ridge fit toward zero on every non-market, non-narrative feature in the store. It is
          not an approach: it answers "what does history say each feature is worth?" for the
          Hypotheses page and is a reference line. Market features are excluded so a hypothesis
          reads "does rest predict wins", not "is rest already priced in" (a later, separate fit).
ensemble  retired (ADR 0018): the mean of the four lines' logits, scored until 2026 Week 9. Its live
          rows stay in the record; nothing writes new ones. The Student is the headline line.
"""

from __future__ import annotations

from nfl.approaches.schema import Approach, FitSpec, Weight

GLOBAL_ID = "global"
ENSEMBLE_ID = "ensemble"
HEADLINE_ID = "student"
EXCLUDED_FAMILIES = {"market", "narrative"}


def global_approach(known_features: set[str]) -> Approach:
    feats = sorted(f for f in known_features if f.split(".", 1)[0] not in EXCLUDED_FAMILIES)
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
