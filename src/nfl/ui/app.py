"""Disposable POC explorer. Reads marts parquet directly. The real site is React + TS later."""

from __future__ import annotations

import plotly.express as px
import polars as pl
import streamlit as st

from nfl.config import get_paths

st.set_page_config(page_title="NFL matchup POC", layout="wide")
P = get_paths()


@st.cache_data(show_spinner=False)
def load(name: str) -> pl.DataFrame:
    f = P.marts / f"{name}.parquet"
    return pl.read_parquet(f) if f.exists() else pl.DataFrame()


@st.cache_data(show_spinner=False)
def games() -> pl.DataFrame:
    return pl.read_parquet(
        f"{P.curated_table('games').as_posix()}/*/*.parquet", hive_partitioning=True
    )


def page_week() -> None:
    st.header("This week")
    preds = load("predictions")
    g = games()
    upcoming = g.filter(pl.col("result").is_null())
    if upcoming.is_empty() or preds.is_empty():
        st.info("No upcoming games or predictions. Run `nfl predict && nfl grade`.")
        return
    season = int(upcoming["season"].max())
    weeks = sorted(upcoming.filter(pl.col("season") == season)["week"].unique().to_list())
    week = st.selectbox("Week", weeks, index=0)
    slate = upcoming.filter((pl.col("season") == season) & (pl.col("week") == week)).sort(
        "kickoff_utc"
    )
    latest = (
        preds.filter(~pl.col("is_backfill"))
        .sort("lock_ts")
        .group_by(["game_id", "model_id"])
        .last()
    )
    wide = latest.pivot(on="model_id", index="game_id", values=["p_home", "spread_home"])
    df = slate.join(wide, on="game_id", how="left")
    show = df.select(
        pl.col("kickoff_utc")
        .dt.replace_time_zone("UTC")
        .dt.convert_time_zone("America/New_York")
        .dt.strftime("%a %m/%d %I:%M %p")
        .alias("kickoff (ET)"),
        pl.concat_str(["away_team", pl.lit(" @ "), "home_team"]).alias("matchup"),
        pl.col("spread_line").alias("market spread (home)"),
        pl.col("total_line").alias("total"),
        *[c for c in df.columns if c.startswith(("p_home_", "spread_home_"))],
    )
    st.caption(
        "Spreads are home-team margin: positive = home favored. p_home = model win probability for home team."
    )
    st.dataframe(show.to_pandas().round(3), width="stretch", hide_index=True)
    if not latest.is_empty():
        st.caption(
            f"Latest lock: {latest['lock_ts'].max()} UTC. Rows are not re-predicted after kickoff."
        )


def page_scorecard() -> None:
    st.header("Scorecard")
    sc = load("scorecard")
    graded = load("graded")
    if sc.is_empty():
        st.info("Run `nfl grade`.")
        return
    season_rows = sc.filter(pl.col("scope") == "season").sort(["season", "log_loss"])
    st.subheader("By season")
    st.dataframe(
        season_rows.drop("scope", "week").to_pandas().round(4), width="stretch", hide_index=True
    )
    st.caption(
        "Lower log loss and Brier are better. ATS% is the model's pick against the market line; "
        "~50% is expected. Differences between models over one season are mostly noise."
    )
    seasons = sorted(graded["season"].unique().to_list(), reverse=True)
    season = st.selectbox("Cumulative log loss by week", seasons, index=0)
    cum = (
        graded.filter(pl.col("season") == season)
        .sort("week")
        .group_by(["model_id", "week"])
        .agg(pl.col("log_loss").sum(), pl.len().alias("n"))
        .sort(["model_id", "week"])
        .with_columns(
            pl.col("log_loss").cum_sum().over("model_id") / pl.col("n").cum_sum().over("model_id")
        )
    )
    fig = px.line(
        cum.to_pandas(),
        x="week",
        y="log_loss",
        color="model_id",
        markers=True,
        labels={"log_loss": "cumulative mean log loss"},
    )
    st.plotly_chart(fig, width="stretch")
    elo = load("elo_ratings")
    if not elo.is_empty():
        st.subheader("Current Elo ratings")
        st.plotly_chart(
            px.bar(elo.to_pandas(), x="team", y="elo", range_y=[1350, 1750]), width="stretch"
        )


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


def page_audit() -> None:
    st.header("Null-rate audit")
    a = load("audit")
    if a.is_empty():
        st.info("Run `nfl audit`.")
        return
    tbl = st.selectbox("Table", sorted(a["tbl"].unique().to_list()))
    piv = (
        a.filter(pl.col("tbl") == tbl)
        .pivot(on="season", index="col", values="null_rate")
        .sort("col")
    )
    seasons = [c for c in piv.columns if c != "col"]
    fig = px.imshow(
        piv.select(seasons).to_pandas().values,
        x=seasons,
        y=piv["col"].to_list(),
        zmin=0,
        zmax=1,
        color_continuous_scale="Reds",
        text_auto=".1%",
        aspect="auto",
    )
    fig.update_layout(height=max(300, 28 * piv.height + 80), coloraxis_showscale=False)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Share of rows where the column is null, per season. plays:ftn is measured on pass/run plays from 2022."
    )


PAGES = {
    "This week": page_week,
    "Scorecard": page_scorecard,
    "Tendencies": page_tendencies,
    "Audit": page_audit,
}
st.sidebar.title("NFL matchup POC")
st.sidebar.caption(f"data root: {P.root}")
PAGES[st.sidebar.radio("Page", list(PAGES))]()
st.sidebar.markdown(
    "---\nData: nflverse (CC-BY), FTN charting via nflverse (CC-BY-SA 4.0). Fan-made, not affiliated with the NFL."
)
