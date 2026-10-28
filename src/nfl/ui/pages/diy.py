"""Build your own approach (M5.9): set group weights, see how they would have done 2005-2025.

Reads marts/site/diy_matrix.json (nfl diy-matrix) and scores in numpy via nfl.approaches.diy.
Overall confidence is not an input: walk-forward calibration sets it from history.
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
# The four approaches by their public ids (ADR 0004 amendment). The Student is the data-only one:
# its DIY comparison line refits every year, the others use their stated persona weights.
PERSONA_NAMES = {
    "traditionalist": "The Traditionalist",
    "analyst": "The Analyst",
    "sharp": "The Sharp",
}
STUDENT_NAME = "The Student"
MARKET_NOTE = (
    "The market's own prediction is what we compare against, so it is never an input here. "
    "These signals only describe how the market is behaving. They are mostly live-only (no history), "
    f"so they barely move the backtest. Capped at {engine.MARKET_GROUP_CAP:.0%} of your budget."
)
START_BLANK, START_DATA = "Blank (equal weights)", "What the data says (The Student)"
HIDDEN_FROM = 2023


@st.cache_resource(show_spinner="Loading the matrix...")
def load_matrix() -> dict | None:
    if not MATRIX_FILE.exists():
        return None
    return engine.prepare(json.loads(MATRIX_FILE.read_text()))


@st.cache_data(show_spinner=False, max_entries=64)
def run_eval(weights: tuple, max_season: int | None, per_season: bool = False) -> dict:
    m = load_matrix()
    w = _unpack(weights, per_season)
    return engine.evaluate(w, m, max_season=max_season)


@st.cache_data(show_spinner=False, max_entries=16)
def run_toward(weights: tuple, max_season: int | None) -> dict:
    return engine.fit_toward(dict(weights), load_matrix(), max_season=max_season)


def _pack(w: dict) -> tuple:
    return tuple(sorted(w.items()))


def _unpack(t: tuple, per_season: bool) -> dict:
    return {k: dict(v) for k, v in t} if per_season else dict(t)


def _student_by_season() -> tuple:
    sf = load_matrix()["student_fitted"]
    return tuple(sorted((int(s), _pack(v["W"])) for s, v in sf.items()))


# ------------------------------------------------------------------------------------- state


def _points_from_weights(w: dict[str, float]) -> dict[str, float]:
    """Signed weights -> signed attention points (largest magnitude = 100)."""
    top = max((abs(v) for v in w.values()), default=0.0)
    return {g: round(100 * v / top) if top else 0 for g, v in w.items()}


def _set_points(signed: dict[str, float]) -> None:
    for g in engine.GROUP_IDS:
        v = signed.get(g, 0.0)
        st.session_state[f"pts_{g}"] = int(abs(v))
        st.session_state[f"dir_{g}"] = "Contrarian" if v < 0 else "Normal"


def _start_points(choice: str) -> dict[str, float]:
    m = load_matrix()
    active = [g for g in m["groups"] if g not in m["inactive"]]
    if choice == START_BLANK:
        return {g: 50.0 for g in active}
    if choice == START_DATA:
        by = next((a for a in data.approaches() if a["id"] == "student"), None)
        w = (by or {}).get("fitted_groups") or m["student_fitted"][str(engine.LAST_SEASON)]["W"]
        return _points_from_weights({g: v for g, v in w.items() if g in active})
    pid = next(k for k, v in PERSONA_NAMES.items() if v == choice)
    return _points_from_weights({g: v for g, v in m["personas"][pid]["W"].items() if g in active})


def _apply_start() -> None:
    _set_points(_start_points(st.session_state["start"]))


def _signed() -> dict[str, float]:
    out = {}
    for g in engine.GROUP_IDS:
        p = float(st.session_state.get(f"pts_{g}", 0))
        out[g] = -p if st.session_state.get(f"dir_{g}") == "Contrarian" else p
    return out


# ------------------------------------------------------------------------------------- charts


def _axis(fig: go.Figure, title: str | None = None, height: int = 320) -> go.Figure:
    n = data.NEUTRAL[data.theme()]
    fig.update_layout(
        height=height, margin={"l": 8, "r": 8, "t": 24, "b": 8}, showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis_title=title,
    )  # fmt: skip
    fig.update_xaxes(gridcolor=n["grid"], zerolinecolor=n["ref"])
    fig.update_yaxes(gridcolor=n["grid"], zerolinecolor=n["ref"])
    return fig


def _heading_colors() -> list[str]:
    pal = data._DARK if data.theme() == "dark" else data._LIGHT
    return [*pal.values(), data.NEUTRAL[data.theme()]["ref"]]


def donut(signed: dict[str, float], groups: list[dict]) -> go.Figure:
    by_heading = {h: 0.0 for h in engine_headings(groups)}
    gh = {g["id"]: g["heading"] for g in groups}
    for g, v in signed.items():
        by_heading[gh[g]] += abs(v)
    labels, vals = list(by_heading), list(by_heading.values())
    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=vals,
            hole=0.55,
            sort=False,
            textinfo="label+percent",
            textposition="outside",
            marker={
                "colors": _heading_colors()[: len(labels)],
                "line": {"width": 2, "color": "rgba(0,0,0,0)"},
            },
            direction="clockwise",
        )
    )
    return _axis(fig, height=340)


def engine_headings(groups: list[dict]) -> list[str]:
    seen: list[str] = []
    for g in groups:
        if g["heading"] not in seen:
            seen.append(g["heading"])
    return seen


def breakdown(signed: dict[str, float], groups: list[dict]) -> go.Figure:
    tot = sum(abs(v) for v in signed.values()) or 1.0
    names = {g["id"]: g["name"] for g in groups}
    hs = engine_headings(groups)
    colors = _heading_colors()
    gh = {g["id"]: g["heading"] for g in groups}
    rows = [(names[g], 100 * v / tot, colors[hs.index(gh[g])]) for g, v in signed.items() if v]
    rows.sort(key=lambda r: abs(r[1]))
    fig = go.Figure(
        go.Bar(
            x=[r[1] for r in rows],
            y=[r[0] for r in rows],
            orientation="h",
            marker_color=[r[2] for r in rows],
            text=[f"{r[1]:+.0f}" for r in rows],
            textposition="outside",
            cliponaxis=False,
        )
    )
    fig.update_xaxes(title="Share of attention (negative = contrarian)")
    return _axis(fig, height=max(220, 26 * len(rows) + 60))


def season_bars(res: dict) -> go.Figure:
    rows = [r for r in res["seasons"] if r["delta"] is not None]
    edge = [-r["delta"] for r in rows]  # market log loss minus yours: up = you beat the market
    c = data.DIVERGING
    fig = go.Figure(
        go.Bar(
            x=[r["season"] for r in rows],
            y=edge,
            marker_color=[c["pos"] if e > 0 else c["neg"] for e in edge],
            hovertemplate="%{x}: %{y:+.4f}<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_color=data.NEUTRAL[data.theme()]["ref"])
    return _axis(fig, "Edge vs market (log loss, up = better)")


def aging_chart(res: dict) -> go.Figure:
    rows = [r for r in res["seasons"] if r["delta"] is not None]
    x = np.array([r["season"] for r in rows], dtype=float)
    y = np.array([-r["delta"] for r in rows])
    fig = go.Figure(
        go.Scatter(x=x, y=y, mode="markers", marker={"size": 8, "color": data.color("analyst")})
    )
    if len(x) >= 4:
        b, a = np.polyfit(x, y, 1)
        fig.add_trace(go.Scatter(x=[x.min(), x.max()], y=[a + b * x.min(), a + b * x.max()],
                                 mode="lines", line={"color": data.NEUTRAL[data.theme()]["market"]}))  # fmt: skip
    fig.add_hline(y=0, line_color=data.NEUTRAL[data.theme()]["ref"])
    return _axis(fig, "Edge vs market (up = better)", 280)


# -------------------------------------------------------------------------------------- page


def game_label(gid: str) -> str:
    p = gid.split("_")
    return f"{p[0]} W{int(p[1])}: {p[2]} @ {p[3]}" if len(p) == 4 else gid


def ll_cell(r: dict) -> str:
    return f"{r['log_loss']:.4f} ({r['ll_lo']:.4f} to {r['ll_hi']:.4f})"


def vs_market(r: dict, market_ll: float) -> str:
    """Plain-terms gap to the market: percent better/worse in log-loss, with the raw points."""
    if r["delta"] is None:
        return "–"
    rel = 100 * r["delta"] / market_ll
    word = "better" if rel < 0 else "worse"
    return f"{abs(rel):.1f}% {word} ({r['delta']:+.4f} log-loss points)"


HEADLINE_HELP = {
    "Log loss": "How far off the probabilities were, averaged over every game. It punishes confident "
    "misses hard. Lower is better; always saying 50% scores 0.693.",
    "Against the market": "Percent better or worse than the betting market's own win probabilities "
    "(vig removed), measured in log loss. The points in brackets are the raw difference; negative "
    "means better than the market.",
}


def headline(mine: dict, others: dict[str, dict], market_ll: float) -> None:
    o = mine["overall"]
    rows = [
        {
            "Approach": "Yours",
            "Log loss (90% range)": ll_cell(o),
            "Against the market": vs_market(o, market_ll),
        }
    ]
    rows += [
        {"Approach": n, "Log loss (90% range)": ll_cell(r["overall"]),
         "Against the market": vs_market(r["overall"], market_ll)}
        for n, r in others.items()
    ]  # fmt: skip
    rows.append({"Approach": "The market (vig removed)", "Log loss (90% range)": f"{market_ll:.4f}",
                 "Against the market": "the reference"})  # fmt: skip
    c1, c2, c3 = st.columns(3)
    c1.metric("Your log loss", f"{o['log_loss']:.4f}", help=HEADLINE_HELP["Log loss"])
    c2.metric(
        "Against the market",
        f"{abs(100 * o['delta'] / market_ll):.1f}% " + ("better" if o["delta"] < 0 else "worse"),
        delta=f"{o['delta']:+.4f} log-loss points",
        delta_color="inverse",
        help=HEADLINE_HELP["Against the market"],
    )
    stu = others[STUDENT_NAME]["overall"]
    c3.metric(
        f"Against {STUDENT_NAME}",
        f"{abs(o['log_loss'] - stu['log_loss']):.4f} " + ("better" if o["log_loss"] < stu["log_loss"] else "worse"),
        help="The Student weights every group equally to start and learns only from past results, "
        "refitting each year. Beating it means your opinions added something the data alone did not.",
    )  # fmt: skip
    if o["d_hi"] < 0:
        v = "Your weights beat the market over this window, and the 90% range excludes zero."
    elif o["d_lo"] > 0:
        v = "Your weights trailed the market over this window, and the 90% range excludes zero."
    else:
        v = "Your weights are statistically indistinguishable from the market over this window."
    better = "ahead of" if o["log_loss"] < stu["log_loss"] else "behind"
    st.write(f"{v} You are {better} the data-only Student, though {o['n']:,} games over "
             f"{o['seasons']} seasons cannot rank close approaches.")  # fmt: skip
    st.dataframe(
        pl.DataFrame(rows), hide_index=True, width="stretch",
        column_config={
            "Log loss (90% range)": st.column_config.TextColumn(help=HEADLINE_HELP["Log loss"]),
            "Against the market": st.column_config.TextColumn(help=HEADLINE_HELP["Against the market"]),
        },
    )  # fmt: skip


def season_link(season: int, signed: dict[str, float]) -> None:
    """Open the Season view on this season with the current weights (query string ?w=...)."""
    try:
        st.page_link(
            "pages/season.py",
            label=f"See every {season} game with your weights",
            icon=":material/date_range:",
            query_params={
                "season": str(season),
                "set": "yours",
                "w": engine.encode_weights(signed),
            },
            help="Opens the Season view: your probability against the market's for each game.",
        )
    except st.errors.StreamlitPageNotFoundError:  # page run on its own (tests), not via app.py
        pass


def main() -> None:
    st.header("Build your own approach")
    m = load_matrix()
    if m is None:
        st.info("No matrix yet. Run `uv run nfl diy-matrix`.")
        st.stop()
    groups = data.groups()
    if not groups:
        data.require(None)
    st.caption(
        "Spend attention points on the things that matter to you and see how those beliefs would have "
        f"done in every game from {m['first_scored']} to {engine.LAST_SEASON}. Overall confidence is "
        "not an input: calibration sets it from earlier seasons, so a loud set of weights gets no credit. "
        "Hover any slider for what it measures."
    )

    if "init" not in st.session_state:
        st.session_state["init"] = True
        q = engine.decode_weights(st.query_params.get("w"))
        _set_points(q if q else _start_points(START_BLANK))

    names = [START_BLANK, *PERSONA_NAMES.values(), START_DATA]
    st.selectbox("Start from", names, key="start", on_change=_apply_start)

    inactive = set(m["inactive"])
    heads = engine_headings(groups)
    market_heading = data.group("market").get("heading")
    left, right = st.columns([3, 2], gap="large")
    with left:
        for h in heads:
            with st.expander(h, expanded=h == heads[0]):
                for g in (g for g in groups if g["heading"] == h):
                    a, b = st.columns([4, 2])
                    off = g["id"] in inactive
                    a.slider(
                        g["name"],
                        0,
                        100,
                        key=f"pts_{g['id']}",
                        help=data.help_text(g["id"]),
                        disabled=off,
                    )
                    b.radio("Direction", ["Normal", "Contrarian"], key=f"dir_{g['id']}", horizontal=True,
                            label_visibility="collapsed", disabled=off, help="Contrarian flips the sign.")  # fmt: skip
                    if off:
                        a.caption("No history yet; ignored.")
                if h == market_heading:
                    st.caption(MARKET_NOTE)
    signed = {g: v for g, v in _signed().items() if g not in inactive}
    signed, market_capped = engine.cap_market(signed)
    total = sum(abs(v) for v in signed.values())
    st.query_params["w"] = engine.encode_weights(signed)
    with right:
        st.metric(
            "Total points",
            f"{total:.0f}",
            help="Points you spent. The charts show them as shares of a 100-point budget.",
        )
        if total == 0:
            st.warning("Give at least one group some points.")
            st.stop()
        if market_capped:
            st.warning(
                f"Market behavior is held at {engine.MARKET_GROUP_CAP:.0%} of your budget "
                f"(the most any approach may put on it), so its weight was reduced to {signed['market']:+.0f}."
            )
        if st.toggle("Show as table", key="as_table"):
            st.dataframe(pl.DataFrame({"Group": list(signed), "Share %": [100 * v / total for v in signed.values()]}),
                         hide_index=True)  # fmt: skip
        else:
            st.plotly_chart(donut(signed, groups), width="stretch")
            st.plotly_chart(breakdown(signed, groups), width="stretch")

    st.divider()
    st.info(
        "Tuning weights until the backtest looks good is overfitting by eye: with ~270 games a season, "
        "some settings will look great by luck. Set your weights first, then reveal the recent seasons."
    )
    hide = st.toggle(
        f"Hide the last 3 seasons ({HIDDEN_FROM}-{engine.LAST_SEASON}) until I reveal them"
    )
    cap = HIDDEN_FROM - 1 if hide else None

    w = _pack({g: v / total for g, v in signed.items()})
    mine = run_eval(w, cap)
    others = {PERSONA_NAMES[p]: run_eval(_pack(m["personas"][p]["W"]), cap) for p in PERSONA_NAMES}
    stu = run_eval(_student_by_season(), cap, True)
    others[STUDENT_NAME] = stu

    st.subheader("1. How you would have done")
    headline(mine, others, mine["overall"]["market_log_loss"])
    st.caption(
        "The approaches here use their stated weights, so their numbers differ slightly from "
        "the tracker, where the public lines are lightly fitted to history."
    )
    if mine["first_season_in_sample"]:
        st.caption("The first season was calibrated on itself.")

    st.subheader(
        "2. Season by season",
        help="Bars above zero are seasons where you were closer to what "
        "happened than the market was.",
    )
    st.plotly_chart(season_bars(mine), width="stretch")
    st.caption("Blue: you beat the market that season. Red: the market beat you.")
    for title, key in (("Best seasons", "best"), ("Worst seasons", "worst")):
        with st.expander(title):
            for r in mine[key]:
                pct = 100 * -r["delta"] / r["market_log_loss"]
                st.markdown(
                    f"**{r['season']}**: {abs(pct):.1f}% {'better' if pct > 0 else 'worse'} than the "
                    f"market over {r['n']} games ({-r['delta']:+.4f} log-loss points; up is better)"
                )
                season_link(r["season"], signed)
                st.dataframe(
                    pl.DataFrame([
                        {"Game": game_label(k["game_id"]), "Home won": bool(k["home_won"]),
                         "Your home win %": round(100 * k["p"], 1),
                         "Market home win %": k["market_p"] and round(100 * k["market_p"], 1),
                         "Cost vs market": round(k["delta"], 3), "Biggest push": f"{data.group(k['group'])['name']} (toward {'the home team' if k['group_logit'] > 0 else 'the road team'})"}
                        for k in r["key_games"]]),
                    hide_index=True, width="stretch",
                    column_config={
                        "Cost vs market": st.column_config.NumberColumn(
                            help="How much more this game hurt your log loss than the market's. "
                            "Higher means you were further off than the market."),
                        "Biggest push": st.column_config.TextColumn(
                            help="The group of beliefs that moved your probability the most."),
                    })  # fmt: skip

    st.subheader(
        "3. Did your weights age?",
        help="Whether your edge over the market has been shrinking or growing over the seasons.",
    )
    st.plotly_chart(aging_chart(mine), width="stretch")
    st.write(mine["aging"]["sentence"])

    st.subheader("4. By game type")
    bc = pl.DataFrame(mine["by_context"]).select(
        pl.col("group").alias("Kind"), pl.col("bucket").alias("Bucket"), pl.col("n").alias("Games"),
        (-pl.col("delta")).round(4).alias("Edge vs market"), pl.col("delta_se").round(4).alias("± s.e."),
    )  # fmt: skip
    st.dataframe(bc, hide_index=True, width="stretch")
    st.caption(
        "Positive edge = better than the market. Close games and blowouts are labeled by outcome."
    )

    st.subheader(
        "5. When you disagree with the market",
        help="Games grouped by how far your home win "
        "chance was from the market's, in points of win probability.",
    )
    dv = pl.DataFrame(mine["divergence"]).select(
        pl.col("bucket").alias("Gap (win-probability points)"), pl.col("n").alias("Games"),
        (100 * pl.col("lean_win_rate")).round(0).alias("Your side won (%)"),
        (100 * pl.col("market_expected_rate")).round(0).alias("Market expected (%)"),
    )  # fmt: skip
    st.dataframe(dv, hide_index=True, width="stretch")

    st.subheader("6. Paper bets (noisy)")
    b = mine["bets"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Units", f"{b['units']:+.1f}", help="Profit in bet sizes: each bet risks 1 unit.")
    c2.metric(
        "ROI",
        "–" if b["roi"] is None else f"{100 * b['roi']:+.1f}%",
        help="Profit as a share of the money risked.",
    )
    c3.metric("Record", f"{b['wins']}-{b['losses']}", help="Bets won and lost.")
    st.caption("1 unit on the moneyline whenever you differ from the vig-free market by more than 5 points. "
               "A few hundred bets cannot separate skill from luck.")  # fmt: skip

    st.subheader("7. What history would do to your weights")
    t = run_toward(_pack({g: v / total for g, v in signed.items()}), cap)
    d = pl.DataFrame(
        {"Group": list(t["shares"]), "You": [t["user_shares"][g] for g in t["shares"]],
         "History": [t["shares"][g] for g in t["shares"]]}
    ).with_columns((pl.col("History") - pl.col("You")).alias("Change")).sort(pl.col("Change").abs(), descending=True)  # fmt: skip
    st.dataframe(
        d.with_columns(pl.col(["You", "History", "Change"]).round(1)),
        hide_index=True,
        width="stretch",
    )
    st.caption("Signed shares of a 100-point budget after a ridge fit toward your weights over all "
               "scored seasons (hindsight by design: this is what the data would nudge you toward).")  # fmt: skip


main()
