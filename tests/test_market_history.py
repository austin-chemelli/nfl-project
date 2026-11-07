from datetime import datetime, timedelta

import polars as pl
import pytest

from nfl import market_history as mh

from .conftest import requires_data

KICK = datetime(2026, 11, 8, 18, 0)


def quotes(ts, spread_home, total, home_ml, away_ml, books=("a", "b", "c"), game="G"):
    rows = []
    for b in books:
        common = {"game_id": game, "snapshot_ts": ts, "kickoff_utc": KICK, "book": b}
        rows += [
            {**common, "market": "h2h", "side": "home", "price_american": home_ml, "point": None},
            {**common, "market": "h2h", "side": "away", "price_american": away_ml, "point": None},
            {**common, "market": "spreads", "side": "home", "price_american": -110.0,
             "point": -spread_home},
            {**common, "market": "spreads", "side": "away", "price_american": -110.0,
             "point": spread_home},
            {**common, "market": "totals", "side": "over", "price_american": -110.0, "point": total},
            {**common, "market": "totals", "side": "under", "price_american": -110.0, "point": total},
        ]  # fmt: skip
    return rows


def frame(*groups):
    return pl.DataFrame([r for g in groups for r in g])


T0 = KICK - timedelta(days=5)


def test_a_snapshot_after_kickoff_never_counts():
    lines = frame(
        quotes(T0, 3.0, 45.0, -150.0, 130.0),
        quotes(KICK - timedelta(hours=2), 3.5, 44.5, -160.0, 140.0),
        quotes(KICK + timedelta(hours=2), 28.0, 60.5, -5000.0, 2000.0),  # in play
    )
    p = mh.paths(lines)
    assert p.height == 2
    assert p["snapshot_ts"].max() < KICK
    s = mh.summary(p.to_dicts(), None)
    assert s["since_first"]["spread_home"] == 0.5
    assert s["since_first"]["total"] == -0.5


def test_a_market_on_too_few_books_is_null():
    lines = frame(quotes(T0, 3.0, 45.0, -150.0, 130.0, books=("a", "b")))
    assert mh.paths(lines).is_empty()


def test_one_snapshot_has_no_move():
    s = mh.summary(mh.paths(frame(quotes(T0, 3.0, 45.0, -150.0, 130.0))).to_dicts(), None)
    assert s["n_points"] == 1
    assert s["since_first"] is None and s["last_day"] is None


def test_since_lock_starts_at_the_line_the_lock_saw():
    lock = T0 + timedelta(days=2, hours=1)
    lines = frame(
        quotes(T0, 3.0, 45.0, -150.0, 130.0),
        quotes(T0 + timedelta(days=2), 3.5, 45.0, -160.0, 140.0),
        quotes(T0 + timedelta(days=4), 6.0, 43.0, -250.0, 210.0),
    )
    s = mh.summary(mh.paths(lines).to_dicts(), lock)
    assert s["since_lock"]["spread_home"] == 2.5
    assert s["since_first"]["spread_home"] == 3.0
    assert s["since_lock"]["p_home"] > 0
    assert mh.summary(mh.paths(lines).to_dicts(), T0 - timedelta(days=1))["since_lock"] is None


def test_last_day_needs_a_day_of_history():
    lines = frame(
        quotes(T0, 3.0, 45.0, -150.0, 130.0),
        quotes(T0 + timedelta(days=3), 4.0, 45.0, -170.0, 150.0),
        quotes(T0 + timedelta(days=3, hours=20), 5.0, 44.0, -200.0, 170.0),
    )
    s = mh.summary(mh.paths(lines).to_dicts(), None)
    assert s["last_day"]["spread_home"] == 1.0
    assert s["last_day"]["hours"] == 20.0


@requires_data
def test_baltimore_moved_toward_jacksonville_in_week_9():
    from nfl.config import get_paths
    from nfl.odds import read_lines

    p = mh.paths(read_lines(get_paths(), (2026, 2026)))
    g = p.filter(pl.col("game_id") == "2026_09_JAX_BAL").to_dicts()
    s = mh.summary(g, None)
    assert s["since_first"]["spread_home"] == pytest.approx(-12.5, abs=1.0)
