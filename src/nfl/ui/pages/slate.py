"""Slate page: one row per game, what each approach picks, divergence from the market highlighted."""

from __future__ import annotations

from datetime import datetime

import polars as pl
import streamlit as st
from streamlit.errors import StreamlitAPIException

from nfl.ui import data
from nfl.ui import slate_helpers as sh

st.header("Slate")
meta = data.require(data.meta())
weeks = meta["weeks"]
season = meta["season"]

c1, c2 = st.columns([1, 4])
week = c1.selectbox(
    "Week",
    weeks,
    index=weeks.index(meta["current_week"]) if meta["current_week"] in weeks else 0,
    format_func=lambda w: f"Week {w}",
    help="NFL regular-season week.",
)
as_table = c2.toggle("Table view", help="The same numbers as a sortable table.")

lock = meta.get("last_lock")
gen = (
    datetime.fromisoformat(meta["generated_at"])
    .astimezone(data.ET)
    .strftime("%b %-d, %-I:%M %p ET")
)
st.caption(
    f"Site data updated {gen}. "
    + (
        f"Last lock: week {lock['week']}, {data.kickoff_et(lock['lock_ts'])}."
        if lock
        else "No live lock yet."
    )
)

sl = data.require(data.slate(season, week), f"No slate for week {week}.")
games = sorted(sl["games"], key=lambda g: g["kickoff_utc"] or "")
cols = [*data.approaches(), {"id": "ensemble", "name": "Ensemble",
                              "blurb": "The average of the four approaches."}]  # fmt: skip


def _name(a: dict) -> str:
    return a["name"].removeprefix("The ")


def _blurb(a: dict) -> str:
    """Hover text for a column header: what the approach is."""
    return a.get("blurb") or "Mean of the four approaches."


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("'", "&#39;").replace('"', "&quot;").replace("<", "&lt;")


HEAD_HELP = {
    "Kickoff (ET)": "Kickoff time, US Eastern.",
    "Game": "Away team @ home team. Open one below for the full breakdown.",
    "Line": "The betting market's spread: the favorite and how many points it is favored by.",
    "Mkt home": "The market's chance that the home team wins, with the bookmaker's margin removed.",
    "Status": "preview = scored now, not a lock; locked = recorded before kickoff; "
    "backfill = finished game scored after the fact by frozen models.",
}


# "Where they disagree" strip
top = sh.disagreements(games)
if top:
    st.subheader("Where they disagree most")
    st.caption("The games where the four approaches are furthest apart on the home team's chance.")
    for d in top:
        g = d["game"]
        st.markdown(
            f"**{g['away']} @ {g['home']}**: {data.label(d['hi']).removeprefix('The ')} "
            f"{sh.side_text(g, d['ps'][d['hi']])} vs "
            f"{data.label(d['lo']).removeprefix('The ')} "
            f"{sh.side_text(g, d['ps'][d['lo']])} "
            f"({100 * d['spread']:.0f} points apart)"
        )

st.subheader(f"Week {week}")
st.caption(
    "One line per approach, plus the average of all four. Each cell: the team that approach "
    "favors and its win chance (hover a column title to learn what that approach is). "
    "Shaded cell with ▲/▼: the approach is 5+ points more on the home (▲) or away (▼) side than "
    "the market. ✓/✗: right/wrong about the winner. Status: **preview** = scored now, not a lock; "
    "**locked** = recorded before kickoff; **backfill** = finished game scored after the fact by "
    "frozen models."
)


def _status_text(g: dict) -> str:
    s, ts = sh.status(g)
    return f"locked {data.kickoff_et(ts)}" if s == "locked" and ts else s


if as_table:
    rows = []
    for g in games:
        mk = g.get("market") or {}
        row = {
            "Kickoff": data.kickoff_et(g["kickoff_utc"]),
            "Game": f"{g['away']} @ {g['home']}",
            "Line": data.spread(mk.get("spread_home"), g["home"], g["away"]),
            "Market home win": mk.get("p_home"),
        }
        for a in cols:
            mid = a["id"]
            pk = sh.pick(g, mid)
            row[_name(a)] = None if pk is None else f"{pk['team']} {data.pct(pk['p'])}"
            row[_name(a) + " vs market"] = None if pk is None else pk["div"]
        row["Status"] = _status_text(g)
        row["Final"] = sh.score_text(g)
        rows.append(row)
    df = pl.DataFrame(rows, infer_schema_length=None)
    st.dataframe(
        df,
        hide_index=True,
        width="stretch",
        column_config={
            "Market home win": st.column_config.NumberColumn(
                format="percent", help=HEAD_HELP["Mkt home"]
            ),
            "Line": st.column_config.TextColumn(help=HEAD_HELP["Line"]),
            "Status": st.column_config.TextColumn(help=HEAD_HELP["Status"]),
            **{_name(a): st.column_config.TextColumn(help=_blurb(a)) for a in cols},
            **{
                _name(a) + " vs market": st.column_config.NumberColumn(
                    format="%+.3f",
                    help=f"{_name(a)}'s home win chance minus the market's (0.05 = 5 points more "
                    "on the home side).",
                )
                for a in cols
            },
        },
    )
else:
    th = "text-align:left;padding:4px 8px;border-bottom:1px solid rgba(128,128,128,.4)"
    td = "padding:4px 8px;border-bottom:1px solid rgba(128,128,128,.2);white-space:nowrap"
    heads = [(h, HEAD_HELP[h]) for h in ["Kickoff (ET)", "Game", "Line", "Mkt home"]]
    heads += [(_name(a), _blurb(a)) for a in cols] + [("Status", HEAD_HELP["Status"])]
    head = "".join(
        f"<th style='{th}' title='{_esc(tip)}'>{h} <span style='opacity:.5'>ⓘ</span></th>"
        for h, tip in heads
    )
    body = []
    for g in games:
        mk = g.get("market") or {}
        k = data.kickoff_et(g["kickoff_utc"])
        cells = [
            f"<td style='{td}'>{k.removesuffix(' ET')}</td>",
            f"<td style='{td}'><b>{g['away']} @ {g['home']}</b></td>",
            f"<td style='{td}'>{data.spread(mk.get('spread_home'), g['home'], g['away'])}</td>",
            f"<td style='{td}'>{data.pct(mk.get('p_home'))}</td>",
        ]
        for a in cols:
            mid = a["id"]
            pk = sh.pick(g, mid)
            if pk is None:
                cells.append(f"<td style='{td}'>–</td>")
                continue
            txt = f"{pk['team']} {data.pct(pk['p'])}"
            style = td
            if pk["div"] is not None and abs(pk["div"]) >= sh.DIVERGE:
                txt += " ▲" if pk["div"] > 0 else " ▼"
                style += f";background:{data.color(mid)}30;font-weight:600"
            ok = sh.correct(g, mid)
            if ok is not None:
                txt += " ✓" if ok else " ✗"
            cells.append(f"<td style='{style}'>{txt}</td>")
        st_txt = _status_text(g)
        if g.get("result"):
            st_txt += f"<br><small>Final: {sh.score_text(g)}</small>"
        cells.append(f"<td style='{td};white-space:normal'>{st_txt}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(
        "<div style='overflow-x:auto'><table style='border-collapse:collapse;width:100%'>"
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )

st.subheader("Open a game")
per_row = 4
for i in range(0, len(games), per_row):
    for col, g in zip(st.columns(per_row), games[i : i + per_row], strict=False):
        label = f"{g['away']} @ {g['home']}"
        try:
            col.page_link("pages/game.py", label=label, query_params={"game": g["game_id"]})
        except StreamlitAPIException:  # outside the navigation shell (tests): plain text
            col.write(label)

st.caption(
    "Probabilities are the models' estimates, not advice. Fan-made, not affiliated with the NFL."
)
