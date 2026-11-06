"""Curate: new pbp columns pass through to curated plays; missing ones in a season don't break."""

import duckdb
import polars as pl

from nfl.config import Paths
from nfl.curate import FTN_COLUMNS, PBP_COLUMNS, curate

RETRO_COLUMNS = [
    "third_down_converted", "third_down_failed", "field_goal_attempt", "field_goal_result",
    "kick_distance", "extra_point_attempt", "extra_point_result", "fumble", "penalty_team",
    "penalty_yards", "first_down_penalty", "return_touchdown", "touchdown", "td_team",
    "punt_blocked", "posteam_score_post", "defteam_score_post",
]  # fmt: skip

WP_DRIVE_COLUMNS = [
    "vegas_home_wp", "vegas_home_wpa", "fixed_drive", "fixed_drive_result",
    "drive_start_yard_line", "drive_end_yard_line", "drive_play_count",
]  # fmt: skip

SCHED_COLS = (  # noqa: SIM905
    "game_id season game_type week gameday weekday gametime location home_team away_team "
    "home_score away_score result total spread_line total_line home_moneyline away_moneyline "
    "home_spread_odds away_spread_odds over_odds under_odds roof surface temp wind div_game "
    "home_rest away_rest home_qb_name away_qb_name home_coach away_coach referee stadium_id stadium"
).split()


def _write(root, dataset, name, df):
    d = root / "raw" / "nflverse" / dataset / "snapshot_ts=20261101T000000Z"
    d.mkdir(parents=True, exist_ok=True)
    df.write_parquet(d / name)


def _sched(season, gid):
    row = {c: None for c in SCHED_COLS}
    row.update(game_id=gid, season=season, game_type="REG", week=1, gameday="2024-09-08",
               weekday="Sunday", gametime="13:00", home_team="BBB", away_team="AAA")  # fmt: skip
    return row


def _pbp(season, gid, extra=True):
    base = {c: [None, None] for c in PBP_COLUMNS}
    base.update(game_id=[gid] * 2, play_id=[1, 2], season=[season] * 2, week=[1, 1],
                season_type=["REG"] * 2, posteam=["AAA", "BBB"], desc=["a", "b"])  # fmt: skip
    if extra:
        base.update(field_goal_attempt=[1.0, 0.0], field_goal_result=["made", None],
                    kick_distance=[45.0, None], fumble=[0.0, 1.0], fumble_lost=[0.0, 1.0],
                    penalty_team=[None, "BBB"], penalty_yards=[None, 10.0],
                    td_team=[None, "BBB"], posteam_score_post=[3.0, 0.0],
                    vegas_home_wp=[0.5, 0.4], vegas_home_wpa=[-0.1, 0.0], fixed_drive=[1.0, 1.0],
                    fixed_drive_result=["Touchdown"] * 2, drive_start_yard_line=["AAA 25", "50"],
                    drive_end_yard_line=["BBB 3"] * 2, drive_play_count=[6.0, 6.0])  # fmt: skip
    df = pl.DataFrame(base, strict=False)
    if not extra:
        df = df.drop(RETRO_COLUMNS)
    return df


def test_retro_columns_pass_through_and_missing_season_is_tolerated(tmp_path):
    paths = Paths(tmp_path)
    _write(tmp_path, "schedules", "games.parquet",
           pl.DataFrame([_sched(2024, "2024_01_AAA_BBB"), _sched(1999, "1999_01_AAA_BBB")]))  # fmt: skip
    _write(tmp_path, "pbp", "play_by_play_2024.parquet", _pbp(2024, "2024_01_AAA_BBB"))
    _write(tmp_path, "pbp", "play_by_play_1999.parquet", _pbp(1999, "1999_01_AAA_BBB", False))
    ftn = {c: [None] for c in FTN_COLUMNS} | {
        "nflverse_game_id": ["2024_01_AAA_BBB"],
        "nflverse_play_id": [1],
    }
    _write(tmp_path, "ftn_charting", "ftn_charting_2024.parquet", pl.DataFrame(ftn, strict=False))
    curate(paths)
    con = duckdb.connect()
    glob = f"{paths.curated_table('plays').as_posix()}/*/*.parquet"
    df = con.sql(f"select * from read_parquet('{glob}', hive_partitioning=true)").pl()
    assert set(RETRO_COLUMNS) <= set(df.columns)
    new = df.filter(pl.col("season") == 2024).sort("play_id")
    assert new["field_goal_result"].to_list() == ["made", None]
    assert new["kick_distance"].to_list() == [45.0, None]
    assert new["penalty_yards"].to_list() == [None, 10.0]
    assert new["td_team"].to_list() == [None, "BBB"]
    assert new["posteam_score_post"].to_list() == [3.0, 0.0]
    assert set(WP_DRIVE_COLUMNS) <= set(df.columns)
    assert new["vegas_home_wp"].to_list() == [0.5, 0.4]
    assert new["drive_start_yard_line"].to_list() == ["AAA 25", "50"]
    assert (new["fumble_lost"] <= new["fumble"]).all()
    assert df.filter(pl.col("season") == 1999)["field_goal_result"].null_count() == 2


def test_season_curate_leaves_other_seasons_untouched(tmp_path):
    import os

    paths = Paths(tmp_path)
    _write(tmp_path, "schedules", "games.parquet",
           pl.DataFrame([_sched(2024, "2024_01_AAA_BBB"), _sched(2025, "2025_01_AAA_BBB")]))  # fmt: skip
    _write(tmp_path, "pbp", "play_by_play_2024.parquet", _pbp(2024, "2024_01_AAA_BBB"))
    _write(tmp_path, "pbp", "play_by_play_2025.parquet", _pbp(2025, "2025_01_AAA_BBB"))
    for yr in (2024, 2025):
        ftn = {c: [None] for c in FTN_COLUMNS} | {
            "nflverse_game_id": [f"{yr}_01_AAA_BBB"],
            "nflverse_play_id": [1],
        }
        _write(
            tmp_path, "ftn_charting", f"ftn_charting_{yr}.parquet", pl.DataFrame(ftn, strict=False)
        )
    curate(paths)
    other = {
        t: sorted((paths.curated_table(t) / "season=2024").glob("*.parquet"))
        for t in ("games", "plays")
    }
    before = {f: (f.stat().st_mtime_ns, f.read_bytes()) for fs in other.values() for f in fs}
    assert before
    for f in before:  # make an accidental rewrite visible even on coarse timestamps
        os.utime(f, ns=(1, 1))
    before = {f: (1, c) for f, (_, c) in before.items()}
    new = _pbp(2025, "2025_01_AAA_BBB")  # a fresher 2025 snapshot with an extra play
    d = tmp_path / "raw" / "nflverse" / "pbp" / "snapshot_ts=20261102T000000Z"
    d.mkdir(parents=True)
    pl.concat([new, new.with_columns(pl.col("play_id") + 10)]).write_parquet(
        d / "play_by_play_2025.parquet"
    )
    curate(paths, seasons=(2025, 2025), tables=("games", "plays"))
    after = {f: (f.stat().st_mtime_ns, f.read_bytes()) for f in before}
    assert after == before  # 2024 files are the same files, same bytes, not rewritten
    n = duckdb.sql(
        f"select count(*) from read_parquet('{paths.curated_table('plays').as_posix()}/season=2025/*.parquet')"
    ).fetchall()[0][0]
    assert n == 4
    assert (paths.curated_table("games") / "season=2024").exists()
