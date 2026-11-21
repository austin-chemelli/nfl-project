"""availability.value_lost and ol_weakest (M24.3): planted examples and point-in-time mutations."""

from datetime import datetime, timedelta

import polars as pl

from nfl.features import availability
from tests.test_availability import BUILD, INJ_SCHEMA, PLAY_SCHEMA, _frame, _games, _inj, _weekly

K2 = datetime(2018, 9, 16, 17, 0)
K3 = K2 + timedelta(days=7)  # the game under test; its stamp (lock) is K3 - 2h

CHART = [
    ("QB", "QB", "q1"),
    ("T", "LT", "t1"),
    ("G", "LG", "g1"),
    ("C", "C", "c1"),
    ("T", "RT", "t2"),
    ("G", "RG", "g2"),
    ("WR", "WR", "w1"),
]
RATES = pl.DataFrame(
    [
        ("2016+", "Out", "all", 0.0),
        ("2016+", "Doubtful", "all", 0.1),
        ("2016+", "Questionable", "QB", 0.8),
        ("2016+", "Questionable", "OL", 0.6),
        ("2016+", "Questionable", "all", 0.7),
    ],
    schema=["era", "status", "pos_group", "rate"],
    orient="row",
)


def _vals(rows, season=2018, week=2):
    return pl.DataFrame(
        [{"season": season, "week": week, "gsis_id": g, "value_pts": v} for g, v in rows]
    )


# week-2 slice: what a week-3 game may read
V2 = [("q1", 2.0), ("t1", 1.0), ("g1", 0.8), ("c1", 0.3), ("t2", 0.6), ("g2", 0.5), ("w1", 0.5)]


def run(inj, values, rates=RATES):
    games = _games(
        [
            ("g2", 2018, 2, K2, "AAA", "BBB"),
            ("g3", 2018, 3, K3, "AAA", "BBB"),
        ]
    )
    depth = pl.DataFrame(_weekly(2018, 3, "AAA", CHART) + _weekly(2018, 2, "AAA", CHART))
    inj = _frame(inj, INJ_SCHEMA | {"date_modified": pl.Datetime("us")})
    df = availability.compute(
        games, inj, depth, _frame([], PLAY_SCHEMA), BUILD, values=values, rates=rates
    )
    return {
        (r["game_id"], r["team"], r["feature"].split(".")[1]): r["value"]
        for r in df.iter_rows(named=True)
        if r["feature"] in ("availability.value_lost", "availability.ol_weakest")
    }


def _inj_rows(extra=()):
    rows = _inj(
        2018,
        3,
        "AAA",
        [("q1", "Questionable"), ("t1", "Out"), ("g1", "Questionable"), ("w1", "Probable")],
    ) + list(extra)
    return [{"date_modified": None, **r} for r in rows]


def test_planted_value_lost_and_ol_weakest():
    out = run(_inj_rows(), _vals(V2))
    # q1 2.0 x (1-0.8) + t1 1.0 x 1 + g1 0.8 x (1-0.6) + w1 (Probable, no rate) 0
    assert abs(out[("g3", "AAA", "value_lost")] - (0.4 + 1.0 + 0.32)) < 1e-9
    # OL: t1 is out (skipped); g1 0.4 out < 0.5 stays; weakest = c1 0.3
    assert out[("g3", "AAA", "ol_weakest")] == 0.3
    # no value slice before week 2 of the data: the week-2 game itself is null
    assert out[("g2", "AAA", "value_lost")] is None
    # the opponent has no chart: null
    assert out[("g3", "BBB", "value_lost")] is None


def test_unvalued_ol_starter_counts_zero_and_all_out_is_null():
    out = run(_inj_rows(), _vals([r for r in V2 if r[0] != "c1"]))
    assert out[("g3", "AAA", "ol_weakest")] == 0.0
    every_ol = [(g, "Out") for g in ("t1", "g1", "c1", "t2", "g2")]
    rows = [{**r, "date_modified": None} for r in _inj(2018, 3, "AAA", every_ol)]
    assert run(rows, _vals(V2))[("g3", "AAA", "ol_weakest")] is None


def test_report_stamped_after_the_lock_is_ignored():
    lock = K3 - availability.store.BACKTEST_ASOF_OFFSET
    base = run(_inj_rows(), _vals(V2))
    late = _inj(2018, 3, "AAA", [("g2", "Out")])[0] | {"date_modified": lock + timedelta(minutes=1)}
    at_lock = late | {"date_modified": lock}
    assert run(_inj_rows([late]), _vals(V2)) == base
    assert run(_inj_rows([at_lock]), _vals(V2)) == base  # known_as_of < lock, strictly
    early = late | {"date_modified": lock - timedelta(minutes=1)}
    moved = run(_inj_rows([early]), _vals(V2))
    assert moved[("g3", "AAA", "value_lost")] == base[("g3", "AAA", "value_lost")] + 0.5
    assert moved[("g3", "AAA", "ol_weakest")] == 0.3  # g2 out, c1 still the lowest


def test_same_week_value_row_is_not_used():
    base = run(_inj_rows(), _vals(V2))
    same_week = _vals([("q1", 9.0), ("t1", 9.0), ("g1", 9.0), ("c1", 0.0)], week=3)
    assert run(_inj_rows(), pl.concat([_vals(V2), same_week])) == base
    # an earlier slice is read: change it and the value moves
    bumped = _vals([(g, v * 2) for g, v in V2])
    assert run(_inj_rows(), bumped)[("g3", "AAA", "value_lost")] == 2 * base[("g3", "AAA", "value_lost")]  # fmt: skip


def test_latest_prior_slice_wins_and_no_tables_means_null():
    v1 = _vals([("q1", 5.0)], week=1)
    out = run(_inj_rows(), pl.concat([v1, _vals(V2)]))
    assert abs(out[("g3", "AAA", "value_lost")] - 1.72) < 1e-9  # q1 from week 2, not week 1
    none = run(_inj_rows(), None)
    assert none[("g3", "AAA", "value_lost")] is None and none[("g3", "AAA", "ol_weakest")] is None
