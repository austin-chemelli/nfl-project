"""Feature groups (ADR 0012): registry rules, grouped configs, inner weights, grouped fitting."""

import numpy as np
import polars as pl
import pytest

from nfl.approaches import fit, schema
from nfl.features import groups as G


def test_registry_partitions_features_and_headings():
    seen = {}
    for g in G.GROUPS.values():
        assert g.heading in G.HEADINGS
        for m in g.members:
            assert m.feature not in seen, (m.feature, seen.get(m.feature), g.id)
            seen[m.feature] = g.id
            assert m.sign in (-1, 0, 1)
    assert len(G.GROUPS) == 15
    assert set(G.FEATURE_GROUP) == set(seen)


def grouped(**over):
    d = {
        "id": "toy",
        "name": "Toy",
        "blurb": "A toy grouped persona for tests.",
        "emphasis": ["quality"],
        "intercept": {"w": 0.1, "why": "home field"},
        "groups": {
            "quality": {"w": 0.5, "why": "better team wins"},
            "offense": {"w": 0.2, "why": "offense matters"},
            "buzz": {"w": 0.1, "why": "vibes"},
        },
    }
    d.update(over)
    return schema.Approach.model_validate(d)


def test_grouped_config_validation():
    a = grouped()
    assert a.grouped and "strength.elo_pre" in a.features
    assert a.resolve({"strength.elo_pre", "strength.epa_off"}) == [
        "strength.elo_pre",
        "strength.epa_off",
    ]
    with pytest.raises(ValueError, match="unknown groups"):
        grouped(groups={"vibes": {"w": 1, "why": "nope"}})
    with pytest.raises(ValueError, match="not in group"):
        grouped(overrides={"quality": {"strength.epa_off": 1.0}})
    with pytest.raises(ValueError, match="exactly one"):
        grouped(weights={"strength.elo_pre": {"w": 1, "why": "both forms"}})


def toy_train(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    elo = rng.standard_normal(n) * 100
    pd = 0.5 * elo / 100 * 6 + rng.standard_normal(n) * 4
    epa = rng.standard_normal(n) * 0.1
    eta = 0.1 + 0.6 * elo / 100 + 4.0 * epa  # offense: 0.4 logit per SD, well above the persona 0.2
    y = (rng.random(n) < 1 / (1 + np.exp(-eta))).astype(float)
    return pl.DataFrame(
        {
            "game_id": [f"g{i}" for i in range(n)],
            "season": 2010 + np.arange(n) // 280,
            "week": 1,
            "y": y,
            "strength.elo_pre": elo,
            "strength.point_diff_pg": pd,
            "strength.epa_off": epa,
            "narrative.sentiment": [None] * n,  # live-only: no history
        },
        schema_overrides={"narrative.sentiment": pl.Float64},
    )


def test_inner_weights_unit_variance_signs_and_live_only_fallback():
    a = grouped()
    train = toy_train()
    feats = [f for f in a.features if f in train.columns]
    from nfl.approaches.engine import Scaler

    sc = Scaler.fit(train, feats)
    z, y = sc.transform(train), train["y"].to_numpy()
    inner = fit.inner_weights(a, train, feats, z, y)
    q = inner["quality"]
    assert q["strength.elo_pre"] > 0
    col = {f: i for i, f in enumerate(feats)}
    comp = z[:, [col[f] for f in q]] @ np.array(list(q.values()))
    assert np.std(comp) == pytest.approx(1.0, rel=1e-6)
    assert inner["buzz"]["narrative.sentiment"] > 0  # declared sign, no history


def test_grouped_persona_is_flat_W_times_v_and_fitted_limits():
    a = grouped()
    train = toy_train()
    r = fit.fit_flavors(a, train, lam=1e9, trained_through=2020)
    inner = r.persona.meta["inner"]
    W = r.persona.meta["group_weights"]
    for f, w in zip(r.persona.features, r.persona.weights, strict=True):
        g = G.FEATURE_GROUP[f]
        assert w == pytest.approx(W.get(g, 0.0) * inner[g][f])
    # huge λ: fitted group weights stay at the persona's
    for g, w in r.fitted.meta["group_weights"].items():
        assert w == pytest.approx(W[g], abs=1e-3)
    # tiny λ: fitted moves toward the data (offense is the strong signal here)
    r2 = fit.fit_flavors(a, train, lam=1e-6, trained_through=2020)
    assert r2.fitted.meta["group_weights"]["offense"] > W["offense"]


def test_overrides_replace_inner_weights():
    a = grouped(overrides={"quality": {"strength.elo_pre": 1.0}})
    r = fit.fit_flavors(a, toy_train(), lam=10.0, trained_through=2020)
    q = r.persona.meta["inner"]["quality"]
    assert q["strength.point_diff_pg"] == 0.0 and q["strength.elo_pre"] > 0
