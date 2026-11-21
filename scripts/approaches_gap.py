"""Model round 3 audit (ADR 0031): where the Student's gap to the market comes from.

Read-only. The Student walked forward in memory (`nfl.approaches.shadow`), the market's vig-free
probability from the backfill rows, per-game log-loss gap = Student − market, summed by bucket so
each bucket's share of the total gap is visible. The late-status proxy: the same fits scored with
the week's injury report removed (what a lock before the final report would see; nflverse stamps
one row per player-week, about 50 hours before kickoff, 2010-2024).

    uv run python scripts/approaches_gap.py --out .notes/approaches-audit/
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import polars as pl

from nfl import catalog
from nfl.approaches import fit, shadow
from nfl.approaches.run import known_features
from nfl.approaches.schema import load_all
from nfl.config import get_paths

REPORT = [
    "availability.injury_impact",
    "availability.starters_out",
    "availability.ol_starters_out",
    "availability.report_count",
    "availability.qb1_out",
]


def ll(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def scored(st, data, null_cols=(), seasons=(2005, 2025), lam=10.0) -> pl.DataFrame:
    out = []
    for s in range(seasons[0], seasons[1] + 1):
        train = data.filter(pl.col("season").is_between(st.fit.train_from, s - 1))
        test = data.filter(pl.col("season") == s)
        m = fit.fit_flavors(st, train, lam, s - 1).public
        t2 = test.with_columns(
            [pl.lit(None, pl.Float64).alias(c) for c in null_cols if c in test.columns]
        )
        out.append(
            test.select("game_id", "season", "week", "y").with_columns(
                pl.Series("p", fit._score(m, t2))
            )
        )
    return pl.concat(out)


def bucket_table(df: pl.DataFrame, key: str) -> pl.DataFrame:
    total = df["gap"].sum()
    return (
        df.group_by(key)
        .agg(
            pl.len().alias("games"),
            pl.col("ll_s").mean().alias("student"),
            pl.col("ll_m").mean().alias("market"),
            pl.col("gap").mean().alias("gap_per_game"),
            (pl.col("gap").sum() / total).alias("share_of_gap"),
        )
        .sort(key)
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    paths = get_paths()
    known = known_features(paths)
    st = load_all()["student"]
    feats = st.resolve(known)
    data = shadow.dataset(
        paths,
        [
            *feats,
            "availability.qb_change",
            "availability.qb1_out",
            "availability.injury_impact",
            "availability.value_lost",
        ],
    )
    base = scored(st, data)
    con = catalog.connect(paths, only=["predictions", "games"])
    mk = con.sql(
        "select p.game_id, p.p_home pm, g.spread_line, g.result from predictions p join games g "
        "using (game_id) where model_id='market_baseline' and is_backfill"
    ).pl()
    df = (
        base.join(mk, on="game_id")
        .join(
            data.select(
                "game_id",
                "availability.qb_change",
                "availability.qb1_out",
                "availability.injury_impact",
                "availability.value_lost",
            ),
            on="game_id",
        )
        .filter(pl.col("season") >= 2016)
    )
    y = df["y"].to_numpy()
    df = df.with_columns(
        pl.Series("ll_s", ll(df["p"].to_numpy(), y)),
        pl.Series("ll_m", ll(df["pm"].to_numpy(), y)),
    ).with_columns((pl.col("ll_s") - pl.col("ll_m")).alias("gap"))
    df = df.with_columns(
        pl.when(pl.col("week") <= 4)
        .then(pl.lit("1-4"))
        .when(pl.col("week") <= 9)
        .then(pl.lit("5-9"))
        .when(pl.col("week") <= 14)
        .then(pl.lit("10-14"))
        .otherwise(pl.lit("15+"))
        .alias("weeks"),
        ((pl.col("p") - pl.col("pm")).abs() * 100)
        .cut([3, 6, 10, 15], labels=["<3", "3-6", "6-10", "10-15", "15+"])
        .alias("disagree_pts"),
        pl.when(pl.col("availability.qb_change").abs() > 0)
        .then(pl.lit("QB change"))
        .when(pl.col("availability.qb1_out").abs() > 0)
        .then(pl.lit("QB1 out"))
        .otherwise(pl.lit("same QBs"))
        .alias("qb"),
        pl.col("availability.injury_impact")
        .abs()
        .cut([2, 5], labels=["<2", "2-5", "5+"])
        .alias("injury_gap"),
        pl.col("spread_line")
        .abs()
        .cut([2.5, 6.5, 9.5], labels=["0-2.5", "3-6.5", "7-9.5", "10+"])
        .alias("fav_size"),
        pl.when(pl.col("spread_line") > 0)
        .then(pl.lit("home fav"))
        .when(pl.col("spread_line") < 0)
        .then(pl.lit("away fav"))
        .otherwise(pl.lit("pick"))
        .alias("fav_side"),
    )
    tables = {
        k: bucket_table(df, k)
        for k in ["season", "weeks", "disagree_pts", "qb", "injury_gap", "fav_size", "fav_side"]
    }
    with pl.Config(tbl_rows=30, float_precision=4):
        for k, t in tables.items():
            print(t)
    # late-status proxy: the injury report removed at scoring time
    early = scored(st, data, null_cols=REPORT)
    e = early.join(base.select("game_id", pl.col("p").alias("p_full")), on="game_id").join(
        mk.select("game_id", "pm"), on="game_id"
    )
    for lo, hi in ((2010, 2024), (2016, 2024)):
        x = e.filter(pl.col("season").is_between(lo, hi))
        yy = x["y"].to_numpy()
        a, b, m = (
            ll(x["p"].to_numpy(), yy).mean(),
            ll(x["p_full"].to_numpy(), yy).mean(),
            ll(x["pm"].to_numpy(), yy).mean(),
        )
        print(
            f"{lo}-{hi}: without report {a:.5f}, with report {b:.5f}, market {m:.5f}; report closes {(a - b) / (a - m):.1%} of the no-report gap"
        )
    # does the market weigh injuries more than the Student? regress logit gap on report features
    from scipy.special import logit

    z = df.with_columns(
        pl.Series(
            "dl",
            logit(np.clip(df["pm"].to_numpy(), 1e-6, 1 - 1e-6))
            - logit(np.clip(df["p"].to_numpy(), 1e-6, 1 - 1e-6)),
        )
    )
    X = np.column_stack(
        [np.ones(z.height)]
        + [
            z[c].fill_null(0).to_numpy()
            for c in (
                "availability.qb_change",
                "availability.qb1_out",
                "availability.injury_impact",
                "availability.value_lost",
            )
        ]
    )
    beta, *_ = np.linalg.lstsq(X, z["dl"].to_numpy(), rcond=None)
    r2 = 1 - np.var(z["dl"].to_numpy() - X @ beta) / np.var(z["dl"].to_numpy())
    print(
        "logit(market) - logit(student) on [1, qb_change, qb1_out, injury_impact, value_lost]:",
        np.round(beta, 3),
        f"R2 {r2:.3f}",
    )
    print("sd of the logit gap", float(np.std(z["dl"].to_numpy())))
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        for k, t in tables.items():
            t.write_csv(args.out / f"gap_{k}.csv")
        df.select("game_id", "season", "week", "p", "pm", "y", "gap").write_parquet(
            args.out / "gap_games.parquet"
        )


if __name__ == "__main__":
    main()
