"""Global fit and ensemble (architecture §3.4, ADR 0004).

global    one ridge fit toward zero on every non-market, non-narrative feature in the store. It is
          not an approach: it answers "what does history say each feature is worth?" for the
          Hypotheses page and is a reference line. Market features are excluded so a hypothesis
          reads "does rest predict wins", not "is rest already priced in" (a later, separate fit).
ensemble  σ(mean of the public lines' logits) over the non-shadow approaches, equal weights (2026).
          Contributions are the per-key mean of the members' contributions, so they still sum to
          the ensemble logit.
"""

from __future__ import annotations

import json

import numpy as np
import polars as pl
from scipy.special import expit
from scipy.stats import norm

from nfl.approaches.engine import SD_MARGIN
from nfl.approaches.schema import Approach, FitSpec, Weight

GLOBAL_ID = "global"
ENSEMBLE_ID = "ensemble"
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


def combine(member_preds: list[pl.DataFrame]) -> pl.DataFrame:
    """member_preds: frames with game_id, logit, contributions (engine.Model.score output), all for
    the same games. Returns game_id, p_home, spread_home, logit, contributions."""
    if not member_preds:
        raise ValueError("ensemble needs at least one member")
    base = member_preds[0].select("game_id")
    for m in member_preds[1:]:
        if m.height != base.height or set(m["game_id"]) != set(base["game_id"]):
            raise ValueError("ensemble members must cover the same games")
    aligned = [base.join(m, on="game_id", how="left") for m in member_preds]
    logit = np.mean(np.column_stack([a["logit"].to_numpy() for a in aligned]), axis=1)
    k = len(aligned)
    blobs = []
    for i in range(base.height):
        acc: dict[str, float] = {}
        for a in aligned:
            for key, v in json.loads(a["contributions"][i]).items():
                acc[key] = acc.get(key, 0.0) + v / k
        blobs.append(json.dumps({key: round(v, 6) for key, v in acc.items()}))
    p = np.clip(expit(logit), 1e-6, 1 - 1e-6)
    return pl.DataFrame(
        {
            "game_id": base["game_id"],
            "p_home": p,
            "spread_home": norm.ppf(p) * SD_MARGIN,
            "logit": logit,
            "contributions": blobs,
        }
    )
