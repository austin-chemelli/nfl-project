"""`fill_unscored`: finished games with no prediction get backfill rows; everything else is untouched."""

from datetime import datetime

import polars as pl

from nfl.approaches import run
from nfl.config import Paths
from nfl.predict import PRED_SCHEMA, existing


def _pred(gid: str, week: int, model: str, backfill: bool, p: float) -> dict:
    return {
        "game_id": gid, "season": 2026, "week": week, "model_id": model, "model_version": "v",
        "lock_ts": datetime(2026, 10, 1), "data_snapshot_ts": "x", "p_home": p,
        "spread_home": None, "total": None, "sd_margin": 13.5, "is_backfill": backfill,
        "slot": "backfill" if backfill else "thu", "contributions": None,
    }  # fmt: skip


def _setup(tmp_path, monkeypatch):
    paths = Paths(tmp_path)
    paths.marts.mkdir(parents=True)
    prev = [
        _pred("2026_07_A_B", 7, "student", True, 0.6),  # backfilled earlier
        _pred("2025_10_A_B", 10, "student", True, 0.5),  # another season's backfill
        _pred("2026_09_E_F", 9, "student", False, 0.7),  # a live lock
    ]
    pl.DataFrame(prev, schema=PRED_SCHEMA).write_parquet(paths.marts / "predictions.parquet")
    games = pl.DataFrame(
        {
            "game_id": ["2026_07_A_B", "2026_08_C_D", "2026_09_E_F", "2026_10_G_H", "2025_10_A_B"],
            "season": [2026, 2026, 2026, 2026, 2025],
            "result": [3, -7, 10, None, 1],
        }
    )
    monkeypatch.setattr(run.store, "games_frame", lambda _p: games)
    scored: list[list[str]] = []

    def fake_score(_paths, g):
        scored.append(g.get_column("game_id").to_list())
        rows = [_pred(gid, 8, m, True, 0.4) for gid in g["game_id"] for m in ("student", "sharp")]
        return pl.DataFrame(rows, schema=PRED_SCHEMA), {"student", "sharp"}

    monkeypatch.setattr(run, "_score", fake_score)
    return paths, scored


def test_scores_only_finished_games_without_a_prediction(tmp_path, monkeypatch):
    paths, scored = _setup(tmp_path, monkeypatch)
    assert run.fill_unscored(paths, 2026) == 2
    # week 7 (backfilled), week 9 (locked) and week 10 (not played) are skipped
    assert scored == [["2026_08_C_D"]]
    out = existing(paths)
    assert out.height == 3 + 2
    # rows already there, live and backfill, in this season and others, are untouched
    kept = out.filter(pl.col("game_id") != "2026_08_C_D").sort("game_id")
    assert kept["p_home"].to_list() == [0.5, 0.6, 0.7]


def test_second_run_writes_nothing(tmp_path, monkeypatch):
    paths, scored = _setup(tmp_path, monkeypatch)
    run.fill_unscored(paths, 2026)
    assert run.fill_unscored(paths, 2026) == 0
    assert len(scored) == 1
    assert existing(paths).height == 5
