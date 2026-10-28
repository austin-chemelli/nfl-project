"""Game page: market vs approaches, why each leans its way (win-probability points), who has the
edge by group, tale of the tape, tendencies, injuries, narrative. Reads game/<game_id>.json (nfl.site contract) via nfl.ui.data."""

from __future__ import annotations

import textwrap

import plotly.graph_objects as go
import polars as pl
import streamlit as st
from plotly.subplots import make_subplots

from nfl.ui import data
from nfl.ui import game_helpers as gh

meta = data.require(data.meta())
season = meta["season"]

# ------------------------------------------------------------------------------------ pick a game
qp_game = st.query_params.get("game")
qp = data.game(qp_game) if qp_game else None
week = qp["week"] if qp else meta["current_week"]
weeks = meta["weeks"]
c1, c2 = st.columns([1, 3])
week = c1.selectbox("Week", weeks, index=weeks.index(week) if week in weeks else 0,
                    format_func=lambda w: f"Week {w}", help="NFL regular-season week.")  # fmt: skip
sl = data.require(data.slate(season, week), f"No slate for week {week}.")
sgames = sorted(sl["games"], key=lambda g: g["kickoff_utc"] or "")
ids = [g["game_id"] for g in sgames]
by_id = {g["game_id"]: g for g in sgames}
idx = ids.index(qp_game) if qp_game in ids else 0
gid = c2.selectbox("Game", ids, index=idx,
                   format_func=lambda i: f"{by_id[i]['away']} @ {by_id[i]['home']}",
                   help="Any game in the selected week.")  # fmt: skip
st.query_params["game"] = gid
g = data.require(data.game(gid), "No detail file for this game yet.")
home, away = g["home"], g["away"]
models = g["models"]

# ----------------------------------------------------------------------------------------- header
st.header(f"{away} @ {home}")
mk = g.get("market") or {}
bits = [
    data.kickoff_et(g["kickoff_utc"]),
    f"{g.get('stadium') or 'stadium n/a'}" + (f" ({g['roof']})" if g.get("roof") else ""),
]
if g.get("neutral_site"):
    bits.append("neutral site")
st.write(" · ".join(bits))
st.write(
    f"**QBs:** {away} {g.get('away_qb') or 'n/a'}, {home} {g.get('home_qb') or 'n/a'}  \n"
    f"**Market:** {data.spread(mk.get('spread_home'), home, away)}, total "
    f"{mk.get('total') if mk.get('total') is not None else '–'}, {home} win {data.pct(mk.get('p_home'))}"
)
if g.get("result"):
    r = g["result"]
    st.success(f"Final: {away} {r['away_score']}, {home} {r['home_score']}")
st_ = (models.get("ensemble") or next(iter(models.values()), {})).get("status", "preview")
st.caption(
    {"preview": "Preview: scored now, not yet a lock.",
     "locked": "Locked: recorded before kickoff.",
     "backfill": "Backfill: finished game scored after the fact by frozen models."}.get(st_, st_)
)  # fmt: skip

# ------------------------------------------------------------------- what each approach thinks
NEU = data.NEUTRAL[data.theme()]
POS, NEG = data.DIVERGING["pos"], data.DIVERGING["neg"]
st.subheader("What each approach thinks")
st.caption(
    f"Each dot is one forecast of {home}'s chance of winning. Each approach has one line (hover "
    "for its character); the dashed line is the betting market, the benchmark everything is "
    "compared with."
)
rows = gh.dot_models(models)
as_tbl = st.toggle("Table view", key="dots_tbl", help="The same numbers as a table.")
if as_tbl:
    st.dataframe(
        pl.DataFrame(
            [{"Model": data.label(m), f"{home} win": models[m]["p_home"],
              "vs market": models[m].get("divergence")} for m in rows]
        ),
        hide_index=True, width="stretch",
        column_config={
            f"{home} win": st.column_config.NumberColumn(
                format="percent", help=f"The model's chance that {home} wins."),
            "vs market": st.column_config.NumberColumn(
                format="%+.3f", help="Model minus market on the home win chance "
                "(0.05 = 5 points more on the home side)."),
        },
    )  # fmt: skip
else:
    fig = go.Figure()
    ps = [models[m]["p_home"] for m in rows]
    for m in rows:
        p = models[m]["p_home"]
        fig.add_trace(go.Scatter(
            x=[p], y=[data.label(m)], mode="markers", name=data.label(m), showlegend=False,
            marker={"size": 11, "color": data.color(m), "line": {"width": 2, "color": data.color(m)}},
            hovertemplate=f"{data.label(m)}<br>{home} win {p:.1%}<extra></extra>",
        ))  # fmt: skip
    if mk.get("p_home") is not None:
        fig.add_vline(x=mk["p_home"], line={"color": NEU["market"], "dash": "dash", "width": 1},
                      annotation_text="market", annotation_position="top")  # fmt: skip
    lo, hi = max(0.0, min(ps) - 0.05), min(1.0, max(ps) + 0.05)
    fig.update_layout(
        height=60 + 30 * len(rows), margin={"l": 0, "r": 10, "t": 30, "b": 0},
        xaxis={"title": f"{home} win probability", "tickformat": ".0%", "range": [lo, hi]},
        yaxis={"autorange": "reversed", "title": None},
    )  # fmt: skip
    st.plotly_chart(fig, width="stretch")
    st.caption("Color follows the approach; gray is a reference. Dashed line: the market.")
with st.expander("What are these approaches?"):
    for a in data.approaches():
        st.markdown(f"**{a['name']}**: {a['blurb']}")

# ----------------------------------------------------------------------------------------- why
st.subheader("Why they lean the way they do")
st.caption(
    f"Each bar is how much one piece of the picture moves the pick, in points of {home}'s win "
    f"chance: how far the chance would drop without that piece. Right pushes toward {home}, "
    f"left toward {away}. The pieces add up only approximately to the total (the effects overlap "
    "and the final probability is also calibrated)."
)
contrib = g.get("contributions") or {}
if not contrib:
    st.info("No contribution breakdown for this game.")
else:
    opts = [m for m in [*data.APPROACH_ORDER, "ensemble"] if m in contrib]
    sel = st.selectbox("Approach", opts, format_func=lambda m: data.label(m), index=0,
                       help="Whose reasoning to show. Each approach weighs the same facts differently.")  # fmt: skip
    cm = contrib[sel]
    items = gh.contribution_items(cm)
    reach = max(max(abs(i["pp"]) for i in items), 1.0) * 1.6
    fig = go.Figure(go.Bar(
        x=[i["pp"] for i in items], y=[i["name"] for i in items], orientation="h", width=0.55,
        marker_color=data.color(sel),
        text=[gh.pts_toward(i["pp"], home, away) for i in items], textposition="outside",
        customdata=[textwrap.fill(i["help"], 50).replace("\n", "<br>") for i in items],
        hovertemplate="<b>%{y}</b>: %{text}<br>%{customdata}<extra></extra>",
    ))  # fmt: skip
    fig.add_vline(x=0, line={"color": NEU["ref"], "width": 1})
    fig.update_layout(
        height=60 + 26 * len(items), margin={"l": 0, "r": 10, "t": 10, "b": 0},
        xaxis={"title": f"← toward {away}   |   toward {home} →  (points of win probability)",
               "range": [-reach, reach]},
        yaxis={"autorange": "reversed", "title": None},
    )  # fmt: skip
    st.plotly_chart(fig, width="stretch")
    st.caption(f"{data.label(sel)} says: {home} win chance {data.pct(cm['p_home'], 1)}. "
               "Home field is the built-in home edge.")  # fmt: skip
    for k in sorted(cm["groups"], key=lambda k: -abs(cm["groups"][k].get("pp") or 0)):
        grp = cm["groups"][k]
        gd = data.group(k)
        with st.expander(f"{gd['name']}: {gh.pts_toward(grp.get('pp'), home, away)}"):
            if gd.get("description"):
                st.caption(gd["description"])
            frs = gh.feature_contrib_rows(grp)
            st.markdown(
                gh.html_table(
                    ["Feature", "Push (points of win chance)"],
                    [[r["label"], gh.pts_toward(r["pp"], home, away)] for r in frs],
                    [[r["help"], ""] for r in frs],
                ),
                unsafe_allow_html=True,
            )

    st.markdown("**Where the four approaches differ**",
                help="The same breakdown for all four approaches side by side.")  # fmt: skip
    apps = [a for a in data.APPROACH_ORDER if a in contrib]
    gids = [x["id"] for x in data.groups() if any(x["id"] in contrib[a]["groups"] for a in apps)]
    fig = go.Figure()
    for a in apps:
        fig.add_trace(go.Bar(
            x=[contrib[a]["groups"].get(k, {}).get("pp", 0.0) for k in gids],
            y=[data.group(k)["name"] for k in gids], orientation="h",
            name=data.label(a).removeprefix("The "), marker_color=data.color(a),
            hovertemplate=f"{data.label(a)}<br>%{{y}}: %{{x:+.1f}} pts<extra></extra>",
        ))  # fmt: skip
    fig.add_vline(x=0, line={"color": NEU["ref"], "width": 1})
    fig.update_layout(
        barmode="group", bargap=0.35, height=120 + 17 * len(gids) * max(len(apps), 1),
        margin={"l": 0, "r": 10, "t": 10, "b": 0},
        xaxis={"title": f"← toward {away}   |   toward {home} →  (points of win probability)"},
        yaxis={"autorange": "reversed", "title": None},
        legend={"orientation": "h", "y": 1.04},
    )  # fmt: skip
    st.plotly_chart(fig, width="stretch")

# -------------------------------------------------------------------------------- tale of the tape
st.subheader("Tale of the tape")
st.caption(
    "Who has the better of each part of the matchup, and the numbers behind it. Hover any "
    "feature or group name for what it means."
)
edges = gh.edge_rows(g.get("edges") or {}, home)
if edges:
    st.markdown("**Who has the edge, by group**",
                help="A bar toward a team means that team is stronger in that group. Its length "
                "says how lopsided this matchup is compared with every game since 2005: 80 means "
                "bigger than 80% of matchups.")  # fmt: skip
    fig = go.Figure(go.Bar(
        x=[e["signed"] for e in edges], y=[e["name"] for e in edges], orientation="h", width=0.55,
        marker_color=[POS if e["signed"] > 0 else NEG for e in edges],
        text=[f"{e['favors']} · {e['pct']:.0f}" for e in edges], textposition="outside",
        customdata=[[e["text"], textwrap.fill(e["help"], 50).replace("\n", "<br>")] for e in edges],
        hovertemplate="<b>%{y}</b><br>%{customdata[0]}<br>%{customdata[1]}<extra></extra>",
    ))  # fmt: skip
    fig.add_vline(x=0, line={"color": NEU["ref"], "width": 1})
    fig.update_layout(
        height=60 + 24 * len(edges), margin={"l": 0, "r": 10, "t": 10, "b": 0},
        xaxis={"title": f"← {away} edge   |   {home} edge →  (bigger than N% of all matchups)",
               "range": [-130, 130], "tickvals": [-100, -50, 0, 50, 100],
               "ticktext": ["100", "50", "0", "50", "100"]},
        yaxis={"autorange": "reversed", "title": None},
    )  # fmt: skip
    st.plotly_chart(fig, width="stretch")
    none = [data.group(k)["name"] for k, e in (g.get("edges") or {}).items() if not e.get("favors")]
    if none:
        st.caption(f"No clear edge: {', '.join(none)}.")
tape = gh.tape(g.get("features") or {})
if not tape:
    st.info("No feature values for this game.")
else:
    tabs = st.tabs(list(tape))
    for tab, (heading, groups) in zip(tabs, tape.items(), strict=True):
        with tab:
            for gid_, gname, frows in groups:
                st.markdown(f"**{gname}**", help=data.help_text(gid_) or None)
                st.markdown(
                    gh.html_table(
                        ["Feature", away, home],
                        [[r["label"], r["away"], r["home"]] for r in frows],
                        [[r["help"], "", ""] for r in frows],
                    ),
                    unsafe_allow_html=True,
                )

# --------------------------------------------------------------------------------- tendencies
st.subheader("Tendencies: offense vs the other side's defense")
st.caption(
    "How each offense has played this season next to how the opposing defense has been played "
    "against, with the league average for scale. Where the dots are far apart, expect a "
    "mismatch."
)
tend = g.get("tendencies") or []
if not tend:
    st.info("No tendency data for this game.")
else:
    show_tbl = st.toggle("Show table", key="tend_tbl", help="Exact values, league averages and "
                         "play counts, including metrics the charts leave out.")  # fmt: skip
    stabs = st.tabs([n for _, n in gh.SITUATIONS])
    for stab, (sit, _sn) in zip(stabs, gh.SITUATIONS, strict=True):
        with stab:
            st.caption(gh.SITUATION_HELP[sit])
            for off_side, off_t, def_t in (("home", home, away), ("away", away, home)):
                st.markdown(f"**{off_t} offense vs {def_t} defense**")
                if show_tbl:
                    st.dataframe(pl.DataFrame(gh.tendency_table(tend, off_side, sit)),
                                 hide_index=True, width="stretch",
                                 column_config={
                                     "Rate": st.column_config.TextColumn(help="Season-to-date rate, shrunk toward the league average when plays are few."),
                                     "League": st.column_config.TextColumn(help="League average in the same situation."),
                                     "Plays": st.column_config.NumberColumn(help="Plays behind the rate."),
                                 })  # fmt: skip
                    continue
                pts = gh.tendency_points(tend, off_side, sit)
                if not pts:
                    st.write("Not enough plays yet.")
                    continue
                fig = make_subplots(
                    rows=len(pts), cols=1, vertical_spacing=0.12 / max(len(pts), 1) * 4
                )
                for i, r in enumerate(pts, 1):
                    vals = [v for v in (r["off"], r["def"], r["league"]) if v is not None]
                    tick = ".0%" if r["unit"] == "pct" else "+.2f"
                    pad = max((max(vals) - min(vals)) * 0.4, 0.02 if r["unit"] == "pct" else 0.03)
                    tip = textwrap.fill(r["help"], 48).replace("\n", "<br>")
                    fig.add_trace(go.Scatter(x=[min(vals), max(vals)], y=[r["label"]] * 2,
                                             mode="lines", line={"color": NEU["grid"], "width": 3},
                                             hoverinfo="skip", showlegend=False), row=i, col=1)  # fmt: skip
                    for key, name, col, sym in (("league", "League average", NEU["ref"], "diamond"),
                                                ("off", f"{off_t} offense", "#2a78d6", "circle"),
                                                ("def", f"{def_t} defense", "#1baf7a", "square")):  # fmt: skip
                        if r[key] is None:
                            continue
                        fig.add_trace(go.Scatter(
                            x=[r[key]], y=[r["label"]], mode="markers", name=name,
                            legendgroup=name, showlegend=i == 1,
                            marker={"size": 12, "color": col, "symbol": sym},
                            hovertemplate=f"<b>{r['label']}</b><br>{name}: {data.fmt(r[key], r['unit'])}"
                            f"<br>{tip}<extra></extra>"), row=i, col=1)  # fmt: skip
                    fig.update_xaxes(tickformat=tick, range=[min(vals) - pad, max(vals) + pad],
                                     row=i, col=1)  # fmt: skip
                fig.update_layout(height=90 + 62 * len(pts), margin={"l": 0, "r": 10, "t": 10, "b": 0},
                                  legend={"orientation": "h", "y": 1.0 + 0.9 / len(pts) * 0.4})  # fmt: skip
                st.plotly_chart(fig, width="stretch", key=f"tend_{sit}_{off_side}")
    with st.expander("What do these metrics mean?"):
        for label_, om, dm, _u, hlp in gh.TENDENCY_PAIRS:
            st.markdown(f"**{label_}**: {hlp}")
    st.caption("Season-to-date rates, shrunk toward the league average when plays are few. Each "
               "row has its own scale.")  # fmt: skip

# ------------------------------------------------------------------------------------- injuries
st.subheader("Injuries")
inj = g.get("injuries") or []
if not inj:
    st.write("No injury report yet.")
else:
    for team in (away, home):
        t = [i for i in inj if i["team"] == team]
        st.markdown(f"**{team}**")
        if not t:
            st.write("None listed.")
            continue
        st.dataframe(
            pl.DataFrame([{"Player": i["player"], "Pos": i["pos"], "Status": i["status"],
                           "Injury": i.get("injury"), "Practice": i.get("practice")} for i in t]),
            hide_index=True, width="stretch",
        )  # fmt: skip

# ------------------------------------------------------------------------------------- narrative
st.subheader("The week's narrative")
nar = g.get("narrative")
if not nar:
    st.info("This week's research hasn't run yet (`/nfl-narrative`).")
else:
    st.caption(f"What the week's coverage says, as of {nar['known_as_of']} (producer: "
               f"{nar['producer']}). Text is written from cited sources; it never feeds the "
               "probabilities.")  # fmt: skip
    if nar.get("consensus_narrative"):
        st.markdown(f"**The story:** {nar['consensus_narrative']}")
    for side in ("away", "home"):
        t = nar[side]
        st.markdown(f"#### {t['team']}")
        st.write(t["summary"])
        st.caption(
            f"QB: {t.get('qb_name') or 'n/a'} ({gh.QB_STATUS.get(t['qb_status'], t['qb_status'])})"
            + (f" · key absences: {', '.join(t['key_absences'])}" if t.get("key_absences") else "")
            + (" · revenge game" if t.get("revenge") else "")
            + (" · lookahead spot" if t.get("lookahead") else "")
        )
        notes = t.get("notes") or []
        if notes:
            st.markdown("**What matters**", help="▲ helps and ▼ hurts this team; more arrows mean a "
                        "bigger effect.")  # fmt: skip
            for n in sorted(notes, key=lambda n: -abs(n.get("impact") or 0)):
                st.markdown(f"- {gh.note_line(n)}")
        trends = t.get("scheme_trends") or []
        if trends:
            st.markdown("**Scheme trends**", help="What analysts say the unit is doing lately and "
                        "whether it is working.")  # fmt: skip
            for tr in trends:
                st.markdown(f"- {gh.trend_line(tr)}")
        if not notes and not trends:
            st.caption("No detailed notes in this research record (older format).")
    mnotes = gh.matchup_notes_sorted(nar)
    if mnotes:
        st.markdown("#### What people are saying about the matchup",
                    help="Takes from public analysis of how these two teams match up. More "
                    "independent sources agreeing means more weight.")  # fmt: skip
        for n in mnotes:
            st.markdown(f"- {gh.matchup_line(n)}")
    with st.expander(f"Claims and sources ({len(nar.get('claims') or [])})"):
        for c in nar.get("claims") or []:
            title = c.get("source_title") or c["source_url"]
            st.markdown(
                f"- {c['claim']} ({c['category']}, {c['confidence']} confidence"
                f"{', ' + c['published_at'] if c.get('published_at') else ''}) "
                f"[{title}]({c['source_url']})"
            )

st.caption(
    "Probabilities are the models' estimates, not advice. Fan-made, not affiliated with the NFL."
)
