"""Season view data: slim per-season JSON written by `nfl diy-matrix` (M5.13)."""

import json

import numpy as np
import pytest

from nfl.approaches import diy
from nfl.config import get_paths
from tests.conftest import requires_data


@requires_data
def test_season_files_are_slim_and_consistent_with_the_matrix():
    paths = get_paths()
    f = paths.site / "season_2015.json"
    if not f.exists():
        diy.build_matrix(paths)
    doc = json.loads(f.read_text())
    n = doc["n"]
    assert 250 <= n <= 290
    for k in ("game_id", "week", "home", "away", "kickoff", "result", "home_won", "market_p"):
        assert len(doc[k]) == n
    assert set(doc["c"]) == set(doc["groups"]) and len(doc["groups"]) == 15
    assert all(len(v) == n for v in doc["c"].values())
    assert f.stat().st_size < 80_000
    assert doc["home_won"] == [int(r > 0) for r in doc["result"]]  # ties are not in the matrix
    assert all(int(g[:4]) == 2015 for g in doc["game_id"])
    # the file's games are exactly the matrix's scored games for that season
    m = diy.load_matrix(paths.site / "diy_matrix.json")
    rows = (m["season"] == 2015) & ~m["warmup"]
    assert set(doc["game_id"]) == set(m["game_id"][rows])


@requires_data
def test_every_scored_season_has_a_file():
    paths = get_paths()
    missing = [s for s in range(2005, 2026) if not (paths.site / f"season_{s}.json").exists()]
    assert not missing


@requires_data
def test_season_predictions_match_the_season_log_loss():
    paths = get_paths()
    m = diy.load_matrix(paths.site / "diy_matrix.json")
    w = {g: 1.0 for g in m["groups"] if g not in m["inactive"]}
    ev = diy.evaluate(w, m)
    row = next(s for s in ev["seasons"] if s["season"] == 2015)
    sp = diy.season_predictions(w, m, 2015)
    y = m["y"][m["season"] == 2015]
    assert diy._ll(sp["p"], y).mean() == pytest.approx(row["log_loss"])
    assert np.all((sp["p"] > 0) & (sp["p"] < 1))


@requires_data
@pytest.mark.parametrize("set_id", ["yours", "student", "sharp"])
def test_season_page_renders_with_query_params(set_id):
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    page = Path(__file__).resolve().parents[1] / "src" / "nfl" / "ui" / "pages" / "season.py"
    at = AppTest.from_file(str(page), default_timeout=120)
    at.query_params["season"] = "2015"
    at.query_params["set"] = set_id
    at.query_params["w"] = "quality:30,offense:20,market:40"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.selectbox[0].value == 2015
    assert at.dataframe  # the games table rendered
    assert at.dataframe[-1].value.shape[0] > 200
