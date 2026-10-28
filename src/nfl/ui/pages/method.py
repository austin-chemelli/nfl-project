"""Method & data (M5.6): what this is, how a lock works, point-in-time rules, honest limits,
data freshness and the null-rate audit. Reads meta.json and audit.json via nfl.ui.data."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nfl.ui import data
from nfl.ui.tracker_helpers import humanize_age, style, table_view

DOCS = "https://github.com/austin-chemelli/nfl-project/tree/main/docs"

st.header("Method & data")

st.markdown(
    """
**What this is.** A weekly NFL preview and prediction tool that is educational first and
market-aware second. Several *approaches* (the Traditionalist, the Analyst, the Sharp, the
Student) weigh the same shared evidence differently, like different kinds of fans, plus an
ensemble (their average). Each approach is **one line**: the persona's own weights, lightly
fitted to history and then calibrated. Models produce every number; an LLM, where used, only
explains and is never allowed to introduce a statistic.

**The market is the reference, never an input** (ADR 0013). The betting market's forecast (the
spread and moneyline probability) is the line every approach is compared against. No approach
is allowed to read it. The Sharp is the one that reads market *behavior* (line moves, public
betting share, disagreement between books) as a capped supplement, never the forecast itself.
Feeding the market to a model and then crediting the model for matching the market was the
mistake that made an early Sharp look as good as the market.

**How it is scored.** Every approach is scored in public against the market and a naive baseline
on forecast quality (log loss, calibration), on odds-weighted paper bets, and on how often it
was right when it disagreed with the market. Forecast quality comes first; betting is a lens.

**How numbers are shown.** Probabilities and rates are percentages, differences are points of
win probability, weights are shares of a 100-point attention budget, and team gaps are
percentile ranks. Log-odds never appear. Log loss is the scoring rule (lower is better, 0.693 is
a coin flip), so it is always shown next to the market's score and in words, for example "0.630,
about 0.02 worse than the market". Differences under 0.005 are noise at this sample size.
"""
)

st.subheader("How a lock works")
st.markdown(
    """
A *lock* is the moment predictions are frozen before kickoff, twice a week (Thursday and
Saturday). It:

1. Downloads the latest public data and an odds snapshot, then rebuilds every feature, each row
   stamped with the time it became known.
2. Scores the games that have not kicked off, using models fitted only through last season:
   every approach, the ensemble, and the market, Elo and naive reference lines.
3. Appends the predictions (they are never edited) and opens paper bets at the current odds.
4. Writes a signed-off file with a checksum and commits it, so the record cannot be quietly
   rewritten. A lock refuses games that have already kicked off, so the live record cannot be
   backfilled.
"""
)

st.subheader("Point-in-time rules")
st.markdown(
    """
- A prediction may only use data that was known **before** the lock time.
- Models used in season S are trained through season S-1 and frozen all year.
- Pre-season "backfill" scores (2005 to 2025 backtest, and weeks before the first live lock) use
  synthetic locks and frozen models. They are scored after the fact, so they are weaker evidence
  than live weeks.
- When a result looks too good, assume leakage before skill.
"""
)

st.subheader(
    "Leaks and bugs we found",
    help="Each of these made a model look better or worse than it was. They are listed so you "
    "can judge how much to trust the rest.",
)
st.markdown(
    """
- **Quarterback starter leak.** The "projected starter" was the passer with the most dropbacks
  in the game, which leaked in-game injuries and benchings into about 3% of team-games. The Sharp
  briefly "beat the market" with an interval below zero. It now uses the game's first passer,
  with a regression test.
- **Market miscalibration.** The remaining Sharp edge was exactly the error of a spread-only
  probability formula (the calibrated spread scored 0.6083, identical to the Sharp). The market
  line is now the vig-free moneyline probability, which removes that fake edge.
- **Lookahead definition.** The "lookahead" feature (next opponent's strength) mostly measured
  "this opponent is weak", a copy of team strength, and fit with the wrong sign. It is now the
  next opponent's rating against an average team, and it comes out weak with an interval that
  includes zero.
- **Team codes.** Play-by-play prints current team codes (LA, LAC, LV) for every season, while
  schedules use the historical ones (STL, SD, OAK). Plays for relocated teams were silently
  dropped from strength features until we joined on franchise codes.
- **Kickoff times and old injury files.** 1999 schedules have no kickoff times (imputed by slot
  and flagged), and older injury files store the season as a decimal.
"""
)

st.subheader("Honest limits")
st.markdown(
    """
- Football data is observational and samples are small: about 180 live games a season cannot
  rank models, and one season's paper profit is mostly noise.
- Markets are efficient. In the 2005 to 2025 backtest every approach trails the market by about
  0.015 to 0.02 log loss, and when an approach disagrees with the market by 10+ points the market has
  been right more often.
- Persona weights are opinions. History-fitted weights describe the past, not the future.
- The Sharp's market-behavior inputs (line moves, public betting share) exist only for live
  games, so its backtest is thin.
- Narrative (news) features exist only for live games; no history to fit.
"""
)

st.subheader(
    "Data freshness",
    help="When each source was last downloaded; stale data would make a lock weaker.",
)
m = data.meta() or {}
a = data.audit() or {}
fresh = a.get("freshness") or m.get("freshness") or {}
if not fresh:
    st.info(data.SITE_MISSING)
else:
    df = pd.DataFrame(
        {
            "Dataset": list(fresh),
            "Latest snapshot": [
                f"{v[:4]}-{v[4:6]}-{v[6:8]} {v[9:11]}:{v[11:13]} UTC" if v else "–"
                for v in fresh.values()
            ],
            "Age": [humanize_age(v) for v in fresh.values()],
        }
    )
    st.dataframe(df, width="stretch", hide_index=True)
    if m.get("generated_at"):
        st.caption(f"Site data generated {m['generated_at']}.")

st.subheader(
    "Null-rate audit",
    help="How much of each column is missing, by season. Missing values are handled explicitly, not silently filled.",
)
nr = pd.DataFrame(a.get("null_rates") or [])
if nr.empty:
    st.info("No null-rate audit yet. Run `uv run nfl audit` then `uv run nfl site`.")
else:
    st.caption(
        "Share of missing values per column and season. Dark cells are columns that are often "
        "empty (for example, FTN charting starts in 2022), which features handle explicitly."
    )
    tbls = sorted(nr["tbl"].unique())
    t = st.selectbox("Table", tbls, key="audit_tbl")
    d = nr[nr["tbl"] == t]
    piv = d.pivot_table(index="col", columns="season", values="null_rate", aggfunc="max")
    piv = piv.loc[piv.max(axis=1).sort_values(ascending=False).index]
    shown = piv.head(40)
    fig = go.Figure(
        go.Heatmap(
            z=shown.values, x=[str(c) for c in shown.columns], y=list(shown.index),
            zmin=0, zmax=1, colorscale=[[0, data.NEUTRAL[data.theme()]["mid"]], [1, data.color("analyst")]],
            colorbar={"title": "null rate", "tickformat": ".0%"},
            hovertemplate="%{y}, %{x}<br>%{z:.1%} null<extra></extra>",
        )
    )  # fmt: skip
    style(fig, 120 + 22 * len(shown), "Season")
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, width="stretch")
    if len(piv) > len(shown):
        st.caption(
            f"Top {len(shown)} of {len(piv)} columns by null rate; the rest are in the table."
        )
    table_view(d, "Table view: null rates")

st.subheader("Docs, credits and license")
st.markdown(
    f"""
- Design docs, decisions (ADRs), tasks, journal and runbook: [{DOCS}]({DOCS})
- Data: [nflverse](https://github.com/nflverse) (CC-BY 4.0), including FTN charting (CC-BY-SA 4.0);
  odds from [The Odds API](https://the-odds-api.com).
- Code is MIT-licensed; published derived data (predictions, features, scorecards) is CC-BY-SA 4.0.
- Fan-made, not affiliated with the NFL.
"""
)
