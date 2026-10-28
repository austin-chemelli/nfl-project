"""Build-your-own evaluator: synthetic-matrix properties and one real-data consistency check."""

import time

import numpy as np
import polars as pl
import pytest

from nfl.approaches import diy
from nfl.config import get_paths
from tests.conftest import requires_data

G = ["quality", "offense", "defense", "quarterback"]
TRUE_W = {"quality": 0.6, "offense": 0.4, "defense": 0.0, "quarterback": 0.3}


def synthetic(n_per=300, seasons=range(2005, 2013), seed=1) -> dict:
    rng = np.random.default_rng(seed)
    season = np.repeat(list(seasons), n_per)
    n = len(season)
    C = rng.normal(size=(n, len(G)))
    logit = C @ np.array([TRUE_W[g] for g in G]) + 0.1
    y = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(float)
    mkt = 1 / (1 + np.exp(-0.7 * logit))
    return {
        "groups": G,
        "inactive": [],
        "first_scored": 2005,
        "n": n,
        "columns": {
            "game_id": [f"{s}_01_AAA_BBB" for s in season],
            "season": season.tolist(),
            "week": [1] * n,
            "y": y.tolist(),
            "mkt_p": mkt.tolist(),
            "warmup": [0] * n,
            "spread_bucket": rng.integers(0, 3, n).tolist(),
            "home_ml": [-150.0] * n,
            "away_ml": [130.0] * n,
        },
        "c": {g: C[:, j].tolist() for j, g in enumerate(G)},
    }


def test_true_weights_beat_random():
    m = synthetic()
    good = diy.evaluate(TRUE_W, m)["overall"]["log_loss"]
    rng = np.random.default_rng(3)
    for _ in range(5):
        rand = dict(zip(G, rng.normal(size=len(G)), strict=True))
        assert good < diy.evaluate(rand, m)["overall"]["log_loss"]


def test_walk_forward_platt_never_uses_scored_season():
    m = synthetic()
    P = diy.prepare(m)
    base = diy.evaluate(TRUE_W, m)
    # flip every outcome in the last season: earlier seasons' calibration must not change
    cols = dict(m["columns"])
    last = max(cols["season"])
    cols["y"] = [1 - v if s == last else v for v, s in zip(cols["y"], cols["season"], strict=True)]
    flipped = diy.evaluate(TRUE_W, m | {"columns": cols})
    for a, b in zip(base["seasons"][:-1], flipped["seasons"][:-1], strict=True):
        assert a["calib_a"] == b["calib_a"] and a["calib_c"] == b["calib_c"]
    # the scored season's own calibration comes from earlier seasons only
    raw = P["_C"] @ np.array([TRUE_W[g] for g in G])
    prior = P["season"] < last
    a, _ = diy._platt(raw[prior], P["y"][prior])
    assert base["seasons"][-1]["calib_a"] == pytest.approx(a)
    assert base["seasons"][0]["in_sample_calibration"] is True
    assert base["seasons"][1]["in_sample_calibration"] is False


def test_max_season_hides_later_seasons():
    m = synthetic()
    r = diy.evaluate(TRUE_W, m, max_season=2009)
    assert r["scored_seasons"][-1] == 2009


def test_fit_toward_huge_lambda_returns_input():
    m = synthetic()
    r = diy.fit_toward(TRUE_W, m, lam=1e8)
    for g in G:
        assert r["weights"][g] == pytest.approx(r["user_scaled"][g], abs=1e-3)
    free = diy.fit_toward({g: 0.0 for g in G}, m, lam=1e-3)
    assert free["weights"]["quality"] > free["weights"]["defense"]


def test_query_param_round_trip():
    signed = {"quality": 30.0, "form": -10.0, "market": 5.5}
    s = diy.encode_weights(signed)
    assert s == "quality:30,form:-10,market:5.5"
    assert diy.decode_weights(s) == signed
    assert diy.decode_weights("bogus:3,quality:x,defense:500") == {"defense": 100.0}
    assert diy.decode_weights(None) == {}


def test_cap_market_limits_share_to_twenty_percent():
    capped, hit = diy.cap_market({"quality": 40.0, "form": 40.0, "market": 100.0})
    assert hit
    share = abs(capped["market"]) / sum(abs(v) for v in capped.values())
    assert share == pytest.approx(0.20)
    ok, hit = diy.cap_market({"quality": 40.0, "market": 5.0})
    assert not hit and ok["market"] == 5.0
    neg, _ = diy.cap_market({"quality": 10.0, "market": -50.0})
    assert neg["market"] < 0


def test_season_predictions_match_evaluate():
    m = synthetic()
    sp = diy.season_predictions(TRUE_W, m, 2010)
    r = diy.evaluate(TRUE_W, m)
    y = np.array(
        [v for v, s in zip(m["columns"]["y"], m["columns"]["season"], strict=True) if s == 2010]
    )
    ll = diy._ll(sp["p"], y).mean()
    assert ll == pytest.approx(next(x for x in r["seasons"] if x["season"] == 2010)["log_loss"])
    assert sp["calib_a"] == pytest.approx(
        next(x for x in r["seasons"] if x["season"] == 2010)["calib_a"]
    )


@requires_data
def test_real_matrix_consistency_with_backfill():
    """The backfill has one public line per approach (traditionalist, analyst, sharp, student).

    The Student's public line is the walk-forward fitted model, so the DIY evaluator on its
    per-season fitted weights must match the backfill `student` rows closely (differences: the
    Platt window, see the diy module docstring). The personas' public lines are the persona weights
    lightly fitted toward the data (ADR 0004 amendment), so the evaluator on the raw persona
    weights cannot match them exactly; only a loose bound is checked for those."""
    paths = get_paths()
    if not (paths.site / "diy_matrix.json").exists():
        diy.build_matrix(paths)
    m = diy.load_matrix(paths.site / "diy_matrix.json")
    graded = pl.read_parquet(paths.marts / "graded.parquet").filter(
        pl.col("season").is_between(2005, 2025) & pl.col("log_loss").is_not_null()
    )

    def backfill(mid: str) -> float:
        return float(graded.filter(pl.col("model_id") == mid)["log_loss"].mean())

    fitted = {int(s): v["W"] for s, v in m["student_fitted"].items()}
    diy.evaluate(fitted, m)
    t = time.perf_counter()
    r = diy.evaluate(fitted, m)
    assert time.perf_counter() - t < 1.0  # ~0.1s idle; headroom for loaded CI
    assert abs(r["overall"]["log_loss"] - backfill("student")) < 0.002

    # Raw persona weights vs the lightly fitted public lines: they differ by design (the public line
    # moves ~25% toward history), so only a loose bound. 0.012 since 2026-10-28: with the market gap
    # removed (ADR 0013 amendment) the Sharp's raw persona is weaker and light fitting helps it more.
    for pid in ("traditionalist", "analyst", "sharp"):
        raw = diy.evaluate(m["personas"][pid]["W"], m)["overall"]["log_loss"]
        assert abs(raw - backfill(pid)) < 0.012, pid
