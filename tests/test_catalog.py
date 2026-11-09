from datetime import datetime, timedelta

import polars as pl
import pytest

from nfl import catalog
from nfl.config import Paths
from nfl.features import store

from .conftest import requires_data

T = datetime(2026, 11, 5, 13, 0)


def feature_rows():
    """Two games; G1's home EPA has three versions (one exactly at T); a game-level feature; G2's away
    side has no value, so its vector is null."""
    r = lambda g, side, f, v, at: {
        "season": 2026, "week": 9, "game_id": g, "side": side, "feature": f, "value": v,
        "known_as_of": at, "source": "test", "version": "1",
    }  # fmt: skip
    return pl.DataFrame(
        [
            r("G1", "home", "strength.epa_off", 0.10, T - timedelta(days=3)),
            r("G1", "home", "strength.epa_off", 0.20, T - timedelta(hours=1)),
            r("G1", "home", "strength.epa_off", 0.90, T),  # at the lock: never visible to it
            r("G1", "away", "strength.epa_off", -0.05, T - timedelta(days=2)),
            r("G1", "game", "environment.rest_days", 1.0, T - timedelta(days=4)),
            r("G2", "home", "strength.epa_off", 0.30, T - timedelta(days=1)),
            r("G2", "away", "strength.epa_off", None, T - timedelta(days=1)),
            r("G2", "home", "strength.epa_off", 0.50, T + timedelta(days=1)),  # the future
        ],
        schema=store.FEATURE_SCHEMA,
    )


@pytest.fixture
def root(tmp_path):
    paths = Paths(tmp_path)
    f = paths.marts / "features" / "season=2026" / "strength.parquet"
    f.parent.mkdir(parents=True)
    feature_rows().write_parquet(f)
    games = paths.curated_table("games") / "season=2026"
    games.mkdir(parents=True)
    pl.DataFrame({"game_id": ["G1", "G2"], "raw_snapshot_ts": ["x", "x"],
                  "kickoff_utc": [T + timedelta(days=3), T + timedelta(days=3, hours=3)]}).write_parquet(
        games / "data_0.parquet"
    )  # fmt: skip
    return paths


def test_features_asof_is_store_as_of_and_never_sees_the_lock_instant(root):
    con = catalog.connect(root)
    sql = con.sql(f"select * from features_asof(timestamp '{T}')").pl()
    want = store.as_of(store.read_features(root), T)
    cols = ["game_id", "side", "feature", "value", "known_as_of"]
    assert sql.select(cols).sort(cols).equals(want.select(cols).sort(cols))
    gb = sql.filter((pl.col("game_id") == "G1") & (pl.col("side") == "home"))
    assert gb["value"].to_list() == [0.20]
    assert 0.50 not in sql["value"].to_list()


def test_game_vectors_match_the_polars_vectors_including_nulls(root):
    con = catalog.connect(root)
    sql = con.sql(f"select * from game_vectors(timestamp '{T}')").pl().sort("game_id", "feature")
    want = store.game_vectors(store.as_of(store.read_features(root), T))
    assert sql.select(want.columns).equals(want)
    assert sql.filter(pl.col("game_id") == "G2")["value"].to_list() == [None]


def test_a_mart_reads_its_single_file_and_its_parts_together(root):
    one = pl.DataFrame({"game_id": ["G1"], "p_home": [0.6]})
    one.write_parquet(root.marts / "predictions.parquet")
    part = root.marts / "predictions" / "lock_ts=20261105T130000Z.parquet"
    part.parent.mkdir(parents=True)
    pl.DataFrame({"game_id": ["G2"], "p_home": [0.4], "extra": ["new column"]}).write_parquet(part)
    con = catalog.connect(root)
    got = con.sql("select game_id, p_home, extra from predictions order by game_id").fetchall()
    assert got == [("G1", 0.6, None), ("G2", 0.4, "new column")]


def test_tables_without_files_get_no_view_and_are_listed(root):
    con = catalog.connect(root)
    names = {d["name"] for d in catalog.describe(con)}
    assert names == {"features", "games"}
    assert "predictions" in catalog.missing(root)


def test_only_limits_the_views_and_games_frame_reads_through_it(root):
    con = catalog.connect(root, only=["games"])
    assert [d["name"] for d in catalog.describe(con)] == ["games"]
    g = store.games_frame(root, min_season=2026)
    assert g["game_id"].to_list() == ["G1", "G2"]
    assert "raw_snapshot_ts" not in g.columns


@requires_data
def test_on_real_data_the_sql_as_of_equals_the_polars_one():
    from nfl.config import get_paths

    paths = get_paths()
    con = catalog.connect(paths, only=["features"])
    ts = datetime(2025, 11, 2, 12)
    keys = ["game_id", "side", "feature"]
    want = store.as_of(store.read_features(paths, seasons=(2025, 2025)), ts).sort(keys)
    got = (
        con.sql(f"select * from features_asof(timestamp '{ts}') where season = 2025")
        .pl()
        .select(want.columns)
        .cast(store.FEATURE_SCHEMA)
        .sort(keys)
    )
    assert got.equals(want)
