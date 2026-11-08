from datetime import datetime

import numpy as np
import polars as pl

from nfl import swings
from nfl.approaches.engine import Model, Scaler

CHART = [("q1", "Lamar Jackson"), ("q2", "Tyler Huntley")]
STARTS = {"last": "q1", "usual": "q1", "names": {"q1": "L.Jackson"}}


def test_candidates_keep_chart_order_and_add_usual_and_last():
    st = {"last": "q3", "usual": "q1", "names": {"q3": "Old Starter"}}
    assert list(swings.candidates(CHART, st)) == ["q1", "q2", "q3"]


def test_assumed_is_the_candidate_whose_value_the_line_holds():
    vals = {"q1": {"strength.qb_epa": 0.1}, "q2": {"strength.qb_epa": -0.11}}
    assert swings.assumed_qb(-0.11, vals) == "q2"
    assert swings.assumed_qb(0.5, vals) is None
    assert swings.assumed_qb(None, vals) is None


def test_a_questionable_starter_brings_the_next_one_up():
    assert swings.alternative(CHART, STARTS, {"q1": "Questionable"}, "q1") == ("q2", "status")


def test_a_line_on_someone_other_than_the_charted_qb1_shows_the_chart():
    assert swings.alternative(CHART, STARTS, {}, "q3") == ("q1", "chart")


def test_a_questionable_usual_starter_who_isnt_assumed():
    st = {"last": "q2", "usual": "q9", "names": {}}
    assert swings.alternative(CHART, st, {"q9": "Questionable"}, "q1") == ("q9", "usual")


def test_nobody_in_doubt_means_no_what_if():
    assert swings.alternative(CHART, STARTS, {}, "q1") is None
    assert swings.alternative([], STARTS, {"q1": "Out"}, "q1") is None


def _rows(home_epa, away_epa):
    k = datetime(2026, 11, 1)
    return pl.DataFrame({
        "game_id": ["G"] * 2, "side": ["home", "away"], "feature": ["strength.qb_epa"] * 2,
        "value": [home_epa, away_epa], "known_as_of": [k, k],
    })  # fmt: skip


def test_a_worse_quarterback_lowers_his_sides_chance_and_leaves_the_rows_alone():
    m = Model("student", ["strength.qb_epa"], 0.0, [1.0], Scaler(["strength.qb_epa"], [0.0], [0.1]))
    rows = _rows(0.1, 0.0)
    base = swings.rescore([("student", m)], rows, "G", datetime(2026, 11, 2))
    worse = swings.apply(rows, "home", {"strength.qb_epa": -0.25})
    what = swings.rescore([("student", m)], worse, "G", datetime(2026, 11, 2))
    assert what["student"] < base["student"]
    assert rows["value"].to_list() == [0.1, 0.0]  # the input is untouched
    assert np.isclose(worse.filter(pl.col("side") == "away")["value"][0], 0.0)


def test_apply_ignores_a_feature_the_rows_dont_have():
    rows = _rows(0.1, 0.0)
    assert swings.apply(rows, "home", {"availability.qb1_out": 1.0}).equals(rows)


def test_weather_is_a_factor_only_past_the_thresholds():
    assert swings.weather_text(55.0, 8.0, 10.0) is None
    assert swings.weather_text(None, None, None) is None
    assert (
        swings.weather_text(28.4, 17.2, 60.0)
        == "Kickoff forecast: wind 17 mph, 60% chance of rain or snow, 28°F"
    )
    assert swings.weather_text(40.0, 15.0, None) == "Kickoff forecast: wind 15 mph"
