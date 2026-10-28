"""Slate and Game pages on contract v2: real site JSON, plus a v2 narrative rendered from example()."""

import copy
from pathlib import Path

import pytest

from nfl.config import get_paths
from nfl.ui import data
from nfl.ui import game_helpers as gh
from nfl.ui import slate_helpers as sh

PAGES = Path(__file__).resolve().parents[1] / "src" / "nfl" / "ui" / "pages"
SITE = get_paths().site
HAS_SITE = (SITE / "meta.json").exists()
pytestmark = pytest.mark.skipif(not HAS_SITE, reason="needs marts/site (run nfl site)")


def _run(page: str, game_id: str | None = None):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PAGES / f"{page}.py"), default_timeout=120)
    if game_id:
        at.query_params["game"] = game_id
    return at.run()


def _first_game(completed: bool) -> str | None:
    import json

    for f in sorted((SITE / "game").glob("*.json")):
        g = json.loads(f.read_text())
        if bool(g.get("result")) == completed and g.get("contributions") and g.get("edges"):
            return g["game_id"]
    return None


def test_slate_one_column_per_approach():
    at = _run("slate")
    assert not at.exception, [e.value for e in at.exception]
    md = " ".join(m.value for m in at.markdown)
    for name in ("Traditionalist", "Analyst", "Sharp", "Student", "Ensemble"):
        assert name in md
    assert "persona" not in md.lower().replace("personal", "")
    assert not [t for t in at.toggle if "flavor" in t.label.lower()]


@pytest.mark.parametrize("completed", [True, False])
def test_game_renders_contributions_and_edges(completed):
    gid = _first_game(completed)
    if gid is None:
        pytest.skip("no such game in site data")
    at = _run("game", gid)
    assert not at.exception, [e.value for e in at.exception]
    text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    assert "points of" in text
    assert "log-odds" not in text.lower()


def test_game_v2_narrative_renders(monkeypatch):
    from streamlit.testing.v1 import AppTest

    from nfl.llm import narrative

    gid = _first_game(False)
    if gid is None:
        pytest.skip("no upcoming game")
    real = data.game(gid)
    g = copy.deepcopy(real)
    ex = narrative.example()
    ex["home_team"], ex["away_team"] = g["home"], g["away"]
    ex["home"]["team"], ex["away"]["team"] = g["home"], g["away"]
    g["narrative"] = ex
    monkeypatch.setattr(data, "game", lambda i: g if i == gid else None)
    # AppTest runs the script in-process, so the patched loader is what the page sees
    at = AppTest.from_file(str(PAGES / "game.py"), default_timeout=120)
    at.query_params["game"] = gid
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    md = " ".join(m.value for m in at.markdown)
    assert "What people are saying about the matchup" in md
    assert "2 sources" in md
    assert "Scheme trends" in md
    assert "working" in md and "▼" in md


def test_helpers_v2():
    assert gh.pts_toward(3.94, "GB", "CAR") == "+3.9 pts toward GB"
    assert gh.pts_toward(-1.2, "GB", "CAR") == "-1.2 pts toward CAR"
    assert gh.impact_marker(2) == "▲▲ helps a lot"
    assert gh.impact_marker(-1) == "▼ hurts"
    assert gh.trend_status(None) == "unclear"
    edges = {
        "defense": {"favors": "GB", "strength_pct": 55.0},
        "health": {"favors": None, "strength_pct": 19.0},
    }
    rows = gh.edge_rows(edges, "GB")
    assert len(rows) == 1 and rows[0]["signed"] == 55.0 and "bigger than 55%" in rows[0]["text"]
    assert (
        sh.pick({"home": "A", "away": "B", "models": {"sharp": {"p_home": 0.4}}}, "sharp")["team"]
        == "B"
    )
