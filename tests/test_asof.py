"""Leakage guards on the real local marts (skipped without data)."""

import polars as pl

from nfl.grade import graded_frame
from nfl.predict import load_games
from tests.conftest import DATA, requires_data


@requires_data
def test_every_graded_prediction_was_locked_before_kickoff():
    g = graded_frame(DATA)
    assert g.height > 0
    late = g.filter(pl.col("lock_ts") >= pl.col("kickoff_utc"))
    assert late.is_empty(), late.select("game_id", "model_id", "lock_ts", "kickoff_utc").head()


@requires_data
def test_backfill_rows_are_not_duplicated_on_rerun():
    preds = pl.read_parquet(DATA.marts / "predictions.parquet").filter(pl.col("is_backfill"))
    dups = preds.group_by(["game_id", "model_id"]).len().filter(pl.col("len") > 1)
    assert dups.is_empty(), dups.head()


@requires_data
def test_elo_backfill_predictions_do_not_use_future_results():
    """Re-running Elo through games up to a cutoff must reproduce the stored prediction for the next game."""
    from nfl.models.elo import Elo

    games = load_games(DATA).filter(pl.col("result").is_not_null()).sort("kickoff_utc", "game_id")
    preds = pl.read_parquet(DATA.marts / "predictions.parquet").filter(
        (pl.col("model_id") == "elo_v0") & pl.col("is_backfill")
    )
    target = preds.filter(pl.col("season") == 2024).sort("lock_ts").row(40, named=True)
    e = Elo()
    for g in games.iter_rows(named=True):
        e.new_season(g["season"])
        neutral = (g["location"] or "Home") != "Home"
        if g["game_id"] == target["game_id"]:
            p = e.predict(g["home_team"], g["away_team"], neutral)
            assert abs(p["p_home"] - target["p_home"]) < 1e-9
            break
        e.update(g["home_team"], g["away_team"], g["result"], neutral)
    else:
        raise AssertionError("target game not found")


@requires_data
def test_every_stored_feature_was_known_before_its_game_kicked_off():
    """Leakage guard for the feature store: no row is stamped at or after kickoff."""
    from nfl.features import store

    feats = store.read_features(DATA)
    if feats.is_empty():
        import pytest

        pytest.skip("feature store not built (run nfl features)")
    games = store.games_frame(DATA).select("game_id", "kickoff_utc")
    late = feats.join(games, on="game_id").filter(pl.col("known_as_of") >= pl.col("kickoff_utc"))
    assert late.is_empty(), late.select("game_id", "feature", "known_as_of", "kickoff_utc").head()
