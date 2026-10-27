"""Market features: vig-free home win probability and the posted lines. Game-level (side='game').

Two sources:
- nflverse schedules (`games`): one untimestamped, closing-ish line per game. Used for completed
  games (stamped kickoff − 2h, the backtest rule) and for upcoming games with no odds snapshot yet.
- The Odds API (`curated/lines`, M3): every snapshot strictly before kickoff becomes rows stamped
  with the snapshot time (known_as_of = snapshot_ts), source 'odds_api', consensus across books.
  Upcoming games with any snapshot use only these, so a lock sees the line as of its snapshot.
  `market.line_move_pts` = consensus home spread now minus at the game's first snapshot.

Convention: spread_line > 0 means the home team is favored.
"""

from __future__ import annotations

from datetime import datetime
from math import erf, sqrt

import polars as pl

from nfl.config import Paths
from nfl.features import store
from nfl.models.market import norm_cdf

SOURCE = "schedules"
VERSION = "1"
SPREAD_SD = 13.5  # same margin SD as nfl.models.market.SD_MARGIN


def american_to_implied(odds: float) -> float:
    """American odds -> raw implied probability (includes vig). -150 -> 0.6, +130 -> 100/230."""
    return -odds / (-odds + 100.0) if odds < 0 else 100.0 / (odds + 100.0)


def vigfree_home(home_ml: float | None, away_ml: float | None) -> float | None:
    """Multiplicative vig removal: p_h / (p_h + p_a). None if either price is missing or zero."""
    if not home_ml or not away_ml:
        return None
    ph, pa = american_to_implied(home_ml), american_to_implied(away_ml)
    return ph / (ph + pa)


def _implied_expr(col: str) -> pl.Expr:
    o = pl.col(col).cast(pl.Float64)
    return (
        pl.when(o == 0)
        .then(None)
        .when(o < 0)
        .then(-o / (-o + 100.0))
        .otherwise(100.0 / (o + 100.0))
    )


def _p_ml_expr() -> pl.Expr:
    ph, pa = _implied_expr("home_moneyline"), _implied_expr("away_moneyline")
    return ph / (ph + pa)


def _p_spread_expr() -> pl.Expr:
    # Phi(spread / SD); polars has no erf, so evaluate elementwise
    return (
        pl.col("spread_line")
        .cast(pl.Float64)
        .map_elements(
            lambda s: 0.5 * (1.0 + erf(s / SPREAD_SD / sqrt(2.0))), return_dtype=pl.Float64
        )
    )


def _p_home(games: pl.DataFrame) -> pl.DataFrame:
    """(game_id, p, from_ml) per game; p null when neither moneylines nor spread exist."""
    return games.select(
        "game_id",
        pl.coalesce(_p_ml_expr(), _p_spread_expr()).alias("p"),
        _p_ml_expr().is_not_null().alias("from_ml"),
    )


def coverage(games: pl.DataFrame) -> dict:
    """Counts of games by p_home source: moneyline, spread fallback, none. Report-only helper."""
    p = _p_home(games).with_columns(games["season"])
    fallback = p.filter(~pl.col("from_ml") & pl.col("p").is_not_null())
    return {
        "games": p.height,
        "moneyline": int(p["from_ml"].sum()),
        "spread_fallback": fallback.height,
        "none": int(p["p"].null_count()),
        "fallback_by_season": dict(sorted(fallback.group_by("season").len().iter_rows())),
    }


def live_values(paths: Paths, games: pl.DataFrame) -> pl.DataFrame:
    """(game_id, feature, value, known_as_of) from Odds API snapshots strictly before kickoff."""
    from nfl import odds

    lines = odds.read_lines(paths)
    if lines.is_empty():
        return pl.DataFrame(
            schema={"game_id": pl.Utf8, "feature": pl.Utf8, "value": pl.Float64,
                    "known_as_of": pl.Datetime("us")}
        )  # fmt: skip
    kick = games.select(
        "game_id", pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us"))
    )
    c = (
        odds.consensus(lines)
        .join(kick, on="game_id")
        .filter(pl.col("snapshot_ts") < pl.col("kickoff_utc"))
        .sort("game_id", "snapshot_ts")
        .with_columns(
            (pl.col("spread_home") - pl.col("spread_home").first().over("game_id")).alias("move")
        )
    )
    wide = c.select(
        "game_id",
        pl.col("snapshot_ts").alias("known_as_of"),
        pl.col("p_home_vigfree").alias("market.p_home_vigfree"),
        pl.col("spread_home").alias("market.spread_line"),
        pl.col("total").alias("market.total_line"),
        pl.col("move").alias("market.line_move_pts"),
    )
    return wide.unpivot(
        index=["game_id", "known_as_of"], variable_name="feature", value_name="value"
    )


def build(paths: Paths, games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    live = live_values(paths, games)
    build_naive = build_ts.replace(tzinfo=None)
    upcoming_with_odds = set(
        games.filter(
            pl.col("game_id").is_in(live["game_id"].unique().to_list())
            & (pl.col("kickoff_utc").dt.replace_time_zone(None) >= build_naive)
        )["game_id"].to_list()
    )
    out = [
        _schedule_rows(games.filter(~pl.col("game_id").is_in(sorted(upcoming_with_odds))), build_ts)
    ]
    if not live.is_empty():
        out.append(
            store.from_game_values(
                live, games, source="odds_api", version=VERSION, build_ts=build_ts
            )
        )
    return pl.concat(out)


def _schedule_rows(games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    p = _p_home(games).select("game_id", pl.col("p").alias("market.p_home_vigfree"))
    vals = games.select(
        "game_id",
        pl.col("spread_line").cast(pl.Float64).alias("market.spread_line"),
        pl.col("total_line").cast(pl.Float64).alias("market.total_line"),
    ).join(p, on="game_id")
    long = vals.unpivot(index="game_id", variable_name="feature", value_name="value")
    return store.from_game_values(long, games, source=SOURCE, version=VERSION, build_ts=build_ts)


__all__ = [
    "SOURCE",
    "VERSION",
    "american_to_implied",
    "build",
    "coverage",
    "norm_cdf",
    "vigfree_home",
]
