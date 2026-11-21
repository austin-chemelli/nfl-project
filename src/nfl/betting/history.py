"""The betting study's base table: one row per game side with the price, the market's vig-free
chance, every approach's chance and the result (ADR 0033).

Prices are nflverse's schedule lines (untimestamped, roughly closing). Model chances are the
walk-forward backfill rows (fits used in season S are trained through S-1, ADR 0005), the last
one before kickoff, so every number here was knowable before the game.
"""

from __future__ import annotations

import polars as pl

from nfl.config import Paths
from nfl.features.market import _implied_expr
from nfl.features.store import games_frame
from nfl.predict import existing

APPROACHES = ("traditionalist", "analyst", "sharp", "student")
FIRST_SEASON = 2006  # moneylines start in 2006 (partial to 2009, full from 2010)


def model_probs(paths: Paths, models: tuple[str, ...], backfill: bool = True) -> pl.DataFrame:
    """game_id × each model's home win chance (`p_<model>`) and home spread (`s_<model>`), from
    the last row before kickoff."""
    games = games_frame(paths).select(
        "game_id", pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us"))
    )
    p = (
        existing(paths)
        .filter(pl.col("model_id").is_in(list(models)) & (pl.col("is_backfill") == backfill))
        .join(games, on="game_id")
        .filter(pl.col("lock_ts") < pl.col("kickoff_utc"))
        .sort("lock_ts")
        .group_by("game_id", "model_id")
        .last()
    )
    wide = p.pivot(on="model_id", index="game_id", values=["p_home", "spread_home"])
    ren = {}
    for m in models:
        for src, dst in ((f"p_home_{m}", f"p_{m}"), (f"spread_home_{m}", f"s_{m}")):
            if src in wide.columns:
                ren[src] = dst
        if len(models) == 1:
            ren |= {"p_home": f"p_{m}", "spread_home": f"s_{m}"}
    return wide.rename({k: v for k, v in ren.items() if k in wide.columns})


def model_versions(paths: Paths, models: tuple[str, ...]) -> dict[str, str]:
    """The model_version of each model's latest backfill row: printed with every study result."""
    p = existing(paths).filter(pl.col("model_id").is_in(list(models)) & pl.col("is_backfill"))
    return dict(
        p.sort("lock_ts").group_by("model_id").agg(pl.col("model_version").last()).iter_rows()
    )


def game_table(paths: Paths, models: tuple[str, ...] = APPROACHES) -> pl.DataFrame:
    """One row per finished game from FIRST_SEASON with any line: prices, vig-free market chance,
    model chances, scores, weather. Regular season and playoffs."""
    g = games_frame(paths).filter(
        (pl.col("season") >= FIRST_SEASON)
        & pl.col("result").is_not_null()
        & pl.col("spread_line").is_not_null()
    )
    ph, pa = _implied_expr("home_moneyline"), _implied_expr("away_moneyline")
    g = g.with_columns((ph / (ph + pa)).alias("p_mkt"), (ph + pa - 1).alias("overround"))
    probs = model_probs(paths, models)
    return g.join(probs, on="game_id", how="left").sort("kickoff_utc", "game_id")


def sides(games: pl.DataFrame, models: tuple[str, ...] = APPROACHES) -> pl.DataFrame:
    """Two rows per game with a moneyline: each side as a bet, in the side's own terms.

    price: the side's American moneyline. p_mkt: its vig-free chance. p_<model>: each model's
    chance for that side. won: 1/0 (ties are 0.5 and settle as a push). fav: the market favorite.
    """
    ml = games.filter(
        pl.col("home_moneyline").is_not_null() & pl.col("away_moneyline").is_not_null()
    )
    keep = ["game_id", "season", "week", "game_type", "kickoff_utc", "result", "spread_line"]
    out = []
    for side, sign in (("home", 1), ("away", -1)):
        cols = [
            *[pl.col(c) for c in keep],
            pl.lit(side).alias("side"),
            pl.col(f"{side}_team").alias("team"),
            pl.col("away_team" if side == "home" else "home_team").alias("opp"),
            pl.col(f"{side}_moneyline").cast(pl.Float64).alias("price"),
            (pl.col("p_mkt") if sign == 1 else 1 - pl.col("p_mkt")).alias("p_mkt"),
            (
                pl.when(pl.col("result") * sign > 0)
                .then(1.0)
                .when(pl.col("result") == 0)
                .then(0.5)
                .otherwise(0.0)
            ).alias("won"),
        ]
        for m in models:
            if f"p_{m}" in games.columns:
                cols.append(
                    (pl.col(f"p_{m}") if sign == 1 else 1 - pl.col(f"p_{m}")).alias(f"p_{m}")
                )
        out.append(ml.select(cols))
    s = pl.concat(out).with_columns(
        (pl.col("p_mkt") > 0.5).alias("fav"),
        pl.when(pl.col("price") > 0)
        .then(pl.col("price") / 100)
        .otherwise(100 / -pl.col("price"))
        .alias("win_units"),
    )
    return s.with_columns(profit_expr().alias("profit"))


def profit_expr(won: str = "won", win_units: str = "win_units") -> pl.Expr:
    """Profit on 1 unit: a win pays win_units, a loss costs 1, a tie (0.5) pushes."""
    w = pl.col(won)
    return pl.when(w == 1).then(pl.col(win_units)).when(w == 0).then(-1.0).otherwise(0.0)
