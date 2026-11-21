"""The betting guide (ADR 0033): price arithmetic, the card's rules, and the point-in-time guards
(the card's record reads only odds known at the lock; the walk-forward search never sees the
season it bets)."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest

from nfl.betting import guide, prices, rules, study

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


def test_bands_and_side_views():
    assert rules.band_of(0.9) == "heavy_fav"
    assert rules.band_of(0.7) == "big_fav"
    assert rules.band_of(0.6) == "fav"
    assert rules.band_of(0.5) == "coin"
    assert rules.band_of(0.1) == "long"
    v = rules.side_view
    assert v(0.43, 0.40) == ("target", "lean_dog")  # an underdog the model likes a little more
    assert v(0.74, 0.70) == ("target", "lean")  # a big favorite, small lean
    assert v(0.51, 0.50) == ("none", "no_view")  # agrees with the market
    assert v(0.66, 0.70) == ("none", "no_view")  # rates it lower
    assert v(0.48, 0.40) == ("avoid", "big_gap")  # 8 points above the market: trust the market
    assert v(0.64, 0.60) == ("avoid", "mid_fav")  # -120 to -185, whatever the model says
    assert v(0.33, 0.30) == ("avoid", "long")  # +185 or longer


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
    "rules": {
        k: {"roi": -0.02, "n": 100, "roi_second": -0.05, "roi_2021_2025": 0.01}
        for k in ("lean_dog", "lean", "mid_fav", "long", "big_gap", "no_view")
    },
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


def _card_games(ids, kicks, homes, aways, roofs):
    n = len(ids)
    return pl.DataFrame({"game_id": ids, "season": [2026] * n, "week": [11] * n, "kickoff_utc": kicks,
                         "home_team": homes, "away_team": aways, "roof": roofs})  # fmt: skip


def _student(ids, p_home):
    return pl.DataFrame({"game_id": ids, "model_id": ["student"] * len(ids), "p_home": p_home,
                         "status": ["preview"] * len(ids)})  # fmt: skip


def test_card_views_both_sides_and_wind():
    now = datetime(2026, 11, 20, 12)
    kick = now + timedelta(days=2)
    games = _card_games(
        ["g1", "g2"], [kick, kick], ["BUF", "LAC"], ["MIA", "NYJ"], ["outdoors", "dome"]
    )
    # g1: market about 59% on BUF (-150/+130): BUF is a -120 to -185 favorite (avoid);
    # the Student gives MIA 44% against about 41%: a small lean on an underdog (target)
    # g2: market about 59% on LAC, the Student 70%: avoid twice over (mid favorite)
    snap = now - timedelta(hours=3)
    rows = _game_lines("g1", snap, kick, -150.0, 130.0) + _game_lines(
        "g2", snap, kick, -150.0, 130.0
    )
    c = guide.card(
        games, _student(["g1", "g2"], [0.56, 0.70]), _lines(rows), {"g1": 18.0}, STUDY, 11, now
    )
    by = {g["game_id"]: {x["team"]: x for x in g["sides"]} for g in c["games"]}
    assert by["g1"]["MIA"]["view"] == "target" and by["g1"]["MIA"]["why"] == "lean_dog"
    assert by["g1"]["BUF"]["view"] == "avoid" and by["g1"]["BUF"]["why"] == "mid_fav"
    assert by["g1"]["MIA"]["needed"]["american"] > 100 and by["g1"]["MIA"]["reason"]
    assert "best" not in by["g1"]["MIA"]  # no book names on the card
    g1 = next(g for g in c["games"] if g["game_id"] == "g1")
    assert g1["total"]["side"] == "under" and g1["total"]["wind_mph"] == 18
    assert next(g for g in c["games"] if g["game_id"] == "g2")["total"] is None
    assert by["g2"]["LAC"]["view"] == "avoid"


def test_card_caps_targets_and_counts_started_games():
    now = datetime(2026, 11, 20, 12)
    n = rules.MAX_TARGETS + 2
    ids = [f"g{i}" for i in range(n)]
    # the two earliest games already kicked off; they still count toward the cap
    kicks = [now - timedelta(hours=2)] * 2 + [now + timedelta(days=2)] * (n - 2)
    games = _card_games(ids, kicks, ["BUF"] * n, ["MIA"] * n, ["dome"] * n)
    snap = now - timedelta(hours=5)
    rows = [
        r
        for gid, k in zip(ids, kicks, strict=True)
        for r in _game_lines(gid, snap, k, -150.0, 130.0)
    ]
    c = guide.card(games, _student(ids, [0.56] * n), _lines(rows), {}, STUDY, 11, now)
    t = [x for g in c["games"] for x in g["sides"] if x["view"] == "target"]
    assert len(t) == rules.MAX_TARGETS
    assert (
        sum(x["team"] == "MIA" and x["view"] == "none" for g in c["games"] for x in g["sides"]) == 2
    )


def test_card_always_lists_targets_ranked_by_history():
    """No side leans: the week still gets MAX_TARGETS targets, best history first, never an avoid."""
    now = datetime(2026, 11, 20, 12)
    kick = now + timedelta(days=2)
    n = 4
    ids = [f"g{i}" for i in range(n)]
    games = _card_games(ids, [kick] * n, ["BUF"] * n, ["MIA"] * n, ["dome"] * n)
    snap = now - timedelta(hours=3)
    # market about 70% BUF (big favorite) / 30% MIA (+185 or longer: avoid); the Student agrees
    rows = [r for gid in ids for r in _game_lines(gid, snap, kick, -250.0, 210.0)]
    cells = [{"band": "big_fav", "cell": "same", "n": 400, "roi": -0.03, "score": -0.025}]
    st = STUDY | {"rules": STUDY["rules"] | {"cells": cells}}
    c = guide.card(games, _student(ids, [0.70] * n), _lines(rows), {}, st, 11, now)
    sides = [x for g in c["games"] for x in g["sides"]]
    t = [x for x in sides if x["view"] == "target"]
    assert len(t) == n  # every BUF side; fewer eligible sides than MAX_TARGETS
    assert all(x["team"] == "BUF" and x["grade"] == "C" and x["label"] for x in t)
    assert all(x["view"] == "avoid" for x in sides if x["team"] == "MIA")
    assert "lost 3.0%" in t[0]["reason"]


def test_record_uses_only_odds_known_at_the_lock():
    lock = datetime(2026, 11, 19, 14)
    p = pl.DataFrame(
        {"game_id": ["g1"], "week": [11], "lock_ts": [lock], "p_home": [0.85], "result": [7]}
    )
    cons = pl.DataFrame({
        "game_id": ["g1", "g1"], "snapshot_ts": [lock - timedelta(hours=2), lock + timedelta(hours=2)],
        # before the lock: a heavy favorite with a small lean (target); after: a coin flip that
        # would make the home side a big disagreement (avoid) and must not be used
        "p_home_vigfree": [0.82, 0.5], "home_ml": [-500.0, -105.0], "away_ml": [400.0, -105.0],
    })  # fmt: skip
    rows = {r["side"]: r for r in guide.grade_at_locks(p, cons)}
    assert rows["home"]["view"] == "target" and rows["home"]["price"] == -500.0
    assert rows["home"]["units"] == pytest.approx(0.2)
    assert rows["away"]["view"] == "avoid" and rows["away"]["units"] == -1.0


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


def test_record_caps_targets_per_week_like_the_card():
    lock = datetime(2026, 11, 19, 14)
    n = rules.MAX_TARGETS + 2
    ids = [f"g{i}" for i in range(n)]
    p = pl.DataFrame({"game_id": ids, "week": [11] * n, "lock_ts": [lock] * n, "p_home": [0.85] * n,
                      "result": [7] * n})  # fmt: skip
    cons = pl.DataFrame({"game_id": ids, "snapshot_ts": [lock - timedelta(hours=1)] * n, "p_home_vigfree": [0.82] * n,
                         "home_ml": [-500.0] * n, "away_ml": [400.0] * n})  # fmt: skip
    rows = guide.grade_at_locks(p, cons)
    assert sum(r["view"] == "target" for r in rows) == rules.MAX_TARGETS


def test_side_rules_match_the_card_rule():
    s = _sides(per=120)
    out = study.side_rules(s, "student")
    d = s.filter(pl.col("p_student").is_not_null())
    views = [rules.side_view(a, b) for a, b in zip(d["p_student"], d["p_mkt"], strict=True)]
    assert out["target"]["n"] == sum(v[0] == "target" for v in views)
    assert out["lean_dog"]["n"] + out["lean"]["n"] == out["target"]["n"]
    assert out["avoid"]["n"] == out["mid_fav"]["n"] + out["long"]["n"] + out["big_gap"]["n"]
    assert set(out["lean_dog_bar"]["checks"]) == {
        "both_halves",
        "range_above_zero",
        "recent",
        "neighbour_agrees",
    }
