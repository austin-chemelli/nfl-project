"""Scheme-prior features (M1.16): what the team's current play-callers have done before.

For every game from 2017 on, each team's offensive and defensive play-caller (the CSV's
end-of-season person: `off_play_caller` else OC, `def_play_caller` else DC; see
`nfl.coaches.assignments`) is looked up and his profile is read from seasons strictly **before the
game's season**. The profile follows the person across teams. Nothing from the target season is
used, so these are point-in-time by construction (completed seasons only); rows get the store's
standard `known_as_of` stamp. Known limit: a mid-season coordinator change uses the person who
finished the season, for the whole season (refinement later).

Scale: the value is the recency-weighted mean (0.7 ** seasons_back) of the unit's **deviation from
that season's league mean**, in the metric's own units (share as a fraction, seconds for time to
throw), so +0.08 on `def_man_rate_prior` = "8 points more man coverage than the league average
that year". Centering within season removes the 2023 charting-provider level shift (and the 2018
start of coverage data: man/two-high priors are null for 2017-2018 targets, and for anyone whose
history precedes 2018 only). Null when the person has no unit-season with that metric before the
target season (a first-time coordinator). Offense features describe the team's own offense,
defense features its own defense.
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from nfl import coaches
from nfl.config import Paths
from nfl.features import store
from nfl.models.elo import TEAM_ALIASES

SOURCE = "participation"
VERSION = "2"
FIRST_TARGET = 2017  # needs a prior season (participation starts 2016)

# feature -> (side, metric in nfl.scheme)
MAP: dict[str, tuple[str, str]] = {
    "scheme.off_11_rate_prior": ("off", "pers_11_share"),
    "scheme.off_heavy_rate_prior": ("off", "pers_heavy_share"),
    "scheme.off_time_to_throw_prior": ("off", "time_to_throw"),
    "scheme.def_man_rate_prior": ("def", "man_rate"),
    "scheme.def_two_high_rate_prior": ("def", "two_high_rate"),
    "scheme.def_pressure_rate_prior": ("def", "pressure_rate"),
}
FEATURES = tuple(MAP)


def compute(games: pl.DataFrame, rows: pl.DataFrame, assign: pl.DataFrame) -> pl.DataFrame:
    """(game_id, team, feature, value) for every game from FIRST_TARGET, both teams, all features.

    `rows` = coaches.profile_rows output; `assign` = coaches.assignments()."""
    g = games.filter(pl.col("season") >= FIRST_TARGET).select(
        "game_id", pl.col("season").cast(pl.Int64), "home_team", "away_team"
    )
    gt = pl.concat(
        [
            g.select("game_id", "season", pl.col("home_team").alias("team")),
            g.select("game_id", "season", pl.col("away_team").alias("team")),
        ]
    ).with_columns(pl.col("team").replace(TEAM_ALIASES).alias("franchise"))

    wanted = {m for _, m in MAP.values()}
    targets = sorted(gt["season"].unique().to_list())
    pri = pl.concat(
        [coaches.priors(rows.filter(pl.col("metric").is_in(wanted)), t) for t in targets]
    ).select("target", "person", "side", "metric", pl.col("prior_dev").alias("value"))

    changed = (
        pl.col("changed_midseason").fill_null(False)
        if "changed_midseason" in assign.columns
        else pl.lit(False)
    )
    parts = []
    for feature, (side, metric) in MAP.items():
        # A unit whose play-caller changed mid-season gets no prior for that season: the CSV names
        # the end-of-season person, so using him for earlier weeks would be look-ahead (review
        # 2026-10-28). Null -> league average downstream.
        who = assign.filter(pl.col("side") == side).select(
            pl.col("season").alias("season"),
            pl.col("team").alias("franchise"),
            pl.when(changed).then(None).otherwise(pl.col("person")).alias("person"),
        )
        p = pri.filter((pl.col("side") == side) & (pl.col("metric") == metric)).select(
            pl.col("target").alias("season"), "person", "value"
        )
        parts.append(
            gt.join(who, on=["season", "franchise"], how="left")
            .join(p, on=["season", "person"], how="left")
            .select("game_id", "team", pl.lit(feature).alias("feature"), "value")
        )
    return pl.concat(parts)


def build(paths: Paths, games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    rows = coaches.profile_rows(paths)
    values = compute(games, rows, coaches.assignments())
    return store.from_team_values(values, games, source=SOURCE, version=VERSION, build_ts=build_ts)
