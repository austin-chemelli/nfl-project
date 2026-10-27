from nfl.models import market
from nfl.models.elo import Elo, EloParams


def test_market_sign_convention_positive_spread_means_home_favored():
    p = market.predict(7.0, 44.5)
    assert p["p_home"] > 0.5 and p["spread_home"] == 7.0
    assert market.predict(-7.0, None)["p_home"] < 0.5
    assert market.predict(None, 44.5) is None


def test_elo_is_deterministic_and_home_field_matters():
    a, b = Elo(), Elo()
    for e in (a, b):
        e.new_season(2024)
        e.update("KC", "DEN", 10)
        e.update("DEN", "KC", -3)
    assert a.ratings == b.ratings
    assert a.predict("KC", "DEN")["p_home"] > a.predict("DEN", "KC")["p_home"]
    neutral = a.predict("KC", "DEN", neutral=True)
    assert neutral["spread_home"] < a.predict("KC", "DEN")["spread_home"]


def test_elo_update_moves_toward_winner_and_is_zero_sum():
    e = Elo(EloParams())
    e.new_season(2024)
    before = e.rating("BUF") + e.rating("NYJ")
    e.update("BUF", "NYJ", 21)
    assert e.rating("BUF") > 1500 > e.rating("NYJ")
    assert abs(e.rating("BUF") + e.rating("NYJ") - before) < 1e-9


def test_offseason_regression_pulls_toward_mean():
    e = Elo()
    e.new_season(2023)
    e.ratings["SF"] = 1700.0
    e.new_season(2024)
    assert 1500 < e.rating("SF") < 1700
