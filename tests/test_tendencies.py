import math
import time

import duckdb
import polars as pl
import pytest

from nfl.tendencies import N0, compute, shrink_decay
from tests.conftest import DATA, requires_data


def _weekly(rows, season=2025):
    """rows: (week, n, sx) for one team/group, plus a second team to define the league."""
    return pl.DataFrame(
        [
            {
                "season": season,
                "week": w,
                "team": t,
                "side": "off",
                "situation": "all",
                "metric": "pass_rate",
                "n": n,
                "sx": sx,
            }
            for t, w, n, sx in rows
        ],
        schema_overrides={"n": pl.Int64, "sx": pl.Float64},
    )


def _row(df, team):
    return df.filter(pl.col("team") == team).row(0, named=True)


def test_n_zero_rate_equals_prior():
    # A has no plays before week 3; league (B only) rate is 0.4. Prior comes from the window.
    wk = _weekly([("A", 5, 10, 9.0), ("B", 1, 100, 40.0)])
    r = shrink_decay(wk, 2025, 3)
    a = _row(r, "A")
    assert a["n"] == 0 and a["n_eff"] == 0 and a["raw_rate"] is None
    assert a["rate"] == pytest.approx(0.4)


def test_empty_window_uses_previous_season_prior():
    wk = pl.concat(
        [
            _weekly([("A", 1, 100, 30.0), ("B", 1, 100, 50.0)], season=2024),
            _weekly([("A", 3, 10, 9.0)]),
        ]
    )
    r = shrink_decay(wk, 2025, 1)
    assert r["rate"].to_list() == pytest.approx([0.4])
    assert set(r["as_of_week"]) == {1}


def test_no_prior_anywhere_is_null():
    r = shrink_decay(_weekly([("A", 5, 10, 9.0)]), 2025, 1)
    assert r.height == 1 and r["rate"][0] is None


def test_large_n_converges_to_raw_rate():
    wk = _weekly([("A", 1, 1_000_000, 800_000.0), ("B", 1, 1_000_000, 200_000.0)])
    r = shrink_decay(wk, 2025, 2)
    a = _row(r, "A")
    assert a["raw_rate"] == pytest.approx(0.8)
    assert a["rate"] == pytest.approx(0.8, abs=1e-4)


def test_decay_half_weight_six_weeks_back():
    # as_of 8: week 7 has weeks_ago 0 (w=1); week 1 has weeks_ago 6 (w=0.5).
    wk = _weekly([("A", 1, 100, 100.0), ("A", 7, 100, 0.0)])
    a = _row(shrink_decay(wk, 2025, 8), "A")
    assert a["n"] == 200
    assert a["n_eff"] == pytest.approx(150.0)
    prior = 0.5  # league = A only, unweighted: 100/200
    assert a["rate"] == pytest.approx((50.0 + N0 * prior) / (150.0 + N0))
    assert math.isclose(a["raw_rate"], 0.5)


def test_as_of_week_excludes_target_and_later():
    wk = _weekly([("A", 1, 10, 10.0), ("A", 4, 10, 0.0), ("A", 5, 10, 0.0)])
    a = _row(shrink_decay(wk, 2025, 4), "A")
    assert a["n"] == 10 and a["raw_rate"] == 1.0
    assert a["as_of_week"] == 4
    # None = all weeks, recorded as max week + 1
    a = _row(shrink_decay(wk, 2025, None), "A")
    assert a["n"] == 30 and a["as_of_week"] == 6


@requires_data
def test_compute_real_data_window():
    t0 = time.perf_counter()
    r = compute(DATA, 2025, 5)
    elapsed = time.perf_counter() - t0
    assert elapsed < 10  # target < 2 s; loose bound for slow CI
    assert set(r["as_of_week"]) == {5}
    plays = f"{DATA.curated_table('plays').as_posix()}/*/*.parquet"
    direct = (
        duckdb.connect()
        .sql(
            f"""select count(*) n from read_parquet('{plays}', hive_partitioning=true)
            where season = 2025 and week < 5 and posteam = 'DET' and play_type is not null
            and play_type in ('pass','run')"""
        )
        .pl()["n"][0]
    )
    got = r.filter(
        (pl.col("team") == "DET")
        & (pl.col("side") == "off")
        & (pl.col("situation") == "all")
        & (pl.col("metric") == "pass_rate")
    )["n"][0]
    assert got == direct
    rate_metrics = r.filter(~pl.col("metric").str.starts_with("epa")).filter(
        pl.col("rate").is_not_null()
    )
    assert rate_metrics["rate"].is_between(0, 1).all()
    assert rate_metrics["raw_rate"].drop_nulls().is_between(0, 1).all()
