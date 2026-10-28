"""Season view (M5.13): one weight set against every game of one season.

Pick a season (and optionally a team) and a weight set: your Build-your-own weights (the `?w=`
query string, which the DIY page's best/worst season callouts pass along), or one of the four
approaches. Shows your win probability for the home team next to the market's, the result, whether
the pick was right, and the group that pushed hardest. Reads marts/site/season_<yyyy>.json for the
games and diy_matrix.json for the walk-forward calibration (nfl diy-matrix writes both).
"""

from __future__ import annotations

import json

import numpy as np
import plotly.graph_objects as go
import polars as pl
import streamlit as st

from nfl.approaches import diy as engine
from nfl.ui import data

MATRIX_FILE = data.SITE / "diy_matrix.json"
YOURS = "Your weights (from Build your own)"
APPROACH_SETS = {
    "traditionalist": "The Traditionalist",
    "analyst": "The Analyst",
    "sharp": "The Sharp",
    "student": "The Student",
}
SET_IDS = {"yours": YOURS} | APPROACH_SETS
EPS = 1e-6


@st.cache_resource(show_spinner="Loading the matrix...")
def load_matrix() -> dict | None:
    if not MATRIX_FILE.exists():
        return None
    return engine.prepare(json.loads(MATRIX_FILE.read_text()))


@st.cache_data(show_spinner=False)
def load_season(season: int) -> dict | None:
    f = data.SITE / f"season_{season}.json"
    return json.loads(f.read_text()) if f.exists() else None


def _qp(key: str, default: str = "") -> str:
    v = st.query_params.get(key)
    return default if v is None else str(v)


def weights_for(set_id: str, m: dict, yours: dict[str, float]) -> dict:
    """Group weights (or per-season weights for the Student) for a weight set."""
    if set_id == "yours":
        capped, _ = engine.cap_market(yours)
        tot = sum(abs(v) for v in capped.values()) or 1.0
        return {g: v / tot for g, v in capped.items()}
    if set_id == "student":
        return {int(s): v["W"] for s, v in m["student_fitted"].items()}
    return dict(m["personas"][set_id]["W"])


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def season_frame(doc: dict, m: dict, weights: dict) -> pl.DataFrame:
    """One row per game: probabilities, result, pick correctness, and the biggest group push."""
    season = int(doc["season"])
    sp = engine.season_predictions(weights, m, season)
    p_by_id = dict(zip(sp["game_id"].tolist(), sp["p"].tolist(), strict=True))
    p = np.array([p_by_id[g] for g in doc["game_id"]])
    groups = list(doc["groups"])
    C = np.column_stack([np.asarray(doc["c"][g], dtype=float) for g in groups])
    W = engine._season_weights(weights, season, groups)
    contrib = sp["calib_a"] * W[None, :] * C  # logit units, summed with the intercept into p
    logit = np.log(np.clip(p, EPS, 1 - EPS) / np.clip(1 - p, EPS, 1 - EPS))
    push = 100 * (
        p[:, None] - _sigmoid(logit[:, None] - contrib)
    )  # win-% points moved by each group
    j = np.argmax(np.abs(push), axis=1)
    top = push[np.arange(len(p)), j]
    y = np.asarray(doc["home_won"], dtype=float)
    mk = np.array([np.nan if v is None else v for v in doc["market_p"]], dtype=float)
    pc = np.clip(p, EPS, 1 - EPS)
    ll = -(y * np.log(pc) + (1 - y) * np.log(1 - pc))
    mc = np.clip(mk, EPS, 1 - EPS)
    mll = -(y * np.log(mc) + (1 - y) * np.log(1 - mc))
    return pl.DataFrame(
        {
            "game_id": doc["game_id"],
            "week": doc["week"],
            "home": doc["home"],
            "away": doc["away"],
            "kickoff": doc["kickoff"],
            "result": doc["result"],
            "home_won": doc["home_won"],
            "p": p,
            "market_p": mk,
            "correct": (p >= 0.5) == (y == 1),
            "market_correct": [
                None if np.isnan(a) else bool((a >= 0.5) == (b == 1))
                for a, b in zip(mk, y, strict=True)
            ],
            "ll": ll,
            "market_ll": mll,
            "push_group": [
                None if abs(t) < 0.05 else groups[k] for k, t in zip(j, top, strict=True)
            ],
            "push_pts": top,
        },
        strict=False,
    )


def result_text(r: dict) -> str:
    res = r["result"]
    if res is None:
        return "–"
    team = r["home"] if res > 0 else r["away"]
    return f"{team} by {abs(res)}"


def push_text(r: dict) -> str:
    g = r["push_group"]
    if g is None:
        return "no strong push"
    toward = r["home"] if r["push_pts"] > 0 else r["away"]
    return f"{data.group(g)['name']}: {abs(r['push_pts']):.1f} pts toward {toward}"


def week_table(df: pl.DataFrame) -> pl.DataFrame:
    """Per week: games, summed edge over the market (market log loss minus yours; up = better)."""
    return (
        df.filter(pl.col("market_ll").is_not_nan())
        .group_by("week")
        .agg(
            pl.len().alias("games"),
            (pl.col("market_ll") - pl.col("ll")).sum().alias("edge_sum"),
            (pl.col("market_ll") - pl.col("ll")).mean().alias("edge"),
            pl.col("correct").sum().alias("right"),
        )
        .sort("week")
    )


def week_chart(wk: pl.DataFrame) -> go.Figure:
    c = data.DIVERGING
    n = data.NEUTRAL[data.theme()]
    edge = wk["edge"].to_list()
    fig = go.Figure(
        go.Bar(
            x=wk["week"].to_list(),
            y=edge,
            marker_color=[c["pos"] if e > 0 else c["neg"] for e in edge],
            customdata=np.column_stack([wk["games"].to_list(), wk["right"].to_list()]),
            hovertemplate="Week %{x}: %{y:+.3f} per game over %{customdata[0]} games, "
            "%{customdata[1]} picks right<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_color=n["ref"])
    fig.update_layout(
        height=240, margin={"l": 8, "r": 8, "t": 16, "b": 8}, showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis_title="Edge per game (up = better than the market)", xaxis_title="Week",
    )  # fmt: skip
    fig.update_xaxes(gridcolor=n["grid"], dtick=1)
    fig.update_yaxes(gridcolor=n["grid"], zerolinecolor=n["ref"])
    return fig


def summary(df: pl.DataFrame, scope: str) -> None:
    n = df.height
    ll, mll = float(df["ll"].mean()), float(df["market_ll"].drop_nans().mean())
    right = int(df["correct"].sum())
    mk = df.filter(pl.col("market_correct").is_not_null())
    mright = int(mk["market_correct"].sum())
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "How far off your probabilities were",
        f"{ll:.3f}",
        delta=f"{ll - mll:+.3f} vs the market's {mll:.3f}",
        delta_color="inverse",
        help="Log loss: a penalty for being wrong that grows fast when you were confident. "
        "Lower is better; always saying 50% scores 0.693. A negative difference means you beat "
        "the market over these games.",
    )
    c2.metric(
        "Picks right",
        f"{right} of {n} ({100 * right / n:.0f}%)",
        delta=f"market {mright} of {mk.height} ({100 * mright / max(mk.height, 1):.0f}%)",
        delta_color="off",
        help="A pick is the team you gave more than a 50% chance. Picking the market's favorite "
        "is the comparison.",
    )
    wk = week_table(df)
    if wk.height:
        best, worst = (
            wk.sort("edge", descending=True).row(0, named=True),
            wk.sort("edge").row(0, named=True),
        )
        c3.metric(
            "Best week",
            f"Week {best['week']}",
            delta=f"{best['edge']:+.3f} per game over {best['games']} games",
            help="Average improvement over the market's log loss per game that week.",
        )
        st.caption(
            f"Worst week: Week {worst['week']} ({worst['edge']:+.3f} per game over {worst['games']} games)."
            f" Scope: {scope}. Edge = the market's log loss minus yours, so positive means you "
            "were closer to what happened."
        )
        st.plotly_chart(week_chart(wk), width="stretch")
    else:
        st.caption("No market line for these games.")


def games_table(df: pl.DataFrame) -> None:
    rows = []
    for r in df.iter_rows(named=True):
        rows.append(
            {
                "Week": r["week"],
                "Game": f"{r['away']} @ {r['home']}",
                "Your home win %": round(100 * r["p"], 1),
                "Market home win %": None
                if np.isnan(r["market_p"])
                else round(100 * r["market_p"], 1),
                "Result": result_text(r),
                "You": "✓" if r["correct"] else "✗",
                "Market": "–"
                if r["market_correct"] is None
                else ("✓" if r["market_correct"] else "✗"),
                "Biggest push": push_text(r),
            }
        )
    st.dataframe(
        pl.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            "Your home win %": st.column_config.NumberColumn(
                format="%.1f%%", help="Your chance that the home team wins, after calibration."
            ),
            "Market home win %": st.column_config.NumberColumn(
                format="%.1f%%",
                help="The betting market's chance for the home team, vig removed. "
                "The reference line, never an input.",
            ),
            "You": st.column_config.TextColumn(help="Did the team you gave over 50% win?"),
            "Market": st.column_config.TextColumn(help="Did the market's favorite win?"),
            "Biggest push": st.column_config.TextColumn(
                help="The group that moved your probability the most, in points of win probability "
                "(how much lower your number would be without it)."
            ),
        },
    )


def main() -> None:
    st.header("Season view")
    m = load_matrix()
    if m is None:
        st.info("No matrix yet. Run `uv run nfl diy-matrix`.")
        st.stop()
    st.caption(
        "Every game of a season, scored with a set of weights. Open it from Build your own to see "
        "why a season went well or badly. Games are listed by week; click a column to sort."
    )

    seasons = list(range(m["first_scored"], engine.LAST_SEASON + 1))
    try:
        s0 = int(_qp("season", str(engine.LAST_SEASON)))
    except ValueError:
        s0 = engine.LAST_SEASON
    yours = engine.decode_weights(_qp("w"))
    set_ids = list(SET_IDS) if yours else [k for k in SET_IDS if k != "yours"]
    set0 = _qp("set", "yours" if yours else "student")
    set0 = set0 if set0 in set_ids else set_ids[0]

    c1, c2, c3 = st.columns([1, 2, 2])
    season = c1.selectbox(
        "Season", seasons, index=seasons.index(s0) if s0 in seasons else len(seasons) - 1
    )
    doc = load_season(season)
    if doc is None:
        st.info(f"No file for {season}. Run `uv run nfl diy-matrix`.")
        st.stop()
    teams = sorted(set(doc["home"]) | set(doc["away"]))
    t0 = _qp("team")
    team = c2.selectbox(
        "Team (optional)", ["All teams", *teams], index=teams.index(t0) + 1 if t0 in teams else 0
    )
    set_id = c3.selectbox(
        "Weights", set_ids, index=set_ids.index(set0), format_func=SET_IDS.get,
        help="Your Build-your-own weights, or one of the four approaches. The approaches here use "
        "their stated weights (the public lines are those weights lightly fitted to history).",
    )  # fmt: skip

    st.query_params.update(
        {"season": str(season), "set": set_id, "team": "" if team == "All teams" else team}
        | ({"w": _qp("w")} if yours else {})
    )
    if set_id == "yours":
        _, hit = engine.cap_market(yours)
        if hit:
            st.caption(
                f"Market behavior is capped at {engine.MARKET_GROUP_CAP:.0%} of the budget, "
                "so its weight was reduced."
            )

    weights = weights_for(set_id, m, yours)
    if set_id == "yours" and not any(weights.values()):
        st.warning("Those weights are all zero.")
        st.stop()
    df = season_frame(doc, m, weights)
    if team != "All teams":
        df = df.filter((pl.col("home") == team) | (pl.col("away") == team))
    scope = f"{team}, {season}" if team != "All teams" else f"all {df.height} games of {season}"
    st.subheader(f"{SET_IDS[set_id]}, {season}")
    summary(df, scope)
    st.subheader("Every game")
    games_table(df)
    if set_id == "yours" and yours:
        try:
            st.page_link(
                "pages/diy.py", label="Back to Build your own", query_params={"w": _qp("w")}
            )
        except st.errors.StreamlitPageNotFoundError:  # page run on its own (tests), not via app.py
            pass


main()
