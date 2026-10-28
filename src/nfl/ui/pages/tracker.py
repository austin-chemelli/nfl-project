"""Season tracker (M5.4, readability pass M5.11): one line per approach, always next to the market.

Reads tracker.json and meta.json via nfl.ui.data. One season (and ~180 live games) cannot rank
models; every section says so where it matters. Log loss is the scoring rule but is always shown
beside the market's and in plain words; nothing is shown in log-odds.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nfl.ui import data
from nfl.ui.tracker_helpers import (
    calibration_scale_sentence,
    calibration_verdict,
    divergence_sentence,
    fold_reliability,
    line,
    ll_vs_market,
    market_wins_when_apart,
    persona_history_headline,
    short_name,
    style,
    table_view,
    text_color,
)

st.header("Season tracker")
T = data.require(data.tracker())
M = data.require(data.meta())
SEASON = T.get("season")
LABEL = data.label
APPS = [a["id"] for a in data.approaches()]
KEY = [*APPS, "ensemble", "market_baseline"]
REFS = ["elo_v0", "home_naive"]
ALL = [m for m in [*KEY, *REFS, "global"] if m in M.get("models", {})]

HELP_LL = (
    "Log loss is the scoring rule: it punishes confident wrong calls hard. Lower is better; "
    "0.693 is a coin flip. The market scores about 0.61, so read every number as a distance "
    "from the market. Differences under 0.005 are noise at this sample size."
)
HELP_MARKET = (
    "The betting market's win probability with the bookmaker's cut removed. It is the reference "
    "line we compare against and is never an input to any approach (ADR 0013)."
)

st.caption(
    "Forecast quality comes first (log loss: lower is better; 0.693 is a coin flip), paper bets "
    "second. About 180 live games a season cannot rank models, and in the 2005 to 2025 backtest "
    "nothing beats the market. Treat everything here as a measurement, not a verdict."
)

# ---------------------------------------------------------------- 1. headline
st.subheader(
    f"{SEASON} so far", help="Games already played this season, each scored against the market."
)
cur = pd.DataFrame(T.get("current_season", []))
wt = T.get("weeks_tracked", {}) or {}
if cur.empty:
    st.info("No graded games this season yet.")
else:
    last = cur.sort_values("week").groupby("model_id").tail(1).set_index("model_id")
    games = cur.groupby("model_id")["n"].sum()
    mk = last["cum_log_loss"].get("market_baseline")
    rows = []
    for m in KEY:
        if m not in last.index:
            continue
        ll = float(last.loc[m, "cum_log_loss"])
        rows.append(
            {
                "Model": LABEL(m),
                "Games": int(games[m]),
                "Log loss": round(ll, 3),
                "vs market": "reference" if m == "market_baseline" else ll_vs_market(
                    ll, None if mk is None else float(mk)).split(";")[0].split(", ", 1)[-1],
                "Live weeks": int(wt.get(m, 0)),
            }
        )  # fmt: skip
    st.dataframe(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
        column_config={
            "Games": st.column_config.NumberColumn(help="Graded games so far this season."),
            "Log loss": st.column_config.NumberColumn(help=HELP_LL),
            "vs market": st.column_config.TextColumn(help=HELP_MARKET),
            "Live weeks": st.column_config.NumberColumn(
                help="Weeks graded from a real pre-kickoff lock, not backfill."
            ),
        },
    )
    live_weeks = int(cur.loc[cur["live"], "week"].nunique())
    if live_weeks == 0:
        st.caption(
            "No live locks have been graded yet, so every number above is backfill: frozen models "
            "scored after the fact on this season's games. Differences under 0.005 are noise."
        )

    # ------------------------------------------------------------ 2. cumulative log loss
    st.subheader(
        "Cumulative log loss by week",
        help="Running average log loss since week 1. Lower is better; compare against the Market line.",
    )
    pick = st.multiselect(
        "Models",
        ALL,
        default=[m for m in [*KEY, "elo_v0"] if m in ALL],
        format_func=LABEL,
        key="cum_models",
        help="Pick which lines to draw. One line per approach; gray lines are references.",
    )
    fig = go.Figure()
    weeks = sorted(cur["week"].unique())
    first_live = cur.loc[cur["live"], "week"].min() if live_weeks else None
    back_end = (first_live - 0.5) if first_live is not None else max(weeks) + 0.5
    fig.add_vrect(
        x0=min(weeks) - 0.5,
        x1=back_end,
        fillcolor=data.NEUTRAL[data.theme()]["mid"],
        opacity=0.6,
        line_width=0,
        annotation_text="backfill (scored after the fact)",
        annotation_position="top left",
        annotation_font_color=text_color(),
    )
    for m in pick:
        d = cur[cur["model_id"] == m].sort_values("week")
        fig.add_scatter(
            x=d["week"],
            y=d["cum_log_loss"],
            name=LABEL(m),
            mode="lines",
            customdata=d[["n", "live"]],
            hovertemplate="%{fullData.name}<br>Week %{x}: %{y:.3f}<br>"
            "%{customdata[0]} games that week<extra></extra>",
            **line(m),
        )
        lv = d[d["live"]]
        if not lv.empty:  # live weeks: filled diamonds on the line
            fig.add_scatter(
                x=lv["week"],
                y=lv["cum_log_loss"],
                mode="markers",
                marker={"symbol": "diamond", "size": 10, "color": data.color(m)},
                showlegend=False,
                hoverinfo="skip",
            )
    style(fig, 400, "Week", "Cumulative mean log loss (lower is better)")
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Shaded weeks are backfill: models frozen before the season, scored after the fact. "
        "Diamonds mark live weeks, graded from locks made before kickoff. A handful of 16-game "
        "weeks is very noisy; lines crossing early means little."
    )
    table_view(cur.rename(columns={"model_id": "model"}), "Table view: cumulative log loss")

# ---------------------------------------------------------------- 3. backtest
st.subheader(
    "Backtest: how far each model sits from the market",
    help="Every game from 2005 on, scored by models that never trained on the season they predict.",
)
bt = pd.DataFrame(T.get("backtest", []))
if not bt.empty:
    mkl = bt.loc[bt["model_id"] == "market_baseline", "log_loss"]
    mk_bt = float(mkl.iloc[0]) if len(mkl) else None
    bt = bt[bt["model_id"] != "market_baseline"].sort_values("d_vs_market")
    fig = go.Figure()
    fig.add_vline(x=0, line_color=data.color("market_baseline"), line_width=2)
    for _, r in bt.iterrows():
        m = r["model_id"]
        fig.add_scatter(
            x=[r["d_vs_market"]],
            y=[LABEL(m)],
            mode="markers",
            showlegend=False,
            marker={"color": data.color(m), "size": 10, "symbol": "circle"},
            error_x={
                "type": "data",
                "symmetric": False,
                "array": [r["d_hi"] - r["d_vs_market"]],
                "arrayminus": [r["d_vs_market"] - r["d_lo"]],
                "color": data.color(m),
                "thickness": 2,
            },
            hovertemplate=f"{LABEL(m)}<br>{r['d_vs_market']:+.3f} vs the market "
            f"(90% range {r['d_lo']:+.3f} to {r['d_hi']:+.3f})<br>"
            f"{int(r['n_games']):,} games<extra></extra>",
        )
    style(fig, 440, "Log loss minus the market's (left of the line = better than the market)")
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, width="stretch")
    st.caption(
        f"{int(bt['first_season'].min())} to {int(bt['last_season'].max())}; the whiskers are a "
        "90% range from resampling whole seasons. The zero line is the market. A model only "
        "beats the market if its whole whisker sits left of the line."
    )
    if mk_bt is not None:
        for m in [x for x in APPS + ["ensemble"] if x in set(bt["model_id"])]:
            ll = float(bt.loc[bt["model_id"] == m, "log_loss"].iloc[0])
            st.markdown(f"- **{LABEL(m)}**: {ll_vs_market(ll, mk_bt)}.")
    table_view(
        bt[["model_id", "n_games", "log_loss", "d_vs_market", "d_lo", "d_hi"]],
        "Table view: backtest",
    )

ss = pd.DataFrame(T.get("seasons", []))
if not ss.empty:
    st.markdown("**Log loss by season**", help=HELP_LL)
    sel = st.multiselect(
        "Models",
        sorted(ss["model_id"].unique()),
        default=[m for m in ["market_baseline", "sharp", "analyst", "ensemble"] if m in ALL],
        format_func=LABEL,
        key="season_models",
        help="Seasons are noisy (about 285 games each); the gaps between lines matter more than the wiggle.",
    )
    fig = go.Figure()
    for m in sel:
        d = ss[ss["model_id"] == m].sort_values("season")
        fig.add_scatter(
            x=d["season"], y=d["log_loss"], name=LABEL(m), mode="lines", customdata=d[["n"]],
            hovertemplate="%{fullData.name}<br>%{x}: %{y:.3f} (%{customdata[0]} games)<extra></extra>",
            **line(m),
        )  # fmt: skip
    style(fig, 360, "Season", "Mean log loss (lower is better)")
    st.plotly_chart(fig, width="stretch")
    table_view(ss.pivot(index="season", columns="model_id", values="log_loss").reset_index())

# ---------------------------------------------------------------- 4. calibration
st.subheader(
    "Calibration: when it says 70%, how often does that team win?",
    help="A calibrated forecaster's 70% calls win about 70% of the time. Points below the dotted "
    "diagonal mean the approach was overconfident; above it, underconfident.",
)
rel = pd.DataFrame(T.get("reliability", []))
if not rel.empty:
    avail = sorted(rel["model_id"].unique())
    rsel = st.multiselect(
        "Compare up to 3",
        avail,
        default=[m for m in ["market_baseline", "traditionalist", "sharp"] if m in avail],
        format_func=LABEL,
        key="rel_models",
        help="Each dot pools games with similar predicted chances; hover for how many games.",
    )
    if len(rsel) > 3:
        st.warning("Showing the first 3 selected models.")
        rsel = rsel[:3]
    fig = go.Figure()
    fig.add_scatter(
        x=[0.5, 1], y=[0.5, 1], mode="lines", name="Perfect calibration", hoverinfo="skip",
        line={"color": data.NEUTRAL[data.theme()]["ref"], "dash": "dot", "width": 1},
    )  # fmt: skip
    for m in rsel:
        d = pd.DataFrame(fold_reliability(rel[rel["model_id"] == m].to_dict("records")))
        fig.add_scatter(
            x=d["mean_p"], y=d["hit_rate"], name=LABEL(m), mode="lines+markers",
            marker={"size": 7}, customdata=d[["n"]],
            hovertemplate="%{fullData.name}<br>said %{x:.0%}, won %{y:.0%}<br>"
            "n = %{customdata[0]:,} games<extra></extra>",
            **line(m),
        )  # fmt: skip
    style(fig, 420, "Chance the approach gave the favored team", "How often that team won")
    fig.update_xaxes(range=[0.5, 1], tickformat=".0%")
    fig.update_yaxes(range=[0.4, 1], tickformat=".0%")
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Each game counts toward the team the approach favored (so a 25% home team is a 75% "
        "away team). Dots on the dotted diagonal are well calibrated; the highest bins hold few "
        "games, so their wobble is mostly noise."
    )
    for m in [x for x in [*APPS, "ensemble", "market_baseline"] if x in avail]:
        st.markdown(
            "- " + calibration_verdict(rel[rel["model_id"] == m].to_dict("records"), LABEL(m))
        )
    table_view(rel[rel["model_id"].isin(rsel)], "Table view: reliability bins")

# ---------------------------------------------------------------- 5. divergence
st.subheader(
    "When an approach disagrees with the market",
    help="For each game, the side an approach likes more than the market does. Did that side win "
    "more often than the market said it would?",
)
dv = pd.DataFrame(T.get("divergence", []))
if not dv.empty:
    dv_apps = [m for m in [*APPS, "ensemble"] if m in set(dv["model_id"])]
    order = ["0-2.5", "2.5-5", "5-10", "10+"]
    wins, tot = market_wins_when_apart(dv[dv["model_id"].isin(dv_apps)].to_dict("records"))
    if tot and wins == tot:
        st.markdown(
            "**The market has been right more often when they disagree.** In every approach, in "
            "every case where the gap was 5+ points, the market's probabilities scored better "
            "than the approach's on those games."
        )
    elif tot:
        st.markdown(
            f"**When they disagree by 5+ points, the market scored better in {wins} of {tot} "
            "approach-and-gap cases.**"
        )
    dsel = st.selectbox(
        "Approach", dv_apps, format_func=LABEL, key="div_model",
        help="Choose whose disagreements to read.",
    )  # fmt: skip
    d = dv[dv["model_id"] == dsel].copy()
    d["o"] = d["bucket"].map({b: i for i, b in enumerate(order)})
    d = d.sort_values("o")
    name = short_name(LABEL(dsel))
    for _, r in d.iterrows():
        st.markdown("- " + divergence_sentence(r.to_dict(), name))
    fig = go.Figure()
    xs = [f"{b} pts apart (n = {int(n):,})" for b, n in zip(d["bucket"], d["n"], strict=True)]
    fig.add_bar(x=xs, y=d["market_expected_rate"], name="Market expected", marker_color=data.color("market_baseline"),
                hovertemplate="Market expected %{y:.0%}<extra></extra>")  # fmt: skip
    fig.add_bar(x=xs, y=d["lean_win_rate"], name=f"{LABEL(dsel)}'s side won", marker_color=data.color(dsel),
                customdata=d[["n"]], hovertemplate="Its side won %{y:.0%} (n = %{customdata[0]:,})<extra></extra>")  # fmt: skip
    style(
        fig,
        340,
        "How far apart the approach and the market were",
        "Win rate of the approach's side",
    )
    fig.update_layout(barmode="group")
    fig.update_yaxes(tickformat=".0%", range=[0, 0.6])
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "If an approach saw something the market missed, its bar would sit above the market's. "
        "The side an approach leans toward is the underdog relative to the market, so bars "
        "below 50% are expected; what matters is the gap between the two bars."
    )
    table_view(d.drop(columns="o"), "Table view: disagreement buckets")

# ---------------------------------------------------------------- 6. paper bets
st.subheader(
    "Paper bets",
    help="Pretend wagers, no money involved. Profit and loss over a season is dominated by luck.",
)
st.markdown(
    "Each lock, every approach stakes a flat 1 unit on the moneyline wherever its win probability "
    "differs from the vig-free market by more than 5 points (a unit wins about 0.9 to 2 units "
    "depending on the price). **Season profit and loss is mostly noise**; closing-line value "
    "(CLV, whether the price you got beat the final price) is the better edge signal. Backfill "
    "bets are priced at nflverse's closing-ish line, so their ROI is a harsh lower bound and "
    "their CLV is undefined (–)."
)
led = pd.DataFrame(T.get("ledger", []))
led = (
    led[led["model_id"].isin([*APPS, "ensemble", "market_baseline", *REFS])]
    if not led.empty
    else led
)
if led.empty:
    st.info("No bets recorded yet.")
else:
    led["Approach"] = led["model_id"].map(LABEL)
    led["Record"] = led.apply(lambda r: f"{r['wins']}-{r['losses']}-{r['pushes']}", axis=1)
    led["Return"] = led["roi"].map(lambda v: data.pct(v, 1))
    led["Kind"] = led["kind"].map({"backfill": "backfill", "live": "live"}).fillna(led["kind"])
    out = led.rename(columns={"bets": "Bets", "units": "Units", "clv": "CLV"})
    out = out.sort_values(["Kind", "Units"], ascending=[True, False])
    st.dataframe(
        out[["Approach", "Kind", "Bets", "Record", "Units", "Return", "CLV"]],
        width="stretch",
        hide_index=True,
        column_config={
            "Kind": st.column_config.TextColumn(help="Backfill = priced after the fact; live = placed at a real lock."),
            "Bets": st.column_config.NumberColumn(help="Games where the approach differed from the market by 5+ points."),
            "Record": st.column_config.TextColumn(help="Wins-losses-pushes."),
            "Units": st.column_config.NumberColumn(help="Profit in units; each bet risks 1 unit. Mostly noise."),
            "Return": st.column_config.TextColumn(help="Profit divided by units staked (ROI)."),
            "CLV": st.column_config.NumberColumn(help="Average edge versus the closing price; positive means the approach beat the final market."),
        },
    )  # fmt: skip
    st.caption(
        "Backfill rows cover every graded season in the backtest, not just this one. Live rows "
        "appear after the first graded locks. Losing a few percent into the market's price is "
        "what a model that trails the market looks like."
    )

# ---------------------------------------------------------------- 7. persona vs history
st.subheader(
    "Persona vs history: what each approach believes vs what history supports",
    help="Every approach spreads 100 attention points over the same feature groups. The persona "
    "chose its split by belief; history's split is what the data alone would choose.",
)
st.markdown(
    "Each approach has **100 attention points** to spread over the same groups of evidence. For "
    "each group: what the persona believes, the public line (the persona after light fitting "
    "and calibration, which is what is scored above), and what history alone would choose. "
    "Hover a bar for the persona's reasoning."
)
apps = {a["id"]: a for a in data.approaches()}
if apps:
    aid = st.selectbox(
        "Approach", list(apps), format_func=lambda i: apps[i]["name"], key="pf_app",
        help="Each approach is a character with its own biases.",
    )  # fmt: skip
    a = apps[aid]
    P, L, H = a.get("persona_share", {}), a.get("public_share", {}), a.get("history_share", {})
    gname = {k: data.group(k)["name"] for k in set(P) | set(L) | set(H)}
    keys = sorted(set(P) | set(L) | set(H), key=lambda k: -max(abs(P.get(k, 0)), abs(H.get(k, 0))))
    nm = [gname[k] for k in keys]
    why = [a.get("why", {}).get(k, "No stated reason (history chose this).") for k in keys]
    col = data.color(aid)
    ref = data.NEUTRAL[data.theme()]["ref"]
    fig = go.Figure()
    for lab, src, c, pat in (
        ("Persona believes", P, col, ""),
        ("Public line (lightly fitted)", L, col, "/"),
        ("History alone would choose", H, ref, ""),
    ):
        fig.add_bar(
            y=nm, x=[src.get(k, 0) for k in keys], name=lab, orientation="h",
            marker={"color": c, "pattern": {"shape": pat}},
            customdata=why,
            hovertemplate="%{y}: " + lab.lower() + " %{x:.1f} of 100 points<br>%{customdata}<extra></extra>",
        )  # fmt: skip
    style(
        fig,
        140 + 48 * len(keys),
        "Share of the 100-point attention budget (negative = history says it points the other way)",
    )
    fig.update_layout(barmode="group")
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, width="stretch")
    st.markdown(f"*{a['blurb']}*")
    head = persona_history_headline(a, gname)
    if head:
        st.markdown(
            f"**{head}**",
            help="Points of the 100-point budget that move if history chose the split.",
        )
    if sent := calibration_scale_sentence(a.get("calibration_scale")):
        st.markdown(
            sent,
            help="Confidence is learned from history for every approach so their records are comparable.",
        )
    tbl = pd.DataFrame(
        {"Group": nm, "Persona": [P.get(k, 0) for k in keys],
         "Public line": [L.get(k, 0) for k in keys], "History": [H.get(k, 0) for k in keys],
         "Why (persona)": why}
    )  # fmt: skip
    table_view(tbl.round(1), "Table view: attention points by group")
