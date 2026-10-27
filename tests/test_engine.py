"""Scoring engine: standardization, symmetry, contributions."""

import json

import numpy as np
import polars as pl
import pytest
from scipy.special import expit

from nfl.approaches import engine, schema

FEATS = ["strength.elo_pre", "form.streak", "environment.neutral_site"]
TEAM = ["strength.elo_pre", "form.streak"]


def toy_model(intercept=0.2, a=1.0, c=0.0):
    sc = engine.Scaler(FEATS, mean=[0.0, 0.0, 0.0], sd=[100.0, 2.0, 1.0])
    return engine.Model("toy", FEATS, intercept, [0.5, 0.2, -0.3], sc, calib_a=a, calib_c=c)


def frame(rows):
    return pl.DataFrame(rows, schema=["game_id", *FEATS], orient="row")


def test_zero_vector_is_home_field_only():
    out = toy_model(intercept=0.2).score(frame([("G", 0.0, 0.0, 0.0)]))
    assert out["p_home"][0] == pytest.approx(expit(0.2))
    assert out["spread_home"][0] > 0


def test_nulls_and_missing_columns_are_league_average():
    m = toy_model()
    a = m.score(frame([("G", None, None, None)]))
    b = m.score(pl.DataFrame({"game_id": ["G"]}))
    assert a["p_home"][0] == pytest.approx(expit(0.2)) == pytest.approx(b["p_home"][0])


def test_swapping_home_and_away_flips_team_contributions():
    m = toy_model(intercept=0.0)
    home = m.score(frame([("G", 120.0, 3.0, 0.0)]))
    away = m.score(frame([("G", -120.0, -3.0, 0.0)]))
    assert home["p_home"][0] == pytest.approx(1 - away["p_home"][0])
    assert home["spread_home"][0] == pytest.approx(-away["spread_home"][0])
    ch, ca = (json.loads(x["contributions"][0]) for x in (home, away))
    for f in TEAM:
        assert ch[f] == pytest.approx(-ca[f])


def test_contributions_sum_to_logit_with_calibration():
    m = toy_model(intercept=0.1, a=0.7, c=0.05)
    out = m.score(frame([("G", 80.0, -1.0, 1.0), ("H", -30.0, 2.0, 0.0)]))
    for row in out.iter_rows(named=True):
        assert sum(json.loads(row["contributions"]).values()) == pytest.approx(
            row["logit"], abs=1e-5
        )
        assert row["p_home"] == pytest.approx(expit(row["logit"]))


def test_scaler_fit_and_roundtrip():
    wide = frame([("A", 100.0, 1.0, 0.0), ("B", -100.0, None, 1.0), ("C", 0.0, 3.0, 0.0)])
    sc = engine.Scaler.fit(wide, FEATS)
    assert sc.mean[0] == pytest.approx(0.0)
    z = sc.transform(wide)
    assert z[1, 1] == 0.0  # null -> league average
    m = engine.Model("x", FEATS, 0.1, [1.0, 0.0, 0.0], sc, 0.9, 0.01, {"lam": 3})
    m2 = engine.Model.from_dict(json.loads(json.dumps(m.to_dict())))
    np.testing.assert_allclose(m.score(wide)["p_home"], m2.score(wide)["p_home"])


def test_persona_model_from_flat_config():
    a = schema.Approach.model_validate(
        {
            "id": "flat",
            "name": "Flat",
            "blurb": "A flat persona.",
            "emphasis": ["market"],
            "intercept": {"w": 0.0, "why": "none"},
            "weights": {
                "market.spread_line": {"w": 0.85, "why": "the line"},
                "strength.elo_pre": {"w": 0.05, "why": "ratings"},
            },
        }
    )
    sc = engine.Scaler(a.features, [0.0] * len(a.features), [1.0] * len(a.features))
    m = engine.persona_model(a, sc)
    assert m.model_id == "flat.persona"
    assert m.weights[a.features.index("market.spread_line")] == 0.85
    with pytest.raises(ValueError):
        engine.persona_model(a, engine.Scaler(["x.y"], [0.0], [1.0]))
