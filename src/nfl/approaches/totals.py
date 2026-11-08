"""The total (ADR 0024, M20.11): `student_total`, a ridge regression for combined points.

Context, not a headline line: scored by MAE and by its over/under side against the market total, in
its own tracker block, never in the scorecard or the README. The market total is never an input
(ADR 0013). Team features enter as home + away (a total cares how much both sides score, not who's
better); weather enters as excess wind and cold, zero under a roof or when unknown.

Walk-forward like the Student: the artifact used in season S is trained on S-TRAIN_SEASONS..S-1 with
features as of kickoff - 1h, the rule live locks use. Artifacts: marts/fits/student_total/<S-1>.json.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl

from nfl.config import Paths
from nfl.features import store

MODEL_ID = "student_total"
VERSION = "1"
TEAM = (
    "strength.epa_off",
    "strength.epa_def",
    "strength.epa_pass_off",
    "strength.epa_pass_def",
    "strength.success_off",
    "strength.success_def",
    "strength.qb_epa",
    "strength.st_epa_pg",
    "decisions.explosive_rate",
    "decisions.pass_rate_oe",
    "availability.qb1_out",
)
GAME = ("environment.is_dome",)
WEATHER = ("weather.wind_mph", "weather.temp_f")
INPUTS = (*(f"sum.{f}" for f in TEAM), *GAME, "weather.wind_over_10", "weather.cold_under_40")
TRAIN_SEASONS = 10
LAMBDA = 25.0  # on standardized inputs; totals are noisy, so shrink hard
SYNTHETIC_LOCK = pl.duration(hours=1)


@dataclass
class TotalModel:
    trained_through: int
    inputs: list[str]
    mean: list[float]
    std: list[float]
    w: list[float]
    b: float
    sd: float
    n: int
    config_hash: str
    model_id: str = MODEL_ID
    version: str = VERSION

    def predict(self, x: pl.DataFrame) -> np.ndarray:
        z = (_matrix(x, self.inputs) - np.array(self.mean)) / np.array(self.std)
        z = np.nan_to_num(z)  # missing -> the training average
        return self.b + z @ np.array(self.w)


def config_hash() -> str:
    spec = json.dumps([VERSION, INPUTS, TRAIN_SEASONS, LAMBDA])
    return hashlib.sha256(spec.encode()).hexdigest()[:12]


def _matrix(x: pl.DataFrame, inputs: list[str] | tuple[str, ...]) -> np.ndarray:
    return x.select([pl.col(c).cast(pl.Float64) for c in inputs]).to_numpy().astype(float)


def vectors(asof: pl.DataFrame) -> pl.DataFrame:
    """As-of rows -> one row per game with INPUTS columns: team features summed over both sides
    (null if either side is missing), game features as they are, weather turned into excess wind
    and cold (zero when it's unknown or under a roof)."""
    team = asof.filter(pl.col("feature").is_in(TEAM) & (pl.col("side") != "game"))
    sums = (
        team.group_by("game_id", "feature")
        .agg(pl.col("value").sum().alias("value"), pl.col("value").count().alias("k"))
        .with_columns(pl.when(pl.col("k") == 2).then(pl.col("value")).alias("value"))
        .with_columns(("sum." + pl.col("feature")).alias("feature"))
        .select("game_id", "feature", "value")
    )
    game = asof.filter(pl.col("feature").is_in([*GAME, *WEATHER]) & (pl.col("side") == "game"))
    long = pl.concat([sums, game.select("game_id", "feature", "value")])
    wide = store.to_wide(long, [*(f"sum.{f}" for f in TEAM), *GAME, *WEATHER])
    return wide.with_columns(
        (pl.col("weather.wind_mph") - 10).clip(lower_bound=0).fill_null(0).alias("weather.wind_over_10"),
        (40 - pl.col("weather.temp_f")).clip(lower_bound=0).fill_null(0).alias("weather.cold_under_40"),
    ).select("game_id", *INPUTS)  # fmt: skip


def families() -> list[str]:
    return sorted({f.split(".", 1)[0] for f in (*TEAM, *GAME, *WEATHER)})


def dataset(paths: Paths, seasons: tuple[int, int]) -> pl.DataFrame:
    """Completed games in `seasons`: game_id, season, week, y (total points), total_line, INPUTS."""
    games = store.games_frame(paths).filter(
        pl.col("season").is_between(*seasons) & pl.col("result").is_not_null()
    )
    locks = games.select("game_id", (pl.col("kickoff_utc") - SYNTHETIC_LOCK).alias("lock_ts"))
    feats = store.read_features(paths, seasons=seasons, families=families())
    x = vectors(store.as_of(feats, locks))
    return (
        games.select(
            "game_id",
            "season",
            "week",
            pl.col("total").cast(pl.Float64).alias("y"),
            pl.col("total_line").cast(pl.Float64),
        )
        .join(x, on="game_id", how="left")
        .sort("season", "week", "game_id")
    )


def fit(train: pl.DataFrame, trained_through: int) -> TotalModel:
    """Ridge on standardized inputs, closed form; the intercept is the training mean."""
    x = _matrix(train, INPUTS)
    y = train["y"].to_numpy().astype(float)
    mean = np.nanmean(x, axis=0)
    std = np.nanstd(x, axis=0)
    std[~np.isfinite(std) | (std == 0)] = 1.0
    mean[~np.isfinite(mean)] = 0.0
    z = np.nan_to_num((x - mean) / std)
    b = float(y.mean())
    w = np.linalg.solve(z.T @ z + LAMBDA * np.eye(z.shape[1]), z.T @ (y - b))
    resid = y - (b + z @ w)
    return TotalModel(trained_through, list(INPUTS), mean.tolist(), std.tolist(), w.tolist(), b,
                      float(resid.std(ddof=z.shape[1] + 1)), len(y), config_hash())  # fmt: skip


def walk_forward(data: pl.DataFrame, scored: tuple[int, int]) -> pl.DataFrame:
    """Each scored season predicted by a model trained on the TRAIN_SEASONS before it."""
    out = []
    for s in range(scored[0], scored[1] + 1):
        train = data.filter(pl.col("season").is_between(s - TRAIN_SEASONS, s - 1))
        test = data.filter(pl.col("season") == s)
        if train.height < 500 or test.is_empty():
            continue
        m = fit(train, s - 1)
        out.append(test.with_columns(pl.Series("pred", m.predict(test)),
                                     pl.lit(m.b).alias("naive")))  # fmt: skip
    return pl.concat(out) if out else pl.DataFrame()


def backtest(paths: Paths, scored: tuple[int, int]) -> pl.DataFrame:
    """Per season: n, MAE of the model, of the market's closing total and of the training mean,
    and how often the model's side of the closing total was right (pushes and ties excluded)."""
    data = dataset(paths, (scored[0] - TRAIN_SEASONS, scored[1]))
    wf = walk_forward(data, scored).filter(pl.col("total_line").is_not_null())
    side = (pl.col("pred") - pl.col("total_line")).sign() * (
        pl.col("y") - pl.col("total_line")
    ).sign()
    rows = wf.group_by("season").agg(
        pl.len().alias("n"),
        (pl.col("y") - pl.col("pred")).abs().mean().alias("mae"),
        (pl.col("y") - pl.col("total_line")).abs().mean().alias("market_mae"),
        (pl.col("y") - pl.col("naive")).abs().mean().alias("naive_mae"),
        (side.filter(side != 0) > 0).mean().alias("side_right"),
    )
    return rows.sort("season")


# ------------------------------------------------------------------------------------- artifacts


def artifact_path(paths: Paths, trained_through: int) -> Path:
    return paths.marts / "fits" / MODEL_ID / f"{trained_through}.json"


def save(paths: Paths, m: TotalModel) -> Path:
    p = artifact_path(paths, m.trained_through)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(m), indent=1))
    return p


def load_or_fit(paths: Paths, trained_through: int, save_fit: bool = True) -> TotalModel:
    """The artifact for a season, refitted when it's missing or its config changed (the fit is
    deterministic from data through `trained_through`, so a refit can't see the future)."""
    p = artifact_path(paths, trained_through)
    if p.exists():
        m = TotalModel(**json.loads(p.read_text()))
        if m.config_hash == config_hash():
            return m
    data = dataset(paths, (trained_through - TRAIN_SEASONS + 1, trained_through))
    m = fit(data, trained_through)
    if save_fit:  # a dry run fits in memory and leaves marts alone
        save(paths, m)
    return m


def score(
    m: TotalModel, feats: pl.DataFrame, slate: pl.DataFrame, lock_ts: datetime
) -> pl.DataFrame:
    """game_id, total, sd_total for a slate, features as of the lock."""
    ids = slate["game_id"].to_list()
    asof = store.as_of(feats.filter(pl.col("game_id").is_in(ids)), lock_ts)
    x = slate.select("game_id").join(vectors(asof), on="game_id", how="left")
    return x.select("game_id").with_columns(
        pl.Series("total", m.predict(x)), pl.lit(m.sd).alias("sd_total")
    )


# ------------------------------------------------------------------------- live rows and grading

ROWS = {"game_id": pl.Utf8, "season": pl.Int64, "week": pl.Int64, "model_id": pl.Utf8,
        "model_version": pl.Utf8, "lock_ts": pl.Datetime("us"), "slot": pl.Utf8,
        "total": pl.Float64, "sd_total": pl.Float64, "market_total": pl.Float64}  # fmt: skip


def ledger_path(paths: Paths) -> Path:
    return paths.marts / "totals.parquet"


def load(paths: Paths) -> pl.DataFrame:
    f = ledger_path(paths)
    return pl.read_parquet(f) if f.exists() else pl.DataFrame(schema=ROWS)


def append(paths: Paths, rows: pl.DataFrame) -> int:
    """Append-only, like predictions: a (game_id, lock_ts) already stored is never rewritten."""
    if rows.is_empty():
        return 0
    rows = rows.select([pl.col(c).cast(t) for c, t in ROWS.items()])
    old = load(paths)
    new = rows.join(old.select("game_id", "lock_ts"), on=["game_id", "lock_ts"], how="anti")
    if new.is_empty():
        return 0
    f = ledger_path(paths)
    f.parent.mkdir(parents=True, exist_ok=True)
    pl.concat([old, new]).write_parquet(f)
    return new.height


def lock_rows(m: TotalModel, scored: pl.DataFrame, slate: pl.DataFrame, market: pl.DataFrame | None,
              lock_ts: datetime, slot: str) -> pl.DataFrame:  # fmt: skip
    mk = (market.select("game_id", pl.col("total").alias("market_total"))
          if market is not None and not market.is_empty()
          else pl.DataFrame(schema={"game_id": pl.Utf8, "market_total": pl.Float64}))  # fmt: skip
    return (
        scored.join(slate.select("game_id", "season", "week"), on="game_id")
        .join(mk, on="game_id", how="left")
        .with_columns(
            pl.lit(MODEL_ID).alias("model_id"),
            pl.lit(f"{VERSION}.{m.config_hash}").alias("model_version"),
            pl.lit(lock_ts).cast(pl.Datetime("us")).alias("lock_ts"),
            pl.lit(slot).alias("slot"),
        )
        .select(list(ROWS))
    )


def grade(paths: Paths, games: pl.DataFrame) -> pl.DataFrame:
    """Each game's last locked total against the final score: error, and whether its side of the
    market total at that lock was right (null on a push or when it matched the market)."""
    rows = load(paths)
    if rows.is_empty():
        return rows
    last = rows.sort("lock_ts").group_by("game_id", maintain_order=True).last()
    done = games.filter(pl.col("result").is_not_null()).select(
        "game_id", pl.col("total").cast(pl.Float64).alias("actual")
    )
    side = (pl.col("total") - pl.col("market_total")).sign() * (
        pl.col("actual") - pl.col("market_total")
    ).sign()
    return last.join(done, on="game_id").with_columns(
        (pl.col("actual") - pl.col("total")).alias("error"),
        pl.when(side != 0).then(side > 0).alias("side_right"),
    )


def summary(graded: pl.DataFrame, rows: pl.DataFrame) -> dict | None:
    """The tracker block: weeks tracked from the first lock, MAE beside the market's, side record."""
    if rows.is_empty():
        return None
    first = rows["lock_ts"].min()
    out = {"first_lock": first.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "weeks": rows.select(pl.struct("season", "week").n_unique()).item(),
           "n": graded.height, "mae": None, "market_mae": None, "side_right": 0, "side_n": 0}  # fmt: skip
    if graded.height:
        g = graded.filter(pl.col("market_total").is_not_null())
        out["mae"] = round(float(graded["error"].abs().mean()), 2)
        if g.height:
            out["market_mae"] = round(float((g["actual"] - g["market_total"]).abs().mean()), 2)
        s = graded["side_right"].drop_nulls()
        out["side_right"], out["side_n"] = int(s.sum()), s.len()
    return out
