"""Fitting: ridge limits, Platt, walk-forward boundaries."""

import numpy as np
import polars as pl
import pytest

from nfl.approaches import fit, schema


def synth(n=4000, w=(0.8, -0.4, 0.0), b=0.2, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n, len(w)))
    y = (rng.random(n) < 1 / (1 + np.exp(-(b + z @ np.array(w))))).astype(float)
    return z, y


def test_ridge_recovers_weights_when_lambda_small():
    z, y = synth()
    b, w = fit.fit_ridge(z, y, w0=np.zeros(3), lam=1e-6)
    np.testing.assert_allclose(w, [0.8, -0.4, 0.0], atol=0.1)
    assert b == pytest.approx(0.2, abs=0.1)


def test_ridge_returns_prior_when_lambda_huge():
    z, y = synth()
    w0 = np.array([0.1, 0.2, 0.3])
    _, w = fit.fit_ridge(z, y, w0=w0, lam=1e9)
    np.testing.assert_allclose(w, w0, atol=1e-3)


def test_platt_recovers_scale():
    rng = np.random.default_rng(1)
    logit = rng.standard_normal(5000) * 2
    y = (rng.random(5000) < 1 / (1 + np.exp(-(0.5 * logit + 0.1)))).astype(float)
    a, c = fit.fit_platt(logit, y)
    assert a == pytest.approx(0.5, abs=0.07)
    assert c == pytest.approx(0.1, abs=0.07)


def toy_data(approach, seasons=range(2010, 2026), per=270, seed=2):
    rng = np.random.default_rng(seed)
    rows = []
    for s in seasons:
        for i in range(per):
            x = rng.standard_normal(len(approach.features))
            y = float(rng.random() < 1 / (1 + np.exp(-(0.15 + 0.6 * x[0]))))
            rows.append((f"{s}_{i}", s, 1 + i // 16, y, *x))
    return pl.DataFrame(
        rows, schema=["game_id", "season", "week", "y", *approach.features], orient="row"
    )


def test_walk_forward_never_trains_on_the_scored_season():
    a = schema.load_all()["analyst"]
    data = toy_data(a)
    res = fit.walk_forward(a, data, (2015, 2025), lam=100.0)
    assert set(res) == set(range(2015, 2026))
    for season, r in res.items():
        for m in (r.persona, r.fitted):
            assert m.meta["trained_through"] < season
            assert m.meta["trained_through"] == season - 1
            assert m.meta["n_games"] == data.filter(pl.col("season") < season).height


def test_select_lambda_and_artifact_roundtrip(tmp_path):
    from nfl.config import Paths

    a = schema.load_all()["sharp"]
    data = toy_data(a)
    lam, table = fit.select_lambda(a, data)
    assert lam in a.fit.lambda_grid
    assert table.height == len(a.fit.lambda_grid)
    r = fit.fit_flavors(a, data.filter(pl.col("season") < 2025), lam, 2024)
    paths = Paths(tmp_path)
    fit.save(paths, r.fitted)
    m = fit.load(paths, "sharp.fitted", 2024)
    test = data.filter(pl.col("season") == 2025).select("game_id", *a.features)
    np.testing.assert_allclose(m.score(test)["p_home"], r.fitted.score(test)["p_home"])
