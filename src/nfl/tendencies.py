"""Team tendency aggregates with shrinkage toward the league rate and recency decay (M1.5).

Output marts/tendencies.parquet, long format:
  season, team, side ('off'|'def'), situation, metric, n, raw_rate, n_eff, rate, as_of_week
`raw_rate` is the plain empirical rate; `rate` is the shrunk, recency-weighted estimate.
Offense metrics are computed over the team's own plays; defense metrics over opponents' plays
against the team. FTN-based metrics exist from 2022.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import duckdb
import polars as pl

from nfl.config import Paths
from nfl.models.elo import TEAM_ALIASES

SITUATIONS: dict[str, str] = {
    "all": "true",
    "early_down": "down in (1, 2)",
    "third_down": "down = 3",
    "third_and_long": "down = 3 and ydstogo >= 7",
    "red_zone": "yardline_100 <= 20",
    "trailing_7plus": "score_differential <= -7",
    "leading_7plus": "score_differential >= 7",
    "two_minute": "half_seconds_remaining <= 120",
    "first_half": "qtr <= 2",
}

# metric -> (numerator expression, denominator filter). Rates are avg(numerator) over rows passing the filter.
OFFENSE: dict[str, tuple[str, str]] = {
    "pass_rate": ("pass", "play_type in ('pass','run')"),
    "shotgun_rate": ("shotgun", "play_type in ('pass','run')"),
    "no_huddle_rate": ("no_huddle", "play_type in ('pass','run')"),
    "motion_rate": ("is_motion::int", "has_ftn and play_type in ('pass','run')"),
    "play_action_rate": ("is_play_action::int", "has_ftn and play_type = 'pass'"),
    "rpo_rate": ("is_rpo::int", "has_ftn and play_type in ('pass','run')"),
    "screen_rate": ("is_screen_pass::int", "has_ftn and play_type = 'pass'"),
    "under_center_rate": ("(qb_location = 'U')::int", "has_ftn and play_type in ('pass','run')"),
    "epa_per_play": ("epa", "play_type in ('pass','run')"),
    "success_rate": ("success", "play_type in ('pass','run')"),
    "fourth_down_go_rate": (
        "(play_type in ('pass','run'))::int",
        "down = 4 and play_type in ('pass','run','punt','field_goal')",
    ),
}
DEFENSE: dict[str, tuple[str, str]] = {
    "blitz_rate": ("(n_blitzers >= 1)::int", "has_ftn and qb_dropback = 1"),
    "pass_rushers_5plus_rate": ("(n_pass_rushers >= 5)::int", "has_ftn and qb_dropback = 1"),
    "box_8plus_vs_run_rate": ("(n_defense_box >= 8)::int", "has_ftn and play_type = 'run'"),
    "box_6minus_vs_run_rate": ("(n_defense_box <= 6)::int", "has_ftn and play_type = 'run'"),
    "epa_per_play_allowed": ("epa", "play_type in ('pass','run')"),
    "success_rate_allowed": ("success", "play_type in ('pass','run')"),
    "pass_rate_faced": ("pass", "play_type in ('pass','run')"),
}


N0 = 50.0  # prior strength in plays
HALF_LIFE_WEEKS = 6.0
_KEY = ["side", "situation", "metric"]

_OUT_COLS = [
    "season",
    "team",
    "side",
    "situation",
    "metric",
    "n",
    "raw_rate",
    "n_eff",
    "rate",
    "as_of_week",
]


def _weekly_query(
    side: str,
    team_col: str,
    metrics: dict[str, tuple[str, str]],
    situation: str,
    cond: str,
    plays: str,
    seasons: list[int],
) -> str:
    aggs = []
    for m, (num, denom) in metrics.items():
        aggs.append(f'count({num}) filter (where {denom}) as "n__{m}"')
        aggs.append(f'sum({num}) filter (where {denom}) as "sx__{m}"')
    in_list = ", ".join(str(int(s)) for s in seasons)
    return f"""
    select season, week, {team_col} as team, {", ".join(aggs)}
    from read_parquet('{plays}', hive_partitioning=true)
    where season in ({in_list}) and {team_col} is not null and play_type is not null and ({cond})
    group by 1, 2, 3
    """


def weekly_aggregates(
    con: duckdb.DuckDBPyConnection,
    paths: Paths,
    seasons: list[int],
    situations: list[str] | None = None,
) -> pl.DataFrame:
    """Per (season, week, team, side, situation, metric): play count n and sum of the 0/1 or EPA value sx.

    `situations` restricts the SITUATIONS computed (default: all); callers needing one or two use it for speed."""
    plays = f"{paths.curated_table('plays').as_posix()}/*/*.parquet"
    frames: list[pl.DataFrame] = []
    for sit, cond in SITUATIONS.items():
        if situations is not None and sit not in situations:
            continue
        for side, team_col, metrics in (("off", "posteam", OFFENSE), ("def", "defteam", DEFENSE)):
            wide = con.sql(_weekly_query(side, team_col, metrics, sit, cond, plays, seasons)).pl()
            for m in metrics:
                frames.append(
                    wide.select(
                        pl.col("season").cast(pl.Int64),
                        pl.col("week").cast(pl.Int64),
                        "team",
                        pl.lit(side).alias("side"),
                        pl.lit(sit).alias("situation"),
                        pl.lit(m).alias("metric"),
                        pl.col(f"n__{m}").cast(pl.Int64).alias("n"),
                        pl.col(f"sx__{m}").cast(pl.Float64).alias("sx"),
                    ).filter(pl.col("n") > 0)
                )
    return pl.concat(frames)


def shrink_decay(
    weekly: pl.DataFrame,
    season: int,
    as_of_week: int | None,
    n0: float = N0,
    half_life: float = HALF_LIFE_WEEKS,
) -> pl.DataFrame:
    """Pure shrinkage + recency-decay math on weekly aggregates (no DuckDB).

    `weekly` columns: season, week, team, side, situation, metric, n, sx (rows for `season`
    and, optionally, `season - 1`). Only `season` rows with week < as_of_week are used; None
    means max week present + 1. A play in week k gets w = 0.5 ** ((as_of_week - 1 - k) / half_life).
    rate = (sum w*x + n0*prior) / (sum w + n0); prior = unweighted league rate over the same
    window, else the previous season's full league rate, else null.
    """
    cur_all = weekly.filter(pl.col("season") == season)
    if as_of_week is None:
        as_of_week = (cur_all["week"].max() + 1) if cur_all.height else 1  # type: ignore[operator]
    cur = cur_all.filter(pl.col("week") < as_of_week).with_columns(
        w=0.5 ** ((as_of_week - 1 - pl.col("week")) / half_life)
    )
    prev = weekly.filter(pl.col("season") == season - 1)

    stats = cur.group_by(["team", *_KEY]).agg(
        n=pl.col("n").sum(),
        sx=pl.col("sx").sum(),
        n_eff=(pl.col("w") * pl.col("n")).sum(),
        swx=(pl.col("w") * pl.col("sx")).sum(),
    )
    league = cur.group_by(_KEY).agg(p_cur=pl.col("sx").sum() / pl.col("n").sum())
    league_prev = prev.group_by(_KEY).agg(p_prev=pl.col("sx").sum() / pl.col("n").sum())

    # Universe: every team of the season (else of the previous season) x every group with any data.
    team_src = cur_all if cur_all.height else prev
    teams = team_src.select("team").unique()
    groups = pl.concat([cur_all.select(_KEY), prev.select(_KEY)]).unique()
    out = (
        teams.join(groups, how="cross")
        .join(stats, on=["team", *_KEY], how="left")
        .join(league, on=_KEY, how="left")
        .join(league_prev, on=_KEY, how="left")
        .with_columns(
            pl.col("n").fill_null(0),
            pl.col("n_eff").fill_null(0.0),
            pl.col("swx").fill_null(0.0),
            prior=pl.coalesce("p_cur", "p_prev"),
        )
        .with_columns(
            raw_rate=pl.when(pl.col("n") > 0).then(pl.col("sx") / pl.col("n")),
            rate=(pl.col("swx") + n0 * pl.col("prior")) / (pl.col("n_eff") + n0),
            season=pl.lit(season, dtype=pl.Int64),
            as_of_week=pl.lit(as_of_week, dtype=pl.Int64),
        )
    )
    return out.select(_OUT_COLS).sort(["team", *_KEY])


def compute(paths: Paths, season: int, as_of_week: int | None) -> pl.DataFrame:
    """Tendencies for one season using only plays with week < as_of_week (None = all played so far)."""
    weekly = weekly_aggregates(duckdb.connect(), paths, [season - 1, season])
    return shrink_decay(weekly, season, as_of_week)


def build(paths: Paths) -> int:
    con = duckdb.connect()
    plays = f"{paths.curated_table('plays').as_posix()}/*/*.parquet"
    all_seasons = sorted(
        con.sql(f"select distinct season from read_parquet('{plays}', hive_partitioning=true)")
        .pl()["season"]
        .to_list()
    )
    weekly = weekly_aggregates(con, paths, all_seasons)
    out = (
        pl.concat([shrink_decay(weekly, s, None) for s in all_seasons])
        .filter(pl.col("n") > 0)
        .sort(["season", "team", "side", "situation", "metric"])
    )
    paths.marts.mkdir(parents=True, exist_ok=True)
    out.write_parquet(paths.marts / "tendencies.parquet")
    return out.height


def rates_asof(
    weekly: pl.DataFrame,
    team_weeks: pl.DataFrame,
    specs: list[tuple[str, str, str, str]],
) -> pl.DataFrame:
    """Shrunk tendency `rate` as of each (season, week, team): only plays from weeks < week count.

    `team_weeks`: columns season, week, team. `specs`: (feature, side, situation, metric).
    Teams are matched through `TEAM_ALIASES` (games use historical codes such as STL/SD/OAK, curated
    plays the current ones). Returns long (season, week, team, feature, value); value is null where tendencies have no
    estimate (e.g. FTN metrics before 2022). One `shrink_decay` call per (season, week), not per team.
    """
    sp = pl.DataFrame(specs, schema=["feature", "side", "situation", "metric"], orient="row")
    wk = weekly.join(sp.select(_KEY).unique(), on=_KEY, how="semi")
    jobs = []
    for season in sorted(team_weeks["season"].unique().to_list()):
        sub = wk.filter(pl.col("season").is_in([season, season - 1]))
        if sub.is_empty():  # no data for these metrics (e.g. FTN before 2022): values stay null
            continue
        weeks = team_weeks.filter(pl.col("season") == season)["week"].unique().sort().to_list()
        jobs += [(sub, int(season), int(week)) for week in weeks]

    def one(job: tuple[pl.DataFrame, int, int]) -> pl.DataFrame:
        sub, season, week = job
        return (
            shrink_decay(sub, season, week)
            .select("team", *_KEY, "rate")
            .with_columns(
                pl.lit(season, dtype=pl.Int64).alias("season"),
                pl.lit(week, dtype=pl.Int64).alias("week"),
            )
        )

    with ThreadPoolExecutor() as pool:  # polars releases the GIL; ~50 ms of overhead per call
        parts = list(pool.map(one, jobs))
    rates = pl.concat(parts) if parts else pl.DataFrame(
        schema={"team": pl.Utf8, "side": pl.Utf8, "situation": pl.Utf8, "metric": pl.Utf8,
                "rate": pl.Float64, "season": pl.Int64, "week": pl.Int64}
    )  # fmt: skip
    return (
        team_weeks.select(
            pl.col("season").cast(pl.Int64),
            pl.col("week").cast(pl.Int64),
            "team",
            pl.col("team").replace(TEAM_ALIASES).alias("_k"),
        )
        .unique()
        .join(sp, how="cross")
        .join(rates.rename({"team": "_k"}), on=["season", "week", "_k", *_KEY], how="left")
        .select("season", "week", "team", "feature", pl.col("rate").alias("value"))
    )
