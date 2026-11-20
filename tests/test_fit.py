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


def test_line_move_is_capped_inside_the_model_only():
    """JAX @ BAL moved 12.5 points and entered at -8.3 SD. The model sees the cap; the input stays."""
    from nfl.approaches.engine import Scaler
    from nfl.features.groups import FEATURE_CAPS

    cap = FEATURE_CAPS["market.line_move_pts"]
    sc = Scaler(["market.line_move_pts", "strength.epa_off"], [0.0, 0.0], [1.5, 1.0])
    wide = pl.DataFrame(
        {"market.line_move_pts": [-12.5, 12.5, 2.0, None], "strength.epa_off": [9.0] * 4}
    )
    z = sc.transform(wide)
    np.testing.assert_allclose(z[:, 0], [-cap / 1.5, cap / 1.5, 2.0 / 1.5, 0.0])
    np.testing.assert_allclose(z[:, 1], 9.0)  # other features are not capped
    assert wide["market.line_move_pts"][0] == -12.5


@pytest.mark.parametrize("approach_id", ["student", "analyst"])
def test_declared_line_move_weight_survives_fitting_with_no_history(approach_id):
    """Line move exists live only, so it can't be learned: its weight stays where the YAML sets it,
    including for the Student, whose public line is the fitted one."""
    a = schema.load_all()[approach_id]
    data = toy_data(a).with_columns(pl.lit(None, dtype=pl.Float64).alias("market.line_move_pts"))
    res = fit.fit_flavors(a, data, lam=100.0, trained_through=2025)
    pub = res.public
    w = pub.weights[pub.features.index("market.line_move_pts")]
    assert w == pytest.approx(a.groups["market"].w, rel=1e-6)


# ---------------------------------------------------------------- shift_10 (ADR 0026, M23.1)


def test_shift_recovers_an_offset():
    rng = np.random.default_rng(3)
    logit = rng.standard_normal(6000) * 1.5
    y = (rng.random(6000) < 1 / (1 + np.exp(-(logit - 0.2)))).astype(float)
    assert fit.fit_shift(logit, y) == pytest.approx(-0.2, abs=0.06)


def test_shift_10_fits_its_offset_on_the_last_ten_training_seasons_only():
    """Home field moves: a model trained since 2002 carries the old level. The offset is fitted on
    the ten seasons before the scored one, never on the scored season itself."""
    rng = np.random.default_rng(4)
    seasons = np.repeat(np.arange(2002, 2026), 300)
    logit = rng.standard_normal(seasons.size)
    home = np.where(seasons > 2015, -0.3, 0.3)  # recent seasons: the model over-states home field
    y = (rng.random(seasons.size) < 1 / (1 + np.exp(-(logit + home)))).astype(float)
    a = schema.load_all()["student"]
    assert a.calibration == "shift_10"
    m = fit.Model(model_id="x", features=["f"], intercept=0.0, weights=[1.0],
                  scaler=fit.Scaler(["f"], [0.0], [1.0]))  # fmt: skip
    pub = fit._public_from(a, m, None, logit[:, None], y, seasons)
    assert pub.calib_a == 1.0
    assert pub.meta["calib_seasons"] == 10 * 300
    assert pub.calib_c == pytest.approx(-0.3, abs=0.08)  # the recent level, not the pooled 0


def test_existing_approach_hashes_are_pinned():
    """The lock refuses a fit whose config hash differs from the YAML. A schema change that alters
    every config's serialized form (a new field with a default) would stop every lock; this pins
    the four live approaches. Changing a persona on purpose: update the pin and follow the
    runbook's cutover (refit, backfill, upload in one go)."""
    # re-pinned 2026-11-20 for model wave 3 (ADR 0031): every config changed on purpose
    pins = {"traditionalist": "c5bbd23735cb", "analyst": "16608e26c57c",
            "sharp": "bbc096a2fd16", "student": "cf0e91518f1c"}  # fmt: skip
    got = {k: fit.config_hash(a) for k, a in schema.load_all().items() if k in pins}
    assert got == pins


def test_only_keeps_just_the_named_approaches(tmp_path, monkeypatch):
    from nfl.approaches import ensemble, run
    from nfl.config import Paths

    monkeypatch.setattr(run, "known_features", lambda paths: {"strength.epa_off"})
    paths = Paths(tmp_path)
    assert [a.id for a in run.scored_approaches(paths, {"sharp"})] == ["sharp"]
    every = [a.id for a in run.scored_approaches(paths)]
    assert {"student", "sharp", ensemble.GLOBAL_ID} <= set(every)
    assert "student_v2" not in every  # folded into the Student (ADR 0031)


# ------------------------------------------------- neutral sites and season weights (ADR 0031)


def test_home_field_is_zero_at_a_neutral_site():
    """The neutral-site rule: a gated model's home-field term (intercept and calibration offset)
    is multiplied by 1 − neutral_site, for every approach; contributions still sum to the logit."""
    import json

    from nfl.approaches.engine import NEUTRAL

    sc = fit.Scaler(["f"], [0.0], [1.0])
    m = fit.Model("x", ["f"], 0.4, [0.5], sc, calib_a=1.0, calib_c=-0.1, neutral_gate=True)
    assert m.inputs == ["f", NEUTRAL]
    wide = pl.DataFrame({"game_id": ["a", "b"], "f": [1.0, 1.0], NEUTRAL: [0.0, 1.0]})
    out = m.score(wide)
    assert out["logit"].to_list() == pytest.approx([0.8, 0.5])
    for row in out.iter_rows(named=True):
        assert sum(json.loads(row["contributions"]).values()) == pytest.approx(row["logit"])
    ungated = fit.Model("x", ["f"], 0.4, [0.5], sc, calib_c=-0.1)
    assert ungated.score(wide)["logit"].to_list() == pytest.approx([0.8, 0.8])
    assert fit.Model.from_dict(m.to_dict()).neutral_gate is True


def test_the_fitted_intercept_ignores_neutral_games():
    """Home field is learned from games with a home crowd only: neutral games don't dilute it."""
    rng = np.random.default_rng(5)
    n = 8000
    neutral = (rng.random(n) < 0.3).astype(float)
    g = 1.0 - neutral
    y = (rng.random(n) < 1 / (1 + np.exp(-0.4 * g))).astype(float)
    b, _ = fit.fit_ridge(np.zeros((n, 0)), y, np.zeros(0), 1.0, g=g)
    assert b == pytest.approx(0.4, abs=0.08)
    b_pooled, _ = fit.fit_ridge(np.zeros((n, 0)), y, np.zeros(0), 1.0)
    assert b_pooled < b - 0.05


def test_season_weights_halve_per_half_life():
    w = fit.season_weights(np.array([2020, 2024, 2024]), 4.0)
    assert w[0] / w[1] == pytest.approx(0.5)
    assert w.mean() == pytest.approx(1.0)
    assert fit.season_weights(np.array([2020]), None) is None
