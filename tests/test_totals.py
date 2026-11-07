from datetime import datetime

import numpy as np
import polars as pl
import pytest

from nfl.approaches import totals
from nfl.config import Paths

LOCK = datetime(2026, 11, 12, 12)


def _asof(gid, home, away, game=None):
    rows = [(gid, "home", f, v) for f, v in home.items()] + [
        (gid, "away", f, v) for f, v in away.items()
    ]
    rows += [(gid, "game", f, v) for f, v in (game or {}).items()]
    return pl.DataFrame(rows, schema=["game_id", "side", "feature", "value"], orient="row")


def test_vectors_sum_both_sides_and_null_when_one_is_missing():
    a = pl.concat([
        _asof("g1", {"strength.epa_off": 0.1}, {"strength.epa_off": 0.05}, {"environment.is_dome": 1.0}),
        _asof("g2", {"strength.epa_off": 0.1}, {}, {"weather.wind_mph": 22.0, "weather.temp_f": 25.0}),
    ])  # fmt: skip
    v = totals.vectors(a).sort("game_id")
    assert v["sum.strength.epa_off"].to_list()[0] == pytest.approx(0.15)
    assert v["sum.strength.epa_off"].to_list()[1] is None
    assert v["weather.wind_over_10"].to_list() == [0.0, 12.0]  # unknown or under a roof: no excess
    assert v["weather.cold_under_40"].to_list() == [0.0, 15.0]
    assert v.columns == ["game_id", *totals.INPUTS]


def _train(n=800, seed=0):
    rng = np.random.default_rng(seed)
    x = {c: rng.normal(size=n) for c in totals.INPUTS}
    y = (
        45
        + 4 * x["sum.strength.epa_off"]
        - 3 * x["weather.wind_over_10"]
        + rng.normal(scale=8, size=n)
    )
    return pl.DataFrame({"game_id": [f"g{i}" for i in range(n)], "season": [2020] * n, "y": y, **x})


def test_fit_finds_the_signal_and_missing_inputs_score_as_average():
    m = totals.fit(_train(), 2025)
    w = dict(zip(m.inputs, m.w, strict=True))
    assert w["sum.strength.epa_off"] > 2.5 and w["weather.wind_over_10"] < -1.5
    assert abs(m.b - 45) < 1.5 and 7 < m.sd < 9
    blank = pl.DataFrame(
        {c: [None] for c in totals.INPUTS}, schema={c: pl.Float64 for c in totals.INPUTS}
    )
    assert m.predict(blank)[0] == pytest.approx(m.b)


def _rows(lock, total=47.5, market=44.5, gid="2026_10_BUF_KC"):
    return pl.DataFrame({"game_id": [gid], "season": [2026], "week": [10], "model_id": [totals.MODEL_ID],
                         "model_version": ["1.x"], "lock_ts": [lock], "slot": ["thu"], "total": [total],
                         "sd_total": [13.4], "market_total": [market]})  # fmt: skip


def test_the_totals_ledger_is_append_only(tmp_path):
    paths = Paths(root=tmp_path)
    assert totals.append(paths, _rows(LOCK)) == 1
    assert totals.append(paths, _rows(LOCK, total=99.0)) == 0  # same game and lock: never rewritten
    assert totals.load(paths)["total"].to_list() == [47.5]
    assert totals.append(paths, _rows(datetime(2026, 11, 14, 17), total=48.0)) == 1
    assert totals.load(paths).height == 2


def test_grade_uses_the_last_lock_and_the_market_side(tmp_path):
    paths = Paths(root=tmp_path)
    totals.append(paths, _rows(LOCK, total=40.0))
    totals.append(paths, _rows(datetime(2026, 11, 14, 17), total=47.5))
    games = pl.DataFrame({"game_id": ["2026_10_BUF_KC"], "result": [3], "total": [51]})
    g = totals.grade(paths, games)
    assert g.height == 1 and g["total"][0] == 47.5 and g["error"][0] == 3.5
    assert g["side_right"][0] is True  # over 44.5 and it went over
    s = totals.summary(g, totals.load(paths))
    assert s["weeks"] == 1 and s["n"] == 1 and s["mae"] == 3.5 and s["market_mae"] == 6.5
    assert (s["side_right"], s["side_n"]) == (1, 1)


def test_an_unplayed_game_is_not_graded_and_the_summary_still_counts_weeks(tmp_path):
    paths = Paths(root=tmp_path)
    totals.append(paths, _rows(LOCK))
    games = pl.DataFrame({"game_id": ["2026_10_BUF_KC"], "result": [None], "total": [None]},
                         schema={"game_id": pl.Utf8, "result": pl.Int64, "total": pl.Int64})  # fmt: skip
    g = totals.grade(paths, games)
    s = totals.summary(g, totals.load(paths))
    assert g.is_empty() and s["n"] == 0 and s["weeks"] == 1 and s["mae"] is None


def test_lock_rows_never_carry_a_win_chance_and_live_in_their_own_file(tmp_path):
    m = totals.fit(_train(), 2025)
    slate = pl.DataFrame({"game_id": ["g1"], "season": [2026], "week": [10]})
    scored = pl.DataFrame({"game_id": ["g1"], "total": [46.0], "sd_total": [13.0]})
    r = totals.lock_rows(m, scored, slate, None, LOCK, "thu")
    assert r.columns == list(totals.ROWS) and "p_home" not in r.columns
    assert r["market_total"][0] is None and r["model_version"][0].endswith(m.config_hash)
    assert totals.ledger_path(Paths(root=tmp_path)).name == "totals.parquet"


def test_expected_score_splits_the_locked_total_by_the_headline_spread():
    from nfl import site

    t = {"total": 47.0, "sd_total": 13.4, "market_total": 44.5, "lock_ts": LOCK}
    e = site._expected_score(t, {"models": {site.HEADLINE_ID: {"spread_home": 3.0}}})
    assert (e["home"], e["away"], e["total"], e["market_total"]) == (25.0, 22.0, 47.0, 44.5)
    assert site._expected_score(t, {"models": {}})["home"] is None
    assert site._expected_score(None, {}) is None


def test_the_weather_family_stays_out_of_the_global_fit_and_hypotheses():
    from nfl.approaches import ensemble

    a = ensemble.global_approach({"strength.epa_off", "weather.wind_mph", "weather.temp_f"})
    assert "weather" in ensemble.EXCLUDED_FAMILIES
    assert (
        "weather.wind_mph" not in a.model_dump_json() and "strength.epa_off" in a.model_dump_json()
    )
