"""The betting guide (ADR 0033): price arithmetic, the card's rules, and the point-in-time guards
(the card's record reads only odds known at the lock; the walk-forward search never sees the
season it bets)."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest

from nfl.betting import guide, prices, study

# ------------------------------------------------------------------ prices


def test_decimal_american_roundtrip():
    for a in (-1400, -250, -110, -100, 100, 130, 450):
        assert prices.american(prices.decimal(a)) == pytest.approx(a if a != -100 else 100)
    assert prices.decimal(-150) == pytest.approx(1 + 100 / 150)
    assert prices.decimal(130) == pytest.approx(2.3)
    with pytest.raises(ValueError):
        prices.decimal(0)


def test_vig_and_hold():
    assert prices.hold(-110, -110) == pytest.approx(0.0455, abs=1e-4)
    assert prices.implied(-110) == pytest.approx(0.5238, abs=1e-4)
    ph, pa = prices.vig_free(-150, 130)
    assert ph + pa == pytest.approx(1)
    assert ph > 0.5


def test_ev_kelly_breakeven():
    assert prices.ev(0.5, 100) == pytest.approx(0)
    assert prices.kelly(0.5, -110) == 0  # no edge: bet nothing
    assert prices.kelly(0.6, 100) == pytest.approx(0.2)
    assert prices.breakeven_price(0.5) == pytest.approx(100)
    assert prices.breakeven_price(0.75) == pytest.approx(-300)
    assert prices.ev(0.75, prices.breakeven_price(0.75)) == pytest.approx(0)


def test_parlay_and_shade_and_exchange():
    assert prices.parlay_decimal([100, 100]) == pytest.approx(4)
    assert prices.shade(-140, 10) == -150
    assert prices.shade(130, 10) == 120
    assert prices.shade(105, 10) == -105  # crosses even money: +95 is not a price
    # a 50c contract with a 0.07·p·(1−p) fee costs 51.75c
    assert prices.decimal(prices.exchange_price(0.5)) == pytest.approx(1 / 0.5175)


# ------------------------------------------------------------------ the card's rules


def test_bands_and_verdicts():
    assert guide.band_of(0.9) == "heavy_fav"
    assert guide.band_of(0.7) == "big_fav"
    assert guide.band_of(0.6) == "fav"
    assert guide.band_of(0.5) == "coin"
    assert guide.band_of(0.1) == "long"
    assert guide.verdict(0.75, 0.70) == "look"  # big favorite, model at least the market
    assert guide.verdict(0.68, 0.70) == "fun"  # big favorite the model rates lower
    assert guide.verdict(0.52, 0.50) == "fun"  # coin flip
    assert guide.verdict(0.65, 0.60) == "skip"  # -120 to -185 favorite
    assert guide.verdict(0.55, 0.40) == "fun"  # the model's upset pick
    assert guide.verdict(0.55, 0.30) == "skip"  # big underdog


def test_blend_and_exchange_cents():
    assert guide.blend(0.6, 0.8, 0.0) == pytest.approx(0.6)
    assert guide.blend(0.6, 0.8, 1.0) == pytest.approx(0.8)
    assert 0.6 < guide.blend(0.6, 0.8, 0.2) < 0.65
    for p in (0.2, 0.5, 0.9):
        c = guide.exchange_max_cents(p) / 100
        assert c + guide.EXCHANGE_FEE * c * (1 - c) == pytest.approx(p)
        assert c < p


STUDY = {
    "seasons": [2006, 2025],
    "blend": {"path": [{"season": 2026, "w": 0.0}]},
    "price": {
        "bands": [
            {"band": b[2], "label": b[3], "prices": b[4], "roi": -0.02, "n": 100}
            for b in study.BANDS
        ]
    },
    "pick_winners": [{"band": "dog", "roi": -0.03, "n": 50}],
    "targeted": [{"key": "under_wind_15", "roi": 0.09, "n": 400}],
}


def _lines(rows):
    return pl.DataFrame(
        rows,
        schema={"game_id": pl.Utf8, "snapshot_ts": pl.Datetime("us"), "kickoff_utc": pl.Datetime("us"),
                "book": pl.Utf8, "market": pl.Utf8, "side": pl.Utf8, "price_american": pl.Float64,
                "point": pl.Float64},
        orient="row",
    )  # fmt: skip


def _game_lines(gid, snap, kick, home_ml, away_ml, books=("draftkings", "fanduel", "betmgm")):
    out = []
    for i, b in enumerate(books):
        out += [
            (gid, snap, kick, b, "h2h", "home", home_ml - 5 * i, None),
            (gid, snap, kick, b, "h2h", "away", away_ml, None),
            (gid, snap, kick, b, "spreads", "home", -110.0, -7.0),
            (gid, snap, kick, b, "spreads", "away", -110.0, 7.0),
            (gid, snap, kick, b, "totals", "over", -110.0, 41.5),
            (gid, snap, kick, b, "totals", "under", -110.0, 41.5),
        ]
    return out


def test_card_verdicts_best_us_price_and_wind():
    now = datetime(2026, 11, 20, 12)
    kick = now + timedelta(days=2)
    games = pl.DataFrame({
        "game_id": ["g1", "g2", "g3"], "season": [2026] * 3, "week": [11] * 3,
        "kickoff_utc": [kick, kick, now - timedelta(hours=1)], "home_team": ["BUF", "LAC", "HOU"],
        "away_team": ["MIA", "NYJ", "IND"], "roof": ["outdoors", "dome", "outdoors"],
    })  # fmt: skip
    allrows = pl.DataFrame({
        "game_id": ["g1", "g2", "g3"], "model_id": ["student"] * 3, "p_home": [0.85, 0.62, 0.8],
        "status": ["preview"] * 3,
    })  # fmt: skip
    snap = now - timedelta(hours=3)
    rows = _game_lines("g1", snap, kick, -400.0, 320.0) + _game_lines(
        "g2", snap, kick, -150.0, 130.0
    )
    rows += _game_lines("g3", snap, now - timedelta(hours=1), -400.0, 320.0)
    # an offshore book with the best price must never be the "best licensed" price
    rows += [
        ("g1", snap, kick, "bovada", "h2h", "home", -200.0, None),
        ("g1", snap, kick, "bovada", "h2h", "away", 320.0, None),
    ]
    c = guide.card(games, allrows, _lines(rows), {"g1": 18.0}, STUDY, 11, now)
    by = {g["game_id"]: g for g in c["games"]}
    assert by["g1"]["verdict"] == "look"
    assert by["g1"]["best"]["book"] in study.US_BOOKS
    assert by["g1"]["best"]["price"] == -400.0
    assert by["g1"]["needed"]["american"] < -300
    assert by["g1"]["total"]["side"] == "under" and by["g1"]["total"]["wind_mph"] == 18
    assert by["g2"]["verdict"] == "skip" and by["g2"]["total"] is None
    assert by["g3"]["verdict"] == "started"


def test_card_caps_looks():
    now = datetime(2026, 11, 20, 12)
    kick = now + timedelta(days=2)
    n = guide.MAX_LOOKS + 2
    ids = [f"g{i}" for i in range(n)]
    games = pl.DataFrame({"game_id": ids, "season": [2026] * n, "week": [11] * n, "kickoff_utc": [kick] * n,
                          "home_team": ["BUF"] * n, "away_team": ["MIA"] * n, "roof": ["dome"] * n})  # fmt: skip
    allrows = pl.DataFrame(
        {
            "game_id": ids,
            "model_id": ["student"] * n,
            "p_home": [0.9] * n,
            "status": ["preview"] * n,
        }
    )
    rows = [
        r for gid in ids for r in _game_lines(gid, now - timedelta(hours=1), kick, -400.0, 320.0)
    ]
    c = guide.card(games, allrows, _lines(rows), {}, STUDY, 11, now)
    assert sum(g["verdict"] == "look" for g in c["games"]) == guide.MAX_LOOKS


def test_record_uses_only_odds_known_at_the_lock():
    lock = datetime(2026, 11, 19, 14)
    p = pl.DataFrame(
        {"game_id": ["g1"], "week": [11], "lock_ts": [lock], "p_home": [0.9], "result": [7]}
    )
    cons = pl.DataFrame({
        "game_id": ["g1", "g1"], "snapshot_ts": [lock - timedelta(hours=2), lock + timedelta(hours=2)],
        # before the lock: a heavy favorite (look); after: a coin flip that must not be used
        "p_home_vigfree": [0.82, 0.5], "home_ml": [-500.0, -105.0], "away_ml": [400.0, -105.0],
    })  # fmt: skip
    rows = guide.grade_at_locks(p, cons)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "look" and rows[0]["price"] == -500.0
    assert rows[0]["units"] == pytest.approx(0.2)


# ------------------------------------------------------------------ the study


def _sides(n_seasons=8, per=60, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for season in range(2006, 2006 + n_seasons):
        for i in range(per):
            p = rng.uniform(0.2, 0.8)
            won = float(rng.random() < p)
            for side, ps, w in (("home", p, won), ("away", 1 - p, 1 - won)):
                price = -100 * ps / (1 - ps) * 1.04 if ps >= 0.5 else 100 * (1 - ps) / ps / 1.04
                rows.append({"game_id": f"{season}_{i}", "season": season, "week": 1 + i % 17, "side": side,
                             "p_mkt": ps, "won": w, "price": price,
                             **{f"p_{m}": float(np.clip(ps + rng.normal(0, 0.05), 0.01, 0.99)) for m in study.history.APPROACHES}})  # fmt: skip
    s = pl.DataFrame(rows).with_columns(
        (pl.col("p_mkt") > 0.5).alias("fav"),
        pl.when(pl.col("price") > 0).then(pl.col("price") / 100).otherwise(100 / -pl.col("price")).alias("win_units"),
    )  # fmt: skip
    return s.with_columns(study.history.profit_expr().alias("profit"))


def test_walk_forward_never_sees_the_season_it_bets():
    s = _sides(per=150)
    # make one rule wildly profitable only in the last season: the search can't know it then
    last = int(s["season"].max())
    s = s.with_columns(
        pl.when((pl.col("season") == last) & ~pl.col("fav"))
        .then(5.0)
        .otherwise(pl.col("profit"))
        .alias("profit")
    )
    out = study.walk_forward(s, study.history.APPROACHES, first_test=2010)
    pick = next(r for r in out["seasons"] if r["season"] == last)
    past = s.filter(pl.col("season") < last)
    # the chosen rule's past return is what the earlier seasons alone say
    rule = study._apply_rule(
        past.with_columns(
            (sum(pl.col(f"p_{m}") for m in study.history.APPROACHES) / 4).alias("p_mean")
        ),
        pick["rule"],
    )
    assert pick["past_roi"] == pytest.approx(rule["profit"].sum() / rule.height, abs=1e-4)


def test_parlay_cost_compounds():
    out = study.parlays(_sides(per=80), "student", legs=(1, 2, 3), per_week=50)
    by = {r["legs"]: r for r in out["by_legs"]}
    assert by[3]["roi"] < by[1]["roi"]
    assert by[2]["compounded_single_roi"] == pytest.approx((1 + by[1]["roi"]) ** 2 - 1, abs=1e-3)


def test_blend_weight_tracks_information():
    s = _sides(per=200)
    # a model that is the market plus noise earns little weight
    assert study.blend_weight(s, "student", 2030) < 0.4
