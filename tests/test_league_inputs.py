"""League simulation inputs: lock-over-scored, market line-over-ratings, strict as-of, rating fit."""

from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest

from nfl.features import store
from nfl.league import inputs

AS_OF = datetime(2026, 11, 5, 12, 0)
TEAMS = ["A", "B", "C", "D", "E", "F"]


def _games(rows):
    return pl.DataFrame(
        rows,
        schema={
            "game_id": pl.Utf8, "season": pl.Int64, "game_type": pl.Utf8,
            "kickoff_utc": pl.Datetime("us"), "home_team": pl.Utf8, "away_team": pl.Utf8,
            "result": pl.Int32,
        },
        orient="row",
    )  # fmt: skip


def _preds(rows):
    return pl.DataFrame(
        rows,
        schema={
            "game_id": pl.Utf8, "model_id": pl.Utf8, "lock_ts": pl.Datetime("us"),
            "p_home": pl.Float64, "is_backfill": pl.Boolean,
        },
        orient="row",
    )  # fmt: skip


def _mkt(rows):
    """Market rows as the odds feature writes them: p, spread and total share a stamp."""
    out = []
    for g, p, kao in rows:
        for f, v in (("p_home_vigfree", p), ("spread_line", 3.0), ("total_line", 45.0)):
            out.append((2026, 9, g, "game", f"market.{f}", v, kao, "odds_api", "1"))
    return pl.DataFrame(out, schema=store.FEATURE_SCHEMA, orient="row")


K1 = AS_OF + timedelta(days=3)
K0 = AS_OF - timedelta(days=7)
GAMES = _games(
    [
        ("P1", 2026, "REG", K0, "A", "B", 3),
        ("P2", 2026, "REG", K0, "C", "D", -7),
        ("R1", 2026, "REG", K1, "A", "C", None),
        ("R2", 2026, "REG", K1, "B", "D", None),
        ("R3", 2026, "REG", K1, "E", "F", None),
        ("PO", 2026, "POST", K1, "A", "B", None),
        ("OLD", 2025, "REG", K0, "A", "B", None),
    ]
)  # fmt: skip
SCORED_FN = lambda slate: pl.DataFrame(
    {"game_id": slate["game_id"], "p_home": [0.5] * slate.height}
)


def test_remaining_excludes_played_other_seasons_and_playoffs():
    rem = inputs.remaining_games(GAMES, 2026)
    assert rem["game_id"].to_list() == ["R1", "R2", "R3"]


def test_locked_row_beats_scored_and_latest_lock_wins():
    preds = _preds(
        [
            ("R1", "student", AS_OF - timedelta(days=2), 0.60, False),
            ("R1", "student", AS_OF - timedelta(days=1), 0.70, False),
            ("R1", "sharp", AS_OF - timedelta(hours=1), 0.10, False),
            ("R2", "student", AS_OF - timedelta(days=1), 0.99, True),  # backfill: ignored
        ]
    )
    out = inputs.build_inputs(
        GAMES, preds, _mkt([]), lambda s: SCORED_FN(s).with_columns(p_home=pl.lit(0.4)), 2026, AS_OF
    )
    st = out["student"]
    assert st.p_home.tolist() == [0.70, 0.4, 0.4]
    assert st.source == ["locked", "scored", "scored"]
    assert st.source_counts == {"locked": 1, "scored": 2}


def test_future_stamped_student_lock_is_ignored():
    preds = _preds(
        [
            ("R1", "student", AS_OF, 0.80, False),  # stamped at the as-of: not strictly before
            ("R2", "student", AS_OF + timedelta(hours=1), 0.80, False),
            ("R3", "student", K1 + timedelta(hours=1), 0.80, False),  # after kickoff
        ]
    )
    st = inputs.build_inputs(GAMES, preds, _mkt([]), SCORED_FN, 2026, AS_OF)["student"]
    assert st.source_counts == {"scored": 3}
    assert st.p_home.tolist() == [0.5, 0.5, 0.5]


def test_scored_games_are_only_the_unlocked_ones():
    seen = []

    def fn(slate):
        seen.append(slate["game_id"].to_list())
        return SCORED_FN(slate)

    preds = _preds([("R1", "student", AS_OF - timedelta(days=1), 0.6, False)])
    inputs.build_inputs(GAMES, preds, _mkt([]), fn, 2026, AS_OF)
    assert seen == [["R2", "R3"], ["P1", "P2"]]  # the unlocked games, then played ones for the fit


def test_market_line_beats_ratings_and_future_line_is_ignored():
    before = AS_OF - timedelta(hours=2)
    feats = _mkt(
        [
            ("R1", 0.65, before),
            ("R2", 0.30, AS_OF + timedelta(hours=1)),  # future: must not be read
            ("P1", 0.60, K0 - timedelta(hours=2)),
            ("P2", 0.40, K0 - timedelta(hours=2)),
        ]
    )
    mk = inputs.build_inputs(GAMES, _preds([]), feats, SCORED_FN, 2026, AS_OF)["market"]
    assert mk.source == ["line", "ratings", "ratings"]
    assert mk.source_counts == {"line": 1, "ratings": 2}
    assert mk.p_home[0] == pytest.approx(0.65)
    assert mk.p_home[1] != pytest.approx(0.30)  # priced from ratings, not the future row


def test_future_closing_line_does_not_move_the_fit():
    base = [("R1", 0.65, AS_OF - timedelta(hours=2)), ("P1", 0.6, K0 - timedelta(hours=2))]
    a = inputs.build_inputs(GAMES, _preds([]), _mkt(base), SCORED_FN, 2026, AS_OF)["market"]
    b = inputs.build_inputs(
        GAMES,
        _preds([]),
        _mkt([*base, ("P2", 0.05, AS_OF + timedelta(minutes=1))]),
        SCORED_FN,
        2026,
        AS_OF,
    )["market"]
    assert a.ratings == b.ratings and a.home_term == b.home_term


def test_missing_student_probability_raises():
    rem = inputs.remaining_games(GAMES, 2026)
    empty = pl.DataFrame(schema={"game_id": pl.Utf8, "p_home": pl.Float64})
    with pytest.raises(ValueError, match="no Student probability"):
        inputs.student_inputs(rem, empty, empty)


def _synthetic(n_games=120, seed=0):
    rng = np.random.default_rng(seed)
    true = dict(zip(TEAMS, rng.normal(0, 0.6, len(TEAMS)), strict=True))
    true = {t: v - np.mean(list(true.values())) for t, v in true.items()}
    h = 0.3
    rows = []
    for i in range(n_games):
        a, b = rng.choice(TEAMS, 2, replace=False)
        rows.append((a, b, 1 / (1 + np.exp(-(true[a] - true[b] + h))), 1.0 + (i % 3)))
    df = pl.DataFrame(rows, schema=["home", "away", "p", "weight"], orient="row")
    return df, true, h


def test_fit_recovers_synthetic_additive_probabilities():
    df, true, h = _synthetic()
    fit = inputs.fit_ratings(df)
    assert fit.home == pytest.approx(h, abs=1e-6)
    for t in TEAMS:
        assert fit.ratings[t] == pytest.approx(true[t], abs=1e-6)
    assert sum(fit.ratings.values()) == pytest.approx(0, abs=1e-9)
    assert fit.r2 == pytest.approx(1.0, abs=1e-9)


def test_underdetermined_fit_is_stable_and_centred():
    # two disconnected pairs plus one team with no games: 7 parameters, 2 informative rows
    df = pl.DataFrame(
        {"home": ["A", "C"], "away": ["B", "D"], "p": [0.7, 0.6], "weight": [1.0, 1.0]}
    )
    f1 = inputs.fit_ratings(df, teams=TEAMS)
    f2 = inputs.fit_ratings(df, teams=TEAMS)
    assert f1.ratings == f2.ratings
    assert all(np.isfinite(v) for v in f1.ratings.values())
    assert sum(f1.ratings.values()) == pytest.approx(0, abs=1e-9)
    assert f1.ratings["E"] == f1.ratings["F"]  # unseen teams tie
    assert inputs.price(f1, "A", "B") > 0.5


def test_price_neutral_drops_home_term():
    r = inputs.Ratings({"A": 0.5, "B": -0.5}, 0.3)
    assert inputs.price(r, "A", "B", neutral=True) == pytest.approx(1 / (1 + np.exp(-1.0)))
    assert inputs.price(r, "A", "B") > inputs.price(r, "A", "B", neutral=True)


def test_a_later_build_with_no_new_data_prices_the_same():
    """Closing lines age from the last game, not the clock: a rebuild can't nudge the fallbacks."""
    feats = _mkt([("P1", 0.6, K0 - timedelta(days=1)), ("P2", 0.55, K0 - timedelta(days=1))])
    remaining = inputs.remaining_games(GAMES, 2026)
    played = GAMES.filter(pl.col("result").is_not_null()).rename(
        {"home_team": "home", "away_team": "away"}
    )
    a = inputs.market_inputs(remaining, played, feats, AS_OF)
    b = inputs.market_inputs(remaining, played, feats, AS_OF + timedelta(days=2))
    assert np.array_equal(a.p_home, b.p_home)


def test_played_games_keep_the_ratings_steady_with_one_game_left():
    """Fitted on remaining games alone, one game left means every rating is 0 and the home term is
    that game's logit. Played games have to hold the fit."""
    teams = [f"T{i}" for i in range(8)]
    r = {t: (i - 3.5) / 4 for i, t in enumerate(teams)}
    past = pl.DataFrame(
        [
            (h, a, 1 / (1 + np.exp(-(r[h] - r[a] + 0.3))), 1.0)
            for h in teams
            for a in teams
            if h != a
        ],
        schema={"home": pl.Utf8, "away": pl.Utf8, "p": pl.Float64, "weight": pl.Float64},
        orient="row",
    )
    rem = pl.DataFrame({"game_id": ["G"], "home": ["T0"], "away": ["T7"]})
    x = inputs._own_fit("student", rem, [0.2], ["scored"], past)
    assert x.home_term == pytest.approx(0.3, abs=0.05)
    assert x.ratings["T7"] - x.ratings["T0"] == pytest.approx(1.75, abs=0.1)
