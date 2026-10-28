"""Explore team tendencies (carried over from the POC explorer). Reads marts/tendencies.parquet."""

from __future__ import annotations

import plotly.express as px
import polars as pl
import streamlit as st

from nfl.config import get_paths

P = get_paths()


@st.cache_data(show_spinner=False)
def load(name: str) -> pl.DataFrame:
    f = P.marts / f"{name}.parquet"
    return pl.read_parquet(f) if f.exists() else pl.DataFrame()


def page_tendencies() -> None:
    st.header("Team tendencies")
    t = load("tendencies")
    if t.is_empty():
        st.info("Run `nfl tendencies`.")
        return
    c1, c2, c3, c4 = st.columns(4)
    season = c1.selectbox("Season", sorted(t["season"].unique().to_list(), reverse=True))
    side = c2.selectbox("Side", ["off", "def"])
    sub = t.filter((pl.col("season") == season) & (pl.col("side") == side))
    metric = c3.selectbox("Metric", sorted(sub["metric"].unique().to_list()))
    situation = c4.selectbox(
        "Situation", sorted(sub["situation"].unique().to_list(), key=lambda s: (s != "all", s))
    )
    d = sub.filter((pl.col("metric") == metric) & (pl.col("situation") == situation)).sort(
        "rate", descending=True
    )
    fig = px.bar(
        d.to_pandas(),
        x="team",
        y="rate",
        hover_data=["n", "n_eff", "raw_rate"],
        title=f"{metric} · {situation} · {season}",
    )
    league = d.select((pl.col("raw_rate") * pl.col("n")).sum() / pl.col("n").sum()).item()
    fig.add_hline(y=league, line_dash="dot", annotation_text=f"league {league:.3f}")
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Bars show `rate`: shrunk toward the league rate (50-play prior) with a 6-week recency half-life. `raw_rate` is the plain empirical rate; `n_eff` is the recency-weighted sample size."
    )

    st.subheader("Compare two teams across situations")
    teams = sorted(sub["team"].unique().to_list())
    a, b = st.columns(2)
    ta = a.selectbox("Team A", teams, index=0)
    tb = b.selectbox("Team B", teams, index=min(1, len(teams) - 1))
    cmp = sub.filter(pl.col("team").is_in([ta, tb]) & (pl.col("metric") == metric)).pivot(
        on="team", index="situation", values="rate"
    )
    ns = sub.filter((pl.col("team") == ta) & (pl.col("metric") == metric)).select(
        "situation", pl.col("n").alias(f"n ({ta})")
    )
    st.dataframe(
        cmp.join(ns, on="situation").to_pandas().round(3), width="stretch", hide_index=True
    )

    st.subheader("Team profile heatmap")
    team = st.selectbox("Team", teams, index=teams.index(ta))
    prof = sub.filter(pl.col("team") == team).pivot(on="situation", index="metric", values="rate")
    st.plotly_chart(
        px.imshow(
            prof.drop("metric").to_pandas().values,
            x=prof.columns[1:],
            y=prof["metric"].to_list(),
            aspect="auto",
            color_continuous_scale="Blues",
            text_auto=".2f",
        ),
        width="stretch",
    )


page_tendencies()
