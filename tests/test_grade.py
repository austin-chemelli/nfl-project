"""Grading v2 on toy graded frames: reliability/ECE, season-bootstrap summary, divergence."""

import polars as pl
import pytest

from nfl import grade


def graded(rows):
    df = pl.DataFrame(
        rows,
        schema=["game_id", "season", "model_id", "p_home", "market_p", "home_win"],
        orient="row",
    )
    p = pl.col("p_home")
    y = pl.col("home_win")
    return df.with_columns((-(y * p.log() + (1 - y) * (1 - p).log())).alias("log_loss"))


def test_perfectly_calibrated_bins_have_zero_ece():
    rows = [(f"g{i}", 2024, "m", 0.75, 0.5, 1.0 if i % 4 else 0.0) for i in range(40)]
    rel = grade.reliability(graded(rows))
    assert rel.height == 1
    assert rel["hit_rate"][0] == pytest.approx(0.75)
    e = grade.ece(rel, ["season", "model_id"])
    assert e["ece"][0] == pytest.approx(0.0)


def test_divergence_buckets_and_lean_side():
    rows = [
        ("a", 2024, "m", 0.72, 0.60, 1.0),  # leans home by 12 -> 10+ bucket, lean won
        ("b", 2024, "m", 0.40, 0.48, 1.0),  # leans away by 8 -> 5-10, lean lost
        ("c", 2024, "m", 0.51, 0.50, 0.0),  # 1 point -> 0-2.5, lean lost
        ("d", 2024, grade.MARKET_ID, 0.5, 0.5, 1.0),  # market itself excluded
    ]
    d = {r["bucket"]: r for r in grade.divergence(graded(rows)).iter_rows(named=True)}
    assert set(d) == {"10+", "5-10", "0-2.5"}
    assert d["10+"]["lean_win_rate"] == 1.0 and d["10+"]["market_expected_rate"] == pytest.approx(
        0.6
    )
    assert d["5-10"]["lean_win_rate"] == 0.0 and d["5-10"]["market_expected_rate"] == pytest.approx(
        0.52
    )


def test_summary_paired_delta_vs_market():
    rows = []
    for s in (2022, 2023, 2024):
        for i in range(10):
            y = float(i % 2)
            rows.append((f"{s}{i}", s, grade.MARKET_ID, 0.5, 0.5, y))
            rows.append((f"{s}{i}", s, "good", 0.6 if y else 0.4, 0.5, y))
    sm = {r["model_id"]: r for r in grade.summary(graded(rows)).iter_rows(named=True)}
    assert sm[grade.MARKET_ID]["d_vs_market"] == pytest.approx(0.0)
    assert sm["good"]["d_vs_market"] < 0  # beat the market on every game
    assert sm["good"]["d_lo"] <= sm["good"]["d_vs_market"] <= sm["good"]["d_hi"]
    assert sm["good"]["seasons"] == 3
