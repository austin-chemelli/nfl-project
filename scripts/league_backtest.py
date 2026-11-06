"""Calibrate the team-strength shock sigma for the league simulation (M14.9). Read-only.

For seasons 2010-2025 and cuts at 6, 9 and 12 games played, freeze the inputs at the cut, simulate
the rest of the regular season (400 runs per sigma) and score P(playoffs) per team with log loss
against the actual qualifiers (teams that played a postseason game; 6 seeds a conference through
2019, 7 from 2020).

Two inputs, both frozen at the cut:
  student  proxy: Student backfill rows for games that kicked off before the cut (their lock
           timestamps precede the cut) -> `fit_ratings` (recency weighted) -> `price` for every
           remaining game. A backfill row for a remaining game was scored just before it, knowing
           every result up to then, so it is never used. The script asserts this.
  elo      Elo ratings as of the cut, no updates after it.

Usage: uv run python scripts/league_backtest.py DATA_ROOT [--out NOTE.md] [--raw rows.parquet]
Never writes under DATA_ROOT. `--raw` also serves as a cache: if it exists, simulation is skipped.
"""

from __future__ import annotations

import argparse
import itertools
import math
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import polars as pl

from nfl.league.divisions import DIVISIONS
from nfl.league.inputs import HALF_LIFE_DAYS, STUDENT_ID, fit_ratings, price
from nfl.league.simulate import simulate_season
from nfl.league.standings import GameResult, canon
from nfl.models.elo import Elo, EloParams

SEASONS = range(2010, 2026)
CUTS = (6, 9, 12)  # games played by every team
SIGMAS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0)
N_RUNS = 400
CLIP = 1 / (2 * N_RUNS)
BOOT = 2000
LN10_400 = math.log(10) / 400
BUCKETS = (0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0001)

_G: pl.DataFrame
_P: pl.DataFrame
_ELO: dict[tuple[int, int], dict[str, float]]
_CUT_TS: dict[tuple[int, int], object]


def n_seeds(season: int) -> int:
    return 7 if season >= 2020 else 6


def load(root: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    g = pl.read_parquet(str(root / "curated" / "games") + "/*/*.parquet", hive_partitioning=True)
    g = g.filter((pl.col("season") >= 2002) & (pl.col("season") <= max(SEASONS)))
    p = pl.read_parquet(root / "marts" / "predictions.parquet").filter(
        (pl.col("model_id") == STUDENT_ID) & pl.col("is_backfill") & pl.col("p_home").is_not_null()
    )
    return g, p


def find_cut(reg: pl.DataFrame, n: int):
    """Earliest week boundary (a week's first kickoff) before which every team has played >= n.

    Games with kickoff < cut count as played; the rest are remaining.
    """
    for cut in sorted(reg.group_by("week").agg(pl.col("kickoff_utc").min())["kickoff_utc"]):
        played = reg.filter(pl.col("kickoff_utc") < cut)
        counts = pl.concat([played["home_team"], played["away_team"]]).value_counts()
        if counts.height == 32 and counts["count"].min() >= n:
            return cut
    raise ValueError(f"no cut with {n} games played")


def actual_qualifiers(g: pl.DataFrame, season: int) -> set[str]:
    post = g.filter((pl.col("season") == season) & (pl.col("game_type") != "REG"))
    return {canon(t) for t in [*post["home_team"], *post["away_team"]]}


def elo_snapshots(g: pl.DataFrame, cuts: dict[tuple[int, int], object]):
    """Walk Elo through all games in kickoff order; copy ratings at each cut (no update after)."""
    out: dict[tuple[int, int], dict[str, float]] = {}
    pending = sorted(cuts.items(), key=lambda kv: kv[1])
    e = Elo(EloParams())
    for r in g.sort("kickoff_utc", "game_id", nulls_last=True).iter_rows(named=True):
        while pending and r["kickoff_utc"] >= pending[0][1]:
            out[pending.pop(0)[0]] = dict(e.ratings)
        e.new_season(r["season"])
        if r["result"] is not None:
            e.update(
                r["home_team"], r["away_team"], r["result"], (r["location"] or "Home") != "Home"
            )
    return out


def student_inputs(reg: pl.DataFrame, preds: pl.DataFrame, cut):
    """(ratings, home term) from Student rows of games kicked off before the cut."""
    played = reg.filter(pl.col("kickoff_utc") < cut)
    rows = preds.join(
        played.select("game_id", "kickoff_utc", "home_team", "away_team"), on="game_id"
    ).filter(pl.col("lock_ts") < cut)
    rem_ids = set(reg.filter(pl.col("kickoff_utc") >= cut)["game_id"])
    # the leakage guard: nothing stamped at or after the cut, nothing for a remaining game
    assert rows["lock_ts"].max() < cut, "a Student row stamped at or after the cut was used"
    assert not rem_ids & set(rows["game_id"]), "a Student row for a remaining game was used"
    assert (rows["lock_ts"] <= rows["kickoff_utc"]).all()
    age = (cut - rows["kickoff_utc"]).dt.total_days().to_numpy()
    fit_in = pl.DataFrame(
        {
            "home": [canon(t) for t in rows["home_team"]],
            "away": [canon(t) for t in rows["away_team"]],
            "p": rows["p_home"],
            "weight": 0.5 ** (age / HALF_LIFE_DAYS),
        }
    )
    return fit_ratings(fit_in, sorted(DIVISIONS))


def run_task(task: tuple[int, int, str]) -> list[tuple]:
    season, n, kind = task
    reg = _G.filter((pl.col("season") == season) & (pl.col("game_type") == "REG"))
    cut = _CUT_TS[(season, n)]
    played = reg.filter(pl.col("kickoff_utc") < cut)
    rem = reg.filter(pl.col("kickoff_utc") >= cut).sort("kickoff_utc", "game_id")
    home = [canon(t) for t in rem["home_team"]]
    away = [canon(t) for t in rem["away_team"]]
    results = [
        GameResult.from_scores(h, a, hs, a_s)
        for h, a, hs, a_s in played.select(
            "home_team", "away_team", "home_score", "away_score"
        ).iter_rows()
    ]
    if kind == "student":
        fit = student_inputs(reg, _P, cut)
        p = np.array([price(fit, h, a) for h, a in zip(home, away, strict=True)])
        ratings, hadv = fit.ratings, fit.home
    else:
        e = Elo(EloParams(), ratings=dict(_ELO[(season, n)]), season=season)
        p = np.array(
            [
                e.predict(h, a, (loc or "Home") != "Home")["p_home"]
                for h, a, loc in zip(home, away, rem["location"], strict=True)
            ]
        )
        ratings = {t: e.rating(t) * LN10_400 for t in DIVISIONS}
        hadv = e.params.hfa * LN10_400
    actual = actual_qualifiers(_G, season)
    seed = season * 1000 + n  # same draws for every sigma and input at this season and cut
    out = []
    for sigma in SIGMAS:
        r = simulate_season(
            results, list(rem["game_id"]), home, away, p, ratings,
            sigma=sigma, home_adv=hadv, n_runs=N_RUNS, rng=seed, n_seeds=n_seeds(season),
        )  # fmt: skip
        out += [(season, n, kind, sigma, t, o.playoffs, t in actual) for t, o in r.teams.items()]
    return out


def init_worker(root: Path) -> None:
    """Load the data and the frozen inputs once per worker (spawn: polars is not fork-safe)."""
    global _G, _P, _ELO, _CUT_TS
    _G, _P = load(root)
    _CUT_TS = {}
    for s in SEASONS:
        reg = _G.filter((pl.col("season") == s) & (pl.col("game_type") == "REG"))
        for n in CUTS:
            _CUT_TS[(s, n)] = find_cut(reg, n)
    _ELO = elo_snapshots(_G, _CUT_TS)


def simulate_all(root: Path, workers: int) -> pl.DataFrame:
    tasks = [(s, n, k) for s in SEASONS for n in CUTS for k in ("student", "elo")]
    with ProcessPoolExecutor(
        workers, mp_context=multiprocessing.get_context("spawn"), initializer=init_worker,
        initargs=(root,),
    ) as ex:  # fmt: skip
        rows = [r for part in ex.map(run_task, tasks) for r in part]
    return pl.DataFrame(
        rows, schema=["season", "cut", "input", "sigma", "team", "p", "y"], orient="row"
    )


# --- analysis ------------------------------------------------------------------------------


def with_loss(df: pl.DataFrame) -> pl.DataFrame:
    pc = pl.col("p").clip(CLIP, 1 - CLIP)
    y = pl.col("y").cast(pl.Float64)
    return df.with_columns(ll=-(y * pc.log() + (1 - y) * (1 - pc).log()))


def season_sums(df: pl.DataFrame, kind: str, cuts=CUTS):
    """(sigma list, per-season loss sums [season, sigma], per-season counts)."""
    d = df.filter((pl.col("input") == kind) & pl.col("cut").is_in(list(cuts)))
    agg = (
        d.group_by("season", "sigma").agg(s=pl.col("ll").sum(), n=pl.len()).sort("season", "sigma")
    )
    seasons = sorted(agg["season"].unique())
    s = np.array(agg["s"]).reshape(len(seasons), len(SIGMAS))
    n = np.array(agg["n"]).reshape(len(seasons), len(SIGMAS))[:, 0]
    return s, n


def boot_diff(s: np.ndarray, n: np.ndarray, a: int, b: int, rng):
    """Mean log loss of column a minus b: (point, se, lo, hi), resampling seasons."""
    idx = rng.integers(0, len(n), (BOOT, len(n)))
    d = (s[idx, a].sum(1) - s[idx, b].sum(1)) / n[idx].sum(1)
    point = (s[:, a].sum() - s[:, b].sum()) / n.sum()
    return point, d.std(), *np.percentile(d, [2.5, 97.5])


def reliability(df: pl.DataFrame, kind: str, sigma: float) -> list[tuple]:
    d = df.filter((pl.col("input") == kind) & (pl.col("sigma") == sigma))
    out = []
    for lo, hi in itertools.pairwise(BUCKETS):
        b = d.filter((pl.col("p") >= lo) & (pl.col("p") < hi))
        out.append(
            (
                lo,
                hi,
                b.height,
                b["p"].mean() if b.height else None,
                b["y"].mean() if b.height else None,
            )
        )
    return out


def label(lo, hi):
    return "<10%" if lo == 0 else ">90%" if hi > 1 else f"{lo:.0%}-{hi:.0%}"


def choose(s, n, rng):
    """Best sigma by pooled loss; then the smallest sigma not worse than best by more than 1 SE."""
    mean = s.sum(0) / n.sum()
    best = int(mean.argmin())
    for j in range(len(SIGMAS)):
        point, se, *_ = boot_diff(s, n, j, best, rng)
        if point <= se:
            return j, best
    return best, best


def report(df: pl.DataFrame) -> str:
    df = with_loss(df)
    rng = np.random.default_rng(0)
    L: list[str] = []
    w = L.append
    for kind, title in (("student", "Student proxy"), ("elo", "Frozen Elo")):
        w(f"## Log loss, {title}\n")
        w("| sigma | " + " | ".join(f"{n} games" for n in CUTS) + " | pooled |")
        w("|---|" + "---|" * (len(CUTS) + 1))
        per = {n: season_sums(df, kind, (n,)) for n in CUTS}
        s_all, n_all = season_sums(df, kind)
        for j, sg in enumerate(SIGMAS):
            cells = [f"{per[n][0][:, j].sum() / per[n][1].sum():.4f}" for n in CUTS]
            w(f"| {sg} | " + " | ".join(cells) + f" | {s_all[:, j].sum() / n_all.sum():.4f} |")
        w("")
        w(f"### Difference from sigma 0, {title}, pooled (season bootstrap, {BOOT} draws)\n")
        w(
            "| sigma | pooled | SE | 95% interval | "
            + " | ".join(f"{n}g diff (SE)" for n in CUTS)
            + " |"
        )
        w("|---|---|---|---|" + "---|" * len(CUTS))
        for j, sg in enumerate(SIGMAS[1:], 1):
            p, se, lo, hi = boot_diff(s_all, n_all, j, 0, rng)
            cc = []
            for n in CUTS:
                q, qse, *_ = boot_diff(*per[n], j, 0, rng)
                cc.append(f"{q:+.4f} ({qse:.4f})")
            w(f"| {sg} | {p:+.4f} | {se:.4f} | [{lo:+.4f}, {hi:+.4f}] | " + " | ".join(cc) + " |")
        w("")
        j, best = choose(s_all, n_all, rng)
        w(f"Best pooled sigma {SIGMAS[best]}; smallest sigma within 1 SE of it: **{SIGMAS[j]}**.\n")
    w(
        "## Reliability by sigma (pooled over seasons and cuts; predicted mean / observed rate / n)\n"
    )
    for kind, title in (("student", "Student proxy"), ("elo", "Frozen Elo")):
        w(f"### {title}\n")
        rel = {sg: reliability(df, kind, sg) for sg in SIGMAS}
        w("| bucket | " + " | ".join(f"sigma {sg}" for sg in SIGMAS) + " |")
        w("|---|" + "---|" * len(SIGMAS))
        for i, (lo, hi, *_rest) in enumerate(rel[SIGMAS[0]]):
            cells = []
            for sg in SIGMAS:
                _, _, nn, pm, ym = rel[sg][i]
                cells.append("-" if not nn else f"{pm:.2f} / {ym:.2f} / {nn}")
            w(f"| {label(lo, hi)} | " + " | ".join(cells) + " |")
        w("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--raw", type=Path, help="parquet of team-season rows; reused if it exists")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    t0 = time.perf_counter()
    if a.raw and a.raw.exists():
        df = pl.read_parquet(a.raw)
    else:
        df = simulate_all(a.root, a.workers)
        if a.raw:
            df.write_parquet(a.raw)
    print(f"simulated in {time.perf_counter() - t0:.0f}s", flush=True)
    text = report(df)
    if a.out:
        a.out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
