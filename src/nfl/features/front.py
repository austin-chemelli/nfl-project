"""Front family: FTN-based scheme tendencies, 2022+ (null before; FTN charting starts in 2022).

Values are tendencies' shrunk, recency-weighted `rate` as of the game's week (plays from weeks
strictly before it, same season). In 2022 week 1 there is no prior, so the value is null.
  front.blitz_rate        defense: dropbacks faced with >= 1 blitzer
  front.box_8plus_rate    defense: runs faced with >= 8 in the box (tendencies `box_8plus_vs_run_rate`)
  front.motion_rate       offense: pass/run plays with pre-snap motion
  front.play_action_rate  offense: pass plays with play action
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import polars as pl

from nfl.config import Paths
from nfl.features import store
from nfl.features.strength import team_games
from nfl.tendencies import rates_asof, weekly_aggregates

SOURCE = "ftn"
VERSION = "1"

SPECS = [
    ("front.blitz_rate", "def", "all", "blitz_rate"),
    ("front.box_8plus_rate", "def", "all", "box_8plus_vs_run_rate"),
    ("front.motion_rate", "off", "all", "motion_rate"),
    ("front.play_action_rate", "off", "all", "play_action_rate"),
]


def compute(games: pl.DataFrame, weekly: pl.DataFrame) -> pl.DataFrame:
    tw = team_games(games).join(games.select("game_id", "week"), on="game_id")
    vals = rates_asof(weekly, tw.select("season", "week", "team"), SPECS)
    return tw.select("game_id", "season", "week", "team").join(
        vals, on=["season", "week", "team"], how="inner"
    ).select("game_id", "team", "feature", "value")  # fmt: skip


def build(paths: Paths, games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    seasons = sorted(int(s) for s in games["season"].unique().to_list())
    weekly = weekly_aggregates(duckdb.connect(), paths, seasons, ["all"])
    values = compute(games, weekly)
    return store.from_team_values(values, games, source=SOURCE, version=VERSION, build_ts=build_ts)
