"""Simulation inputs: one win probability per remaining regular-season game, per variant.

Student variant: the latest real (non-backfill) locked Student row stamped before both the as-of
and the kickoff; otherwise the Student scored now through `lock.score_approaches`.
Market variant: the vig-free moneyline from `lock.market_at` where a line exists; otherwise a
rating model (`fit_ratings`) fitted to the upcoming lines plus this season's closing moneylines,
weighted toward recent games.

Point in time: every function takes an explicit `as_of` and uses only rows stamped strictly before
it (ADR 0005). Nothing reads the clock. The pure functions take DataFrames; `load_inputs` is the
thin disk wrapper. A game counts as remaining when it has no result.

`fit_ratings` solves a ridge-regularised least squares on the ratings (RIDGE, 1e-10 on the squared
rating norm; the home term is unpenalised) and centres the ratings to sum to zero afterwards. The
ridge makes an underdetermined or disconnected schedule return the minimum-norm answer, and is
small enough to leave a well-determined fit exact to about 1e-8 on the logit.
"""

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import polars as pl

from nfl import lock
from nfl.approaches import fit
from nfl.approaches.schema import load_all
from nfl.config import Paths
from nfl.features import store

STUDENT_ID = "student"
RIDGE = 1e-10
HALF_LIFE_DAYS = 28.0  # closing moneylines lose half their weight every four weeks
P_CLIP = 1e-6


@dataclass
class Ratings:
    ratings: dict[str, float]  # logit points, centred to sum to zero
    home: float  # home term (logit), not centred
    r2: float | None = None  # weighted-free R squared on the logit, over the fitted rows
    n_rows: int = 0


@dataclass
class VariantInputs:
    """Inputs for one variant, aligned by position; build.py hands these to the simulator."""

    variant: str
    game_ids: list[str]
    home: list[str]
    away: list[str]
    p_home: np.ndarray
    source: list[str]
    source_counts: dict[str, int]
    ratings: dict[str, float]  # fitted to this variant's own p_home (prices playoff games)
    home_term: float
    fit_r2: float | None = None
    market_fit: Ratings | None = field(default=None, repr=False)  # fit behind market fallbacks
    model_version: str = ""  # the Student's config hash; the snapshot rows carry it


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), P_CLIP, 1 - P_CLIP)
    return np.log(p / (1 - p))


def fit_ratings(rows: pl.DataFrame, teams: list[str] | None = None) -> Ratings:
    """Fit logit p = home + r_home - r_away. rows: home, away, p, weight (any set of games)."""
    if rows.is_empty():
        return Ratings({t: 0.0 for t in teams or []}, 0.0, None, 0)
    names = sorted(set(teams or []) | set(rows["home"]) | set(rows["away"]))
    ix = {t: i for i, t in enumerate(names)}
    n, k = rows.height, len(names)
    A = np.zeros((n, k + 1))
    for r, (h, a) in enumerate(zip(rows["home"], rows["away"], strict=True)):
        A[r, ix[h]] += 1.0
        A[r, ix[a]] -= 1.0
    A[:, k] = 1.0
    y = _logit(rows["p"].to_numpy())
    w = np.sqrt(rows["weight"].to_numpy().astype(float))
    pen = np.zeros((k, k + 1))
    pen[np.arange(k), np.arange(k)] = np.sqrt(RIDGE)
    X = np.vstack([A * w[:, None], pen])
    z = np.r_[y * w, np.zeros(k)]
    beta, *_ = np.linalg.lstsq(X, z, rcond=None)
    r = beta[:k] - beta[:k].mean()
    pred = A @ np.r_[r, beta[k]]
    ss = ((y - y.mean()) ** 2).sum()
    r2 = float(1 - ((y - pred) ** 2).sum() / ss) if ss > 0 else None
    return Ratings({t: float(r[i]) for t, i in ix.items()}, float(beta[k]), r2, n)


def price(ratings: Ratings, home: str, away: str, neutral: bool = False) -> float:
    """P(home wins) from fitted ratings; neutral drops the home term (the Super Bowl)."""
    h = 0.0 if neutral else ratings.home
    d = ratings.ratings.get(home, 0.0) - ratings.ratings.get(away, 0.0) + h
    return float(1 / (1 + np.exp(-d)))


def remaining_games(games: pl.DataFrame, season: int) -> pl.DataFrame:
    """Unplayed regular-season games: game_id, kickoff_utc, home, away."""
    return (
        games.filter(
            (pl.col("season") == season)
            & (pl.col("game_type") == "REG")
            & pl.col("result").is_null()
        )
        .sort("kickoff_utc", "game_id")
        .select("game_id", pl.col("kickoff_utc").cast(pl.Datetime("us")), "home_team", "away_team")
        .rename({"home_team": "home", "away_team": "away"})
    )


def locked_student(preds: pl.DataFrame, remaining: pl.DataFrame, as_of: datetime) -> pl.DataFrame:
    """game_id, p_home: latest real Student lock row stamped before the as-of and the kickoff."""
    cut = pl.lit(as_of.replace(tzinfo=None), dtype=pl.Datetime("us"))
    return (
        preds.filter(
            (pl.col("model_id") == STUDENT_ID)
            & ~pl.col("is_backfill")
            & pl.col("p_home").is_not_null()
            & (pl.col("lock_ts") < cut)
        )
        .join(remaining.select("game_id", "kickoff_utc"), on="game_id", how="inner")
        .filter(pl.col("lock_ts") < pl.col("kickoff_utc"))
        .sort("lock_ts")
        .group_by("game_id", maintain_order=True)
        .last()
        .select("game_id", "p_home")
    )


def games_needing_score(remaining: pl.DataFrame, locked: pl.DataFrame) -> pl.DataFrame:
    return remaining.filter(~pl.col("game_id").is_in(locked["game_id"].to_list()))


def _own_fit(variant: str, rem: pl.DataFrame, p, source, extra=None) -> VariantInputs:
    counts: dict[str, int] = {}
    for s in source:
        counts[s] = counts.get(s, 0) + 1
    fit = fit_ratings(
        pl.DataFrame(
            {"home": rem["home"], "away": rem["away"], "p": p, "weight": np.ones(rem.height)}
        ),
        teams=sorted(set(rem["home"]) | set(rem["away"])),
    )
    return VariantInputs(
        variant,
        rem["game_id"].to_list(),
        rem["home"].to_list(),
        rem["away"].to_list(),
        np.asarray(p, dtype=float),
        list(source),
        counts,
        fit.ratings,
        fit.home,
        fit.r2,
        extra,
    )


def student_inputs(
    remaining: pl.DataFrame, locked: pl.DataFrame, scored: pl.DataFrame
) -> VariantInputs:
    """Merge locked rows (win) with freshly scored rows. Raises if a game has neither."""
    lk = dict(zip(locked["game_id"], locked["p_home"], strict=True))
    sc = {
        g: p
        for g, p in zip(scored["game_id"], scored["p_home"], strict=True)
        if p is not None and not np.isnan(p)
    }
    p, src, missing = [], [], []
    for g in remaining["game_id"]:
        if g in lk:
            p.append(lk[g])
            src.append("locked")
        elif g in sc:
            p.append(sc[g])
            src.append("scored")
        else:
            missing.append(g)
    if missing:
        raise ValueError(f"no Student probability for {len(missing)} games, e.g. {missing[:3]}")
    return _own_fit(STUDENT_ID, remaining, p, src)


def market_inputs(
    remaining: pl.DataFrame,
    played: pl.DataFrame,
    feats: pl.DataFrame,
    as_of: datetime,
    half_life_days: float = HALF_LIFE_DAYS,
) -> VariantInputs:
    """Line where one exists, else ratings fitted to upcoming lines + closing moneylines.

    played: this season's finished games (game_id, kickoff_utc, home, away). feats: long feature
    rows; only those with known_as_of < as_of are read (lock.market_at)."""
    cut = as_of.replace(tzinfo=None)
    up = lock.market_at(feats, remaining, cut).filter(pl.col("p_home").is_not_null())
    cl = lock.market_at(feats, played, cut).filter(pl.col("p_home").is_not_null())
    up_rows = up.select("game_id", "p_home").join(
        remaining.select("game_id", "home", "away"), on="game_id"
    )
    # Age from the last game played, not the clock: a site build with no new data must price the
    # same, or every rebuild would nudge these fits and reseed the simulation.
    anchor = played["kickoff_utc"].max() if played.height else cut
    age = (pl.lit(anchor, dtype=pl.Datetime("us")) - pl.col("kickoff_utc")).dt.total_seconds()
    age = age / 86400
    cl_rows = cl.select("game_id", "p_home").join(
        played.select("game_id", "home", "away", "kickoff_utc"), on="game_id"
    )
    cl_rows = cl_rows.with_columns((0.5 ** (age.clip(lower_bound=0) / half_life_days)).alias("w"))
    fit_rows = pl.concat(
        [
            up_rows.select(
                "home", "away", pl.col("p_home").alias("p"), pl.lit(1.0).alias("weight")
            ),
            cl_rows.select(
                "home", "away", pl.col("p_home").alias("p"), pl.col("w").alias("weight")
            ),
        ]
    )
    teams = sorted(set(remaining["home"]) | set(remaining["away"]) | set(played["home"]))
    mfit = fit_ratings(fit_rows, teams=teams)
    line = dict(zip(up["game_id"], up["p_home"], strict=True))
    p, src = [], []
    for g, h, a in zip(remaining["game_id"], remaining["home"], remaining["away"], strict=True):
        if g in line:
            p.append(line[g])
            src.append("line")
        else:
            p.append(price(mfit, h, a))
            src.append("ratings")
    return _own_fit("market", remaining, p, src, mfit)


def build_inputs(
    games: pl.DataFrame,
    preds: pl.DataFrame,
    feats: pl.DataFrame,
    score_fn,
    season: int,
    as_of: datetime,
) -> dict[str, VariantInputs]:
    """Pure core. score_fn(slate: DataFrame[game_id, ...]) -> DataFrame[game_id, p_home] scores the
    games that have no lock (the wrapper binds the models and `as_of`)."""
    as_of = as_of.replace(tzinfo=None)
    remaining = remaining_games(games, season)
    played = (
        games.filter(
            (pl.col("season") == season)
            & (pl.col("game_type") == "REG")
            & pl.col("result").is_not_null()
        )
        .select("game_id", pl.col("kickoff_utc").cast(pl.Datetime("us")), "home_team", "away_team")
        .rename({"home_team": "home", "away_team": "away"})
    )
    locked = locked_student(preds, remaining, as_of)
    need = games_needing_score(remaining, locked)
    scored = (
        score_fn(need)
        if need.height
        else pl.DataFrame(schema={"game_id": pl.Utf8, "p_home": pl.Float64})
    )
    return {
        STUDENT_ID: student_inputs(remaining, locked, scored),
        "market": market_inputs(remaining, played, feats, as_of),
    }


def load_inputs(
    paths: Paths, season: int, as_of: datetime, check_hash: bool = True
) -> dict[str, VariantInputs]:
    """Thin disk wrapper: read games, predictions and features, then `build_inputs`."""
    from nfl import predict

    as_of = as_of.replace(tzinfo=None)
    games = store.games_frame(paths).filter(pl.col("season") == season)
    preds = predict.existing(paths)
    feats = store.read_features(paths, seasons=(season, season))
    # Only the Student is needed, so load it alone (same config-hash guard as lock.load_models).
    cfg = load_all()[STUDENT_ID]
    try:
        model = fit.load(paths, STUDENT_ID, season - 1)
    except FileNotFoundError as e:
        raise RuntimeError(f"no Student fit trained through {season - 1} (run nfl fit)") from e
    if check_hash and model.meta.get("config_hash") != fit.config_hash(cfg):
        raise RuntimeError("student: the YAML changed since its fit; run `nfl fit`")
    student = [(STUDENT_ID, model)]

    def score(slate: pl.DataFrame) -> pl.DataFrame:
        sc = lock.score_approaches(student, feats, slate, as_of)
        return sc[0].frame.select("game_id", "p_home")

    out = build_inputs(games, preds, feats, score, season, as_of)
    out["student"].model_version = str(model.meta.get("config_hash", ""))
    return out
