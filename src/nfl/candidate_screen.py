"""The candidate gates (ADR 0026, M23.2): `nfl candidates run` -> `marts/candidates.parquet`.

As of a game in week w = the same season, weeks < w, only games with w >= 4 (`MIN_WEEK`). Inputs are the
`team_week` SQL model (plays) and `games`; nothing here reads a play of week w for a week-w value.

Gates (same math as the throwaway screen of 2026-11-08):
1. Split-half r: odd against even regular-season weeks, one point per team-season.
2. Future: first half (weeks 1-8) against second half (weeks 10-18), per team-season: r with the
   second-half outcome and the partial r beyond the stat the candidate would replace; bootstrap 90% CI
   over team-seasons.
3. Residual: slope of (result - Student spread) and (result - market spread_line) on the standardized
   home-minus-away candidate (totals: home + away against total - Student total, total - total_line),
   in points per SD, season-block bootstrap 90% CI (400 resamples, fixed seed). The Student is the
   `predictions` rows with model_id 'student' and is_backfill. Candidates are oriented by `good`, so a
   positive spread slope means "helps".

Verdicts are constants documented on `verdict` and match ADR 0026.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import polars as pl

from nfl import candidates as cand
from nfl import catalog, io
from nfl.config import Paths
from nfl.models.elo import TEAM_ALIASES

SCREEN_VERSION = "1"
MIN_WEEK = 4
BOOTSTRAPS = 400
SEED = 7
MIN_SPLIT_UNITS = (
    30  # a split candidate needs this many team-seasons in the split-half, else 'none'
)
STABLE = 0.3  # split-half r at or above this: stable
LUCK_BELOW = 0.1  # a luck-type measure under this split-half r is 'luck'
ONE_SCORE = 8
FIRST_HALF = (1, 8)
SECOND_HALF = (10, 18)

# team_week column -> short name; prefixed o_ (side off) and d_ (side def) in the team-game frame.
_TW = {
    "plays": "n", "epa_sum": "epa", "epa_noto_sum": "noto", "success_sum": "succ",
    "dropbacks": "db", "sacks": "sacks", "interceptions": "ints", "fumbles": "fum",
    "fumbles_lost": "fum_lost", "proe_sum": "proe_sum", "proe_n": "proe_n",
    "neutral_plays": "neutral", "wepa_sum": "wepa", "wepa_w": "w",
}  # fmt: skip
SUM_COLS = (
    ["games", "os_wins", "os_games"]
    + [f"o_{v}" for v in _TW.values()]
    + [f"d_{v}" for v in _TW.values()]
)

GATE_COLS = [
    "split_half", "split_half_lo", "split_half_hi", "split_n",
    "future_r", "future_r_lo", "future_r_hi",
    "future_partial", "future_partial_lo", "future_partial_hi", "future_n",
    "resid_st", "resid_st_lo", "resid_st_hi",
    "resid_mk", "resid_mk_lo", "resid_mk_hi", "resid_n",
]  # fmt: skip
_INT_COLS = {"split_n", "future_n", "resid_n"}
SCHEMA: dict[str, pl.DataType] = {
    "candidate": pl.String, "screen_version": pl.String, "run_at": pl.Datetime("us"),
    "label": pl.String, "kind": pl.String, "interesting": pl.Boolean, "note": pl.String,
    "pregame": pl.Boolean, "in_model": pl.Boolean,
    **{c: (pl.Int64 if c in _INT_COLS else pl.Float64) for c in GATE_COLS},
    "verdict": pl.String,
}  # fmt: skip


def ledger_path(paths: Paths):
    return paths.marts / "candidates.parquet"


# ---- verdicts


def verdict(
    split_half: float | None,
    *,
    luck: bool,
    kind: str,
    future_partial_lo: float | None,
    resid_st: tuple[float, float] | None,
    resid_mk: tuple[float, float] | None,
    pregame: bool = True,
) -> str:
    """One of 'use', 'context', 'luck', 'none' (ADR 0026).

    - 'luck': split-half r < LUCK_BELOW (0.1) and the measure is a luck-type candidate: failing the
      stability gate is the point; it becomes a regression or a luck readout, not a rating.
    - 'none': unstable (split-half r < STABLE, 0.3), or no gate passes. A candidate whose split-half is
      not defined (a game-level or player-linked measure) is judged on the residual gate alone.
    - 'context': stable (split-half r >= 0.3) but gates 2 and 3 fail: worth showing, not worth weighting.
    - 'use': stable (or split-half undefined) and the future partial r CI is above 0, or a residual
      CI excludes 0 (against the market in either direction; against the Student only when it is a
      total or the slope is positive: a negative spread slope means the Student already over-weights
      it). **'use' means "go to the shadow approach" (the fourth gate), not "ship".**
    - A candidate that isn't `pregame` (observed wind, the game's actual passer) is capped at
      'context': it can't be known at a lock, so it can't go to the shadow approach.
    """
    if split_half is not None:
        if luck and split_half < LUCK_BELOW:
            return "luck"
        if split_half < STABLE:
            return "none"
    excludes = lambda ci: ci is not None and (ci[0] > 0 or ci[1] < 0)
    st_ok = excludes(resid_st) and (kind == "total" or resid_st[0] > 0)
    if (future_partial_lo is not None and future_partial_lo > 0) or st_ok or excludes(resid_mk):
        return "use" if pregame else "context"
    return "context" if split_half is not None else "none"


# ---- math


def _clean(v) -> float | None:
    return None if v is None or not np.isfinite(v) else float(v)


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or x.std() == 0 or y.std() == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def _partial(y: np.ndarray, x: np.ndarray, c: np.ndarray) -> float:
    if len(x) < 4 or c.std() == 0 or np.allclose(x, c):
        return float("nan")
    ry = y - np.polyval(np.polyfit(c, y, 1), c)
    rx = x - np.polyval(np.polyfit(c, x, 1), c)
    return _pearson(rx, ry)


def _ci(boot: list[float]) -> tuple[float | None, float | None]:
    b = np.array([v for v in boot if np.isfinite(v)])
    if len(b) < 10:
        return None, None
    lo, hi = np.percentile(b, [5, 95])
    return float(lo), float(hi)


def _split_half(x: np.ndarray, y: np.ndarray) -> dict:
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    rng = np.random.default_rng(SEED)
    boot = []
    for _ in range(BOOTSTRAPS):
        i = rng.integers(0, len(x), len(x))
        boot.append(_pearson(x[i], y[i]))
    lo, hi = _ci(boot)
    return {
        "split_half": _clean(_pearson(x, y)) if len(x) else None,
        "split_half_lo": lo, "split_half_hi": hi, "split_n": len(x),
    }  # fmt: skip


def _future(x: np.ndarray, y: np.ndarray, c: np.ndarray, has_base: bool) -> dict:
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(c)
    x, y, c = x[ok], y[ok], c[ok]
    rng = np.random.default_rng(SEED)
    br, bp = [], []
    for _ in range(BOOTSTRAPS):
        i = rng.integers(0, len(x), len(x))
        br.append(_pearson(x[i], y[i]))
        bp.append(_partial(y[i], x[i], c[i]) if has_base else float("nan"))
    r_lo, r_hi = _ci(br)
    p_lo, p_hi = _ci(bp)
    return {
        "future_r": _clean(_pearson(x, y)), "future_r_lo": r_lo, "future_r_hi": r_hi,
        "future_partial": _clean(_partial(y, x, c)) if has_base else None,
        "future_partial_lo": p_lo, "future_partial_hi": p_hi, "future_n": len(x),
    }  # fmt: skip


def slope_ci(x: np.ndarray, y: np.ndarray, seasons: np.ndarray) -> tuple:
    """Slope of y on the standardized x (y units per SD of x) with a season-block bootstrap 90% CI."""
    ok = np.isfinite(x) & np.isfinite(y)
    x, y, seasons = x[ok], y[ok], seasons[ok]
    if len(x) < 30 or x.std() == 0:
        return None, None, None, len(x)
    z = (x - x.mean()) / x.std()
    us = np.unique(seasons)
    stats = np.array(
        [[m.sum(), z[m].sum(), y[m].sum(), (z[m] * y[m]).sum(), (z[m] ** 2).sum()]
         for m in (seasons == s for s in us)]
    )  # fmt: skip

    def slope(w: np.ndarray) -> float:
        n, sz, sy, szy, szz = w @ stats
        d = n * szz - sz * sz
        return float((n * szy - sz * sy) / d) if d > 0 else float("nan")

    rng = np.random.default_rng(SEED)
    boot = [
        slope(np.bincount(rng.integers(0, len(us), len(us)), minlength=len(us)).astype(float))
        for _ in range(BOOTSTRAPS)
    ]
    lo, hi = _ci(boot)
    return slope(np.ones(len(us))), lo, hi, len(x)


# ---- frames


def _canon(col: str) -> pl.Expr:
    return pl.col(col).replace(TEAM_ALIASES)


def team_games(tw: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    """One row per (game, team) of the regular season: that game's own sums (SUM_COLS), games = 1.

    `tw` is the team_week model; `games` needs game_id, season, week, home_team, away_team, result.
    Games' historical codes (STL, SD, OAK) map to the franchise code plays print."""
    base = games.filter(pl.col("result").is_not_null())
    rows = pl.concat(
        [
            base.select(
                "game_id", "season", "week", _canon("home_team").alias("team"),
                pl.col("result").alias("margin"),
            ),
            base.select(
                "game_id", "season", "week", _canon("away_team").alias("team"),
                (-pl.col("result")).alias("margin"),
            ),
        ]
    )  # fmt: skip
    close = pl.col("margin").abs() <= ONE_SCORE
    rows = rows.with_columns(
        pl.lit(1.0).alias("games"),
        pl.when(close).then(pl.when(pl.col("margin") > 0).then(1.0).when(pl.col("margin") == 0)
                            .then(0.5).otherwise(0.0)).otherwise(0.0).alias("os_wins"),
        close.cast(pl.Float64).alias("os_games"),
    )  # fmt: skip
    agg = tw.group_by("game_id", "team").agg(
        [
            pl.col(src).filter(pl.col("side") == side).sum().cast(pl.Float64).alias(f"{p}_{dst}")
            for p, side in (("o", "off"), ("d", "def"))
            for src, dst in _TW.items()
        ]
    )
    return (
        rows.join(agg, on=["game_id", "team"], how="left")
        .with_columns(
            pl.col(c).fill_null(0.0) for c in SUM_COLS if c not in ("games", "os_wins", "os_games")
        )
        .drop("margin")
    )


def asof_frame(tg: pl.DataFrame, cols: list[str] | None = None) -> pl.DataFrame:
    """For every team-game (week w), the sums over that team's games of the same season with week < w.

    The only place the screen's as-of rule lives: `week_j < week`, strictly. Teams with no earlier
    game (week 1, or after nothing played) have no row. `cols` defaults to SUM_COLS."""
    cols = cols or SUM_COLS
    past = tg.select("season", "team", pl.col("week").alias("wk"), *cols)
    return (
        tg.select("game_id", "season", "week", "team")
        .join(past, on=["season", "team"])
        .filter(pl.col("wk") < pl.col("week"))
        .group_by("game_id", "season", "week", "team")
        .agg(pl.col(c).sum() for c in cols)
    )


SPLIT_COLS = ["s_n", "s_epa", "r_n", "r_epa"]


def split_team_games(tsw: pl.DataFrame, tg: pl.DataFrame, split: str, side: str) -> pl.DataFrame:
    """`tg` (team_games, so the outcome columns of the future gate stay) plus, for one split's unit
    (M25.2): `s_n`, `s_epa` the plays and EPA in the situation (flag true), `r_n`, `r_epa` outside it
    (flag false).
    `tsw` is the team_split_week model; a game with no row for the split (FTN not charted, an opponent
    tier before Week 4) has zeros, so its gap is null."""
    agg = (
        tsw.filter((pl.col("split") == split) & (pl.col("side") == side))
        .group_by("game_id", "team")
        .agg(
            pl.col("plays").filter(pl.col("flag")).sum().cast(pl.Float64).alias("s_n"),
            pl.col("epa_sum").filter(pl.col("flag")).sum().cast(pl.Float64).alias("s_epa"),
            pl.col("plays").filter(~pl.col("flag")).sum().cast(pl.Float64).alias("r_n"),
            pl.col("epa_sum").filter(~pl.col("flag")).sum().cast(pl.Float64).alias("r_epa"),
        )
    )
    return tg.join(agg, on=["game_id", "team"], how="left").with_columns(
        pl.col(c).fill_null(0.0) for c in SPLIT_COLS
    )


def qb_sack_frame(con, season_from: int) -> pl.DataFrame:
    """Per (game_id, team): the game's main passer's sacks per dropback in his earlier games (this and
    two prior seasons, any team), shrunk with 200 dropbacks at 6.5%. Needs plays directly. The passer
    is the one who threw most in this game, so the value is post-game information."""
    return con.sql(f"""
        with qg as (
            select season, week, game_id, posteam team, passer_player_id qb,
                sum(coalesce(qb_dropback, 0)) db, sum(coalesce(sack, 0)) sacks
            from plays
            where season >= {season_from - 2} and season_type = 'REG' and passer_player_id is not null
            group by all
        ), starter as (
            select * from (
                select *, row_number() over (partition by game_id, team order by db desc, qb) rk from qg
            ) where rk = 1
        )
        select s.game_id, s.team,
            (coalesce(sum(h.sacks), 0) + 200 * 0.065) / (coalesce(sum(h.db), 0) + 200) as qb_sack_rate
        from starter s left join qg h
            on h.qb = s.qb and (h.season * 100 + h.week) < (s.season * 100 + s.week)
            and h.season >= s.season - 2
        group by s.game_id, s.team
    """).pl()


def _agg_weeks(tg: pl.DataFrame, lo: int, hi: int, cols: list[str] | None = None) -> pl.DataFrame:
    return (
        tg.filter(pl.col("week").is_between(lo, hi))
        .group_by("season", "team")
        .agg(pl.col(c).sum() for c in cols or SUM_COLS)
    )


def _aligned(a: pl.DataFrame, b: pl.DataFrame, ea: pl.Expr, eb: pl.Expr):
    j = (
        a.select("season", "team", ea.alias("a"))
        .join(b.select("season", "team", eb.alias("b")), on=["season", "team"])
        .sort("season", "team")
    )  # join order is not stable, and the bootstrap indexes rows
    return j["a"].to_numpy().astype(float), j["b"].to_numpy().astype(float)


_OUTCOME = {
    "off": cand.BASE["epa_off"],
    "def": cand.BASE["epa_def"],
    "net": cand.BASE["epa_net"],
}


def team_gates(c: cand.Candidate, tg: pl.DataFrame, cols: list[str] | None = None) -> dict:
    """Gates 1 and 2 for a team-level candidate on the regular-season team-games `tg`.

    A split candidate (M25.2) passes its own frame `tg` (`split_team_games`) and `cols`; the gap is
    then computed per team-season over odd and over even weeks (and over the two halves), each needing
    `MIN_SPLIT_PLAYS` plays on both sides or the unit drops out of that gate."""
    out: dict = {}
    sign = float(c.good)
    v = c.value() * sign
    odd = _agg_weeks(tg.filter(pl.col("week") % 2 == 1), 1, 30, cols)
    even = _agg_weeks(tg.filter(pl.col("week") % 2 == 0), 1, 30, cols)
    out |= _split_half(*_aligned(odd, even, v, v))
    if c.outcome:
        first, second = _agg_weeks(tg, *FIRST_HALF, cols), _agg_weeks(tg, *SECOND_HALF, cols)
        x, y = _aligned(first, second, v, _OUTCOME[c.outcome]())
        ctrl = _aligned(first, second, cand.BASE[c.replaces](), v)[0] if c.replaces else x * 0
        out |= _future(x, y, ctrl, bool(c.replaces))
    return out


def game_sample(con, season_from: int) -> pl.DataFrame:
    """Regular-season games with a result and a Student backfill forecast."""
    return con.sql(f"""
        select g.game_id, g.season, g.week, g.home_team, g.away_team, g.result, g.total,
            g.spread_line, g.total_line, g.roof, g.wind,
            p.spread_home as st_spread, p.total as st_total
        from games g join predictions p
            on p.game_id = g.game_id and p.model_id = 'student' and p.is_backfill
        where g.game_type = 'REG' and g.result is not null and g.season >= {season_from}
    """).pl()


def residual_gates(c: cand.Candidate, games: pl.DataFrame, asof: pl.DataFrame, qb=None) -> dict:
    """Gate 3: slopes of the Student's and the market's residual on the standardized candidate."""
    games = games.filter(pl.col("week") >= MIN_WEEK)
    if c.level == "game":
        games = games.with_columns(c.value().alias("_x"))
        x = games["_x"].to_numpy().astype(float)
    else:
        a = asof
        if qb is not None:
            a = a.join(qb, on=["game_id", "team"], how="left")
        a = a.select("game_id", "team", (c.value() * float(c.good)).alias("_v"))
        games = (
            games.with_columns(_canon("home_team").alias("_h"), _canon("away_team").alias("_a"))
            .join(a.rename({"_v": "_vh"}), left_on=["game_id", "_h"], right_on=["game_id", "team"])
            .join(a.rename({"_v": "_va"}), left_on=["game_id", "_a"], right_on=["game_id", "team"])
        )
        vh, va = games["_vh"].to_numpy().astype(float), games["_va"].to_numpy().astype(float)
        x = vh - va if c.kind == "spread" else vh + va
    if c.kind == "spread":
        y_st, y_mk = games["result"] - games["st_spread"], games["result"] - games["spread_line"]
    else:
        y_st, y_mk = games["total"] - games["st_total"], games["total"] - games["total_line"]
    seasons = games["season"].to_numpy()
    st = slope_ci(x, y_st.to_numpy().astype(float), seasons)
    mk = slope_ci(x, y_mk.to_numpy().astype(float), seasons)
    return {
        "resid_st": st[0], "resid_st_lo": st[1], "resid_st_hi": st[2],
        "resid_mk": mk[0], "resid_mk_lo": mk[1], "resid_mk_hi": mk[2], "resid_n": mk[3],
    }  # fmt: skip


# ---- ledger


def screen(con, season_from: int = 2006, only: str | None = None) -> list[dict]:
    """Run the gates for every candidate (or `only` one); returns ledger rows (without run_at)."""
    if "team_week" not in {d["name"] for d in catalog.describe(con)}:
        raise ValueError("no team_week table: run `nfl models build` first")
    if only and only not in cand.BY_ID:
        raise ValueError(f"no candidate {only!r}; have {', '.join(cand.BY_ID)}")
    chosen = [cand.BY_ID[only]] if only else list(cand.CANDIDATES)
    games_all = con.sql(
        f"select * from games where game_type = 'REG' and season >= {season_from}"
    ).pl()
    tw = con.sql(
        f"select * from team_week where season_type = 'REG' and season >= {season_from}"
    ).pl()
    tg = team_games(tw, games_all)
    asof = asof_frame(tg)
    if "team_split_week" not in {d["name"] for d in catalog.describe(con)}:
        if only:  # a full run without the split model still screens the rest
            if cand.BY_ID[only].frame == "team_split_week":
                raise ValueError("no team_split_week table: run `nfl models build` first")
        else:
            chosen = [c for c in chosen if c.frame != "team_split_week"]
    need_split = any(c.frame == "team_split_week" for c in chosen)
    tsw = (
        con.sql(
            f"select * from team_split_week where season >= {season_from} "
            "and game_id in (select game_id from games where game_type = 'REG')"
        ).pl()
        if need_split
        else None
    )
    split_cols = SUM_COLS + SPLIT_COLS
    games = game_sample(con, season_from)
    qb = qb_sack_frame(con, season_from) if any(c.id == "qb_sack_rate" for c in chosen) else None
    rows = []
    for c in chosen:
        g: dict = {k: None for k in GATE_COLS}
        c_asof = asof
        if c.frame == "team_split_week":
            ctg = split_team_games(tsw, tg, c.split, c.side)
            g |= team_gates(c, ctg, split_cols)
            if g["split_n"] < MIN_SPLIT_UNITS:  # too rare a situation: no r, and no verdict
                g |= {"split_half": None, "split_half_lo": None, "split_half_hi": None}
            c_asof = asof_frame(ctg, split_cols)
        elif c.level == "team" and c.halves:
            g |= team_gates(c, tg)
        g |= residual_gates(c, games, c_asof, qb if c.id == "qb_sack_rate" else None)
        g = {k: _clean(v) if k not in _INT_COLS else v for k, v in g.items()}
        rows.append(
            {
                "candidate": c.id, "screen_version": SCREEN_VERSION, "label": c.label,
                "kind": c.kind, "interesting": c.interesting, "note": c.note,
                "pregame": c.pregame, "in_model": c.in_model, **g,
                "verdict": verdict(
                    (0.0 if c.frame == "team_split_week" and g["split_half"] is None
                     else g["split_half"]) if c.halves and c.level == "team" else None,
                    luck=c.luck, kind=c.kind, future_partial_lo=g["future_partial_lo"],
                    resid_st=_interval(g, "resid_st"), resid_mk=_interval(g, "resid_mk"),
                    pregame=c.pregame,
                ),
            }
        )  # fmt: skip
    return rows


def _interval(g: dict, p: str) -> tuple[float, float] | None:
    return None if g[p] is None or g[p + "_lo"] is None else (g[p + "_lo"], g[p + "_hi"])


def latest(paths: Paths) -> pl.DataFrame:
    """The newest ledger row per candidate."""
    df = io.read(ledger_path(paths), SCHEMA)
    return df.sort("run_at").group_by("candidate", maintain_order=True).last()


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) or isinstance(b, float):
        return abs(a - b) <= 1e-9 + 1e-9 * abs(b)
    return a == b


def run(paths: Paths, only: str | None = None, season_from: int = 2006) -> int:
    """Screen and append rows that differ from the candidate's latest row (same screen_version and
    identical numbers, label, kind, flag and note append nothing). Returns rows appended."""
    con = catalog.connect(paths)
    rows = screen(con, season_from, only)
    prev = {r["candidate"]: r for r in latest(paths).iter_rows(named=True)}
    now = datetime.now(UTC).replace(tzinfo=None)
    new = []
    for r in rows:
        p = prev.get(r["candidate"])
        if (
            p
            and p["screen_version"] == r["screen_version"]
            and all(_same(r[k], p[k]) for k in r if k != "screen_version")
        ):
            continue
        new.append({**r, "run_at": now})
    if not new:
        return 0
    return io.append(ledger_path(paths), pl.DataFrame(new, schema_overrides=SCHEMA), SCHEMA)
