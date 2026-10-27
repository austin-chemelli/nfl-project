"""Strength family: Elo plus season-to-date, prior-shrunk EPA / success / point differential.

Every value for a game uses only games that kicked off strictly before it, within the same season
(regular season and postseason both count). Shrunk mean: (sum_x + n0 * prior) / (n + n0).

Priors (week 1 of a season equals the prior exactly):
  EPA / success: 0.7 * team's full previous-season value + 0.3 * previous-season league mean.
    A team with no previous-season plays (e.g. the first season loaded, 1999) gets the league mean
    of the previous season if one exists; with no previous season at all: 0 for EPA, 0.43 for success.
  point_diff_pg: 0.5 * previous-season point differential per game (0 if none).
Previous-season lookups map franchise relocations through `TEAM_ALIASES` (OAK -> LV, ...).

Extras (M1.11), same strictly-earlier rule:
  pythag_win_pct  PF^2.37 / (PF^2.37 + PA^2.37) to date, shrunk on the ratio toward 0.5:
                  (n * raw + 4 * 0.5) / (n + 4) with n = games played (week 1 = 0.5).
  luck            n / (n + 4) * (raw win% - raw pythag), i.e. the gap shrunk toward 0 (ties = 0.5).
  sos             mean pre-game Elo of opponents already faced this season (1505 before any).
  st_epa_pg       special-teams EPA per game, zero-sum (see `_special_teams`), n0 = 4 games.
  epa_{pass,rush}_{off,def}, epa_early_off (downs 1-2), epa_nongarbage_off (pre-snap wp in
                  [0.1, 0.9]): same shrinkage as epa_off with n0 = 180 / 120 / 300 / 300 plays.
  sack_rate_{off,def}  sacks / dropbacks, n0 = 150 dropbacks, same previous-season prior blend.
  epa_{off,def}_adj    weekly ridge, see `_adjusted`.
  qb_epa, qb_cpoe      follow the projected starter, see `nfl.features.qb`.
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import numpy as np
import polars as pl

from nfl.config import Paths
from nfl.features import qb, store
from nfl.models.elo import TEAM_ALIASES, pregame_ratings

SOURCE = "pbp"
VERSION = "2"

N0_PLAYS = 300.0
N0_GAMES = 4.0
PRIOR_EPA = 0.0
PRIOR_SUCCESS = 0.43
PRIOR_SACK = 0.065
TEAM_W = 0.7  # weight on the team's own previous season in the prior
PD_PRIOR_W = 0.5
PYTH_EXP = 2.37
SOS_PRIOR = 1505.0
N0_PASS = 180.0  # n0 = 300 plays split 60/40 pass/run
N0_RUN = 120.0
N0_DROPBACKS = 150.0
RIDGE_LAMBDA = 20.0  # games' worth of pull toward the previous-season adjusted value
WP_LO, WP_HI = 0.1, 0.9
ST_TYPES = ["kickoff", "punt", "field_goal", "extra_point", "other"]
ST_TWO_SIDED = ("kickoff", "punt")  # return / coverage plays: both units are credited

# (feature, plays side, play column, default prior with no previous season, n0, frame name)
_RATES = [
    ("strength.epa_off", "off", "epa", PRIOR_EPA, N0_PLAYS, "base"),
    ("strength.epa_def", "def", "epa", PRIOR_EPA, N0_PLAYS, "base"),
    ("strength.success_off", "off", "success", PRIOR_SUCCESS, N0_PLAYS, "base"),
    ("strength.success_def", "def", "success", PRIOR_SUCCESS, N0_PLAYS, "base"),
    ("strength.epa_pass_off", "off", "epa", PRIOR_EPA, N0_PASS, "pass"),
    ("strength.epa_pass_def", "def", "epa", PRIOR_EPA, N0_PASS, "pass"),
    ("strength.epa_rush_off", "off", "epa", PRIOR_EPA, N0_RUN, "run"),
    ("strength.epa_rush_def", "def", "epa", PRIOR_EPA, N0_RUN, "run"),
    ("strength.epa_early_off", "off", "epa", PRIOR_EPA, N0_PLAYS, "early"),
    ("strength.epa_nongarbage_off", "off", "epa", PRIOR_EPA, N0_PLAYS, "nongarbage"),
    ("strength.sack_rate_off", "off", "sack", PRIOR_SACK, N0_DROPBACKS, "dropbacks"),
    ("strength.sack_rate_def", "def", "sack", PRIOR_SACK, N0_DROPBACKS, "dropbacks"),
]


def load_plays(paths: Paths, min_season: int) -> pl.DataFrame:
    """Pass/run plays with an EPA (the original strength input; `form` also uses this)."""
    con = duckdb.connect()
    glob = f"{paths.curated_table('plays').as_posix()}/*/*.parquet"
    return con.sql(
        "select game_id, posteam, defteam, cast(epa as double) epa, cast(success as double) success "
        f"from read_parquet('{glob}', hive_partitioning=true) "
        f"where season >= {min_season} and play_type in ('pass','run') and epa is not null "
        "and posteam is not null and defteam is not null"
    ).pl()


def load_plays_all(paths: Paths, min_season: int) -> pl.DataFrame:
    """Every play with both teams known (pass/run, special teams, no-plays) and the columns the
    extras need. Filtering to the analysis sets happens in `compute`."""
    con = duckdb.connect()
    glob = f"{paths.curated_table('plays').as_posix()}/*/*.parquet"
    return con.sql(
        "select game_id, play_id, posteam, defteam, play_type, cast(epa as double) epa, "
        "cast(success as double) success, cast(down as double) down, cast(wp as double) wp, "
        'cast("pass" as double) is_pass, cast(sack as double) sack, '
        "cast(qb_dropback as double) qb_dropback, cast(special_teams_play as double) "
        "special_teams_play, passer_player_id, passer_player_name, cast(qb_epa as double) qb_epa, "
        "cast(cpoe as double) cpoe "
        f"from read_parquet('{glob}', hive_partitioning=true) "
        f"where season >= {min_season} and posteam is not null and defteam is not null"
    ).pl()


def _canon(col: str = "team") -> pl.Expr:
    return pl.col(col).replace(TEAM_ALIASES)


def team_games(games: pl.DataFrame) -> pl.DataFrame:
    """One row per (game, team): season, kickoff, margin (null until played)."""
    base = games.select(
        "game_id",
        pl.col("season").cast(pl.Int64),
        "kickoff_utc",
        "home_team",
        "away_team",
        "result",
    )
    home = base.select(
        "game_id", "season", "kickoff_utc", pl.col("home_team").alias("team"),
        pl.col("result").cast(pl.Float64).alias("margin"),
    )  # fmt: skip
    away = base.select(
        "game_id", "season", "kickoff_utc", pl.col("away_team").alias("team"),
        (-pl.col("result").cast(pl.Float64)).alias("margin"),
    )  # fmt: skip
    return pl.concat([home, away])


def _prev_tables(tot: pl.DataFrame, sum_col: str, n_col: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Previous-season value per (season, ckey) and league mean per season, both keyed by the
    season they will serve as a prior for."""
    prev = tot.with_columns((pl.col("season") + 1).alias("season"))
    league = prev.group_by("season").agg((pl.col(sum_col).sum() / pl.col(n_col).sum()).alias("_lg"))
    team = prev.select("season", "ckey", (pl.col(sum_col) / pl.col(n_col)).alias("_tv"))
    return team, league


def _shrunk(tg: pl.DataFrame, frames: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """tg: team-games sorted for cumulative sums. Returns tg plus one column per `_RATES` entry;
    each is read from the named play frame, shrunk with its own n0."""
    out = tg
    for feat, side, col, default, n0, frame in _RATES:
        key = "posteam" if side == "off" else "defteam"
        valid = frames[frame].filter(pl.col(col).is_not_null())
        # pbp uses current codes for every season (LA, LAC, LV) while games use the historical
        # ones (STL, SD, OAK): match on the canonical franchise code, never the printed one.
        gt = valid.with_columns(_canon(key).alias("ckey")).group_by("game_id", "ckey").agg(
            pl.col(col).sum().alias("_s"), pl.len().cast(pl.Float64).alias("_n")
        )  # fmt: skip
        out = out.join(gt, on=["game_id", "ckey"], how="left").with_columns(
            pl.col("_s").fill_null(0.0), pl.col("_n").fill_null(0.0)
        )
        grp = ["team", "season"]
        out = out.with_columns(
            (pl.col("_s").cum_sum().over(grp) - pl.col("_s")).alias("_cs"),
            (pl.col("_n").cum_sum().over(grp) - pl.col("_n")).alias("_cn"),
        )
        # previous-season totals per (canonical team, season)
        tot = out.group_by("ckey", "season").agg(
            pl.col("_s").sum().alias("_ts"), pl.col("_n").sum().alias("_tn")
        ).filter(pl.col("_tn") > 0)  # fmt: skip
        team_prev, league_prev = _prev_tables(tot, "_ts", "_tn")
        out = out.join(team_prev, on=["season", "ckey"], how="left").join(
            league_prev, on="season", how="left"
        )
        prior_expr = (
            pl.when(pl.col("_tv").is_not_null() & pl.col("_lg").is_not_null())
            .then(TEAM_W * pl.col("_tv") + (1 - TEAM_W) * pl.col("_lg"))
            .when(pl.col("_lg").is_not_null())
            .then(pl.col("_lg"))
            .otherwise(pl.lit(default))
        )
        out = out.with_columns(
            ((pl.col("_cs") + n0 * prior_expr) / (pl.col("_cn") + n0)).alias(feat)
        ).drop("_s", "_n", "_cs", "_cn", "_tv", "_lg")
    return out


def _point_diff(tg: pl.DataFrame) -> pl.DataFrame:
    grp = ["team", "season"]
    played = pl.col("margin").is_not_null().cast(pl.Float64)
    m = pl.col("margin").fill_null(0.0)
    out = tg.with_columns(
        (m.cum_sum().over(grp) - m).alias("_cm"),
        (played.cum_sum().over(grp) - played).alias("_cg"),
    )
    tot = out.group_by("ckey", "season").agg(
        m.sum().alias("_ts"), played.sum().alias("_tn")
    ).filter(pl.col("_tn") > 0)  # fmt: skip
    prev = tot.with_columns(
        (pl.col("season") + 1).alias("season"), (pl.col("_ts") / pl.col("_tn")).alias("_pv")
    ).select("season", "ckey", "_pv")
    out = out.join(prev, on=["season", "ckey"], how="left")
    prior = PD_PRIOR_W * pl.col("_pv").fill_null(0.0)
    return out.with_columns(
        ((pl.col("_cm") + N0_GAMES * prior) / (pl.col("_cg") + N0_GAMES)).alias(
            "strength.point_diff_pg"
        )
    ).drop("_cm", "_cg", "_pv")


def _results(tg: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    """pythag_win_pct, luck and sos. Adds `_gp` (games played before this one) for reuse."""
    grp = ["team", "season"]
    scores = pl.concat(
        [
            games.select(
                "game_id", pl.col("home_team").alias("team"),
                pl.col("home_score").cast(pl.Float64).alias("_pf"),
                pl.col("away_score").cast(pl.Float64).alias("_pa"),
            ),
            games.select(
                "game_id", pl.col("away_team").alias("team"),
                pl.col("away_score").cast(pl.Float64).alias("_pf"),
                pl.col("home_score").cast(pl.Float64).alias("_pa"),
            ),
        ]
    )  # fmt: skip
    elo = pregame_ratings(games)
    opp = pl.concat(
        [
            games.select("game_id", pl.col("home_team").alias("team")).join(
                elo.select("game_id", pl.col("away_elo").alias("_oe")), on="game_id"
            ),
            games.select("game_id", pl.col("away_team").alias("team")).join(
                elo.select("game_id", pl.col("home_elo").alias("_oe")), on="game_id"
            ),
        ]
    )
    played = pl.col("margin").is_not_null().cast(pl.Float64)
    margin = pl.col("margin").fill_null(0.0)
    win = (
        pl.when(margin > 0).then(1.0).when(margin == 0).then(0.5).otherwise(0.0) * played
    )  # unplayed games carry margin null -> weight 0
    out = (
        tg.join(scores, on=["game_id", "team"], how="left")
        .join(opp, on=["game_id", "team"], how="left")
        .with_columns(
            played.alias("_pl"),
            (pl.col("_pf").fill_null(0.0) * played).alias("_pf"),
            (pl.col("_pa").fill_null(0.0) * played).alias("_pa"),
            win.alias("_w"),
            (pl.col("_oe").fill_null(0.0) * played).alias("_oe"),
        )
    )
    cum = lambda c: pl.col(c).cum_sum().over(grp) - pl.col(c)
    out = out.with_columns(
        cum("_pl").alias("_gp"), cum("_pf").alias("_cpf"), cum("_pa").alias("_cpa"),
        cum("_w").alias("_cw"), cum("_oe").alias("_coe"),
    )  # fmt: skip
    pf_e = pl.col("_cpf") ** PYTH_EXP
    pa_e = pl.col("_cpa") ** PYTH_EXP
    raw = pl.when(pf_e + pa_e > 0).then(pf_e / (pf_e + pa_e)).otherwise(0.5)
    n = pl.col("_gp")
    out = out.with_columns(raw.alias("_raw"))
    out = out.with_columns(
        ((n * pl.col("_raw") + N0_GAMES * 0.5) / (n + N0_GAMES)).alias("strength.pythag_win_pct"),
        pl.when(n > 0)
        .then(n / (n + N0_GAMES) * (pl.col("_cw") / n - pl.col("_raw")))
        .otherwise(0.0)
        .alias("strength.luck"),
        pl.when(n > 0).then(pl.col("_coe") / n).otherwise(SOS_PRIOR).alias("strength.sos"),
    )
    return out.drop("_pf", "_pa", "_oe", "_pl", "_w", "_cpf", "_cpa", "_cw", "_coe", "_raw")


def _special_teams(tg: pl.DataFrame, plays: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    """st_epa_pg: season-to-date special-teams EPA per game, (sum + 0) / (games + 4).

    Plays: `special_teams_play` = 1 or play_type in kickoff / punt / field_goal / extra_point (the
    flag is null in 1999-2000 and almost empty in 2003-04; the play types are complete). nflfastR
    gives EPA from the posteam's view; posteam is the receiving team on kickoffs and the kicking
    team on punts, FGs and PATs (checked against the play descriptions). Kickoffs and punts credit
    the posteam +EPA and the defteam -EPA (returns vs coverage, zero-sum); FGs, PATs and the few
    flagged no-plays credit only the posteam (kicker). League-average EPA per play type is
    subtracted first so that kickoff volume (good offenses kick more) and rule changes (kickoff EPA
    drifts 0.4 -> 0.0 -> 0.25) don't leak into the rating; the average uses only the season's games
    that kicked off strictly before the target game.
    """
    grp = ["team", "season"]
    kick = ["kickoff", "punt", "field_goal", "extra_point"]
    st = plays.filter(
        ((pl.col("special_teams_play") == 1) | pl.col("play_type").is_in(kick))
        & pl.col("epa").is_not_null()
        & ~pl.col("play_type").is_in(["pass", "run"])
    ).with_columns(
        pl.when(pl.col("play_type").is_in(kick))
        .then(pl.col("play_type"))
        .otherwise(pl.lit("other"))
        .alias("_t")
    )
    gk = games.select("game_id", pl.col("season").cast(pl.Int64), "kickoff_utc")
    st = st.join(gk, on="game_id")
    keys = tg.select("season", "kickoff_utc").unique().sort("kickoff_utc")
    total = pl.lit(0.0)
    out = tg
    for t in ST_TYPES:
        sub = st.filter(pl.col("_t") == t)
        lg = (
            sub.group_by("season", "kickoff_utc")
            .agg(pl.col("epa").sum().alias("_ls"), pl.len().cast(pl.Float64).alias("_ln"))
            .sort("kickoff_utc")
            .with_columns(
                pl.col("_ls").cum_sum().over("season"), pl.col("_ln").cum_sum().over("season")
            )
        )
        if lg.is_empty():
            lg = pl.DataFrame(
                schema={
                    "season": pl.Int64,
                    "kickoff_utc": keys.schema["kickoff_utc"],
                    "_ls": pl.Float64,
                    "_ln": pl.Float64,
                }
            )
        mean = qb.asof_strictly_before(keys, lg, by=["season"]).select(
            "season",
            "kickoff_utc",
            pl.when(pl.col("_ln") > 0)
            .then(pl.col("_ls") / pl.col("_ln"))
            .otherwise(0.0)
            .alias(f"_m_{t}"),
        )
        two = t in ST_TWO_SIDED
        credits = [
            sub.select(
                "game_id", _canon("posteam").alias("ckey"),
                pl.col("epa").alias("_x"), pl.lit(1.0).alias("_c"),
            )
        ]  # fmt: skip
        if two:
            credits.append(
                sub.select(
                    "game_id",
                    _canon("defteam").alias("ckey"),
                    (-pl.col("epa")).alias("_x"),
                    pl.lit(-1.0).alias("_c"),
                )
            )
        gt = pl.concat(credits).group_by("game_id", "ckey").agg(
            pl.col("_x").sum(), pl.col("_c").sum()
        )  # fmt: skip
        out = (
            out.join(gt, on=["game_id", "ckey"], how="left")
            .join(mean, on=["season", "kickoff_utc"], how="left")
            .with_columns(
                pl.col("_x").fill_null(0.0),
                pl.col("_c").fill_null(0.0),
                pl.col(f"_m_{t}").fill_null(0.0),
            )
            .with_columns(
                (pl.col("_x").cum_sum().over(grp) - pl.col("_x")).alias("_cx"),
                (pl.col("_c").cum_sum().over(grp) - pl.col("_c")).alias("_cc"),
            )
        )
        total = total + (pl.col("_cx") - pl.col(f"_m_{t}") * pl.col("_cc"))
        out = out.with_columns(total.alias("_tot")).drop("_x", "_c", "_cx", "_cc", f"_m_{t}")
        total = pl.col("_tot")
    return out.with_columns(
        (pl.col("_tot") / (pl.col("_gp") + N0_GAMES)).alias("strength.st_epa_pg")
    ).drop("_tot")


def _solve_spd(A: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Gaussian elimination without pivoting (A is symmetric positive definite). LAPACK's solve
    differs in the last bit with memory alignment, which would make identical inputs give
    non-identical features; this is elementwise numpy only, so it is reproducible."""
    n = len(b)
    M = np.hstack([A, b[:, None]]).astype(float)
    for i in range(n):
        M[i] /= M[i, i]
        f = M[:, i].copy()
        f[i] = 0.0
        M -= f[:, None] * M[i][None, :]
    return M[:, n]


def _ridge(
    obs: tuple[np.ndarray, ...], mask: np.ndarray, T: int, pen: np.ndarray, theta0: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """One ridge solve on the masked observations; returns (offense effects, defense effects)."""
    oi, di, hv, yv = (a[mask] for a in obs)
    X = np.zeros((len(yv), 2 + 2 * T))
    r = np.arange(len(yv))
    X[:, 0] = 1.0
    X[:, 1] = hv
    X[r, 2 + oi] = 1.0
    X[r, 2 + T + di] = 1.0
    # einsum, not BLAS: bit-identical results for identical inputs whatever the alignment
    A = np.einsum("ni,nj->ij", X, X) + np.diag(pen)
    b = np.einsum("ni,n->i", X, yv) + pen * theta0
    th = _solve_spd(A, b)
    return th[2 : 2 + T], th[2 + T :]


def _adjusted(games: pl.DataFrame, base: pl.DataFrame, lam: float = RIDGE_LAMBDA) -> pl.DataFrame:
    """Opponent-adjusted EPA/play per (season, week, canonical team): `_adj_off`, `_adj_def`.

    For every (season, week): game-level offense EPA/play (pass + run) of every game of that season
    kicking off strictly before the week's first kickoff is modelled as
        y = mu + h * [offense is the home team] + o[offense team] + d[defense team]
    and solved by ridge with the effects pulled toward 0.7 * the team's previous-season final
    effect (centered to a league mean of zero; teams without one, e.g. expansion, get 0):
        min sum (y - fit)^2 + lam * (|o - o0|^2 + |d - d0|^2),  mu and h unpenalized.
    lam = 20 means the prior counts like 20 games of evidence (each game is one unit-weight
    observation per side). `_adj_off` = o (higher is better); `_adj_def` = d, EPA allowed relative
    to an average defense (lower is better). With no earlier games the solution is exactly the
    prior (week 1). The "final" fit through each season's last game becomes next season's prior.
    """
    g = games.select(
        "game_id",
        pl.col("season").cast(pl.Int64),
        pl.col("week").cast(pl.Int64),
        "kickoff_utc",
        _canon("home_team").alias("_home"),
        _canon("away_team").alias("_away"),
        (pl.col("location").fill_null("Home") == "Home").alias("_hfa"),
    )
    y = (
        base.with_columns(_canon("posteam").alias("_o"), _canon("defteam").alias("_d"))
        .group_by("game_id", "_o", "_d")
        .agg(pl.col("epa").mean().alias("_y"))
        .join(g, on="game_id")
        .with_columns(
            ((pl.col("_o") == pl.col("_home")) & pl.col("_hfa")).cast(pl.Float64).alias("_h")
        )
    )
    rows = []
    prev: dict[str, tuple[float, float]] = {}
    for season in sorted(g["season"].unique().to_list()):
        gs = g.filter(pl.col("season") == season)
        teams = sorted(set(gs["_home"]) | set(gs["_away"]))
        idx = {t: i for i, t in enumerate(teams)}
        T = len(teams)
        ys = y.filter(pl.col("season") == season)
        oi = np.array([idx[t] for t in ys["_o"]], dtype=int)
        di = np.array([idx[t] for t in ys["_d"]], dtype=int)
        hv = ys["_h"].to_numpy()
        yv = ys["_y"].to_numpy()
        kv = ys["kickoff_utc"].to_numpy()
        o0 = np.array([TEAM_W * prev.get(t, (0.0, 0.0))[0] for t in teams])
        d0 = np.array([TEAM_W * prev.get(t, (0.0, 0.0))[1] for t in teams])
        obs = (oi, di, hv, yv)
        theta0 = np.concatenate([[0.0, 0.0], o0, d0])
        pen = np.concatenate([[1e-10, 1e-10], np.full(2 * T, lam)])

        weeks = gs.filter(pl.col("kickoff_utc").is_not_null()).group_by("week").agg(
            pl.col("kickoff_utc").min().alias("_cut")
        )  # fmt: skip
        for wk, cut in weeks.iter_rows():
            o, d = _ridge(obs, kv < np.datetime64(cut), T, pen, theta0)
            rows += [(season, wk, t, o[i], d[i]) for t, i in idx.items()]
        if len(yv):
            o, d = _ridge(obs, np.ones(len(yv), dtype=bool), T, pen, theta0)
            prev = {t: (o[i] - o.mean(), d[i] - d.mean()) for t, i in idx.items()}
    return pl.DataFrame(
        rows,
        schema={
            "season": pl.Int64,
            "week": pl.Int64,
            "ckey": pl.Utf8,
            "strength.epa_off_adj": pl.Float64,
            "strength.epa_def_adj": pl.Float64,
        },
        orient="row",
    )


def compute(games: pl.DataFrame, plays: pl.DataFrame) -> pl.DataFrame:
    """Long (game_id, team, feature, value) for every team-game in `games`.

    `plays`: every play with posteam and defteam (see `load_plays_all`).

    1999 games have no `gametime`, hence a null `kickoff_utc`; chronology there falls back to the
    game date at 17:00 UTC (13:00 ET, the usual Sunday slot) so that every "strictly earlier"
    cut works. The date is the only information used, so same-day games count as simultaneous."""
    if "gameday" in games.columns:
        games = games.with_columns(
            pl.coalesce(
                "kickoff_utc", pl.col("gameday").cast(pl.Datetime("us")) + pl.duration(hours=17)
            ).alias("kickoff_utc")
        )
    tg = (
        team_games(games)
        .join(games.select("game_id", pl.col("week").cast(pl.Int64)), on="game_id")
        .with_columns(_canon().alias("ckey"))
        .sort("team", "season", "kickoff_utc", "game_id", nulls_last=True)
    )
    base = plays.filter(pl.col("play_type").is_in(["pass", "run"]) & pl.col("epa").is_not_null())
    is_pass = pl.col("is_pass").fill_null(0.0) == 1
    frames = {
        "base": base,
        "pass": base.filter(is_pass),
        "run": base.filter(~is_pass),
        "early": base.filter(pl.col("down").is_in([1.0, 2.0])),
        "nongarbage": base.filter(pl.col("wp").is_between(WP_LO, WP_HI)),
        "dropbacks": plays.filter(pl.col("qb_dropback") == 1).with_columns(
            pl.col("sack").fill_null(0.0)
        ),
    }
    tg = _shrunk(tg, frames)
    tg = _point_diff(tg)
    tg = _results(tg, games)
    tg = _special_teams(tg, plays, games)
    adj = _adjusted(games, base)
    tg = tg.join(adj, on=["season", "week", "ckey"], how="left")
    feats = [f for f, *_ in _RATES] + [
        "strength.point_diff_pg",
        "strength.pythag_win_pct",
        "strength.luck",
        "strength.sos",
        "strength.st_epa_pg",
        "strength.epa_off_adj",
        "strength.epa_def_adj",
    ]

    elo = pregame_ratings(games)
    elo_long = pl.concat(
        [
            games.select("game_id", pl.col("home_team").alias("team")).join(
                elo.select("game_id", pl.col("home_elo").alias("value")), on="game_id"
            ),
            games.select("game_id", pl.col("away_team").alias("team")).join(
                elo.select("game_id", pl.col("away_elo").alias("value")), on="game_id"
            ),
        ]
    ).with_columns(pl.lit("strength.elo_pre").alias("feature"))

    long = tg.select("game_id", "team", *feats).unpivot(
        feats, index=["game_id", "team"], variable_name="feature", value_name="value"
    )
    qb_long = qb.compute(tg.select("game_id", "team", "ckey", "season", "kickoff_utc"), plays)
    return pl.concat([elo_long.select(long.columns), long, qb_long.select(long.columns)])


def build(paths: Paths, games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    plays = load_plays_all(paths, int(games["season"].min()))
    values = compute(games, plays)
    return store.from_team_values(values, games, source=SOURCE, version=VERSION, build_ts=build_ts)
