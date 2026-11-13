"""How often a player listed on the final injury report plays (ADR 0027, M24.1).

For every regular-season (season, week, team, player) on the injury report, did he play at least
one snap that week? "Played" comes from snap counts (PFR ids, joined to gsis ids through `players`);
a team-week with no snap rows at all (a bye, or a game PFR hasn't published) is left out rather
than counted as "didn't play". Snap counts start in 2013.

Grouped by era, the final report status and a position group, with counts and a 90% Wilson
interval. Two eras, because the league changed the statuses in 2016: Probable was dropped and
Questionable went from roughly "50-50" to "uncertain". Only the current era should be read as
today's rates.

The report is the final one of the week (the public file keeps one row per player-week), so this
says nothing about Wednesday's report; daily snapshots from the live ingest can add that later.
"""

from __future__ import annotations

import math
from pathlib import Path

import polars as pl

from nfl import catalog
from nfl.config import Paths
from nfl.io import write_parquet

FIRST_SEASON = 2013  # snap counts are empty upstream before this
CURRENT_ERA_FROM = 2016  # Probable dropped, Questionable redefined
Z90 = 1.6448536269514722

# injury-report position -> group. Edge rushers report as DE or LB, so the groups follow the report.
POS_GROUP: dict[str, str] = {
    "QB": "QB",
    "RB": "RB", "FB": "RB",
    "WR": "WR",
    "TE": "TE",
    "T": "OL", "G": "OL", "C": "OL",
    "DE": "DL", "DT": "DL",
    "LB": "LB",
    "CB": "DB", "S": "DB",
    "K": "ST", "P": "ST", "LS": "ST",
}  # fmt: skip
STATUSES = ("Out", "Doubtful", "Questionable", "Probable", "None")

_SQL = """
with inj as (
    select distinct season, week, team, gsis_id, trim(position) as position,
        coalesce(nullif(trim(report_status), ''), 'None') as status
    from injuries
    where game_type = 'REG' and season between {lo} and {hi} and gsis_id is not null
),
snaps as (
    select s.season, s.week, s.team, p.gsis_id,
        max(coalesce(s.offense_snaps, 0) + coalesce(s.defense_snaps, 0) + coalesce(s.st_snaps, 0)) > 0
            as played,
        max(greatest(coalesce(s.offense_pct, 0), coalesce(s.defense_pct, 0),
                     case when trim(s.position) in ('K', 'P', 'LS') then coalesce(s.st_pct, 0) else 0 end))
            as share
    from snap_counts s join players p on p.pfr_id = s.pfr_player_id
    where s.game_type = 'REG'
    group by 1, 2, 3, 4
),
-- a role before this week: his largest share of his unit's snaps in an earlier game this season
role as (
    select i.season, i.week, i.team, i.gsis_id, max(sn.share) as prior_share
    from inj i join snaps sn
      on sn.season = i.season and sn.gsis_id = i.gsis_id and sn.week < i.week
    group by 1, 2, 3, 4
),
team_weeks as (select distinct season, week, team from snap_counts where game_type = 'REG')
select i.season, i.week, i.team, i.gsis_id, i.position, i.status,
    coalesce(sn.played, false) as played, r.prior_share
from inj i
join team_weeks using (season, week, team)
join role r using (season, week, team, gsis_id)
left join snaps sn using (season, week, team, gsis_id)
where r.prior_share >= {min_share}
"""
MIN_SHARE = 0.25  # had a role: at least this share of his unit's snaps in an earlier game


def listed(paths: Paths, seasons: tuple[int, int] = (FIRST_SEASON, 2025)) -> pl.DataFrame:
    """One row per listed player-week with his final status and whether he played, for players who
    already had a role this season (`MIN_SHARE`): a healthy backup who never takes a snap isn't
    a player who sat out. Week 1 and players with no earlier game this season are left out."""
    con = catalog.connect(paths, only=["injuries", "snap_counts", "players"])
    df = con.sql(_SQL.format(lo=seasons[0], hi=seasons[1], min_share=MIN_SHARE)).pl()
    return df.with_columns(
        pl.col("position").replace_strict(POS_GROUP, default=None).alias("pos_group"),
        pl.when(pl.col("season") >= CURRENT_ERA_FROM)
        .then(pl.lit(f"{CURRENT_ERA_FROM}+"))
        .otherwise(pl.lit(f"{FIRST_SEASON}-{CURRENT_ERA_FROM - 1}"))
        .alias("era"),
    ).filter(pl.col("pos_group").is_not_null())


# the practice statuses that say a player is hurt, and how the pages name them (M24.7)
PRACTICE = {
    "Did Not Participate In Practice": "Did not practice",
    "Limited Participation in Practice": "Limited in practice",
}


def wilson(k: int, n: int, z: float = Z90) -> tuple[float, float]:
    """Wilson score interval for k successes in n."""
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def rates(df: pl.DataFrame) -> pl.DataFrame:
    """Play rates by era, status and position group, plus an "all" group per status."""
    keys = ["era", "status", "pos_group"]
    by_group = df.group_by(keys).agg(pl.len().alias("n"), pl.col("played").sum().alias("played"))
    overall = (
        df.group_by(["era", "status"])
        .agg(pl.len().alias("n"), pl.col("played").sum().alias("played"))
        .with_columns(pl.lit("all").alias("pos_group"))
        .select(keys + ["n", "played"])
    )
    out = pl.concat([by_group, overall]).with_columns(
        (pl.col("played") / pl.col("n")).alias("rate")
    )
    ci = [wilson(int(k), int(n)) for k, n in out.select("played", "n").iter_rows()]
    order = {s: i for i, s in enumerate(STATUSES)}
    return (
        out.with_columns(
            pl.Series("lo", [c[0] for c in ci]),
            pl.Series("hi", [c[1] for c in ci]),
            pl.col("status").replace_strict(order, default=len(order)).alias("_o"),
        )
        .sort("era", "_o", "pos_group")
        .drop("_o")
        .with_columns(pl.col("n").cast(pl.Int64), pl.col("played").cast(pl.Int64))
    )


def out_path(paths: Paths) -> Path:
    return paths.marts / "derived" / "status_to_play.parquet"


def build(paths: Paths, seasons: tuple[int, int] = (FIRST_SEASON, 2025)) -> pl.DataFrame:
    """Compute and write `marts/derived/status_to_play.parquet` (a full rewrite: derived, not a record)."""
    r = rates(listed(paths, seasons))
    path = out_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_parquet(r, path)
    return r
