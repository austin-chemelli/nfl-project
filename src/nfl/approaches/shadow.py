"""Shadow backtests: an approach variant walked forward in memory, paired against a baseline.

Model round 3 (ADR 0031). The ledger's last gate (ADR 0026) is "earns it in a shadow approach":
paired Δ log loss against today's Student, 2016 onward, season-block bootstrap 90% CI excluding 0.
This module runs that gate without writing a fit or a prediction row:

    data = shadow.dataset(paths, features)              # once, the superset of every variant's features
    base = shadow.backtest(student, data)                # walk-forward p per game, 2005-2025
    alt = shadow.backtest(student_with_x, data)
    shadow.paired(alt, base)                             # Δ log loss with its CI

`knobs(...)` patches the fitter's module constants (inner ridge λ, its prior, the public ridge, the
history threshold, season decay) for one experiment and restores them after. A variant scored here
uses exactly the code path `nfl fit` uses (`fit.fit_flavors`), so a gain here is a gain there.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import numpy as np
import polars as pl

from nfl.approaches import fit
from nfl.approaches.schema import Approach
from nfl.config import Paths

SCORED = (2005, 2025)
PAIRED_FROM = 2016


def dataset(
    paths: Paths, features: list[str], seasons: tuple[int, int] = (2002, 2025)
) -> pl.DataFrame:
    """Completed, non-tied games with every feature as of the synthetic lock (fit.load_dataset)."""
    return fit.load_dataset(paths, sorted(set(features)), seasons)


@contextmanager
def knobs(**kw) -> Iterator[None]:
    """Temporarily set fit-module constants, e.g. knobs(INNER_LAMBDA=1000, DECAY_HALF_LIFE=8)."""
    old = {k: getattr(fit, k) for k in kw}
    try:
        for k, v in kw.items():
            setattr(fit, k, v)
        yield
    finally:
        for k, v in old.items():
            setattr(fit, k, v)


def backtest(
    approach: Approach,
    data: pl.DataFrame,
    scored: tuple[int, int] = SCORED,
    lam: float | None = None,
    which: str = "public",
) -> pl.DataFrame:
    """game_id, season, week, y, p: each season scored by the model trained through the one before.
    λ is selected on the validation seasons when not given (as `nfl fit` does)."""
    feats = [f for f in approach.features if f in data.columns]
    approach = approach.model_copy()
    from nfl.approaches.engine import NEUTRAL

    extra = [NEUTRAL] if NEUTRAL in data.columns and NEUTRAL not in feats else []
    cols = ["game_id", "season", "week", "y", *feats, *extra]
    d = data.select(cols)
    if lam is None:
        lam, _ = fit.select_lambda(approach, d)
    out = []
    for s in range(scored[0], scored[1] + 1):
        train = d.filter(pl.col("season").is_between(approach.fit.train_from, s - 1))
        test = d.filter(pl.col("season") == s)
        if train.height < 100 or test.is_empty():
            continue
        res = fit.fit_flavors(approach, train, lam, s - 1)
        model = getattr(res, which)
        p = fit._score(model, test)
        out.append(test.select("game_id", "season", "week", "y").with_columns(pl.Series("p", p)))
    return pl.concat(out).with_columns(pl.lit(lam).alias("lam"))


def log_loss(df: pl.DataFrame) -> float:
    return fit.log_loss(df["p"].to_numpy(), df["y"].to_numpy())


def paired(
    alt: pl.DataFrame,
    base: pl.DataFrame,
    seasons_from: int = PAIRED_FROM,
    n_boot: int = 2000,
    seed: int = 0,
    ci: float = 0.90,
) -> dict:
    """Δ log loss (alt − base, negative = alt better) on games both scored, seasons ≥ seasons_from,
    with a season-block bootstrap CI (resample whole seasons: games within a season share a fit)."""
    j = (
        alt.select("game_id", "season", "y", pl.col("p").alias("pa"))
        .join(base.select("game_id", pl.col("p").alias("pb")), on="game_id")
        .filter(pl.col("season") >= seasons_from)
    )
    y = j["y"].to_numpy()

    def ll(p):
        p = np.clip(p, 1e-12, 1 - 1e-12)
        return -(y * np.log(p) + (1 - y) * np.log(1 - p))

    d = ll(j["pa"].to_numpy()) - ll(j["pb"].to_numpy())
    seasons = j["season"].to_numpy()
    uniq = np.unique(seasons)
    by = {s: d[seasons == s] for s in uniq}
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        x = np.concatenate([by[s] for s in pick])
        boots.append(x.mean())
    lo, hi = np.quantile(boots, [(1 - ci) / 2, 1 - (1 - ci) / 2])
    wins = sum(1 for s in uniq if by[s].mean() < 0)
    return {
        "n": len(d),
        "ll_alt": float(ll(j["pa"].to_numpy()).mean()),
        "ll_base": float(ll(j["pb"].to_numpy()).mean()),
        "delta": float(d.mean()),
        "lo": float(lo),
        "hi": float(hi),
        "seasons_better": f"{wins}/{len(uniq)}",
    }


@contextmanager
def registry(
    add: dict[str, list] | None = None,
    drop: set[str] | None = None,
    weighted: set[str] | None = None,
) -> Iterator[None]:
    """Temporarily change group membership for an experiment: `add` = {group: [Member, ...]},
    `drop` = features removed from whatever group holds them. Patches the dicts the schema and
    the fitter read, and restores them after. `weighted` lifts context_only from those groups."""
    from dataclasses import replace

    from nfl.approaches import schema
    from nfl.features import groups as reg

    old = dict(reg.GROUPS)
    new = {}
    for gid, g in old.items():
        members = tuple(m for m in g.members if m.feature not in (drop or set()))
        members += tuple((add or {}).get(gid, []))
        ctx = g.context_only and gid not in (weighted or set())
        new[gid] = replace(g, members=members, context_only=ctx)
    try:
        for mod in (reg, schema, fit):
            if hasattr(mod, "GROUPS"):
                mod.GROUPS.clear()
                mod.GROUPS.update(new)
        yield
    finally:
        reg.GROUPS.clear()
        reg.GROUPS.update(old)
