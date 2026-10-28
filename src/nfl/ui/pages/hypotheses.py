"""Hypotheses: what 2002-2025 says about each feature, holding the others fixed (M5.5),
and how any one feature or group did season by season (M5.12). Effects are in points of win
probability; logit coefficients never reach the page.

Reads only marts/site/hypotheses.json (written by `nfl hypotheses`)."""

from __future__ import annotations

import textwrap

import plotly.graph_objects as go
import polars as pl
import streamlit as st
from plotly.subplots import make_subplots

from nfl.ui import data

st.header("Hypotheses")

h = data.hypotheses()
if h is None:
    st.info("No hypotheses yet. Run `uv run nfl hypotheses`.")
    st.stop()

feats = h["features"]
gname = {g["id"]: g["name"] for g in data.groups()}
UNGROUPED = "Not in a group"
VERDICTS = ["matters", "weak", "no evidence"]
VERDICT_NOTE = {
    "matters": "the 90% range excludes zero and the effect is at least 0.75 points per +1 SD",
    "weak": "a small effect with a clear interval, or one bigger than its noise but not clear",
    "no evidence": "indistinguishable from zero",
}
THEME = data.theme()
INK = "#e4e3df" if THEME == "dark" else "#2b2a27"
SURFACE = "#1f1f1d" if THEME == "dark" else "#ffffff"
GRID = data.NEUTRAL[THEME]["grid"]
REF = data.NEUTRAL[THEME]["ref"]
ACCENT = data.color("analyst")
STYLE = {  # verdict -> (symbol, fill, line); shape carries the verdict as well as color
    "matters": ("circle", ACCENT, ACCENT),
    "weak": ("diamond", REF, REF),
    "no evidence": ("circle-open", SURFACE, REF),
}


def wrap(text: str, width: int = 60) -> str:
    return "<br>".join(textwrap.wrap(text or "", width))


def gl(f: dict) -> str:
    return gname.get(f["group"], UNGROUPED) if f["group"] else UNGROUPED


for f in feats:
    f["gname"] = gl(f)

lo_s, hi_s = h["trained_seasons"]
st.markdown(
    f"Every approach is a set of beliefs about what wins football games. Here is what history "
    f"({lo_s}-{hi_s}, {h['n_games']:,} games) says about each belief, one feature at a time, "
    f"**holding the other football features fixed**. Market lines are left out."
)
with st.expander("How to read this, and the caveats", expanded=False):
    st.markdown(
        "- **Effect** = change in the home team's win probability, in points, when the feature "
        "is one standard deviation (SD) better for the home side than the away side, at a "
        "pick'em game. +1.0 means a 50% game becomes 51%.\n"
        "- **Range** = the 5th to 95th percentile over 200 refits that resample whole seasons. "
        "The fit is shrunk toward zero, so every effect is modest.\n"
        "- **Observational, not causal.** Teams that rest more are not randomly assigned.\n"
        "- **Collinear features share credit.** Several strength measures say nearly the same "
        "thing, so credit splits between them, or goes to whichever is cleanest. "
        "'On its own' shows the feature fit alone; the gap to the 'after the others' number is the shared credit.\n"
        "- **Small samples for newer data.** Features that start in 2022 (FTN charting) have "
        "about a fifth of the games; their intervals are wide.\n"
        "- Verdicts: " + "; ".join(f"**{k}**: {v}" for k, v in VERDICT_NOTE.items()) + "."
    )

# ------------------------------------------------------------------------------------ filters
c1, c2 = st.columns(2)
all_groups = sorted({f["gname"] for f in feats}, key=lambda n: (n == UNGROUPED, n))
sel_g = c1.multiselect(
    "Group", all_groups, placeholder="All groups", help="Show only features in these groups."
)
sel_v = c2.multiselect(
    "Verdict",
    VERDICTS,
    placeholder="All verdicts",
    help="; ".join(f"{k}: {v}" for k, v in VERDICT_NOTE.items()),
)
shown = [
    f for f in feats if (not sel_g or f["gname"] in sel_g) and (not sel_v or f["verdict"] in sel_v)
]
if not shown:
    st.info("No features match these filters.")
    st.stop()

counts = {v: sum(f["verdict"] == v for f in feats) for v in VERDICTS}
st.caption(
    f"{len(feats)} features: "
    + ", ".join(f"{counts[v]} {v}" for v in VERDICTS)
    + f". Showing {len(shown)}."
)

# ------------------------------------------------------------------------------------- chart
order = sorted(shown, key=lambda f: (f["gname"] == UNGROUPED, f["gname"], -abs(f["coef"])))
ylabels = [f"{f['gname']} · {f['label']}" for f in order]
fig = go.Figure()
for v in VERDICTS:
    sub = [(f, y) for f, y in zip(order, ylabels, strict=True) if f["verdict"] == v]
    if not sub:
        continue
    sym, fill, line = STYLE[v]
    fig.add_trace(
        go.Scatter(
            x=[f["effect_pp"] for f, _ in sub],
            y=[y for _, y in sub],
            mode="markers",
            name=v,
            marker={"symbol": sym, "size": 9, "color": fill, "line": {"color": line, "width": 2}},
            error_x={
                "type": "data",
                "symmetric": False,
                "array": [f["effect_hi_pp"] - f["effect_pp"] for f, _ in sub],
                "arrayminus": [f["effect_pp"] - f["effect_lo_pp"] for f, _ in sub],
                "color": line,
                "thickness": 1.5,
                "width": 0,
            },
            customdata=[
                [
                    f["effect_lo_pp"],
                    f["effect_hi_pp"],
                    f["marginal_pp"],
                    f["coverage"],
                    wrap(f.get("description", "")),
                ]
                for f, _ in sub
            ],
            hovertemplate=(
                "<b>%{y}</b><br>%{customdata[4]}<br>"
                "after the others: %{x:+.2f} pts (90% range %{customdata[0]:+.2f} to "
                "%{customdata[1]:+.2f})<br>on its own: %{customdata[2]:+.2f} pts"
                "<br>%{customdata[3]}<extra></extra>"
            ),
        )
    )
fig.add_vline(x=0, line={"color": REF, "width": 1})
fig.update_layout(
    height=max(320, 22 * len(order) + 120),
    margin={"l": 8, "r": 8, "t": 8, "b": 8},
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font={"color": INK, "size": 12},
    legend={"orientation": "h", "y": 1.0, "yanchor": "bottom", "x": 0},
    xaxis={
        "title": "Points of win probability per +1 SD edge (90% range)",
        "gridcolor": GRID,
        "gridwidth": 1,
        "zeroline": False,
    },
    yaxis={"autorange": "reversed", "showgrid": False, "type": "category", "automargin": True},
)
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
st.caption(
    "Filled circle = matters, diamond = weak, open circle = no evidence. "
    "Rows are grouped by feature group, largest effect first. Hover a row for what it measures."
)

# ------------------------------------------------------------------- beliefs vs evidence callout


def pct_rank(vals: list[float]) -> list[float]:
    s = pl.Series(vals)
    return (s.rank("average") / len(vals)).to_list()


belief_r = pct_rank([f["group_belief"] for f in feats])
evid_r = pct_rank([abs(f["coef"]) / f["se"] if f["se"] > 0 else 0.0 for f in feats])
gaps = sorted(
    (
        {**f, "gap": b - e, "belief_pct": b, "evid_pct": e}
        for f, b, e in zip(feats, belief_r, evid_r, strict=True)
        if f["group"] and f["group_belief"] > 0
    ),
    key=lambda f: -f["gap"],
)[:3]
st.subheader("Beliefs vs evidence")
st.caption(
    "Each feature gets two ranks among all features: how heavily the personas weight its "
    "group (average absolute weight), and how strong the evidence is (the effect divided by "
    "its noise across resampled seasons). These are the three with the biggest gap, where the personas lean on "
    "something history supports least. A rank, not a dollar value: group weights and feature "
    "effects are in different units."
)
cols = st.columns(len(gaps)) if gaps else []
for col, f in zip(cols, gaps, strict=False):
    with col, st.container(border=True):
        st.markdown(f"**{f['label']}**  \n{f['gname']}", help=f.get("description") or None)
        st.write(
            f"Belief rank {100 * f['belief_pct']:.0f}th percentile; "
            f"evidence rank {100 * f['evid_pct']:.0f}th. Verdict: **{f['verdict']}**."
        )

# ------------------------------------------------------------------------------------- table
st.subheader("All features")
rows = [
    {
        "Feature": f["label"],
        "Group": f["gname"],
        "Verdict": f["verdict"],
        "After the others (pts)": round(f["effect_pp"], 2),
        "On its own (pts)": round(f["marginal_pp"], 2),
        "What it means": f["sentence"],
        "Coverage": f["coverage"],
        "Personas that lean on it": ", ".join(p["name"] for p in f["personas"]) or "–",
    }
    for f in sorted(shown, key=lambda f: -abs(f["coef"]))
]
st.dataframe(
    rows,
    hide_index=True,
    width="stretch",
    column_config={
        "What it means": st.column_config.TextColumn(
            width="large", help="A +1 SD edge in the feature, in points of win probability."
        ),
        "Feature": st.column_config.TextColumn(
            help="Hover the chart above for what each measures."
        ),
        "After the others (pts)": st.column_config.NumberColumn(
            help="Win-probability points per +1 SD, holding the other features fixed."
        ),
        "On its own (pts)": st.column_config.NumberColumn(
            help="Win-probability points per +1 SD, the feature fit alone."
        ),
    },
)
st.caption(
    f"Generated {h['generated_at'][:16].replace('T', ' ')} UTC. "
    "'On its own' fits the feature alone; 'after the others' holds the rest fixed."
)


# -------------------------------------------------------------------------- look at one thing
st.subheader("Look at one thing")
bs = h.get("by_season", {}).get("items", {})
if not bs:
    st.info("No season-by-season series yet. Run `uv run nfl hypotheses`.")
    st.stop()
st.markdown(
    "Pick a single feature or a whole group and see how well it predicts on its own, season by "
    "season. Each season is scored by a model trained only on the seasons before it, so nothing "
    "peeks ahead. Some years a signal does more than others."
)


def item_name(key: str) -> str:
    it = bs[key]
    return f"{it['label']} (group)" if it["kind"] == "group" else f"{it['label']}"


options = sorted(bs, key=lambda k: (bs[k]["kind"] != "group", item_name(k).lower()))
picked = st.multiselect(
    "Features or groups (up to 3)",
    options,
    default=[k for k in ("group:quality",) if k in bs],
    max_selections=3,
    format_func=item_name,
    placeholder="Type to search, e.g. rest, EPA, quarterback",
    help="Groups are the high-level beliefs the personas weight; features are the single "
    "measurements inside them. Groups use the same composites as the DIY page.",
)
if not picked:
    st.caption("Choose at least one.")
    st.stop()

SERIES_COLORS = [data.color("analyst"), data.color("traditionalist"), data.color("sharp")]
PANELS = (
    ("edge_win_rate", "How often the team with the edge won", True),
    ("improvement", "Better than picking the home team at its usual rate", False),
)
for key in picked:
    st.markdown(
        f"**{item_name(key)}**: " + bs[key]["sentence"], help=bs[key]["description"] or None
    )

fig2 = make_subplots(
    rows=2,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.12,
    subplot_titles=[p[1] for p in PANELS],
)
for i, key in enumerate(picked):
    it, col = bs[key], SERIES_COLORS[i]
    ser = {r["season"]: r for r in it["series"]}
    xs = list(range(h["by_season"]["first_scored"], max(ser) + 1))
    for row, (field, _, as_pct) in enumerate(PANELS, start=1):
        ys = [
            (100 * ser[s][field] if as_pct else ser[s][field])
            if s in ser and ser[s][field] is not None
            else None
            for s in xs
        ]
        avg = it["pooled"][field]
        avg = 100 * avg if as_pct else avg
        fig2.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines+markers",
                name=item_name(key),
                legendgroup=key,
                showlegend=row == 1,
                line={"color": col, "width": 2},
                marker={"size": 6, "color": col},
                connectgaps=False,
                customdata=[
                    [
                        ser[s]["n_edge"] if s in ser else 0,
                        ser[s]["n_games"] if s in ser else 0,
                        ser[s]["skill_pct"] if s in ser else 0,
                        wrap(it["description"], 50),
                    ]
                    for s in xs
                ],
                hovertemplate=(
                    "<b>%{fullData.name} · %{x}</b><br>%{customdata[3]}<br>"
                    + (
                        "edge team won %{y:.1f}%<br>"
                        if as_pct
                        else "%{y:+.2f} log-loss points better than the baseline "
                        "(%{customdata[2]:+.1f}% skill)<br>"
                    )
                    + "%{customdata[0]} games with an edge, %{customdata[1]} games"
                    "<extra></extra>"
                ),
            ),
            row=row,
            col=1,
        )
        fig2.add_hline(
            y=avg,
            line={"color": col, "width": 1, "dash": "dot"},
            row=row,
            col=1,
            annotation_text=f"average {avg:.1f}{'%' if as_pct else ''}",
            annotation_position="top left" if i == 0 else "bottom left",
            annotation_font={"size": 10, "color": col},
        )
fig2.add_hline(y=50, line={"color": REF, "width": 1}, row=1, col=1)
fig2.add_hline(y=0, line={"color": REF, "width": 1}, row=2, col=1)
fig2.update_layout(
    height=560,
    margin={"l": 8, "r": 8, "t": 40, "b": 8},
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font={"color": INK, "size": 12},
    legend={"orientation": "h", "y": 1.12, "yanchor": "bottom", "x": 0},
    hovermode="closest",
)
fig2.update_yaxes(gridcolor=GRID, zeroline=False, ticksuffix="%", row=1, col=1)
fig2.update_yaxes(gridcolor=GRID, zeroline=False, title_text="log-loss points", row=2, col=1)
fig2.update_xaxes(showgrid=False, dtick=2)
st.plotly_chart(fig2, width="stretch", config={"displayModeBar": False})
st.caption(
    "Top: of the games where the feature favored one side, how often that side won (50% = no "
    "better than a coin flip). Bottom: how much better the one-feature model's probabilities are "
    "than always giving the home team its historical win rate, in log-loss points (x100); above "
    "zero is better. Dotted lines are the long-run averages. Gaps are seasons without enough "
    "data (for example, charting data that starts in 2022). Hover a point for the number of games."
)
