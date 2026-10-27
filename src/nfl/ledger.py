"""Paper ledger: odds-weighted bets, settlement, closing-line value (ADR 0006).

open      For every (model, game), at the model's last lock before kickoff: if |model p − vig-free
          market p| > EDGE_THRESHOLD, 1 unit on the moneyline of the side the model likes more than
          the market. Otherwise, if |model spread − market spread| ≥ SPREAD_THRESHOLD, 1 unit on that
          side of the spread. Market numbers at the lock: the latest Odds API consensus snapshot at
          or before lock_ts (live rows), or nflverse's schedule line (backfill rows).
          marts/bets.parquet: live bets are immutable (first one per model × game wins forever);
          backfill bets are derived and rebuilt on every run.
settle    Derived each run into marts/bets_settled.parquet: result, units, closing line, CLV.
          Closing line: our latest snapshot within CLOSE_WINDOW before kickoff, else nflverse's
          schedule line (the historical endpoint is paid-only). CLV is movement toward the bet:
          moneyline in vig-free probability points, spread in points. Null when bet and close are
          the same nflverse number (all backfill bets), since that is zero by construction.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

import polars as pl

from nfl import odds
from nfl.config import Paths
from nfl.features.market import _implied_expr
from nfl.features.store import games_frame
from nfl.predict import existing

EDGE_THRESHOLD = 0.05
SPREAD_THRESHOLD = 1.5
CLOSE_WINDOW = timedelta(hours=3)
STAKE = 1.0
NO_BET_MODELS = {"market_baseline"}

BET_SCHEMA = {
    "bet_id": pl.Utf8,
    "model_id": pl.Utf8,
    "game_id": pl.Utf8,
    "season": pl.Int64,
    "week": pl.Int64,
    "lock_ts": pl.Datetime("us"),
    "is_backfill": pl.Boolean,
    "market": pl.Utf8,  # 'h2h' | 'spreads'
    "side": pl.Utf8,  # 'home' | 'away'
    "price_american": pl.Float64,
    "point": pl.Float64,  # spreads: book convention for the bet side (−3.5 = laying 3.5)
    "model_p": pl.Float64,  # model's win probability for the bet side
    "market_p_vigfree": pl.Float64,  # market's, at the lock
    "edge": pl.Float64,
    "stake_units": pl.Float64,
    "line_source": pl.Utf8,  # 'odds_api' | 'nflverse'
    "line_snapshot_ts": pl.Datetime("us"),
}


def _vigfree(home_ml: str, away_ml: str) -> pl.Expr:
    ph, pa = _implied_expr(home_ml), _implied_expr(away_ml)
    return ph / (ph + pa)


def _schedule_market(games: pl.DataFrame) -> pl.DataFrame:
    """nflverse's line per game in the consensus shape (spread_home: + = home favored)."""
    return games.select(
        "game_id",
        pl.col("home_moneyline").cast(pl.Float64).alias("home_ml"),
        pl.col("away_moneyline").cast(pl.Float64).alias("away_ml"),
        pl.col("spread_line").cast(pl.Float64).alias("spread_home"),
        pl.col("home_spread_odds").cast(pl.Float64).alias("home_spread_price"),
        pl.col("away_spread_odds").cast(pl.Float64).alias("away_spread_price"),
    ).with_columns(_vigfree("home_ml", "away_ml").alias("p_home_vigfree"))


def _bet_candidates(paths: Paths, games: pl.DataFrame) -> pl.DataFrame:
    """Last lock before kickoff per (model, game, is_backfill), with the market at that lock."""
    # the model's spread is renamed so it never collides with the market's `spread_home`
    preds = (
        existing(paths)
        .filter(~pl.col("model_id").is_in(sorted(NO_BET_MODELS)))
        .rename({"spread_home": "spread_home_pred"})
        .drop("total")
    )
    kick = games.select(
        "game_id", pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us"))
    )
    p = (
        preds.join(kick, on="game_id")
        .filter(pl.col("lock_ts") < pl.col("kickoff_utc"))
        .sort("lock_ts")
        .group_by("game_id", "model_id", "is_backfill")
        .last()
    )
    sched = _schedule_market(games)
    back = (
        p.filter(pl.col("is_backfill"))
        .join(sched, on="game_id", how="inner")
        .with_columns(
            pl.lit("nflverse").alias("line_source"),
            pl.lit(None, dtype=pl.Datetime("us")).alias("line_snapshot_ts"),
        )
    )
    live = p.filter(~pl.col("is_backfill"))
    lines = odds.read_lines(paths)
    if live.is_empty() or lines.is_empty():
        return back
    cons = odds.consensus(lines).sort("snapshot_ts")
    live = (
        live.sort("lock_ts")
        .join_asof(
            cons.rename({"snapshot_ts": "line_snapshot_ts"}),
            left_on="lock_ts",
            right_on="line_snapshot_ts",
            by="game_id",
            strategy="backward",
            check_sortedness=False,
        )
        .filter(pl.col("line_snapshot_ts").is_not_null())
        .with_columns(pl.lit("odds_api").alias("line_source"))
    )
    return pl.concat([back, live.select(back.columns)], how="vertical_relaxed")


def decide(c: pl.DataFrame) -> pl.DataFrame:
    """Candidates -> bets (BET_SCHEMA). Pure: unit-testable without data."""
    edge = pl.col("p_home") - pl.col("p_home_vigfree")
    ml = c.filter(edge.abs() > EDGE_THRESHOLD).with_columns(
        pl.lit("h2h").alias("market"),
        pl.when(edge > 0).then(pl.lit("home")).otherwise(pl.lit("away")).alias("side"),
    )
    ml = ml.with_columns(
        pl.when(pl.col("side") == "home")
        .then("home_ml")
        .otherwise("away_ml")
        .alias("price_american"),
        pl.lit(None, dtype=pl.Float64).alias("point"),
    )
    sdiff = pl.col("spread_home_pred") - pl.col("spread_home")
    sp = (
        c.filter(
            (edge.abs() <= EDGE_THRESHOLD)
            & pl.col("spread_home").is_not_null()
            & (sdiff.abs() >= SPREAD_THRESHOLD)
        )
        .with_columns(
            pl.lit("spreads").alias("market"),
            pl.when(sdiff > 0).then(pl.lit("home")).otherwise(pl.lit("away")).alias("side"),
        )
        .with_columns(
            pl.when(pl.col("side") == "home")
            .then("home_spread_price")
            .otherwise("away_spread_price")
            .fill_null(-110.0)
            .alias("price_american"),
            # book convention: home point = −spread_home; away point = +spread_home
            pl.when(pl.col("side") == "home")
            .then(-pl.col("spread_home"))
            .otherwise(pl.col("spread_home"))
            .alias("point"),
        )
    )
    both = pl.concat([ml, sp.select(ml.columns)], how="vertical_relaxed").filter(
        pl.col("price_american").is_not_null() & pl.col("p_home_vigfree").is_not_null()
    )
    home = pl.col("side") == "home"
    out = both.with_columns(
        pl.when(home).then("p_home").otherwise(1 - pl.col("p_home")).alias("model_p"),
        pl.when(home)
        .then("p_home_vigfree")
        .otherwise(1 - pl.col("p_home_vigfree"))
        .alias("market_p_vigfree"),
        pl.lit(STAKE).alias("stake_units"),
    ).with_columns((pl.col("model_p") - pl.col("market_p_vigfree")).alias("edge"))
    ids = [
        hashlib.sha1(f"{m}|{g}|{t}|{k}".encode()).hexdigest()[:16]
        for m, g, t, k in out.select("model_id", "game_id", "lock_ts", "market").iter_rows()
    ]
    return (
        out.with_columns(pl.Series("bet_id", ids, dtype=pl.Utf8))
        .select(list(BET_SCHEMA))
        .cast(BET_SCHEMA)
    )


def load_bets(paths: Paths) -> pl.DataFrame:
    f = paths.marts / "bets.parquet"
    return pl.read_parquet(f).cast(BET_SCHEMA) if f.exists() else pl.DataFrame(schema=BET_SCHEMA)


def open_bets(paths: Paths) -> tuple[int, int]:
    """Returns (live bets added, backfill bets written)."""
    games = games_frame(paths)
    new = decide(_bet_candidates(paths, games))
    prev = load_bets(paths)
    live_prev = prev.filter(~pl.col("is_backfill"))
    have = live_prev.select("model_id", "game_id").unique()
    live_new = new.filter(~pl.col("is_backfill")).join(have, on=["model_id", "game_id"], how="anti")
    backfill = new.filter(pl.col("is_backfill"))
    out = pl.concat([live_prev, live_new, backfill]).sort("lock_ts", "model_id", "game_id")
    paths.marts.mkdir(parents=True, exist_ok=True)
    out.write_parquet(paths.marts / "bets.parquet")
    return live_new.height, backfill.height


def _closing(paths: Paths, games: pl.DataFrame) -> pl.DataFrame:
    """Closing market per game: our last snapshot within CLOSE_WINDOW before kickoff, else nflverse."""
    sched = _schedule_market(games).with_columns(pl.lit("nflverse").alias("closing_source"))
    lines = odds.read_lines(paths)
    if lines.is_empty():
        return sched
    kick = games.select(
        "game_id", pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us"))
    )
    own = (
        odds.consensus(lines)
        .join(kick, on="game_id")
        .filter(
            (pl.col("snapshot_ts") < pl.col("kickoff_utc"))
            & (pl.col("snapshot_ts") >= pl.col("kickoff_utc") - CLOSE_WINDOW)
        )
        .sort("snapshot_ts")
        .group_by("game_id")
        .last()
        .with_columns(pl.lit("odds_api").alias("closing_source"))
        .select(sched.columns)
    )
    return pl.concat([own, sched.join(own.select("game_id"), on="game_id", how="anti")])


def settle(paths: Paths) -> pl.DataFrame:
    bets = load_bets(paths)
    games = games_frame(paths)
    close = _closing(paths, games)
    df = bets.join(games.select("game_id", "result"), on="game_id", how="left").join(
        close, on="game_id", how="left"
    )
    out = settle_frame(df)
    out.write_parquet(paths.marts / "bets_settled.parquet")
    return out


def settle_frame(df: pl.DataFrame) -> pl.DataFrame:
    """Pure settlement. df: BET_SCHEMA + result + closing market columns (home_ml, away_ml,
    spread_home, p_home_vigfree, closing_source)."""
    home = pl.col("side") == "home"
    margin = pl.when(home).then(pl.col("result")).otherwise(-pl.col("result"))  # bet side's margin
    ml_score = margin
    sp_score = margin + pl.col("point")
    score = pl.when(pl.col("market") == "h2h").then(ml_score).otherwise(sp_score)
    result = (
        pl.when(pl.col("result").is_null())
        .then(None)
        .when(score > 0)
        .then(pl.lit("win"))
        .when(score < 0)
        .then(pl.lit("loss"))
        .otherwise(pl.lit("push"))
    )
    price = pl.col("price_american")
    win_units = pl.when(price > 0).then(price / 100).otherwise(100 / -price) * pl.col("stake_units")
    units = (
        pl.when(result == "win")
        .then(win_units)
        .when(result == "loss")
        .then(-pl.col("stake_units"))
        .when(result == "push")
        .then(0.0)
    )
    close_p_side = pl.when(home).then("p_home_vigfree").otherwise(1 - pl.col("p_home_vigfree"))
    close_point_side = pl.when(home).then(-pl.col("spread_home")).otherwise(pl.col("spread_home"))
    same_number = (pl.col("line_source") == "nflverse") & (pl.col("closing_source") == "nflverse")
    clv = (
        pl.when(same_number)
        .then(None)
        .when(pl.col("market") == "h2h")
        .then(close_p_side - pl.col("market_p_vigfree"))
        .otherwise(pl.col("point") - close_point_side)
    )
    return df.with_columns(
        result.alias("result_bet"),
        units.alias("units_net"),
        close_p_side.alias("closing_p_vigfree"),
        pl.when(pl.col("market") == "spreads").then(close_point_side).alias("closing_point"),
        clv.alias("clv"),
    ).select(
        *BET_SCHEMA,
        pl.col("result_bet").alias("result"),
        "units_net",
        "closing_source",
        "closing_p_vigfree",
        "closing_point",
        "clv",
    )


def summary(settled: pl.DataFrame) -> pl.DataFrame:
    """Per (model, is_backfill, season): bets, record, units, ROI, mean edge, mean CLV."""
    done = settled.filter(pl.col("result").is_not_null())
    return (
        done.group_by("model_id", "is_backfill", "season", "market")
        .agg(
            pl.len().alias("bets"),
            (pl.col("result") == "win").sum().alias("wins"),
            (pl.col("result") == "loss").sum().alias("losses"),
            (pl.col("result") == "push").sum().alias("pushes"),
            pl.col("units_net").sum().alias("units"),
            (pl.col("units_net").sum() / pl.col("stake_units").sum()).alias("roi"),
            pl.col("edge").mean().alias("mean_edge"),
            pl.col("clv").mean().alias("mean_clv"),
            pl.col("clv").count().alias("n_clv"),
        )
        .sort("model_id", "is_backfill", "season", "market")
    )
