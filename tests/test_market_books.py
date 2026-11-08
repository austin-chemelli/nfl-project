from datetime import datetime, timedelta

import polars as pl

from nfl import market_books as mb

KICK = datetime(2026, 11, 8, 18, 0)
T = KICK - timedelta(hours=3)


def book(name, spread_home, total, home_ml=-150.0, away_ml=130.0, ts=T, updated=None, game="G"):
    """One book's quotes: spread in the nflverse sign (+ = home favored), as the site shows it."""
    up = (updated or ts).strftime("%Y-%m-%dT%H:%M:%SZ")
    common = {"game_id": game, "snapshot_ts": ts, "kickoff_utc": KICK, "book": name,
              "book_last_update": up}  # fmt: skip
    return [
        {**common, "market": "h2h", "side": "home", "price_american": home_ml, "point": None},
        {**common, "market": "h2h", "side": "away", "price_american": away_ml, "point": None},
        {**common, "market": "spreads", "side": "home", "price_american": -110.0, "point": -spread_home},
        {**common, "market": "spreads", "side": "away", "price_american": -110.0, "point": spread_home},
        {**common, "market": "totals", "side": "over", "price_american": -105.0, "point": total},
        {**common, "market": "totals", "side": "under", "price_american": -115.0, "point": total},
    ]  # fmt: skip


def frame(*books):
    return pl.DataFrame([r for b in books for r in b])


def test_books_that_agree_raise_no_flag():
    b = mb.by_game(frame(book("a", 3.0, 45.0), book("b", 3.5, 45.0), book("c", 3.0, 45.5)))["G"]
    assert b["flags"] == []
    assert b["spread"] == {"lo": 3.0, "hi": 3.5, "median": 3.0, "gap": 0.5}
    assert b["key"] is None
    rows = {r["book"]: r for r in b["books"]}
    assert rows["a"]["spread_home"] == 3.0
    assert rows["a"]["over_price"] == -105.0
    assert 0.5 < rows["a"]["p_home"] < 0.6  # the moneyline without the vig


def test_books_on_both_sides_of_a_key_number_are_flagged_at_any_gap():
    b = mb.by_game(frame(book("a", 2.5, 45.0), book("b", 3.5, 45.0), book("c", 3.0, 45.0)))["G"]
    assert b["flags"] == ["spread_key"]
    assert b["key"] == 3.0


def test_books_split_on_the_favorite_cross_pickem():
    b = mb.by_game(frame(book("a", -1.5, 42.0), book("b", 1.5, 42.0), book("c", 0.0, 42.0)))["G"]
    assert set(b["flags"]) == {"spread_gap", "spread_key"}
    assert b["key"] == 0.0
    assert all(str(r["spread_home"]) != "-0.0" for r in b["books"])


def test_a_one_point_gap_on_the_same_side_is_left_alone_but_a_wide_total_is_not():
    b = mb.by_game(frame(book("a", 1.0, 42.0), book("b", 2.0, 43.5), book("c", 1.5, 42.5)))["G"]
    assert b["flags"] == ["total_gap"]


def test_only_the_latest_pre_kickoff_snapshot_counts():
    early = [book(n, 7.0, 45.0, ts=T - timedelta(days=2)) for n in "abc"]
    late = [book(n, 3.0, 45.0) for n in "abc"]
    in_play = [book(n, 20.0, 60.0, ts=KICK + timedelta(hours=1)) for n in "abc"]
    b = mb.by_game(frame(*early, *late, *in_play))["G"]
    assert b["snapshot_ts"] == T
    assert b["spread"]["lo"] == b["spread"]["hi"] == 3.0


def test_a_stale_book_is_left_out_and_counted():
    old = T - mb.STALE - timedelta(minutes=1)
    b = mb.by_game(
        frame(
            book("a", 3.0, 45.0),
            book("b", 3.0, 45.0),
            book("c", 3.0, 45.0),
            book("d", 9.0, 45.0, updated=old),
        )
    )["G"]
    assert b["flags"] == []
    assert b["n_stale"] == 1
    assert {r["book"] for r in b["books"]} == {"a", "b", "c"}


def test_fewer_than_min_books_has_no_range():
    assert mb.by_game(frame(book("a", 3.0, 45.0), book("b", 9.0, 45.0))) == {}
