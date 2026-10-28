"""Streamlit app (P1 UI): navigation shell. Pages live in nfl/ui/pages/ and read marts/site/*.json via
nfl.ui.data. The React site (P2) reads the same JSON."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

st.set_page_config(page_title="NFL approaches", page_icon="🏈", layout="wide")
HERE = Path(__file__).parent / "pages"

pages = {
    "This week": [
        st.Page(
            HERE / "slate.py", title="Slate", icon=":material/calendar_view_week:", default=True
        ),
        st.Page(HERE / "game.py", title="Game", icon=":material/sports_football:"),
    ],
    "Track record": [
        st.Page(HERE / "tracker.py", title="Season tracker", icon=":material/query_stats:"),
        st.Page(HERE / "hypotheses.py", title="Hypotheses", icon=":material/science:"),
        st.Page(HERE / "coaches.py", title="Coaches & schemes", icon=":material/groups:"),
    ],
    "Play": [
        st.Page(HERE / "diy.py", title="Build your own", icon=":material/tune:"),
        st.Page(HERE / "season.py", title="Season view", icon=":material/date_range:"),
    ],
    "About": [
        st.Page(HERE / "method.py", title="Method & data", icon=":material/info:"),
        st.Page(HERE / "explore.py", title="Explore tendencies", icon=":material/table_chart:"),
    ],
}
st.navigation(pages, position="sidebar").run()
st.sidebar.caption(
    "Data: nflverse (CC-BY), FTN charting via nflverse (CC-BY-SA 4.0), The Odds API. "
    "Fan-made, not affiliated with the NFL."
)
