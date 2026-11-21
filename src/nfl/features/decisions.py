"""Decisions family: play-calling aggressiveness and style, season-to-date.

Every value for a game uses only plays from games that kicked off strictly before it, in the same
season (postseason counts); week 1 equals the prior. Cumulative features follow strength.py:
shrunk mean = (sum_x + n0 * prior) / (n + n0).

  decisions.fourth_go_rate_oe  4th down, ydstogo <= 3, yardline_100 in [35, 65], play_type in
                               pass/run/punt/field_goal: team go rate (pass/run) minus the league
                               rate (same plays, season to date). Team rate shrunk to the league
                               rate with n0 = 10, i.e. (go - n * L) / (n + 10). 0 when no data yet.
  decisions.pass_rate_oe       mean nflfastR `pass_oe` (percentage points) on early downs (1-2,
                               pass/run, non-null), n0 = 150, prior 0.7 * team's previous season
                               + 0.3 * previous-season league mean (0 if none).
  decisions.early_down_pass_rate  tendencies off / early_down / pass_rate, as of the game's week.
  decisions.explosive_rate     (pass >= 20 yds + run >= 12 yds) / pass+run plays, n0 = 200, same
                               prior blend (default 0.09 with no previous season).
  decisions.turnover_margin_pg (takeaways - giveaways) per game on pass/run plays, shrunk toward 0
                               with n0 = 4 games. Giveaway = interception thrown + fumble lost by
                               the offense.
  decisions.one_score_luck     (wins in one-score games (|margin| <= 8) - 0.5 * one-score games) /
                               games played, season to date; ties count half a win. Unshrunk;
                               null before the team's first game of the season.
  decisions.penalty_yds_pg     penalty yards against (accepted, `penalty_team` = the team) per game,
                               shrunk with n0 = 4 games, same prior blend (default 55).
  decisions.pace               seconds of game clock between consecutive snaps of one drive (same
                               quarter, 0 < gap <= 60) when the snap is a pass/run in neutral
                               situations (wp 0.2-0.8, quarters 1-3), n0 = 150, same prior blend
                               (default 28).
  decisions.proe_leading       like pass_rate_oe but only plays with score_differential >= 7;
  decisions.proe_trailing      ... and <= -7. n0 = 100, same prior blend.
  decisions.hc_tenure          seasons the game's head coach (schedule `home_coach`/`away_coach`,
                               an empty name takes the team's previous game's coach) has led the
                               team without a break, including this season. Null for a coach whose
                               run starts in the first season of the games table (tenure unknown).
  decisions.hc_new             1 when hc_tenure is 1, else 0 (null when tenure is null).
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import polars as pl

from nfl.config import Paths
from nfl.features import store
from nfl.features.strength import TEAM_W, _canon, _prev_tables, team_games
from nfl.tendencies import rates_asof, weekly_aggregates

SOURCE = "pbp"
VERSION = "3"

N0_GO = 10.0
N0_OE = 150.0
N0_EXPLOSIVE = 200.0
N0_TURNOVER = 4.0
N0_PROE_SPLIT = 100.0
N0_PACE = 150.0
N0_PENALTY = 4.0
PACE_DEFAULT = 28.0
PENALTY_DEFAULT = 55.0
LEAD_MARGIN = 7
ONE_SCORE = 8.0
EXPLOSIVE_DEFAULT = 0.09
PASS_OE_DEFAULT = 0.0

TENDENCY_SPECS = [("decisions.early_down_pass_rate", "off", "early_down", "pass_rate")]

_STATS = """
select game_id, posteam as team,
  count(*) filter (where down = 4 and ydstogo <= 3 and yardline_100 between 35 and 65
                   and play_type in ('pass','run','punt','field_goal')) as go_n,
  count(*) filter (where down = 4 and ydstogo <= 3 and yardline_100 between 35 and 65
                   and play_type in ('pass','run')) as go_s,
  count(*) filter (where down in (1, 2) and play_type in ('pass','run')
                   and pass_oe is not null) as oe_n,
  coalesce(sum(cast(pass_oe as double)) filter (where down in (1, 2)
                   and play_type in ('pass','run') and pass_oe is not null), 0) as oe_s,
  count(*) filter (where down in (1, 2) and play_type in ('pass','run') and pass_oe is not null
                   and score_differential >= {lead}) as lead_n,
  coalesce(sum(cast(pass_oe as double)) filter (where down in (1, 2)
                   and play_type in ('pass','run') and pass_oe is not null
                   and score_differential >= {lead}), 0) as lead_s,
  count(*) filter (where down in (1, 2) and play_type in ('pass','run') and pass_oe is not null
                   and score_differential <= -{lead}) as trail_n,
  coalesce(sum(cast(pass_oe as double)) filter (where down in (1, 2)
                   and play_type in ('pass','run') and pass_oe is not null
                   and score_differential <= -{lead}), 0) as trail_s,
  count(*) filter (where play_type in ('pass','run')) as ex_n,
  count(*) filter (where (play_type = 'pass' and yards_gained >= 20)
                   or (play_type = 'run' and yards_gained >= 12)) as ex_s,
  coalesce(sum(coalesce(interception, 0) + coalesce(fumble_lost, 0))
           filter (where play_type in ('pass','run')), 0) as giveaways
from read_parquet('{glob}', hive_partitioning=true)
where season >= {min_season} and posteam is not null and defteam is not null
group by 1, 2
"""
_TAKEAWAYS = """
select game_id, defteam as team,
  coalesce(sum(coalesce(interception, 0) + coalesce(fumble_lost, 0))
           filter (where play_type in ('pass','run')), 0) as takeaways
from read_parquet('{glob}', hive_partitioning=true)
where season >= {min_season} and posteam is not null and defteam is not null
group by 1, 2
"""
_PENALTIES = """
select game_id, penalty_team as team,
  coalesce(sum(cast(penalty_yards as double)), 0) as pen_yds
from read_parquet('{glob}', hive_partitioning=true)
where season >= {min_season} and penalty = 1 and penalty_team is not null
group by 1, 2
"""
_PACE = """
with p as (
  select game_id, posteam as team, play_type, wp, qtr, game_seconds_remaining,
    lag(game_seconds_remaining) over (
      partition by game_id, posteam, drive, qtr order by play_id) as prev_secs
  from read_parquet('{glob}', hive_partitioning=true)
  where season >= {min_season} and posteam is not null and play_type is not null
)
select game_id, team, count(*) as pace_n, sum(prev_secs - game_seconds_remaining) as pace_s
from p
where play_type in ('pass','run') and wp between 0.2 and 0.8 and qtr <= 3
  and prev_secs - game_seconds_remaining > 0 and prev_secs - game_seconds_remaining <= 60
group by 1, 2
"""

STAT_COLS = [
    "go_n", "go_s", "oe_n", "oe_s", "lead_n", "lead_s", "trail_n", "trail_s", "ex_n", "ex_s",
    "giveaways", "takeaways", "pen_yds", "pace_n", "pace_s",
]  # fmt: skip


def load_game_stats(paths: Paths, min_season: int) -> pl.DataFrame:
    """One row per (game_id, team) with that team's offensive counts and takeaways."""
    con = duckdb.connect()
    glob = f"{paths.curated_table('plays').as_posix()}/*/*.parquet"
    kw = {"glob": glob, "min_season": min_season}
    out = con.sql(_STATS.format(**kw, lead=LEAD_MARGIN)).pl()
    for q in (_TAKEAWAYS, _PENALTIES, _PACE):
        out = out.join(
            con.sql(q.format(**kw)).pl(), on=["game_id", "team"], how="full", coalesce=True
        )
    return out.with_columns(
        pl.col(c).fill_null(0).cast(pl.Float64) for c in STAT_COLS
    ).with_columns(pl.lit(1.0).alias("played"))


def _cum_before(tg: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
    """Add `_c<col>`: the team's season-to-date sum of `col` over earlier games (tg is sorted)."""
    return tg.with_columns(
        (pl.col(c).cum_sum().over("team", "season") - pl.col(c)).alias(f"_c{c}") for c in cols
    )


def _prior_blend(tg: pl.DataFrame, s: str, n: str, default: float) -> tuple[pl.DataFrame, pl.Expr]:
    """tg with previous-season columns joined, and the prior expr: 0.7 * team's previous-season rate + 0.3 * previous-season league rate."""
    tot = (
        tg.group_by("ckey", "season")
        .agg(pl.col(s).sum().alias("_ts"), pl.col(n).sum().alias("_tn"))
        .filter(pl.col("_tn") > 0)
    )
    team_prev, league_prev = _prev_tables(tot, "_ts", "_tn")
    tg = tg.join(team_prev, on=["season", "ckey"], how="left").join(
        league_prev, on="season", how="left"
    )
    expr = (
        pl.when(pl.col("_tv").is_not_null() & pl.col("_lg").is_not_null())
        .then(TEAM_W * pl.col("_tv") + (1 - TEAM_W) * pl.col("_lg"))
        .when(pl.col("_lg").is_not_null())
        .then(pl.col("_lg"))
        .otherwise(pl.lit(default))
    )
    return tg, expr


def _shrunk_rate(tg: pl.DataFrame, feat: str, s: str, n: str, n0: float, default: float):
    tg, prior = _prior_blend(tg, s, n, default)
    return tg.with_columns(
        ((pl.col(f"_c{s}") + n0 * prior) / (pl.col(f"_c{n}") + n0)).alias(feat)
    ).drop("_tv", "_lg")


def _go_rate_oe(tg: pl.DataFrame) -> pl.DataFrame:
    """Team go rate minus league go rate, both season to date (kickoff strictly earlier for the
    league); the team rate is shrunk to the league rate: (go - n * L) / (n + n0)."""
    lg = (
        tg.group_by("season", "kickoff_utc")
        .agg(pl.col("go_s").sum().alias("_ls"), pl.col("go_n").sum().alias("_ln"))
        .sort("season", "kickoff_utc", nulls_last=True)
        .with_columns(
            (pl.col("_ls").cum_sum().over("season") - pl.col("_ls")).alias("_cls"),
            (pl.col("_ln").cum_sum().over("season") - pl.col("_ln")).alias("_cln"),
        )
        .select("season", "kickoff_utc", "_cls", "_cln")
    )
    L = pl.col("_cls") / pl.col("_cln")
    return (
        tg.join(lg, on=["season", "kickoff_utc"], how="left")
        .with_columns(
            pl.when(pl.col("_cln") > 0)
            .then((pl.col("_cgo_s") - pl.col("_cgo_n") * L) / (pl.col("_cgo_n") + N0_GO))
            .otherwise(0.0)
            .alias("decisions.fourth_go_rate_oe")
        )
        .drop("_cls", "_cln")
    )


def _coach_tenure(games: pl.DataFrame) -> pl.DataFrame:
    """(game_id, team, hc_tenure, hc_new): from the schedule's coach names, point in time because
    a game's coach is known before kickoff (a missing name takes the team's previous game's)."""
    rows = pl.concat(
        [
            games.select("game_id", "kickoff_utc", pl.col("season").cast(pl.Int64),
                         pl.col(f"{side}_team").alias("team"),
                         pl.col(f"{side}_coach").alias("coach"))
            for side in ("home", "away")
        ]
    )  # fmt: skip
    first = rows["season"].min()
    rows = (
        rows.with_columns(pl.col("coach").replace("", None))
        .with_columns(_canon().alias("ckey"))
        .sort("ckey", "kickoff_utc", "game_id", nulls_last=True)
        .with_columns(pl.col("coach").forward_fill().over("ckey"))
        .with_columns(
            (pl.col("coach") != pl.col("coach").shift(1).over("ckey"))
            .fill_null(True)
            .cum_sum()
            .over("ckey")
            .alias("_run")
        )
        .with_columns(pl.col("season").min().over("ckey", "_run").alias("_start"))
        .with_columns(
            pl.when(pl.col("coach").is_null() | (pl.col("_start") == first))
            .then(None)
            .otherwise(pl.col("season") - pl.col("_start") + 1)
            .cast(pl.Float64)
            .alias("decisions.hc_tenure")
        )
        .with_columns(
            pl.when(pl.col("decisions.hc_tenure").is_null())
            .then(None)
            .otherwise((pl.col("decisions.hc_tenure") == 1).cast(pl.Float64))
            .alias("decisions.hc_new")
        )
    )
    return rows.select("game_id", "team", "decisions.hc_tenure", "decisions.hc_new")


def compute(games: pl.DataFrame, stats: pl.DataFrame, weekly: pl.DataFrame) -> pl.DataFrame:
    """Long (game_id, team, feature, value) for every team-game in `games`."""
    cols = [*STAT_COLS, "played"]
    tg = (
        team_games(games)
        .with_columns(_canon().alias("ckey"))
        .join(stats.rename({"team": "ckey"}), on=["game_id", "ckey"], how="left")
        .with_columns(pl.col(c).fill_null(0.0) for c in cols)
        .with_columns(
            (pl.col("takeaways") - pl.col("giveaways")).alias("_margin"),
        )
        .sort("team", "season", "kickoff_utc", "game_id", nulls_last=True)
    )
    tg = _cum_before(tg, [*cols, "_margin"])
    tg = _go_rate_oe(tg)
    tg = _shrunk_rate(tg, "decisions.pass_rate_oe", "oe_s", "oe_n", N0_OE, PASS_OE_DEFAULT)
    tg = _shrunk_rate(
        tg, "decisions.explosive_rate", "ex_s", "ex_n", N0_EXPLOSIVE, EXPLOSIVE_DEFAULT
    )
    tg = tg.with_columns(
        (pl.col("_c_margin") / (pl.col("_cplayed") + N0_TURNOVER)).alias(
            "decisions.turnover_margin_pg"
        )
    )
    played = pl.col("margin").is_not_null()
    one = played & (pl.col("margin").abs() <= ONE_SCORE)
    win = (
        pl.when(pl.col("margin") > 0).then(1.0).when(pl.col("margin") == 0).then(0.5).otherwise(0.0)
    )
    tg = tg.with_columns(
        played.cast(pl.Float64).alias("_gp"),
        pl.when(one).then(win - 0.5).otherwise(0.0).alias("_os"),
    )
    tg = _cum_before(tg, ["_gp", "_os"])
    tg = tg.with_columns(
        pl.when(pl.col("_c_gp") > 0)
        .then(pl.col("_c_os") / pl.col("_c_gp"))
        .otherwise(None)
        .alias("decisions.one_score_luck")
    )
    tg = _shrunk_rate(tg, "decisions.proe_leading", "lead_s", "lead_n", N0_PROE_SPLIT, 0.0)
    tg = _shrunk_rate(tg, "decisions.proe_trailing", "trail_s", "trail_n", N0_PROE_SPLIT, 0.0)
    tg = _shrunk_rate(tg, "decisions.pace", "pace_s", "pace_n", N0_PACE, PACE_DEFAULT)
    tg = _shrunk_rate(
        tg, "decisions.penalty_yds_pg", "pen_yds", "played", N0_PENALTY, PENALTY_DEFAULT
    )
    feats = [
        "decisions.proe_leading",
        "decisions.proe_trailing",
        "decisions.pace",
        "decisions.penalty_yds_pg",
        "decisions.one_score_luck",
        "decisions.fourth_go_rate_oe",
        "decisions.pass_rate_oe",
        "decisions.explosive_rate",
        "decisions.turnover_margin_pg",
    ]
    if {"home_coach", "away_coach"} <= set(games.columns):
        tg = tg.join(_coach_tenure(games), on=["game_id", "team"], how="left")
        feats += ["decisions.hc_tenure", "decisions.hc_new"]
    long = tg.select("game_id", "team", *feats).unpivot(
        feats, index=["game_id", "team"], variable_name="feature", value_name="value"
    )
    tw = tg.join(games.select("game_id", "week"), on="game_id")
    tend = rates_asof(weekly, tw.select("season", "week", "team"), TENDENCY_SPECS)
    tend = tw.select("game_id", "season", "week", "team").join(
        tend, on=["season", "week", "team"], how="inner"
    ).select("game_id", "team", "feature", "value")  # fmt: skip
    return pl.concat([long, tend.select(long.columns)])


def build(paths: Paths, games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    seasons = sorted(int(s) for s in games["season"].unique().to_list())
    stats = load_game_stats(paths, seasons[0])
    weekly = weekly_aggregates(duckdb.connect(), paths, seasons, ["early_down"])
    values = compute(games, stats, weekly)
    return store.from_team_values(values, games, source=SOURCE, version=VERSION, build_ts=build_ts)
