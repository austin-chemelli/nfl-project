"""Grade predictions against results, build the scorecard, and export site JSON.

For each (game, model) the graded prediction is the last lock before kickoff. Metrics per
season/week/model: log loss, Brier, ECE, spread MAE, ATS record vs. the market line (ADR 0006).
Also written: reliability bins, a per-model summary with season-bootstrap CIs vs. the market, and
divergence buckets (when a model disagreed with the vig-free market by X points, who was right).
"""

from __future__ import annotations

import json

import numpy as np
import polars as pl
from rich.console import Console
from rich.table import Table

from nfl.config import Paths
from nfl.predict import load_games

EPS = 1e-6
N_BINS = 10
DIVERGENCE_BUCKETS = [
    0.0,
    0.025,
    0.05,
    0.10,
]  # |model p - market p|; labels 0-2.5, 2.5-5, 5-10, 10+
BOOTSTRAP = 500
MARKET_ID = "market_baseline"


def _market_p(paths: Paths) -> pl.DataFrame:
    """Vig-free market home probability per game (moneylines, spread fallback)."""
    from nfl.features import market as market_features
    from nfl.features.store import games_frame

    g = games_frame(paths)
    return market_features._p_home(g).select("game_id", pl.col("p").alias("market_p"))


def graded_frame(paths: Paths) -> pl.DataFrame:
    preds = pl.read_parquet(paths.marts / "predictions.parquet")
    games = load_games(paths).select(
        "game_id",
        "kickoff_utc",
        "result",
        "total",
        "spread_line",
        "total_line",
        "home_team",
        "away_team",
    )
    df = preds.join(games, on="game_id", how="inner").join(
        _market_p(paths), on="game_id", how="left"
    )
    # latest lock strictly before kickoff (or any lock if kickoff unknown)
    df = df.filter(pl.col("kickoff_utc").is_null() | (pl.col("lock_ts") < pl.col("kickoff_utc")))
    df = df.sort("lock_ts").group_by(["game_id", "model_id"]).last()
    played = df.filter(pl.col("result").is_not_null() & (pl.col("result") != 0))
    home_win = (pl.col("result") > 0).cast(pl.Float64)
    p = pl.col("p_home").clip(EPS, 1 - EPS)
    ats_pick_home = pl.col("spread_home") > pl.col(
        "spread_line"
    )  # model likes home more than market does
    cover_home = pl.col("result") > pl.col("spread_line")
    push = pl.col("result") == pl.col("spread_line")
    return played.with_columns(
        home_win.alias("home_win"),
        (-(home_win * p.log() + (1 - home_win) * (1 - p).log())).alias("log_loss"),
        ((p - home_win) ** 2).alias("brier"),
        (pl.col("spread_home") - pl.col("result")).abs().alias("spread_abs_err"),
        pl.when(
            pl.col("spread_line").is_null()
            | push
            | (pl.col("spread_home") == pl.col("spread_line"))
        )
        .then(None)  # no line, push, or no disagreement with the market => no ATS pick
        .otherwise((ats_pick_home == cover_home).cast(pl.Float64))
        .alias("ats_win"),
    )


def scorecard(graded: pl.DataFrame) -> pl.DataFrame:
    aggs = [
        pl.len().alias("n_games"),
        pl.col("log_loss").mean(),
        pl.col("brier").mean(),
        pl.col("spread_abs_err").mean().alias("spread_mae"),
        pl.col("ats_win").mean().alias("ats_pct"),
        pl.col("ats_win").count().alias("n_ats"),
    ]
    weekly = (
        graded.group_by(["season", "week", "model_id"])
        .agg(aggs)
        .with_columns(pl.lit("week").alias("scope"))
    )
    season = (
        graded.group_by(["season", "model_id"])
        .agg(aggs)
        .with_columns(pl.lit(None, pl.Int64).alias("week"), pl.lit("season").alias("scope"))
    )
    return pl.concat([weekly, season.select(weekly.columns)]).sort(
        ["season", "week", "model_id"], nulls_last=True
    )


def reliability(graded: pl.DataFrame) -> pl.DataFrame:
    """Per (season, model, bin): n, mean predicted p, observed home-win rate."""
    return (
        graded.with_columns((pl.col("p_home") * N_BINS).floor().clip(0, N_BINS - 1).alias("bin"))
        .group_by(["season", "model_id", "bin"])
        .agg(
            pl.len().alias("n"),
            pl.col("p_home").mean().alias("mean_p"),
            pl.col("home_win").mean().alias("hit_rate"),
        )
        .sort(["season", "model_id", "bin"])
    )


def ece(rel: pl.DataFrame, keys: list[str]) -> pl.DataFrame:
    """Expected calibration error from reliability bins, aggregated over `keys`."""
    return (
        rel.group_by([*keys, "bin"])
        .agg(
            pl.col("n").sum(),
            ((pl.col("mean_p") * pl.col("n")).sum() / pl.col("n").sum()).alias("mp"),
            ((pl.col("hit_rate") * pl.col("n")).sum() / pl.col("n").sum()).alias("hr"),
        )
        .group_by(keys)
        .agg(
            ((pl.col("mp") - pl.col("hr")).abs() * pl.col("n"))
            .sum()
            .truediv(pl.col("n").sum())
            .alias("ece")
        )
    )


def summary(graded: pl.DataFrame, seed: int = 0) -> pl.DataFrame:
    """Per model over all graded seasons: log loss with a 90% CI from resampling whole seasons, and
    the same for the paired difference vs. the market baseline (negative = beat the market)."""
    per = graded.group_by(["model_id", "season"]).agg(
        pl.len().alias("n"), pl.col("log_loss").sum().alias("ll_sum")
    )
    mkt = graded.filter(pl.col("model_id") == MARKET_ID).select(
        "game_id", pl.col("log_loss").alias("mll")
    )
    paired = (
        graded.join(mkt, on="game_id", how="inner")
        .group_by(["model_id", "season"])
        .agg(pl.len().alias("n_p"), (pl.col("log_loss") - pl.col("mll")).sum().alias("d_sum"))
    )
    per = per.join(paired, on=["model_id", "season"], how="left")
    rng = np.random.default_rng(seed)
    rows = []
    for (mid,), g in per.group_by(["model_id"], maintain_order=True):
        n, ll = g["n"].to_numpy(), g["ll_sum"].to_numpy()
        n_p, d = g["n_p"].fill_null(0).to_numpy(), g["d_sum"].fill_null(0.0).to_numpy()
        k = len(n)
        idx = rng.integers(0, k, size=(BOOTSTRAP, k))
        boot_ll = ll[idx].sum(1) / n[idx].sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            boot_d = d[idx].sum(1) / n_p[idx].sum(1)
        rows.append(
            {
                "model_id": mid,
                "seasons": k,
                "first_season": int(g["season"].min()),
                "last_season": int(g["season"].max()),
                "n_games": int(n.sum()),
                "log_loss": float(ll.sum() / n.sum()),
                "ll_lo": float(np.quantile(boot_ll, 0.05)),
                "ll_hi": float(np.quantile(boot_ll, 0.95)),
                "d_vs_market": float(d.sum() / n_p.sum()) if n_p.sum() else None,
                "d_lo": float(np.nanquantile(boot_d, 0.05)) if n_p.sum() else None,
                "d_hi": float(np.nanquantile(boot_d, 0.95)) if n_p.sum() else None,
            }
        )
    return pl.DataFrame(rows).sort("log_loss")


def divergence(graded: pl.DataFrame) -> pl.DataFrame:
    """Per (model, bucket of |p - market_p|): how the side the model leaned toward (relative to the
    market) actually did, against what the market expected for that side."""
    g = graded.filter(pl.col("market_p").is_not_null() & (pl.col("model_id") != MARKET_ID))
    lean_home = pl.col("p_home") > pl.col("market_p")
    gap = (pl.col("p_home") - pl.col("market_p")).abs()
    b = DIVERGENCE_BUCKETS
    bucket = (
        pl.when(gap < b[1])
        .then(pl.lit("0-2.5"))
        .when(gap < b[2])
        .then(pl.lit("2.5-5"))
        .when(gap < b[3])
        .then(pl.lit("5-10"))
        .otherwise(pl.lit("10+"))
    )
    mp = pl.col("market_p").clip(EPS, 1 - EPS)
    market_ll = -(pl.col("home_win") * mp.log() + (1 - pl.col("home_win")) * (1 - mp).log())
    return (
        g.with_columns(
            bucket.alias("bucket"),
            pl.when(lean_home)
            .then(pl.col("home_win"))
            .otherwise(1 - pl.col("home_win"))
            .alias("lean_won"),
            pl.when(lean_home)
            .then(pl.col("market_p"))
            .otherwise(1 - pl.col("market_p"))
            .alias("lean_mkt_p"),
            market_ll.alias("market_ll"),
        )
        .group_by(["model_id", "bucket"])
        .agg(
            pl.len().alias("n"),
            pl.col("lean_won").mean().alias("lean_win_rate"),
            pl.col("lean_mkt_p").mean().alias("market_expected_rate"),
            pl.col("log_loss").mean().alias("model_log_loss"),
            pl.col("market_ll").mean().alias("market_log_loss"),
        )
        .sort(["model_id", "bucket"])
    )


def upcoming_slate(paths: Paths) -> pl.DataFrame:
    preds = pl.read_parquet(paths.marts / "predictions.parquet").filter(~pl.col("is_backfill"))
    games = load_games(paths).filter(pl.col("result").is_null())
    if games.is_empty() or preds.is_empty():
        return pl.DataFrame()
    week = games.select(pl.col("week").min()).item()
    season = games.select(pl.col("season").max()).item()
    slate = games.filter((pl.col("season") == season) & (pl.col("week") == week))
    latest = preds.sort("lock_ts").group_by(["game_id", "model_id"]).last()
    wide = latest.pivot(on="model_id", index="game_id", values=["p_home", "spread_home"])
    return slate.join(wide, on="game_id", how="left").sort("kickoff_utc")


def grade(paths: Paths, console: Console) -> None:
    g = graded_frame(paths)
    rel = reliability(g)
    sc = scorecard(g)
    sc = sc.join(
        pl.concat(
            [
                ece(rel, ["season", "model_id"]).with_columns(pl.lit("season").alias("scope")),
            ]
        ),
        on=["season", "model_id", "scope"],
        how="left",
    )
    sc.write_parquet(paths.marts / "scorecard.parquet")
    g.write_parquet(paths.marts / "graded.parquet")
    rel.write_parquet(paths.marts / "reliability.parquet")
    summ = summary(g)
    summ.write_parquet(paths.marts / "summary.parquet")
    divergence(g).write_parquet(paths.marts / "divergence.parquet")

    t = Table(title="season scorecard (REG+POST, graded games)")
    for c in ("season", "model", "games", "log loss", "brier", "spread MAE", "ATS%", "n ATS"):
        t.add_column(c, justify="right")
    for r in (
        sc.filter(pl.col("scope") == "season").sort(["season", "log_loss"]).iter_rows(named=True)
    ):
        t.add_row(
            str(r["season"]),
            r["model_id"],
            str(r["n_games"]),
            f"{r['log_loss']:.4f}",
            f"{r['brier']:.4f}",
            f"{r['spread_mae']:.2f}",
            f"{r['ats_pct']:.1%}" if r["ats_pct"] is not None else "-",
            str(r["n_ats"]),
        )
    console.print(t)

    t = Table(title="all graded seasons: log loss (90% CI by season bootstrap), vs. market")
    for c in ("model", "seasons", "games", "log loss", "CI", "Δ vs market", "Δ CI"):
        t.add_column(c, justify="right")
    for r in summ.iter_rows(named=True):
        d = r["d_vs_market"]
        t.add_row(
            r["model_id"],
            f"{r['first_season']}-{r['last_season']}",
            f"{r['n_games']:,}",
            f"{r['log_loss']:.4f}",
            f"{r['ll_lo']:.4f}-{r['ll_hi']:.4f}",
            f"{d:+.4f}" if d is not None else "-",
            f"{r['d_lo']:+.4f}..{r['d_hi']:+.4f}" if d is not None else "-",
        )
    console.print(t)

    paths.site.mkdir(parents=True, exist_ok=True)
    (paths.site / "scorecard.json").write_text(sc.write_json())
    slate = upcoming_slate(paths)
    if not slate.is_empty():
        season, week = slate["season"][0], slate["week"][0]
        (paths.site / f"week_{season}_{week}.json").write_text(
            json.dumps(
                slate.with_columns(pl.col("kickoff_utc").cast(pl.Utf8)).to_dicts(),
                indent=1,
                default=str,
            )
        )
        console.print(
            f"[bold]grade:[/bold] slate for {season} week {week}: {slate.height} games -> site/"
        )
