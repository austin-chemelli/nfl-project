"""Coaches & schemes (M5.14): what each play-caller's units have done, set against that season's
league, and what that says about a team's coordinators this year.

Reads only marts/site/coaches.json (written by `nfl.coaches.build_profiles`). Percentiles are
within-season (the charting provider changed in 2023, so raw rates are never compared across
seasons). Two modes: Team view (this season's coordinators and their histories) and Coach view
(one person across seasons and teams)."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from nfl.ui import data

st.header("Coaches & schemes")

site = data._load("coaches.json")
if site is None:
    st.info("No coaches data yet. Run `uv run python -c \"from nfl.config import get_paths; "
            "from nfl.coaches import build_profiles; build_profiles(get_paths())\"`.")  # fmt: skip
    st.stop()

M = site["metrics"]
CUR = site["current_season"]
THEME = data.theme()
INK = "#e4e3df" if THEME == "dark" else "#2b2a27"
GRID = data.NEUTRAL[THEME]["grid"]
REF = data.NEUTRAL[THEME]["ref"]
ACCENT = data.color("analyst")
SIDE_NAME = {"off": "Offense", "def": "Defense"}
KEY = {
    "off": ["pers_11_share", "pers_heavy_share", "time_to_throw", "pressure_allowed_rate"],
    "def": ["man_rate", "two_high_rate", "blitz_rate", "pressure_rate"],
}
LINE_COLORS = [data.color(k) for k in ("analyst", "traditionalist", "sharp", "student")]

st.caption(
    "Percentiles compare a unit with the rest of the league in the **same season**: 80% means "
    "more than 80% of teams. Two data notes: coverage (man / zone / two-high) is charted only "
    "from **2018**, and the charting provider changed in **2023**, so league-wide man rates jump "
    "(29% in 2022, 42% in 2023, 49% in 2024, 31% in 2025). That is why nothing here averages raw "
    "rates across seasons. Observational: a coordinator's numbers also reflect his roster."
)
with st.expander("What each measure means"):
    for side in ("off", "def"):
        st.markdown(f"**{SIDE_NAME[side]}**")
        for d in M.values():
            if d["side"] == side:
                tag = "what they chose" if d["kind"] == "scheme" else "how it went"
                st.markdown(f"- **{d['label']}** ({tag}): {d['help']}")

mode = st.radio(
    "View",
    ["Team view", "Coach view"],
    horizontal=True,
    help="Team view: this season's head coach and play-callers for one team, with their history. "
    "Coach view: any coordinator across the seasons and teams he has worked.",
)


def pct0(p: float | None) -> str:
    return "–" if p is None else f"{100 * p:.0f}%"


def layout(fig: go.Figure, height: int) -> None:
    fig.update_layout(
        height=height,
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": INK},
        legend={"orientation": "h", "y": 1.12},
    )


def prior_bars(prior: dict, side: str, kind: str, key: str) -> None:
    """Horizontal percentile bars (one hue; 50% = league middle) for a person's prior profile."""
    items = [
        (m, v)
        for m, v in prior["metrics"].items()
        if M[m]["side"] == side and M[m]["kind"] == kind and v["pct"] is not None
    ]
    if not items:
        st.caption("Not enough charted plays yet.")
        return
    order = [m for m in M if any(m == i[0] for i in items)]
    items.sort(key=lambda i: order.index(i[0]))
    labels = [M[m]["label"] for m, _ in items][::-1]
    pcts = [v["pct"] for _, v in items][::-1]
    hover = [
        f"<b>{M[m]['label']}</b><br>{pct0(v['pct'])} percentile, recency-weighted over "
        f"{v['seasons']} season(s)<br>{M[m]['help']}"
        for m, v in items
    ][::-1]
    fig = go.Figure(
        go.Bar(
            x=pcts, y=labels, orientation="h", marker={"color": ACCENT}, width=0.55,
            text=[pct0(p) for p in pcts], textposition="outside", cliponaxis=False,
            hovertext=hover, hoverinfo="text",
        )
    )  # fmt: skip
    fig.add_vline(x=0.5, line={"color": REF, "width": 1})
    fig.update_xaxes(range=[0, 1.12], tickformat=".0%", showgrid=True, gridcolor=GRID,
                     tickvals=[0, 0.25, 0.5, 0.75, 1])  # fmt: skip
    fig.update_yaxes(showgrid=False)
    layout(fig, 40 * len(items) + 50)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)


def person_card(name: str, side: str, block: dict, key: str) -> None:
    role = (
        "Play-caller"
        if block["source"] == "play_caller"
        else "Coordinator (play-caller not confirmed)"
    )
    hc = " Also the head coach." if block["is_head_coach"] else ""
    st.subheader(f"{SIDE_NAME[side]}: {name}")
    st.caption(f"{role}.{hc}")
    st.markdown(block["sentence"])
    prior = block["prior"]
    if not prior:
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Seasons of history", prior["n_seasons"],
              help="Seasons before this one in which he held a play-calling job with charted "
              "data. His history travels with him across teams.")  # fmt: skip
    c2.metric("Teams", prior["n_teams"], help=", ".join(prior["teams"]))
    c3.metric("Consistency", (prior["consistency"] or "too early").capitalize(),
              help="How much his unit's percentile moved from season to season (average spread "
              "across the scheme measures). Needs 3+ seasons. 'Changes a lot' means his "
              "tendencies are a weak guide to this season.")  # fmt: skip
    st.caption(prior["history"] + ".")
    st.markdown("**What he chooses** (percentile vs league, recent seasons weighted most)")
    prior_bars(prior, side, "scheme", f"{key}-scheme")
    st.markdown("**How it has gone** (EPA-based; for a defense, a high percentile means worse)")
    prior_bars(prior, side, "result", f"{key}-result")


# ------------------------------------------------------------------------------------- team view
if mode == "Team view":
    teams = sorted(site["teams"])
    team = st.selectbox(f"Team ({CUR} season)", teams, help="Franchise code.")
    t = site["teams"][team]
    st.markdown(f"**Head coach:** {t['head_coach']}")
    st.caption(
        f"Profiles use seasons before {CUR} only. New coordinators have no participation "
        f"history; their {CUR} tendencies come only from news (see the game page narrative)."
    )
    cols = st.columns(2)
    for col, side in zip(cols, ("off", "def")):
        with col:
            b = t[side]
            if b is None:
                st.subheader(SIDE_NAME[side])
                st.caption("No play-caller established in the coordinator table.")
            else:
                person_card(b["name"], side, b, f"{team}-{side}")

# ------------------------------------------------------------------------------------ coach view
else:
    people = sorted(site["people"], key=lambda p: p["name"])

    def last_stint(p: dict) -> str:
        s = max((s for sd in p["sides"] for s in sd["seasons"]), key=lambda s: s["season"])
        return f"{p['name']} (last: {s['team']} {s['season']})"

    labels = {last_stint(p): p for p in people}
    pick = st.selectbox("Coordinator or play-caller", list(labels), index=None,
                        placeholder="Type a name",
                        help="Everyone who called plays for a team since 2016.")  # fmt: skip
    if pick is None:
        st.stop()
    p = labels[pick]
    sides = {SIDE_NAME[sd["side"]]: sd for sd in p["sides"]}
    side_name = (
        st.radio("Unit", list(sides), horizontal=True) if len(sides) > 1 else next(iter(sides))
    )
    sd = sides[side_name]
    side = sd["side"]
    seasons = sd["seasons"]
    summ = sd["summary"]
    st.subheader(f"{p['name']}: {side_name.lower()} play-caller")
    st.markdown(
        summ["sentence"]
        if summ
        else f"No seasons before {CUR} with data; only {CUR} so far, which is not a history yet."
    )
    st.caption(
        "Stints: "
        + ", ".join(
            f"{s['season']} {s['team']}" + (" (so far)" if s["partial"] else "") for s in seasons
        )
        + ". Hover a point for the team and the exact value."
    )

    st.markdown("**Percentile by season**")
    opts = [m for m, d in M.items() if d["side"] == side and d["kind"] == "scheme"]
    chosen = st.multiselect("Measures", opts, default=KEY[side], format_func=lambda m: M[m]["label"],
                            max_selections=4,
                            help="Up to four lines. 50% is the league middle that season.")  # fmt: skip
    xs = [s["season"] for s in seasons]
    ticks = [f"{s['season']}<br>{s['team']}" for s in seasons]
    fig = go.Figure()
    for i, m in enumerate(chosen):
        pts = [(s, s["metrics"].get(m)) for s in seasons]
        pts = [(s, v) for s, v in pts if v and v["pct"] is not None]
        fig.add_trace(go.Scatter(
            x=[s["season"] for s, _ in pts], y=[v["pct"] for _, v in pts], name=M[m]["label"],
            mode="lines+markers", line={"color": LINE_COLORS[i], "width": 2},
            marker={"color": LINE_COLORS[i], "size": 7,
                    "symbol": ["circle-open" if s["partial"] else "circle" for s, _ in pts]},
            customdata=[[s["team"], pct0(v["pct"])] for s, v in pts],
            hovertemplate="%{x} %{customdata[0]}<br>" + M[m]["label"] + ": %{customdata[1]} "
            "percentile<extra></extra>",
        ))  # fmt: skip
    fig.add_hline(y=0.5, line={"color": REF, "width": 1})
    fig.update_yaxes(
        range=[0, 1], tickformat=".0%", gridcolor=GRID, tickvals=[0, 0.25, 0.5, 0.75, 1]
    )
    fig.update_xaxes(tickvals=xs, ticktext=ticks, showgrid=False)
    layout(fig, 380)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="coach-lines")
    st.caption(
        "The team under each season marks moves between teams. Open circles = the season in "
        "progress. Coverage measures start in 2018, so older seasons have no man or two-high point."
    )

    # ------------------------------------------------------------ results vs opponent tendencies
    st.markdown("**How his unit did against specific kinds of opponents**")
    pairs = {
        "off": [("epa_vs_man", "epa_vs_zone"), ("epa_vs_pressure", None)],
        "def": [
            ("epa_allowed_vs_11", "epa_allowed_vs_heavy"),
            ("epa_allowed_man", "epa_allowed_zone"),
        ],
    }[side]
    verb = "EPA per dropback" if side == "off" else "EPA per play allowed (lower is better)"
    for n, (a, b) in enumerate(pairs):
        ms = [m for m in (a, b) if m]
        fig = go.Figure()
        for i, m in enumerate(ms):
            pts = [(s, s["metrics"].get(m)) for s in seasons]
            pts = [(s, v) for s, v in pts if v and v["rate"] is not None]
            fig.add_trace(go.Bar(
                x=[f"{s['season']} {s['team']}" for s, _ in pts], y=[v["rate"] for _, v in pts],
                name=M[m]["label"], marker={"color": [LINE_COLORS[i]] * len(pts)},
                hovertemplate="%{x}<br>" + M[m]["label"] + ": %{y:+.3f} EPA/play<extra></extra>",
            ))  # fmt: skip
        fig.add_hline(y=0, line={"color": REF, "width": 1})
        fig.update_layout(barmode="group", bargap=0.35)
        fig.update_yaxes(gridcolor=GRID, zeroline=False)
        fig.update_xaxes(showgrid=False)
        layout(fig, 280)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=f"res-{n}")
    st.caption(
        f"{verb}. Bars are the unit's own results by season; 0 is roughly an average play. "
        "Samples are a few hundred plays per bar, so small differences are noise."
    )

    # ------------------------------------------------------------ season table with the QB
    rows = []
    for s in seasons:
        q = s["qb"]
        r = {"Season": s["season"], "Team": s["team"],
             "Source": "play-caller" if s["source"] == "play_caller" else "coordinator"}  # fmt: skip
        if side == "off":
            r["Primary QB"] = q["name"] if q else "–"
            r["QB dropbacks"] = q["dropbacks"] if q else None
        for m in KEY[side]:
            v = s["metrics"].get(m)
            r[M[m]["label"]] = data.fmt(v["rate"] if v else None, M[m]["unit"])
        rows.append(r)
    st.markdown("**Season by season**")
    if side == "off":
        st.caption("Primary QB = most dropbacks that season for that team. The QB shapes some of "
                   "these numbers (time to throw, pressure), so read a play-caller's change "
                   "alongside a QB change.")  # fmt: skip
    st.dataframe(rows, hide_index=True, width="stretch")
