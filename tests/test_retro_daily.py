"""M9.6: the daily path confines itself to the current season and repairs old curated plays."""

import shutil
from pathlib import Path

import duckdb
import polars as pl

from nfl.config import Paths
from nfl.curate import FTN_COLUMNS, curate
from nfl.retro.daily import plays_need_recurate, run
from tests.test_curate import _pbp, _sched, _write

EXP = Path(__file__).parent / "fixtures" / "retro" / "expectations.json"


def _tree(tmp_path):
    paths = Paths(tmp_path)
    _write(tmp_path, "schedules", "games.parquet",
           pl.DataFrame([_sched(2024, "2024_01_AAA_BBB"), _sched(2025, "2025_01_AAA_BBB")]))  # fmt: skip
    for yr in (2024, 2025):
        _write(tmp_path, "pbp", f"play_by_play_{yr}.parquet", _pbp(yr, f"{yr}_01_AAA_BBB"))
        ftn = {c: [None] for c in FTN_COLUMNS} | {
            "nflverse_game_id": [f"{yr}_01_AAA_BBB"],
            "nflverse_play_id": [1],
        }
        _write(
            tmp_path, "ftn_charting", f"ftn_charting_{yr}.parquet", pl.DataFrame(ftn, strict=False)
        )
    curate(paths)
    (paths.marts / "retro").mkdir(parents=True)
    shutil.copy(EXP, paths.marts / "retro" / "expectations.json")
    return paths


def _snapshot(paths, season):
    return {
        f: f.read_bytes()
        for t in ("games", "plays")
        for f in (paths.curated_table(t) / f"season={season}").glob("*.parquet")
    }


def test_daily_leaves_other_seasons_untouched(tmp_path):
    paths = _tree(tmp_path)
    before = _snapshot(paths, 2024)
    assert before and not plays_need_recurate(paths)
    r = run(paths, season=2025, fetch=False)
    assert not r.recurated_plays
    assert _snapshot(paths, 2024) == before


def test_old_curated_plays_trigger_a_full_plays_curate(tmp_path):
    paths = _tree(tmp_path)
    old = next((paths.curated_table("plays") / "season=2024").glob("*.parquet"))
    pl.read_parquet(old).drop("third_down_converted").write_parquet(old)  # pre-M9.1 partition
    assert plays_need_recurate(paths)
    r = run(paths, season=2025, fetch=False)
    assert r.recurated_plays and not plays_need_recurate(paths)
    glob = f"{paths.curated_table('plays').as_posix()}/*/*.parquet"
    cols = duckdb.sql(f"select * from read_parquet('{glob}', hive_partitioning=true)").columns
    assert "third_down_converted" in cols
    seasons = duckdb.sql(
        f"select distinct season from read_parquet('{glob}', hive_partitioning=true)"
    ).fetchall()
    assert {s[0] for s in seasons} == {2024, 2025}
