"""Grading v2 on toy graded frames: reliability/ECE, season-bootstrap summary, divergence."""

from datetime import datetime, timedelta

import polars as pl
import pytest

from nfl import grade
from nfl.config import Paths


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


def _preds(rows):
    from nfl.predict import PRED_SCHEMA

    base = {"season": 2026, "week": 9, "model_version": "v", "data_snapshot_ts": "s", "spread_home": 1.0,
            "total": 44.0, "sd_margin": 13.5, "slot": None, "contributions": None}  # fmt: skip
    return pl.DataFrame([base | r for r in rows], schema=PRED_SCHEMA)


def test_graded_frame_keeps_the_live_lock_over_a_later_backfill_row(tmp_path, monkeypatch):
    kick = datetime(2026, 11, 6, 1, 15)
    locked = {"game_id": "G", "model_id": "market_baseline", "lock_ts": datetime(2026, 11, 5, 14),
              "is_backfill": False, "p_home": 0.55}  # fmt: skip
    backfill = locked | {"lock_ts": kick - timedelta(hours=1), "is_backfill": True, "p_home": 0.59}
    other = {"game_id": "H", "model_id": "market_baseline", "lock_ts": kick - timedelta(hours=1),
             "is_backfill": True, "p_home": 0.4}  # fmt: skip
    too_late = locked | {"lock_ts": kick + timedelta(hours=1), "p_home": 0.9}
    paths = Paths(tmp_path)
    paths.marts.mkdir(parents=True)
    _preds([locked, backfill, other, too_late]).write_parquet(paths.marts / "predictions.parquet")
    games = pl.DataFrame({
        "game_id": ["G", "H"], "kickoff_utc": [kick, kick], "result": [3, -3], "total": [40, 40],
        "spread_line": [1.0, 1.0], "total_line": [44.0, 44.0], "home_team": ["A", "B"], "away_team": ["C", "D"],
    })  # fmt: skip
    monkeypatch.setattr(grade, "load_games", lambda p: games)
    monkeypatch.setattr(
        grade, "_market_p", lambda p: pl.DataFrame({"game_id": ["G", "H"], "market_p": [0.5, 0.5]})
    )
    by = {r["game_id"]: r for r in grade.graded_frame(paths).iter_rows(named=True)}
    assert by["G"]["p_home"] == 0.55 and by["G"]["is_backfill"] is False
    assert by["H"]["p_home"] == 0.4 and by["H"]["is_backfill"] is True  # no lock: backfill stands


def test_predict_adds_no_backfill_row_for_a_game_with_a_live_lock(tmp_path, monkeypatch):
    from nfl import predict as P

    kick = datetime(2026, 11, 6, 1, 15)
    live = {"game_id": "G", "model_id": "market_baseline", "lock_ts": datetime(2026, 11, 5, 14),
            "is_backfill": False, "p_home": 0.55}  # fmt: skip
    paths = Paths(tmp_path)
    paths.marts.mkdir(parents=True)
    _preds([live]).write_parquet(paths.marts / "predictions.parquet")
    row = {"season": 2026, "week": 9, "kickoff_utc": kick, "result": 3, "location": "Home",
           "spread_line": 3.0, "total_line": 44.0, "home_moneyline": -150.0, "away_moneyline": 130.0,
           "home_team": "A", "away_team": "B", "home_score": 24, "away_score": 21, "raw_snapshot_ts": "s"}  # fmt: skip
    games = pl.DataFrame([row | {"game_id": "G"}, row | {"game_id": "H"}])
    monkeypatch.setattr(P, "load_games", lambda p: games)
    P.predict(paths, (2026, 2026))
    out = pl.read_parquet(paths.marts / "predictions.parquet")
    g = out.filter((pl.col("game_id") == "G") & (pl.col("model_id") == "market_baseline"))
    assert g.height == 1 and g["is_backfill"].to_list() == [False]  # the live lock stands alone
    assert out.filter(pl.col("game_id") == "G")["model_id"].n_unique() == 3  # others still fill in
    assert out.filter(pl.col("game_id") == "H")["model_id"].n_unique() == 3
