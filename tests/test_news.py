"""The news adjustment (ADR 0032): bounded, double-count-free, repeatability-gated, exact in points."""

import json
from datetime import datetime

import numpy as np
import polars as pl
import pytest
from scipy.special import expit
from scipy.stats import norm

from nfl.approaches import news
from nfl.features import store

KAO = datetime(2026, 11, 7, 12, 0)


def asof(rows):
    """rows: (side, feature, value) for game G."""
    return pl.DataFrame(
        [(2026, 9, "G", s, f, v, KAO, "t", "1") for s, f, v in rows],
        schema=store.FEATURE_SCHEMA,
        orient="row",
    )


def adj(rows, w=None):
    r = news.adjustment(asof(rows), ["G"], w).row(0, named=True)
    return r["adj_pts"], json.loads(r["reasons"])


def test_declared_weights_match_the_adr_and_each_has_a_why():
    assert news.CAP_PTS == 1.5
    assert news.WEIGHTS == {
        "news.qb_change_confirmed": -1.1,
        "narrative.qb_status": -0.5,
        "news.starters_ruled_out": -0.2,
        "narrative.injury_impact": -0.2,
        "narrative.motivation": 0.3,
    }
    assert set(news.WHY) == set(news.WEIGHTS) and all(news.WHY.values())


def test_no_inputs_no_adjustment():
    assert adj([]) == (0.0, [])
    assert adj([("home", "strength.elo_pre", 1600.0)]) == (0.0, [])


def test_sign_is_home_minus_away_in_points():
    pts, rs = adj([("away", "narrative.qb_status", 1.0), ("home", "narrative.motivation", 1.0)])
    assert pts == pytest.approx(
        0.5 + 0.3
    )  # the away QB's trouble and the home must-win help the home side
    assert {r["team"] for r in rs} == {"home", "away"}
    assert sum(r["pts"] for r in rs) == pytest.approx(
        pts
    )  # reasons sum to the adjustment (uncapped)


def test_cap_binds_at_one_and_a_half_points_both_ways():
    rows = [("home", "narrative.qb_status", 2.0), ("home", "narrative.injury_impact", 3.0),
            ("home", "news.starters_ruled_out", 4.0)]  # fmt: skip
    pts, rs = adj(rows)
    assert sum(r["pts"] for r in rs) == pytest.approx(
        -(1.0 + 0.6 + 0.8)
    )  # the raw sum, before the cap
    assert pts == -1.5
    flipped = [(("away" if s == "home" else "home"), f, v) for s, f, v in rows]
    assert adj(flipped)[0] == 1.5


def test_reasons_are_sorted_by_size():
    _, rs = adj([("home", "narrative.injury_impact", 1.0), ("home", "narrative.qb_status", 2.0)])
    assert [r["input"] for r in rs] == ["narrative.qb_status", "narrative.injury_impact"]


@pytest.mark.parametrize("gate", ["availability.qb1_out", "availability.qb_change"])
def test_qb_status_is_not_counted_when_the_chart_already_flags_the_qb(gate):
    pts, rs = adj([("home", "narrative.qb_status", 2.0), ("home", gate, 1.0)])
    assert (pts, rs) == (0.0, [])
    # the gate is per team: the away team's flag doesn't switch off the home team's rating
    pts, _ = adj([("home", "narrative.qb_status", 2.0), ("away", gate, 1.0)])
    assert pts == pytest.approx(-1.0)


def test_confirmed_qb_change_counts_only_while_the_chart_shows_no_change():
    base = [("home", "news.qb_change_confirmed", 1.0)]
    assert adj(base)[0] == pytest.approx(-1.1)
    assert adj([*base, ("home", "availability.qb_change", 1.0)]) == (0.0, [])
    # a team whose QB1 is out but with no charted change still gets the confirmed change
    assert adj([*base, ("home", "availability.qb1_out", 1.0)])[0] == pytest.approx(-1.1)


def test_unrepeatable_rating_gets_zero_weight_only_with_enough_pairs(monkeypatch):
    table = {
        "qb_status": (0.60, 12),  # measured and poor: out
        "injury_impact": (0.60, 11),  # too few pairs: counts
        "narrative.motivation": (0.70, 30),  # exactly at the bar: counts (needs < 0.70 to lose)
    }
    monkeypatch.setattr(news, "agreement_table", lambda paths: table)
    w = news.weights(object())
    assert w["narrative.qb_status"] == 0.0
    assert w["narrative.injury_impact"] == -0.2
    assert w["narrative.motivation"] == 0.3
    pts, rs = adj([("home", "narrative.qb_status", 2.0)], w)
    assert (pts, rs) == (0.0, [])


def test_unmeasured_counts_in_full(monkeypatch):
    monkeypatch.setattr(news, "agreement_table", lambda paths: {})
    assert news.weights(object()) == news.WEIGHTS
    assert news.weights(None) == news.WEIGHTS


def test_agreement_table_survives_a_missing_module(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "nfl.llm.repeat", None)  # import raises ImportError
    assert news.agreement_table(object()) == {}


def test_logit_adjustment_is_exact_in_points_at_the_lines_own_spread():
    spread = np.array([-10.2, 0.0, 3.0])
    logit = np.log(norm.cdf(spread / 13.5) / (1 - norm.cdf(spread / 13.5)))
    for pts in (-1.5, -0.4, 1.5):
        d = news.adj_logit(spread, logit, np.full(3, pts))
        shifted = norm.ppf(expit(logit + d)) * 13.5
        assert shifted == pytest.approx(spread + pts)
    assert (news.adj_logit(spread, logit, np.zeros(3)) == 0).all()


def scored_frame():
    spread = norm.ppf(0.7) * 13.5
    logit = float(np.log(0.7 / 0.3))
    contrib = json.dumps({"home_field": 0.2, "strength.elo_pre": logit - 0.2})
    return pl.DataFrame(
        {"game_id": ["G", "H"], "p_home": [0.7, 0.7], "spread_home": [spread] * 2,
         "logit": [logit] * 2, "contributions": [contrib] * 2}
    )  # fmt: skip


def test_apply_moves_spread_by_the_points_and_contributions_still_sum_to_the_logit():
    adj_df = news.adjustment(asof([("home", "narrative.qb_status", 2.0)]), ["G", "H"])
    out = news.apply(scored_frame(), adj_df).sort("game_id")
    g, h = out.row(0, named=True), out.row(1, named=True)
    assert g["spread_home"] == pytest.approx(norm.ppf(0.7) * 13.5 - 1.0)
    assert g["p_home"] == pytest.approx(expit(g["logit"])) and g["p_home"] < 0.7
    assert sum(json.loads(g["contributions"]).values()) == pytest.approx(g["logit"])
    assert g["news_pts"] == -1.0 and json.loads(g["news_reasons"])[0]["pts"] == -1.0
    # a game with no news is untouched, byte for byte (the backfill can't move)
    assert h["p_home"] == 0.7 and h["contributions"] == scored_frame()["contributions"][1]
    assert "news" not in json.loads(h["contributions"]) and h["news_pts"] == 0.0


def test_describe_speaks_plain_words_on_each_teams_own_line():
    rs = [{"input": "narrative.qb_status", "team": "home", "value": 1.0, "pts": -0.5},
          {"input": "news.starters_ruled_out", "team": "away", "value": 2.0, "pts": 0.4}]  # fmt: skip
    d = news.describe(rs, "HOU", "IND")
    assert d == [{"label": "QB questionable", "team": "HOU", "pts": -0.5},
                 {"label": "2 starters ruled out", "team": "IND", "pts": -0.4}]  # fmt: skip


def test_points_from_logit_recovers_the_adjustment():
    spread = np.array([-4.0])
    logit = np.log(norm.cdf(spread / 13.5) / (1 - norm.cdf(spread / 13.5)))
    d = float(news.adj_logit(spread, logit, np.array([1.2]))[0])
    assert news.points_from_logit(float(logit[0]) + d, d) == pytest.approx(1.2)


def test_ruled_out_counts_net_of_the_official_report():
    assert adj([("home", "news.starters_ruled_out", 3.0)])[0] == pytest.approx(-0.6)
    pts, rs = adj([("home", "news.starters_ruled_out", 3.0), ("home", "availability.starters_out", 2.0)])  # fmt: skip
    assert pts == pytest.approx(-0.2) and rs[0]["value"] == 1.0
    assert adj([("home", "news.starters_ruled_out", 2.0), ("home", "availability.starters_out", 2.0)]) == (0.0, [])  # fmt: skip


def test_injury_impact_counts_only_when_the_report_and_chart_show_nothing():
    base = ("home", "narrative.injury_impact", 2.0)
    assert adj([base])[0] == pytest.approx(-0.4)
    assert adj([base, ("home", "availability.starters_out", 1.0)]) == (0.0, [])
    assert adj([base, ("home", "availability.qb1_out", 1.0)]) == (0.0, [])
    assert adj([base, ("home", "availability.qb_change", 1.0)]) == (0.0, [])


def test_one_qb_situation_yields_one_qb_term():
    # a confirmed change: no qb_status, no injury_impact, no ruled-out starters on top (TB at DET)
    rows = [("home", "news.qb_change_confirmed", 1.0), ("home", "narrative.qb_status", 2.0),
            ("home", "narrative.injury_impact", 3.0), ("home", "news.starters_ruled_out", 2.0)]  # fmt: skip
    pts, rs = adj(rows)
    assert [r["input"] for r in rs] == ["news.qb_change_confirmed"] and pts == pytest.approx(-1.1)
    # without the change the other terms are back
    assert len(adj(rows[1:])[1]) == 3


def test_agreement_table_survives_a_corrupt_file(tmp_path):
    from nfl.config import Paths

    paths = Paths(tmp_path)
    f = paths.marts / "narrative_repeat.parquet"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"not a parquet file")
    with pytest.warns(UserWarning, match="repeat agreement unreadable"):
        assert news.agreement_table(paths) == {}
    assert news.weights(paths) == news.WEIGHTS
