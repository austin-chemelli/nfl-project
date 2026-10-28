"""Hypotheses: verdicts on synthetic data with a known truth, determinism, sentences."""

import json

import numpy as np

from nfl import hypotheses as h
from tests.conftest import requires_data


def _synthetic(n_seasons=16, per=250, seed=1):
    rng = np.random.default_rng(seed)
    n = n_seasons * per
    z = rng.normal(size=(n, 3))  # 0: real effect, 1: real but small, 2: pure noise
    eta = 0.4 * z[:, 0]
    y = (rng.random(n) < 1 / (1 + np.exp(-eta))).astype(float)
    seasons = np.repeat(np.arange(2002, 2002 + n_seasons), per)
    return z, y, seasons


def test_known_effect_matters_and_noise_does_not():
    z, y, s = _synthetic()
    r = h.analyze(z, y, s, lam=100.0, n_boot=60)
    v = [h.verdict(r["coef"][j], r["lo"][j], r["hi"][j], r["se"][j]) for j in range(3)]
    assert v[0] == "matters"
    assert v[2] == "no evidence"
    assert r["lo"][0] > 0
    assert r["marginal"][0] > 0.2


def test_bootstrap_reproducible_and_seed_matters():
    z, y, s = _synthetic(n_seasons=8, per=100)
    a = h.analyze(z, y, s, 100.0, n_boot=20, seed=7)
    b = h.analyze(z, y, s, 100.0, n_boot=20, seed=7)
    c = h.analyze(z, y, s, 100.0, n_boot=20, seed=8)
    assert np.array_equal(a["lo"], b["lo"]) and np.array_equal(a["se"], b["se"])
    assert not np.array_equal(a["lo"], c["lo"])


def test_verdict_rules():
    assert h.verdict(0.10, 0.05, 0.15, 0.03) == "matters"
    assert h.verdict(0.02, 0.01, 0.03, 0.006) == "weak"  # excludes 0, tiny
    assert h.verdict(0.05, -0.02, 0.12, 0.04) == "weak"  # |coef| > 1 SE
    assert h.verdict(0.01, -0.05, 0.07, 0.04) == "no evidence"


def test_sentence_format():
    s = h.sentence("rest days", 0.02, -0.03, 0.07, 1.2)
    assert "+0.5 points" in s and "includes zero" in s and "SD ≈ 1.2" in s
    assert "excludes zero" in h.sentence("elo pre", 0.5, 0.4, 0.6, 80.0)


def test_fit_one_recovers_effect_and_zero():
    rng = np.random.default_rng(3)
    z = rng.normal(size=20000)
    y = (rng.random(20000) < 1 / (1 + np.exp(-(0.2 + 0.5 * z)))).astype(float)
    b, w = h.fit_one(z, y)
    assert abs(b - 0.2) < 0.06 and abs(w - 0.5) < 0.06
    assert abs(h.fit_one(rng.normal(size=20000), y)[1]) < 0.06


def test_by_season_walk_forward_and_coverage():
    rng = np.random.default_rng(5)
    seasons = np.repeat(np.arange(2002, 2018), 250)
    x = rng.normal(size=len(seasons))
    y = (rng.random(len(x)) < 1 / (1 + np.exp(-0.8 * x))).astype(float)
    r = h.by_season_one(x, y, seasons, sign=1)
    assert r["series"][0]["season"] == h.FIRST_EVAL
    assert all(row["improvement"] > 0 for row in r["series"])
    assert 0.6 < r["pooled"]["edge_win_rate"] < 0.8
    assert r["pooled"]["skill_pct"] > 0
    # a feature only observed from 2012: no season before 2012 + enough history is scored
    x2 = np.where(seasons >= 2012, x, np.nan)
    first = h.by_season_one(x2, y, seasons, sign=1)["series"][0]["season"]
    assert first >= 2013
    # noise: edge team wins about half and improvement is not positive on average
    noise = h.by_season_one(rng.normal(size=len(x)), y, seasons, sign=1)["pooled"]
    assert abs(noise["edge_win_rate"] - 0.5) < 0.05 and noise["improvement"] < 0.2


def test_season_sentence():
    pooled = {"edge_win_rate": 0.61, "first_season": 2005, "last_season": 2025, "improvement": 2.5,
              "best_season": 2013, "worst_season": 2020}  # fmt: skip
    s = h.season_sentence("Offensive EPA per play", pooled)
    assert "won 61%" in s and "strongest in 2013, weakest in 2020" in s and "improved" in s


@requires_data
def test_build_real_data():
    from nfl.config import get_paths

    paths = get_paths()
    summary = h.build(paths)
    d = json.loads((paths.site / "hypotheses.json").read_text())
    assert len(d["features"]) > 30 and summary["n_features"] == len(d["features"])
    assert {f["verdict"] for f in d["features"]} <= set(h.VERDICTS)
    f0 = d["features"][0]
    assert {"effect_pp", "effect_lo_pp", "effect_hi_pp", "marginal_pp", "description"} <= set(f0)
    items = d["by_season"]["items"]
    assert any(k.startswith("group:") for k in items) and "strength.epa_off" in items
