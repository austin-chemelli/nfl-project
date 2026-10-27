"""Curated tables built with DuckDB from the latest raw snapshot of each upstream file.

Tables (partitioned by season under curated/<table>/season=YYYY/):
  games        one row per game from schedules, with kickoff_utc
  plays        pbp subset joined to FTN charting (2022+) on (game_id, play_id)
  injuries     weekly injury reports (no report date upstream; week-level only)
  depth_charts timestamped depth chart entries
  lines        Odds API snapshots matched to games (nfl.odds.curate_lines)

Deterministic: rebuildable from raw at any time. `raw_snapshot_ts` records which snapshot fed each row.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import duckdb

from nfl.config import DATASETS, Paths
from nfl.ingest import list_snapshots

PBP_COLUMNS = [
    "game_id",
    "play_id",
    "season",
    "week",
    "season_type",
    "game_date",
    "home_team",
    "away_team",
    "posteam",
    "posteam_type",
    "defteam",
    "drive",
    "series",
    "qtr",
    "down",
    "ydstogo",
    "yardline_100",
    "goal_to_go",
    "score_differential",
    "half_seconds_remaining",
    "game_seconds_remaining",
    "play_type",
    "pass",
    "rush",
    "qb_dropback",
    "shotgun",
    "no_huddle",
    "pass_length",
    "air_yards",
    "yards_gained",
    "xpass",
    "pass_oe",
    "interception",
    "fumble_lost",
    "sack",
    "qb_scramble",
    "passer_player_id",
    "passer_player_name",
    "qb_epa",
    "cpoe",
    "special_teams_play",
    "epa",
    "success",
    "wp",
    "fourth_down_converted",
    "fourth_down_failed",
    "penalty",
    "aborted_play",
    "desc",
]
FTN_COLUMNS = [
    "starting_hash",
    "qb_location",
    "n_offense_backfield",
    "n_defense_box",
    "is_no_huddle",
    "is_motion",
    "is_play_action",
    "is_screen_pass",
    "is_rpo",
    "is_trick_play",
    "is_qb_out_of_pocket",
    "is_qb_sneak",
    "n_blitzers",
    "n_pass_rushers",
    "read_thrown",
    "is_interception_worthy",
    "is_throw_away",
    "is_catchable_ball",
    "is_contested_ball",
    "is_drop",
]


def latest_files(paths: Paths, dataset: str) -> dict[int | None, Path]:
    """season -> path of the most recent snapshot of that season's file (None key for single-file sets)."""
    _tag, pattern, first = DATASETS[dataset]
    out: dict[int | None, Path] = {}
    if first is None:
        snaps = list_snapshots(paths, dataset, pattern)
        if snaps:
            out[None] = snaps[-1][1]
        return out
    base = paths.raw_dataset(dataset)
    if not base.exists():
        return out
    rx = re.compile(pattern.replace("{season}", r"(\d{4})").replace(".", r"\."))
    found: dict[int, tuple[str, Path]] = {}
    for d in sorted(base.glob("snapshot_ts=*")):
        ts = d.name.split("=", 1)[1]
        for f in d.iterdir():
            m = rx.fullmatch(f.name)
            if m:
                found[int(m.group(1))] = (ts, f)  # sorted ascending => last wins
    return {s: p for s, (_, p) in sorted(found.items())}


def _ts_of(p: Path) -> str:
    return p.parent.name.split("=", 1)[1]


def _read_many(files: dict[int | None, Path], extra: str = "") -> str:
    """SQL fragment: union of parquet files with raw_snapshot_ts attached and hive partitioning off."""
    parts = [
        f"select *{extra}, '{_ts_of(p)}' as raw_snapshot_ts from read_parquet('{p.as_posix()}', hive_partitioning=false)"
        for p in files.values()
    ]
    return " union all by name ".join(parts)


def _write_partitioned(con: duckdb.DuckDBPyConnection, sql: str, out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    con.execute(
        f"copy ({sql}) to '{out_dir.as_posix()}' (format parquet, partition_by (season), overwrite_or_ignore)"
    )


def _counts(
    con: duckdb.DuckDBPyConnection, table: str, out_dir: Path
) -> list[tuple[str, int, int]]:
    rows = con.execute(
        f"select season, count(*) from read_parquet('{out_dir.as_posix()}/*/*.parquet', hive_partitioning=true) group by 1 order by 1"
    ).fetchall()
    return [(table, int(s), int(n)) for s, n in rows]


def curate(paths: Paths, seasons: tuple[int, int] | None = None) -> list[tuple[str, int, int]]:
    con = duckdb.connect()
    con.execute("set timezone='UTC'")
    summary: list[tuple[str, int, int]] = []
    lo, hi = seasons or (0, 9999)
    season_filter = f"season between {lo} and {hi}"

    # games
    sched = latest_files(paths, "schedules")
    if sched:
        sql = f"""
        with s as ({_read_many(sched)})
        select game_id, season, game_type, week, gameday::date as gameday, weekday, gametime,
               -- 1999 schedules have no gametime: impute the slot's usual Eastern start (flagged)
               timezone('America/New_York', (gameday || ' ' || coalesce(gametime,
                   case weekday when 'Monday' then '21:00' when 'Thursday' then '20:30'
                                when 'Saturday' then '16:30' else '13:00' end))::timestamp)
                   at time zone 'UTC' as kickoff_utc,
               gametime is null as kickoff_imputed,
               location, home_team, away_team, home_score, away_score, result, total,
               spread_line, total_line, home_moneyline, away_moneyline,
               home_spread_odds, away_spread_odds, over_odds, under_odds,
               roof, surface, temp, wind, div_game, home_rest, away_rest,
               home_qb_name, away_qb_name, home_coach, away_coach, referee, stadium_id, stadium,
               raw_snapshot_ts
        from s where {season_filter}
        """
        out = paths.curated_table("games")
        _write_partitioned(con, sql, out)
        summary += _counts(con, "games", out)

    # plays = pbp ⋈ ftn
    pbp = latest_files(paths, "pbp")
    ftn = latest_files(paths, "ftn_charting")
    if pbp:
        pbp_sel = ", ".join(f'p."{c}"' for c in PBP_COLUMNS)
        ftn_sel = ", ".join(f'f."{c}"' for c in FTN_COLUMNS)
        ftn_sql = (
            _read_many(ftn)
            if ftn
            else "select null::varchar nflverse_game_id, null::int nflverse_play_id where false"
        )
        sql = f"""
        with p as (select {", ".join(f'"{c}"' for c in PBP_COLUMNS)}, raw_snapshot_ts from ({_read_many(pbp)})),
             f as ({ftn_sql}),
             g as (select game_id, kickoff_utc from read_parquet('{paths.curated_table("games").as_posix()}/*/*.parquet', hive_partitioning=true))
        select {pbp_sel}, g.kickoff_utc,
               {ftn_sel}, f.nflverse_play_id is not null as has_ftn,
               p.raw_snapshot_ts
        from p
        left join f on p.game_id = f.nflverse_game_id and p.play_id = f.nflverse_play_id
        left join g on p.game_id = g.game_id
        where p.{season_filter}
        """
        out = paths.curated_table("plays")
        _write_partitioned(con, sql, out)
        summary += _counts(con, "plays", out)

    # injuries (week-level; upstream has no report date)
    inj = latest_files(paths, "injuries")
    if inj:
        # pre-2022 files store season (and week) as doubles; normalize so partitions are season=YYYY
        sql = f"select * replace (season::int as season, week::int as week) from ({_read_many(inj)}) where {season_filter}"
        out = paths.curated_table("injuries")
        _write_partitioned(con, sql, out)
        summary += _counts(con, "injuries", out)

    # depth charts (season derived from file)
    dc = latest_files(paths, "depth_charts")
    if dc:
        parts = []
        for s, p in dc.items():
            cols = {
                r[0]
                for r in con.execute(
                    f"describe select * from read_parquet('{p.as_posix()}', hive_partitioning=false)"
                ).fetchall()
            }
            star = "* exclude (season)" if "season" in cols else "*"
            parts.append(
                f"select {s} as season, {star}, '{_ts_of(p)}' as raw_snapshot_ts from read_parquet('{p.as_posix()}', hive_partitioning=false)"
            )
        sql = f"select * from ({' union all by name '.join(parts)}) where {season_filter}"
        out = paths.curated_table("depth_charts")
        _write_partitioned(con, sql, out)
        summary += _counts(con, "depth_charts", out)

    # lines (The Odds API snapshots, matched to games)
    from nfl.features.store import games_frame
    from nfl.odds import curate_lines

    if paths.curated_table("games").exists():
        n = curate_lines(paths, games_frame(paths))
        if n:
            summary.append(("lines", 0, n))

    return summary
