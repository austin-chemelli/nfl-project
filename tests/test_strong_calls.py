import json
from datetime import datetime

import polars as pl

from nfl import strong_calls as sc
from nfl.lock import Scored

LOCK = datetime(2026, 11, 5, 14)
SLATE = pl.DataFrame({"game_id": ["G", "H"], "season": [2026, 2026], "week": [9, 9],
                      "home_team": ["BAL", "KC"], "away_team": ["JAX", "DEN"]})  # fmt: skip
MARKET = pl.DataFrame({"game_id": ["G", "H"], "p_home": [0.52, 0.60], "spread_home": [1.0, 3.0]})
CONTRIB = json.dumps({"home_field": 0.2, "strength.qb_epa": 0.3, "strength.epa_off": 0.1,
                      "strength.epa_def": -0.25, "form.streak": 0.05})  # fmt: skip


def scored(p_g, p_h, model="student"):
    f = pl.DataFrame({"game_id": ["G", "H"], "p_home": [p_g, p_h], "spread_home": [3.0, 3.5],
                      "contributions": [CONTRIB, CONTRIB]})  # fmt: skip
    return Scored(model, "v", f)


def test_only_gaps_of_ten_points_or_more_become_calls():
    out = sc.calls([scored(0.62, 0.65)], MARKET, SLATE, LOCK, {"student": "The Student"})
    assert out["game_id"].to_list() == ["G"]
    assert out["side"][0] == "home" and out["team"][0] == "BAL"


def test_reference_models_never_make_calls():
    assert sc.calls(
        [scored(0.9, 0.9, "global"), scored(0.9, 0.9, "market_baseline")], MARKET, SLATE, LOCK, {}
    ).is_empty()


def test_top_groups_pull_toward_the_side_only():
    names = [g["name"] for g in sc.top_groups(CONTRIB, "home")]
    assert names[0] == "Quarterback" and "Defense" not in names
    assert [g["name"] for g in sc.top_groups(CONTRIB, "away")] == ["Defense"]


def test_the_sentence_uses_only_stored_numbers_and_names_the_assumption():
    swings = {"G": [{"kind": "qb", "team": "BAL", "why": "status",
                     "assumed": {"name": "Lamar Jackson", "p_home": {"student": 0.62}},
                     "alternative": {"name": "Tyler Huntley", "p_home": {"student": 0.54}}}]}  # fmt: skip
    out = sc.calls([scored(0.62, 0.65)], MARKET, SLATE, LOCK, {"student": "The Student"}, swings)
    s = out["sentence"][0]
    assert s.startswith("The Student has BAL at 62% against the market's 52%.")
    assert "It assumes Lamar Jackson starts for BAL; with Tyler Huntley it reads 54%." in s
    assert out["what_if_p_home"][0] == 0.54


def test_an_away_call_reads_from_the_away_side():
    out = sc.calls([scored(0.40, 0.65)], MARKET, SLATE, LOCK, {"student": "The Student"})
    assert out["sentence"][0].startswith("The Student has JAX at 60% against the market's 48%.")


def test_append_only(tmp_path):
    from nfl.config import Paths

    paths = Paths(tmp_path)
    paths.marts.mkdir(parents=True)
    first = sc.calls([scored(0.62, 0.65)], MARKET, SLATE, LOCK, {})
    sc.append(paths, first)
    sc.append(paths, sc.calls([scored(0.30, 0.65)], MARKET, SLATE, LOCK, {}))
    got = sc.load(paths)
    assert got.height == 2
    assert got.head(1).drop("lock_ts").equals(first.drop("lock_ts"))


def test_grading_result_log_loss_and_closing_move():
    c = sc.calls([scored(0.62, 0.65)], MARKET, SLATE, LOCK, {})
    games = pl.DataFrame({"game_id": ["G"], "result": [7]})
    g = sc.grade(c, games, {"G": 2.5}).row(0, named=True)
    assert g["result"] == "right"
    assert g["log_loss"] < g["market_log_loss"]
    assert g["closing_toward"] is True  # spread 1.0 -> 2.5 toward BAL, the call's side
    assert sc.grade(c, pl.DataFrame({"game_id": ["G"], "result": [None]}), {})["result"][0] is None


def test_record_counts_per_approach():
    c = sc.grade(
        sc.calls([scored(0.62, 0.65)], MARKET, SLATE, LOCK, {}),
        pl.DataFrame({"game_id": ["G"], "result": [-3]}),
        {},
    )
    r = {x["model_id"]: x for x in sc.record(c)}
    assert r["student"]["decided"] == 1 and r["student"]["right"] == 0
    assert r["analyst"]["n"] == 0
