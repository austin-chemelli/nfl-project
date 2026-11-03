"""League expectations for the game retrospective (M9.3, ADR 0016).

Output `marts/retro/expectations.json` (shape: `nfl.retro.schema.Expectations`), built from the
regular-season plays of a season window. All EPA values are "mean EPA of the good outcome minus
mean EPA of the bad one", reported as positive numbers (what the bad outcome cost).

Definitions (regular season only, `season_type = 'REG'`):
- Distance buckets (3rd and 4th down): `1` (ydstogo <= 1), `2-3`, `4-6`, `7-10`, `11+`.
- third_down: `down = 3` and `play_type in ('pass','run')` (no_play penalties, kneels, spikes,
  punts and FGs are out). Only plays flagged `third_down_converted` or `third_down_failed` count.
  v2: plays with an interception or a lost fumble, and aborted plays, are dropped from the
  attempts (the turnover factors price them; counting them here too would double count).
  rate = mean of `third_down_converted`; value = mean EPA converted - mean EPA failed.
- fourth_down: the same with `down = 4` and `fourth_down_converted`/`fourth_down_failed`
  (went for it).
- field_goal: `field_goal_attempt = 1`, buckets on `kick_distance`: `<30` (0-29), `30-34`, ...,
  `55-59`, `60+` (open). Made = `field_goal_result = 'made'`; value = mean EPA made - not made.
- extra_point_rate: `extra_point_attempt = 1`, share with `extra_point_result = 'good'`.
- fumble_lost_share: mean `fumble_lost` over plays with `fumble = 1`. v2: offensive pass/run
  plays with an EPA only, the plays the game retro counts. value_fumble_lost =
  mean EPA (fumble, not lost) - mean EPA (fumble, lost).
- value_interception: mean EPA of dropbacks without an interception - mean EPA of interceptions.
- value_penalty_yard: accepted penalties on `play_type = 'no_play'` with `penalty_yards > 0`; EPA
  from the penalized team's view (`epa` if `penalty_team = posteam` else `-epa`);
  value = -(sum of that EPA) / (sum of penalty_yards). Compared within the play (same team codes).
- special_teams_big_plays_pg: kick and punt return TDs (`special_teams_play = 1`; interception
  and fumble return TDs are left to the turnover factors), blocked punts and blocked FGs, per
  team-game for the benefiting team (count / (2 x games)). value_special_teams_big_play = mean |EPA| of those plays.
- played_like: per regular-season game with a result (ties out), each team's offensive
  `pass`/`run` plays without `interception` or lost fumble: EPA per play, d = home - away.
  Logistic (maximum likelihood, Newton) of home win on [1, d_epa]. Success rate is left out
  (`b_success = 0`): on 2015-2025 it correlates 0.74 with EPA and its coefficient turns negative
  once EPA is in (EPA alone +8.9, success alone +10.3, both +9.7 / -2.4), i.e. it adds noise.
"""

from __future__ import annotations

import json
import math

import duckdb
import numpy as np
import polars as pl

from nfl.config import Paths, now_utc
from nfl.retro.schema import Bucket, Expectations, PlayedLikeFit

VERSION = "retro_exp_v2"

DIST_BUCKETS: list[tuple[str, float, float | None]] = [
    ("1", 1, 1),
    ("2-3", 2, 3),
    ("4-6", 4, 6),
    ("7-10", 7, 10),
    ("11+", 11, None),
]
FG_BUCKETS: list[tuple[str, float, float | None]] = [
    ("<30", 0, 29),
    ("30-34", 30, 34),
    ("35-39", 35, 39),
    ("40-44", 40, 44),
    ("45-49", 45, 49),
    ("50-54", 50, 54),
    ("55-59", 55, 59),
    ("60+", 60, None),
]


def expectations_path(paths: Paths):
    return paths.marts / "retro" / "expectations.json"


def _plays(paths: Paths, seasons: tuple[int, int]) -> pl.DataFrame:
    glob = f"{paths.curated_table('plays').as_posix()}/*/*.parquet"
    return duckdb.sql(
        f"""
        select game_id, season, home_team, away_team, posteam, defteam, down, ydstogo, play_type,
               epa, success, interception, fumble, fumble_lost, qb_dropback, penalty,
               aborted_play, third_down_converted, third_down_failed, fourth_down_converted,
               fourth_down_failed, field_goal_attempt, field_goal_result, kick_distance,
               extra_point_attempt, extra_point_result, penalty_team, penalty_yards,
               return_touchdown, special_teams_play, punt_blocked
        from read_parquet('{glob}', hive_partitioning=true)
        where season_type = 'REG' and season between {int(seasons[0])} and {int(seasons[1])}
        """
    ).pl()


def _games(paths: Paths, seasons: tuple[int, int]) -> pl.DataFrame:
    glob = f"{paths.curated_table('games').as_posix()}/*/*.parquet"
    return duckdb.sql(
        f"""
        select game_id, home_score, away_score from read_parquet('{glob}', hive_partitioning=true)
        where game_type = 'REG' and season between {int(seasons[0])} and {int(seasons[1])}
          and home_score is not null and away_score is not null
        """
    ).pl()


def _in_bucket(col: pl.Expr, lo: float, hi: float | None) -> pl.Expr:
    e = col >= lo
    return e if hi is None else e & (col <= hi)


def _mean_epa(df: pl.DataFrame, cond: pl.Expr) -> float:
    v = df.filter(cond)["epa"].drop_nulls().mean()
    return float(v) if v is not None else float("nan")  # type: ignore[arg-type]


def _gap(df: pl.DataFrame, good: pl.Expr, bad: pl.Expr) -> float:
    """Mean EPA good minus bad; 0.0 when either side is empty (no NaN in the JSON)."""
    g = _mean_epa(df, good) - _mean_epa(df, bad)
    return 0.0 if math.isnan(g) else g


def _buckets(
    df: pl.DataFrame, col: str, spec: list[tuple[str, float, float | None]], good: pl.Expr,
    bad: pl.Expr,
) -> list[Bucket]:  # fmt: skip
    out = []
    for key, lo, hi in spec:
        cell = df.filter(_in_bucket(pl.col(col), lo, hi))
        n = cell.height
        out.append(
            Bucket(
                key=key,
                lo=float(lo),
                hi=None if hi is None else float(hi),
                rate=float(cell.select(good.cast(pl.Float64).mean()).item()) if n else 0.0,
                n=n,
                value=_gap(cell, good, bad),
            )
        )
    return out


def _down_buckets(plays: pl.DataFrame, down: int, conv: str, fail: str) -> list[Bucket]:
    df = plays.filter(
        (pl.col("down") == down)
        & pl.col("play_type").is_in(["pass", "run"])
        & (pl.col("interception").fill_null(0) != 1)
        & (pl.col("fumble_lost").fill_null(0) != 1)
        & (pl.col("aborted_play").fill_null(0) != 1)
        & ((pl.col(conv) == 1) | (pl.col(fail) == 1))
    )
    return _buckets(df, "ydstogo", DIST_BUCKETS, pl.col(conv) == 1, pl.col(fail) == 1)


def fit_logistic(x: np.ndarray, y: np.ndarray, iters: int = 50) -> np.ndarray:
    """Maximum-likelihood logistic regression by Newton steps (tiny ridge for stability)."""
    beta = np.zeros(x.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(x @ beta)))
        grad = x.T @ (y - p) - 1e-8 * beta
        hess = (x * (p * (1 - p))[:, None]).T @ x + 1e-8 * np.eye(x.shape[1])
        step = np.linalg.solve(hess, grad)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-10:
            break
    return beta


def _played_like(plays: pl.DataFrame, games: pl.DataFrame) -> PlayedLikeFit:
    off = plays.filter(
        pl.col("play_type").is_in(["pass", "run"])
        & pl.col("epa").is_not_null()
        & (pl.col("interception").fill_null(0) != 1)
        & (pl.col("fumble_lost").fill_null(0) != 1)
        & pl.col("posteam").is_not_null()
    )
    team = off.group_by("game_id", "posteam").agg(
        pl.col("epa").mean().alias("epa"),
        pl.col("success").mean().alias("succ"),
        pl.col("home_team").first().alias("home_team"),
    )
    home = team.filter(pl.col("posteam") == pl.col("home_team")).select(
        "game_id", pl.col("epa").alias("h_epa"), pl.col("succ").alias("h_succ")
    )
    away = team.filter(pl.col("posteam") != pl.col("home_team")).select(
        "game_id", pl.col("epa").alias("a_epa"), pl.col("succ").alias("a_succ")
    )
    df = (
        home.join(away, on="game_id")
        .join(games.filter(pl.col("home_score") != pl.col("away_score")), on="game_id")
        .drop_nulls()
    )
    d_epa = (df["h_epa"] - df["a_epa"]).to_numpy()
    y = (df["home_score"] > df["away_score"]).cast(pl.Float64).to_numpy()
    b = fit_logistic(np.column_stack([np.ones(len(y)), d_epa]), y)
    return PlayedLikeFit(intercept=float(b[0]), b_epa=float(b[1]), b_success=0.0, n=len(y))


def build(paths: Paths, seasons: tuple[int, int] = (2015, 2025)) -> Expectations:
    plays = _plays(paths, seasons)
    games = _games(paths, seasons)

    # field goals
    fg = plays.filter(
        (pl.col("field_goal_attempt") == 1)
        & pl.col("kick_distance").is_not_null()
        & (pl.col("field_goal_result").fill_null("") != "blocked")
    )
    made = pl.col("field_goal_result") == "made"
    fg_buckets = _buckets(fg, "kick_distance", FG_BUCKETS, made, ~made)

    # extra points
    xp = plays.filter(pl.col("extra_point_attempt") == 1)
    xp_rate = float((xp["extra_point_result"] == "good").mean())  # type: ignore[arg-type]

    # fumbles
    fum = plays.filter(
        (pl.col("fumble") == 1)
        & pl.col("play_type").is_in(["pass", "run"])
        & pl.col("epa").is_not_null()
        & pl.col("posteam").is_not_null()
    )
    lost = pl.col("fumble_lost") == 1
    fumble_share = float(fum["fumble_lost"].fill_null(0).mean())  # type: ignore[arg-type]
    value_fumble = _mean_epa(fum, ~lost) - _mean_epa(fum, lost)

    # interceptions
    db = plays.filter(pl.col("qb_dropback") == 1)
    ints = pl.col("interception") == 1
    value_int = _mean_epa(db, ~ints) - _mean_epa(db, ints)

    # penalties: EPA from the penalized team's view per penalty yard
    pen = plays.filter(
        (pl.col("penalty") == 1)
        & (pl.col("play_type") == "no_play")
        & (pl.col("penalty_yards") > 0)
        & pl.col("epa").is_not_null()
        & pl.col("penalty_team").is_not_null()
    )
    pen_epa = (
        pl.when(pl.col("penalty_team") == pl.col("posteam"))
        .then(pl.col("epa"))
        .otherwise(-pl.col("epa"))
    )
    value_pen = -float(pen.select(pen_epa.sum()).item()) / float(pen["penalty_yards"].sum())

    # special-teams big plays
    st = plays.filter(
        ((pl.col("return_touchdown") == 1) & (pl.col("special_teams_play") == 1))
        | (pl.col("punt_blocked") == 1)
        | (pl.col("field_goal_result") == "blocked")
    )
    n_games = plays["game_id"].n_unique()
    st_pg = st.height / (2 * n_games) if n_games else 0.0
    st_val = float(st["epa"].drop_nulls().abs().mean() or 0.0)  # type: ignore[arg-type]

    return Expectations(
        version=VERSION,
        built_at=now_utc().isoformat(),
        seasons=seasons,
        third_down=_down_buckets(plays, 3, "third_down_converted", "third_down_failed"),
        fourth_down=_down_buckets(plays, 4, "fourth_down_converted", "fourth_down_failed"),
        field_goal=fg_buckets,
        extra_point_rate=xp_rate,
        extra_point_n=xp.height,
        fumble_lost_share=fumble_share,
        fumble_n=fum.height,
        value_fumble_lost=value_fumble,
        value_interception=value_int,
        value_penalty_yard=value_pen,
        special_teams_big_plays_pg=st_pg,
        value_special_teams_big_play=st_val,
        played_like=_played_like(plays, games),
    )


def write(paths: Paths, exp: Expectations):
    out = expectations_path(paths)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(exp.model_dump(mode="json"), indent=1) + "\n")
    return out


def load(paths: Paths) -> Expectations:
    return Expectations.model_validate_json(expectations_path(paths).read_text())
