"""Feature store unit tests on toy frames (no local data needed)."""

from datetime import datetime, timedelta

import polars as pl
import pytest

from nfl.config import Paths
from nfl.features import store

K1 = datetime(2025, 9, 7, 17, 0)  # played
K2 = datetime(2025, 9, 14, 17, 0)  # upcoming relative to BUILD
BUILD = datetime(2025, 9, 10, 12, 0)

GAMES = pl.DataFrame(
    {
        "game_id": ["G1", "G2"],
        "season": [2025, 2025],
        "week": [1, 2],
        "home_team": ["DET", "GB"],
        "away_team": ["CHI", "DET"],
        "kickoff_utc": [K1, K2],
    }
)


def team_rows(vals, build=BUILD, version="v1"):
    df = pl.DataFrame(vals, schema=["game_id", "team", "feature", "value"], orient="row")
    return store.from_team_values(df, GAMES, source="test", version=version, build_ts=build)


def test_stamp_played_vs_upcoming():
    rows = team_rows(
        [("G1", "DET", "strength.elo_pre", 1550.0), ("G2", "GB", "strength.elo_pre", 1500.0)]
    )
    by_game = dict(zip(rows["game_id"], rows["known_as_of"]))
    assert by_game["G1"] == K1 - store.BACKTEST_ASOF_OFFSET  # synthetic, strictly before kickoff-1h
    assert by_game["G2"] == BUILD  # upcoming: known at build time
    assert set(rows["side"]) == {"home"}


def test_team_not_in_game_raises():
    with pytest.raises(ValueError, match="team not in game"):
        team_rows([("G1", "GB", "strength.elo_pre", 1.0)])


def test_validate_rejects_bad_names_and_mixed_sides():
    with pytest.raises(ValueError, match="family"):
        team_rows([("G1", "DET", "elo_pre", 1.0)])
    t = team_rows([("G1", "DET", "env.x", 1.0)])
    g = store.from_game_values(
        pl.DataFrame({"game_id": ["G1"], "feature": ["env.x"], "value": [1.0]}),
        GAMES,
        source="t",
        version="v",
        build_ts=BUILD,
    )
    with pytest.raises(ValueError, match="mix"):
        store.validate(pl.concat([t, g]))


def test_game_vectors_diff_and_nulls():
    rows = pl.concat(
        [
            team_rows(
                [
                    ("G1", "DET", "strength.elo_pre", 1550.0),
                    ("G1", "CHI", "strength.elo_pre", 1500.0),
                    ("G1", "DET", "form.streak", 2.0),  # away side missing -> null
                ]
            ),
            store.from_game_values(
                pl.DataFrame(
                    {"game_id": ["G1"], "feature": ["environment.is_dome"], "value": [1.0]}
                ),
                GAMES,
                source="t",
                version="v",
                build_ts=BUILD,
            ),
        ]
    )
    v = {f: x for _, f, x in store.game_vectors(rows).iter_rows()}
    assert v["strength.elo_pre"] == 50.0
    assert v["form.streak"] is None
    assert v["environment.is_dome"] == 1.0


def test_as_of_strict_and_latest(tmp_path):
    paths = Paths(tmp_path)
    early = team_rows([("G2", "GB", "market.x", 1.0)], build=BUILD)
    later = team_rows([("G2", "GB", "market.x", 2.0)], build=BUILD + timedelta(days=1))
    store.write_features(paths, early)
    store.write_features(paths, later)
    df = store.read_features(paths)
    assert df.height == 2
    # strictly before: a lock exactly at the first stamp sees nothing
    assert store.as_of(df, BUILD).is_empty()
    assert store.as_of(df, BUILD + timedelta(hours=1))["value"].to_list() == [1.0]
    assert store.as_of(df, BUILD + timedelta(days=2))["value"].to_list() == [2.0]
    # per-game lock frame
    locks = pl.DataFrame({"game_id": ["G2"], "lock_ts": [BUILD + timedelta(hours=1)]})
    assert store.as_of(df, locks)["value"].to_list() == [1.0]


def test_backtest_rows_visible_to_synthetic_lock():
    rows = team_rows([("G1", "DET", "strength.elo_pre", 1.0)])
    locks = pl.DataFrame({"game_id": ["G1"], "lock_ts": [K1 - timedelta(hours=1)]})
    assert store.as_of(rows, locks).height == 1


def test_write_is_upsert_and_skips_unchanged_values(tmp_path):
    paths = Paths(tmp_path)
    a = team_rows([("G2", "GB", "form.streak", 1.0)], build=BUILD)
    assert store.write_features(paths, a) == 1
    # identical rebuild at the same stamp replaces, no growth
    assert store.write_features(paths, a) == 1
    assert store.read_features(paths).height == 1
    # later build with the same value: skipped
    same = team_rows([("G2", "GB", "form.streak", 1.0)], build=BUILD + timedelta(hours=6))
    assert store.write_features(paths, same) == 0
    assert store.read_features(paths).height == 1
    # rebuilt backtest value for a played game replaces in place
    b1 = team_rows([("G1", "DET", "form.streak", 1.0)])
    b2 = team_rows([("G1", "DET", "form.streak", 3.0)])
    store.write_features(paths, b1)
    store.write_features(paths, b2)
    g1 = store.read_features(paths).filter(pl.col("game_id") == "G1")
    assert g1["value"].to_list() == [3.0]


def test_read_filters_and_to_wide(tmp_path):
    paths = Paths(tmp_path)
    store.write_features(
        paths,
        team_rows(
            [
                ("G1", "DET", "strength.elo_pre", 1550.0),
                ("G1", "CHI", "strength.elo_pre", 1500.0),
                ("G1", "DET", "form.streak", 1.0),
                ("G1", "CHI", "form.streak", -1.0),
            ]
        ),
    )
    assert set(store.read_features(paths, families=["form"])["feature"]) == {"form.streak"}
    assert store.read_features(paths, seasons=(2010, 2024)).is_empty()
    vec = store.game_vectors(store.read_features(paths))
    w = store.to_wide(vec, ["strength.elo_pre", "form.streak", "front.blitz_rate"])
    assert w.columns == ["game_id", "strength.elo_pre", "form.streak", "front.blitz_rate"]
    assert w.row(0) == ("G1", 50.0, 2.0, None)
