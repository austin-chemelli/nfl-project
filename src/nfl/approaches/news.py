"""The news adjustment (ADR 0032): late news reaches every line as one bounded number of points.

    adj = clip(Σ wₖ · (homeₖ − awayₖ), ±CAP_PTS)         home-minus-away, points; > 0 helps the home team

The weights are declared here, not fitted: each is sized by a historical proxy where one exists (the
`why`) and none can be backtested (the research can't be redone for past weeks). The adjustment is
added to every public line in logit space at the line's own spread, so the cap is exact in points:

    adj_logit = logit(Φ((spread_core + adj) / 13.5)) − logit_core

`student.core` (the Student without it) is written beside the Student at the lock and is the twin the
tracker judges the news against. Inputs are the features known before the lock: the narrative ratings
and two countable facts (`news.*`, written by `features/narrative.py`; absent = 0). Two guards:

- no double count: a team whose depth chart already flags the quarterback (`availability.qb1_out`,
  `availability.qb_change`) gets no `qb_status` and no `injury_impact`; a confirmed change counts
  only while `availability.qb_change` is 0, and then it is the team's whole QB story (no
  `qb_status`, `injury_impact` or `starters_ruled_out` on top); `injury_impact` counts only while
  the official report lists no starter out (`availability.starters_out` is 0); ruled-out starters
  count net of the official report: max(0, `news.starters_ruled_out` - `availability.starters_out`),
  worked out here at the lock from the report rows the lock reads;
- repeatability: a rating whose two research runs agree within one step on fewer than 70% of pairs,
  once at least 12 pairs exist, gets weight 0 (`nfl.llm.repeat.agreement`; unmeasured counts in full).

Pure: no model, no store writes. Historically every input is null, so the backfill never moves.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass

import numpy as np
import polars as pl
from scipy.special import expit, logit
from scipy.stats import norm

from nfl.config import Paths

CAP_PTS = (
    1.5  # about 5 points of win chance: closes a Houston-sized lag, can't override the football
)
MIN_AGREEMENT = 0.70
MIN_PAIRS = 12
SD_MARGIN = 13.5  # the engine's Normal-margin convention (engine.SD_MARGIN)
P_CLIP = 1e-6


@dataclass(frozen=True)
class Weight:
    feature: str
    pts: float  # points per unit of the team's own value; sign = what it does to that team
    label: str  # plain words for the site, e.g. "QB questionable"
    why: str


_W = [
    Weight(
        "news.qb_change_confirmed", -1.1, "a new starting QB",
        "Reporting confirms a different starting QB than the team's last game, not yet on the depth "
        "chart. Sized from the Student's availability.qb_change (1.07 points).",
    ),
    Weight(
        "narrative.qb_status", -0.5, "QB status",
        "0 healthy, 1 questionable, 2 backup or unknown, for a team whose chart doesn't already flag "
        "the QB. Half of qb1_out (1.59 points) per step.",
    ),
    Weight(
        "news.starters_ruled_out", -0.2, "starters ruled out",
        "Starters the research reports out, minus those the official report the lock reads already "
        "lists (availability.starters_out), so none counts twice. The Student's starters_out is "
        "worth 0.22 points each.",
    ),
    Weight(
        "narrative.injury_impact", -0.2, "injuries",
        "0 to 3, one key starter per step, sized like starters_out (0.22 points).",
    ),
    Weight(
        "narrative.motivation", 0.3, "motivation",
        "-1 nothing to play for, +1 must-win. Half of the 0.59 points it was worth inside a group; "
        "no history.",
    ),
]  # fmt: skip
# Not here, so weight 0 (no evidence they predict sides): revenge, lookahead, sentiment, hype,
# weather_concern, coaching_turmoil.
WEIGHTS: dict[str, float] = {w.feature: w.pts for w in _W}
WHY: dict[str, str] = {w.feature: w.why for w in _W}
LABELS: dict[str, str] = {w.feature: w.label for w in _W}

QB_GATED = "narrative.qb_status"  # counts only while the chart doesn't flag the QB
CHANGE_GATED = "news.qb_change_confirmed"  # counts only while availability.qb_change is 0
RULED_OUT = "news.starters_ruled_out"  # net of the official report, at the lock
INJURY = "narrative.injury_impact"  # counts only while the official report lists no starter out
GATES = ("availability.qb1_out", "availability.qb_change", "availability.starters_out")
INPUTS = [*WEIGHTS, *GATES]
SIDES = ("home", "away")


def agreement_table(paths: Paths) -> dict[str, tuple[float, int]]:
    """rating -> (share of pairs agreeing within one step, n pairs), from the repeat runs. Empty when
    nothing is measured (or the module isn't there yet): unmeasured ratings count in full."""
    try:
        from nfl.llm import repeat  # lazy: written by the research side

        return dict(repeat.agreement(paths))
    except ImportError, AttributeError:
        return {}
    except Exception as e:  # noqa: BLE001  (a corrupt or unreadable repeat file never blocks a lock)
        warnings.warn(f"news: repeat agreement unreadable ({type(e).__name__}); declared weights", stacklevel=2)  # fmt: skip
        return {}


def weights(paths: Paths | None = None) -> dict[str, float]:
    """The declared weights with every unrepeatable rating at 0 (agreement < 0.70 over >= 12 pairs)."""
    out = dict(WEIGHTS)
    if paths is None:
        return out
    for rating, (share, n) in agreement_table(paths).items():
        feat = rating if rating in out else f"narrative.{rating}"
        if feat in out and n >= MIN_PAIRS and share < MIN_AGREEMENT:
            out[feat] = 0.0
    return out


def _team_values(asof: pl.DataFrame, game_ids: list[str]) -> dict[tuple[str, str, str], float]:
    """(game_id, side, feature) -> value for the inputs, non-null only."""
    if asof.is_empty():
        return {}
    x = asof.filter(
        pl.col("game_id").is_in(game_ids)
        & pl.col("feature").is_in(INPUTS)
        & (pl.col("side") != "game")
        & pl.col("value").is_not_null()
    )
    return {
        (r[0], r[1], r[2]): float(r[3])
        for r in x.select("game_id", "side", "feature", "value").iter_rows()
    }


def reasons_for(
    vals: dict[tuple[str, str, str], float], gid: str, w: dict[str, float]
) -> list[dict]:
    """The inputs behind one game's adjustment, largest first: {input, team, value, pts}. `pts` is
    home-minus-away (positive helps the home team), before the cap."""
    out = []
    for side, sign in (("home", 1.0), ("away", -1.0)):
        get = lambda f, s=side: vals.get((gid, s, f), 0.0)
        flagged = get("availability.qb1_out") != 0 or get("availability.qb_change") != 0
        changed = get(CHANGE_GATED) != 0 and get("availability.qb_change") == 0  # the QB story
        official = get("availability.starters_out")
        for feat, wt in w.items():
            v = get(feat)
            if feat == RULED_OUT:
                v = max(0.0, v - official)
            if not v or not wt:
                continue
            if feat == CHANGE_GATED and not changed:
                continue
            if changed and feat in (QB_GATED, INJURY, RULED_OUT):
                continue  # one QB situation, one QB term
            if feat == QB_GATED and flagged:
                continue
            if feat == INJURY and (flagged or official != 0):
                continue
            out.append(
                {"input": feat, "team": side, "value": round(v, 4), "pts": round(sign * wt * v, 4)}
            )
    return sorted(out, key=lambda r: (-abs(r["pts"]), r["input"], r["team"]))


def adjustment(
    asof: pl.DataFrame, game_ids: list[str], w: dict[str, float] | None = None
) -> pl.DataFrame:
    """game_id, adj_pts (capped), reasons (JSON). `asof` = store.as_of rows (long, per side)."""
    w = WEIGHTS if w is None else w
    vals = _team_values(asof, game_ids)
    pts, reasons = [], []
    for gid in game_ids:
        rs = reasons_for(vals, gid, w) if vals else []
        raw = sum(r["pts"] for r in rs)
        pts.append(float(np.clip(raw, -CAP_PTS, CAP_PTS)))
        reasons.append(json.dumps(rs))
    return pl.DataFrame(
        {"game_id": game_ids, "adj_pts": pts, "reasons": reasons},
        schema={"game_id": pl.Utf8, "adj_pts": pl.Float64, "reasons": pl.Utf8},
    )


def adj_logit(spread_core: np.ndarray, logit_core: np.ndarray, adj_pts: np.ndarray) -> np.ndarray:
    """The adjustment in logit units at each line's own spread: the shifted spread is exactly
    spread_core + adj_pts."""
    p = np.clip(norm.cdf((spread_core + adj_pts) / SD_MARGIN), P_CLIP, 1 - P_CLIP)
    return np.where(adj_pts == 0.0, 0.0, logit(p) - logit_core)


def apply(scored: pl.DataFrame, adj: pl.DataFrame) -> pl.DataFrame:
    """Add the adjustment to a scored frame (engine.Model.score output): p_home, spread_home, logit
    and contributions (a `news` entry when it is not 0, so they still sum to the logit). Adds `news_pts` and
    `news_reasons`. A game without an adjustment row is left as it is."""
    f = scored.join(adj, on="game_id", how="left").with_columns(
        pl.col("adj_pts").fill_null(0.0), pl.col("reasons").fill_null("[]")
    )
    pts = f.get_column("adj_pts").to_numpy()
    dl = adj_logit(f.get_column("spread_home").to_numpy(), f.get_column("logit").to_numpy(), pts)
    new_logit = f.get_column("logit").to_numpy() + dl
    p = np.where(pts == 0.0, f.get_column("p_home").to_numpy(), expit(new_logit))
    p = np.clip(p, P_CLIP, 1 - P_CLIP)
    blobs = []
    for c, d in zip(f.get_column("contributions").to_list(), dl, strict=True):
        if c is None:
            blobs.append(None)
            continue
        if d == 0.0:  # nothing to add: historical rows keep their exact contributions
            blobs.append(c)
            continue
        blobs.append(json.dumps(json.loads(c) | {"news": round(float(d), 6)}))
    return f.with_columns(
        pl.Series("p_home", p),
        pl.Series("spread_home", f.get_column("spread_home").to_numpy() + pts),
        pl.Series("logit", new_logit),
        pl.Series("contributions", blobs, dtype=pl.Utf8),
        pl.col("adj_pts").alias("news_pts"),
        pl.col("reasons").alias("news_reasons"),
    ).drop("adj_pts", "reasons")


def _label(feat: str, v: float) -> str:
    """Plain words for one input, from its value ('QB questionable', '2 starters ruled out')."""
    n = round(abs(v))
    if feat == "narrative.qb_status":
        return "QB questionable" if v < 1.5 else "backup QB or unknown"
    if feat == "news.qb_change_confirmed":
        return "a new starting QB confirmed"
    if feat == RULED_OUT:
        return f"{n} starter{'s' if n != 1 else ''} ruled out"
    if feat == "narrative.injury_impact":
        return {1: "a role player or two hurt", 2: "a key starter hurt"}.get(
            n, "several key starters hurt"
        )
    if feat == "narrative.motivation":
        return "must-win" if v > 0 else "nothing to play for"
    return LABELS.get(feat, feat)


def describe(reasons: list[dict], home: str, away: str) -> list[dict]:
    """Reasons for the site: {label, team, pts}, `pts` = points the item moves the named team's own
    line (negative = hurts that team). Largest first."""
    out = []
    for r in reasons:
        team = home if r["team"] == "home" else away
        own = r["pts"] if r["team"] == "home" else -r["pts"]
        out.append({"label": _label(r["input"], r["value"]), "team": team, "pts": round(own, 2)})
    return out


def points_from_logit(logit_total: float, news_logit: float) -> float:
    """The adjustment in points recovered from a stored row: the final spread minus the spread the
    logit had before the news entry."""
    return float(
        norm.ppf(expit(logit_total)) * SD_MARGIN
        - norm.ppf(expit(logit_total - news_logit)) * SD_MARGIN
    )
