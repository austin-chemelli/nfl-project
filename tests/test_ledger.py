"""Ledger: bet decisions, settlement (win/loss/push, payouts), CLV sign, live immutability."""

from datetime import datetime

import polars as pl
import pytest

from nfl import ledger
from nfl.config import Paths

LOCK = datetime(2026, 11, 7, 17, 0)


def cand(**kw):
    base = {
        "game_id": "G",
        "season": 2026,
        "week": 9,
        "model_id": "m.fitted",
        "lock_ts": LOCK,
        "is_backfill": False,
        "p_home": 0.60,
        "spread_home_pred": 3.0,
        "home_ml": -150.0,
        "away_ml": 130.0,
        "spread_home": 3.0,
        "home_spread_price": -110.0,
        "away_spread_price": -110.0,
        "p_home_vigfree": 0.58,
        "line_source": "odds_api",
        "line_snapshot_ts": LOCK,
    }
    base.update(kw)
    return pl.DataFrame([base])


def test_no_bet_inside_thresholds():
    assert ledger.decide(cand()).is_empty()  # 2-point edge, same spread


def test_moneyline_bet_on_the_side_the_model_likes_more():
    b = ledger.decide(cand(p_home=0.50))  # market 0.58 home -> model likes away by 8 points
    assert b.height == 1
    r = b.row(0, named=True)
    assert (r["market"], r["side"], r["price_american"]) == ("h2h", "away", 130.0)
    assert r["edge"] == pytest.approx(0.08)
    assert r["model_p"] == pytest.approx(0.50) and r["market_p_vigfree"] == pytest.approx(0.42)


def test_spread_bet_when_no_moneyline_edge():
    b = ledger.decide(cand(spread_home_pred=5.0))  # model: home by 5; market: home by 3
    r = b.row(0, named=True)
    assert (r["market"], r["side"], r["point"]) == ("spreads", "home", -3.0)


def settle_one(
    bet_kw, result, close_p_home=0.58, close_spread_home=3.0, sources=("odds_api", "odds_api")
):
    bets = ledger.decide(cand(**bet_kw))
    df = bets.with_columns(
        pl.lit(result, dtype=pl.Float64).alias("result"),
        pl.lit(close_p_home).alias("p_home_vigfree"),
        pl.lit(close_spread_home).alias("spread_home"),
        pl.lit(sources[1]).alias("closing_source"),
        pl.lit(sources[0]).alias("line_source"),
    )
    return ledger.settle_frame(df).row(0, named=True)


def test_moneyline_payouts_and_push():
    r = settle_one({"p_home": 0.50}, result=-3)  # away +130 wins
    assert r["result"] == "win" and r["units_net"] == pytest.approx(1.30)
    r = settle_one({"p_home": 0.50}, result=7)
    assert r["result"] == "loss" and r["units_net"] == -1.0
    r = settle_one({"p_home": 0.66}, result=4)  # home -150 wins
    assert r["result"] == "win" and r["units_net"] == pytest.approx(100 / 150)
    r = settle_one({"p_home": 0.50}, result=0)
    assert r["result"] == "push" and r["units_net"] == 0.0


def test_spread_cover_and_push():
    assert settle_one({"spread_home_pred": 5.0}, result=4)["result"] == "win"  # home −3, won by 4
    assert settle_one({"spread_home_pred": 5.0}, result=3)["result"] == "push"
    assert settle_one({"spread_home_pred": 5.0}, result=2)["result"] == "loss"
    assert settle_one({"spread_home_pred": 5.0}, result=None)["result"] is None


def test_clv_sign():
    # bet away at market away p 0.42; close moves to away 0.46 -> +4 points of CLV
    assert settle_one({"p_home": 0.50}, 0, close_p_home=0.54)["clv"] == pytest.approx(0.04)
    # bet home −3; closes home −4 -> got the better number by 1 point
    assert settle_one({"spread_home_pred": 5.0}, 0, close_spread_home=4.0)["clv"] == pytest.approx(
        1.0
    )
    # same nflverse number at bet and close: CLV is undefined, not zero
    r = settle_one({"p_home": 0.50}, 0, sources=("nflverse", "nflverse"))
    assert r["clv"] is None


def test_live_bets_are_immutable(tmp_path, monkeypatch):
    paths = Paths(tmp_path)
    first = ledger.decide(cand(p_home=0.50))
    later = ledger.decide(cand(p_home=0.70, lock_ts=datetime(2026, 11, 8, 17, 0)))
    calls = iter([first, later])
    monkeypatch.setattr(ledger, "games_frame", lambda p: pl.DataFrame())
    monkeypatch.setattr(ledger, "_bet_candidates", lambda p, g: pl.DataFrame())
    monkeypatch.setattr(ledger, "decide", lambda c: next(calls))
    assert ledger.open_bets(paths) == (1, 0)
    assert ledger.open_bets(paths) == (0, 0)  # same model × game: the first bet stands
    stored = ledger.load_bets(paths)
    assert stored.height == 1 and stored["side"][0] == "away"
