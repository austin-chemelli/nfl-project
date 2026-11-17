"""`nfl retro daily` (M9.6, ADR 0016): the 07:00 ET cloud job.

Ingest the current season's pbp and schedules, curate only that season's games and plays (other
seasons' partitions are never rewritten), build the retros that are missing or stale, then the
recaps for every week and the site files. Builds the expectations first if the file is
missing or from an older version.

Old curated plays: DuckDB binds a `*/*.parquet` glob to the first file's schema, so a bucket
whose historical partitions predate M9.1 (no `third_down_converted` etc.) would fail in the
expectations and the game builder. When any partition lacks the column, all plays are re-curated
once (all seasons, plays only).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import duckdb

from nfl.config import Paths, current_season
from nfl.retro import expectations
from nfl.retro.game import build
from nfl.retro.week import write_recap
from nfl.site import write_retro

PROBE_COLUMN = "third_down_converted"
MAX_WEEK = 22  # regular season plus playoffs; write_recap skips a week with no retros


@dataclass
class DailyResult:
    season: int
    written: list[str]
    up_to_date: int
    skipped: int
    weeks: list[int]
    site_files: int
    built_expectations: bool
    recurated_plays: bool = False


def plays_need_recurate(paths: Paths) -> bool:
    """True when any curated plays partition lacks the M9.1 columns (cheap: parquet metadata)."""
    for f in sorted(paths.curated_table("plays").glob("season=*/*.parquet")):
        cols = {
            r[0]
            for r in duckdb.sql(f"describe select * from read_parquet('{f.as_posix()}')").fetchall()
        }
        if PROBE_COLUMN not in cols:
            return True
    return False


def expectations_stale(paths: Paths) -> bool:
    """True when the expectations file is missing or from another version: a code change that
    refits them (v3 added the deserved-to-win fit) then reaches the bucket on the next run, and
    every retro rebuilds because its stamped version differs."""
    p = expectations.expectations_path(paths)
    if not p.exists():
        return True
    try:
        return json.loads(p.read_text()).get("version") != expectations.VERSION
    except OSError, ValueError:
        return True


def run(paths: Paths, season: int | None = None, fetch: bool = True) -> DailyResult:
    from nfl.curate import curate
    from nfl.ingest import ingest

    season = season or current_season()
    if fetch:
        ingest(
            paths,
            datasets=["schedules", "pbp"],
            seasons={"pbp": (season, season)},
        )
    curate(paths, seasons=(season, season), tables=("games", "plays"))
    recurated = plays_need_recurate(paths)
    if recurated:
        print("retro daily: old curated plays lack the retro columns; re-curating all plays once")
        curate(paths, tables=("plays",))
    built = expectations_stale(paths)
    if built:
        expectations.write(paths, expectations.build(paths))
    rep = build(paths, season)
    # Every week's recap, not only the weeks rebuilt: a recap is a cheap summary of its retros,
    # and a change to how it is computed then reaches every week the next morning.
    for wk in range(1, MAX_WEEK + 1):
        write_recap(paths, season, wk)
    published = write_retro(paths, season)
    return DailyResult(
        season, rep.written, rep.up_to_date, rep.skipped, sorted(rep.weeks), len(published), built,
        recurated,
    )  # fmt: skip
