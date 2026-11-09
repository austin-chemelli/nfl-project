"""What a player is worth in points of spread, week by week (ADR 0027, M24.2).

One row per (season, week, player) for regular-season weeks from 2013 (snap counts) for the v1
groups (QB, RB, WR, TE, OL, EDGE, CB, S): the value **as of the start of that week**, from games
before it only. Values are for a player in his role: what the team loses, against a replacement,
if he doesn't play.

    value = TOP_STARTER_POINTS[group] x quality multiplier x role

* **Quality** is a percentile among the group's regular starters in the same as-of slice, of a blend
  of production and a prior. Production is recency-weighted (this season 1, each season back x0.75,
  three seasons) and shrunk toward the group mean: quarterbacks EPA per dropback (as
  `features/qb.py`), receivers receiving EPA per game, running backs rushing plus receiving EPA per
  game, edges sacks plus QB hits per game, corners and safeties passes defended plus twice the
  interceptions per game. The prior is the contract's share of the cap (contracts active that
  season) or, on a rookie deal, the draft slot. Linemen have no free per-player production and use
  the prior alone.
* **The multiplier** maps the percentile linearly from 0 at `REPLACEMENT_PCT` to 1 at `TOP_PCT`,
  capped at `MAX_MULTIPLIER`.
* **Role** is his average share of his unit's snaps over his last three games (any season), and
  counts fully from `FULL_ROLE`.

This is a Python model through the catalog until M23's SQL runner lands; its output path follows the
runner's layout (`marts/derived/player_value.parquet`). Known limits: a contract signed during a
season counts from that season's start; receiver EPA carries some of the quarterback's credit; a
player traded mid-season takes his whole history to the new team.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from nfl import catalog
from nfl.config import Paths
from nfl.io import write_parquet
from nfl.players import priors as P

FIRST_SEASON = 2013

_PLAYER_GAMES = """
with groups as (
    select gsis_id, display_name,
        coalesce({pff}, {ngs}) as grp_player,
        draft_year, draft_pick
    from players
),
snaps as (
    select s.season, s.week, s.game_type, s.team, p.gsis_id, trim(s.position) as snap_pos,
        max(greatest(coalesce(s.offense_pct, 0), coalesce(s.defense_pct, 0))) as share
    from snap_counts s join players p on p.pfr_id = s.pfr_player_id
    where s.season >= {lo}
    group by all
),
pw as (
    select season, week, player_id as gsis_id,
        coalesce(receiving_epa, 0) as rec_epa,
        coalesce(rushing_epa, 0) + coalesce(receiving_epa, 0) as rush_rec_epa,
        coalesce(def_sacks, 0) + coalesce(def_qb_hits, 0) as pressure,
        coalesce(def_pass_defended, 0) + 2 * coalesce(def_interceptions, 0) as ball
    from player_weeks where season >= {lo}
),
qb as (
    select season, week, passer_player_id as gsis_id, count(*) as dropbacks, sum(qb_epa) as qb_epa
    from plays where qb_dropback = 1 and passer_player_id is not null and season >= {lo}
    group by all
)
select sn.season, sn.week, sn.game_type, sn.team, sn.gsis_id, g.display_name as player,
    coalesce(g.grp_player, {snap}) as grp, sn.share,
    pw.rec_epa, pw.rush_rec_epa, pw.pressure, pw.ball, qb.dropbacks, qb.qb_epa
from snaps sn
left join groups g using (gsis_id)
left join pw using (season, week, gsis_id)
left join qb using (season, week, gsis_id)
"""


def _case(col: str) -> str:
    whens = " ".join(f"when '{k}' then '{v}'" for k, v in P.POSITION_GROUP.items())
    return f"case trim({col}) {whens} else null end"


def player_games(paths: Paths, lo: int = FIRST_SEASON - P.SEASONS_BACK) -> pl.DataFrame:
    """One row per player and game with his group, snap share and the game's production numbers."""
    con = catalog.connect(paths, only=["players", "snap_counts", "player_weeks", "plays"])
    sql = _PLAYER_GAMES.format(
        lo=lo, pff=_case("pff_position"), ngs=_case("ngs_position"), snap=_case("sn.snap_pos")
    )
    df = con.sql(sql).pl().filter(pl.col("grp").is_not_null())
    # the game's production measure for the player's group; quarterbacks count dropbacks, not games
    x = (
        pl.when(pl.col("grp") == "QB").then(pl.col("qb_epa"))
        .when(pl.col("grp").is_in(["WR", "TE"])).then(pl.col("rec_epa"))
        .when(pl.col("grp") == "RB").then(pl.col("rush_rec_epa"))
        .when(pl.col("grp") == "EDGE").then(pl.col("pressure"))
        .when(pl.col("grp").is_in(["CB", "S"])).then(pl.col("ball"))
        .otherwise(None)
    )  # fmt: skip
    n = pl.when(pl.col("grp") == "QB").then(pl.col("dropbacks")).otherwise(pl.lit(1.0))
    return df.with_columns(
        x.fill_null(0.0).alias("x"), n.fill_null(0.0).cast(pl.Float64).alias("n")
    )


def contract_prior(paths: Paths) -> pl.DataFrame:
    """Per (player, season): the larger APY share of the cap of contracts active that season, flagged
    when it's a rookie deal (signed in the draft year)."""
    con = catalog.connect(paths, only=["contracts"])
    c = con.sql(
        "select gsis_id, year_signed, years, apy_cap_pct, draft_year = year_signed as rookie "
        "from contracts where gsis_id is not null and years > 0"
    ).pl()
    rows = []
    for r in c.iter_rows(named=True):
        for s in range(r["year_signed"], r["year_signed"] + r["years"]):
            rows.append((r["gsis_id"], s, r["apy_cap_pct"], bool(r["rookie"])))
    df = pl.DataFrame(rows, schema=["gsis_id", "season", "apy_cap_pct", "rookie"], orient="row")
    return df.group_by("gsis_id", "season").agg(pl.col("apy_cap_pct").max(), pl.col("rookie").all())


def _draft(paths: Paths) -> pl.DataFrame:
    con = catalog.connect(paths, only=["players"])
    return con.sql("select gsis_id, draft_pick from players where gsis_id is not null").pl()


def targets(games: pl.DataFrame, seasons: tuple[int, int]) -> pl.DataFrame:
    """The (season, week) pairs to value: every regular-season week that has snap counts."""
    return (
        games.filter((pl.col("game_type") == "REG") & pl.col("season").is_between(*seasons))
        .select("season", "week")
        .unique()
        .sort("season", "week")
    )


def as_of(pg: pl.DataFrame, season: int, week: int) -> pl.DataFrame:
    """Every player's history strictly before (season, week): decayed production sums, his role and
    his team. Players without a game in this or last season are left out."""
    before = pg.filter(
        (pl.col("season") < season) | ((pl.col("season") == season) & (pl.col("week") < week))
    ).filter(pl.col("season") >= season - P.SEASONS_BACK)
    if before.is_empty():
        return pl.DataFrame()
    w = pl.lit(P.SEASON_DECAY) ** (season - pl.col("season"))
    recent = before.sort("season", "week", descending=True)
    last3 = recent.group_by("gsis_id", maintain_order=True).head(3)
    role = last3.group_by("gsis_id").agg(
        pl.col("share").mean().alias("role"),
        pl.col("team").first().alias("team"),
        pl.col("grp").first().alias("grp"),
        pl.col("player").first().alias("player"),
        pl.col("season").first().alias("last_season"),
    )
    prod = before.group_by("gsis_id").agg(
        (pl.col("x") * w).sum().alias("wx"),
        (pl.col("n") * w).sum().alias("wn"),
        pl.len().alias("games"),
    )
    out = role.join(prod, on="gsis_id").filter(pl.col("last_season") >= season - 1)
    return out.with_columns(pl.lit(season).alias("season"), pl.lit(week).alias("week"))


def _pct_against(values: pl.Series, pool: pl.Series) -> pl.Series:
    """Each value's percentile against the pool (share of the pool below it, ties half)."""
    s = pool.drop_nulls().sort()
    if s.is_empty():
        return pl.Series([None] * len(values), dtype=pl.Float64)
    arr = s.to_list()
    import bisect

    n = len(arr)
    out = []
    for v in values.to_list():
        if v is None:
            out.append(None)
            continue
        lo, hi = bisect.bisect_left(arr, v), bisect.bisect_right(arr, v)
        out.append((lo + (hi - lo) / 2) / n)
    return pl.Series(out, dtype=pl.Float64)


def score(slice_: pl.DataFrame, means: dict[str, float], prior: pl.DataFrame) -> pl.DataFrame:
    """Quality, multiplier and value for one as-of slice (one season and week)."""
    if slice_.is_empty():
        return slice_
    s = slice_.join(prior, on=["gsis_id", "season"], how="left")
    n0 = pl.col("grp").replace_strict(P.N0, default=4.0)
    mean = pl.col("grp").replace_strict(means, default=0.0)
    s = s.with_columns(((pl.col("wx") + n0 * mean) / (pl.col("wn") + n0)).alias("production"))
    parts = []
    for grp, g in s.group_by("grp"):
        grp = grp[0]
        pool = g.filter(pl.col("role") >= P.REGULAR_ROLE)
        if pool.is_empty():
            pool = g
        prod_pct = _pct_against(g["production"], pool["production"])
        prior_pct = _prior_pct(g)
        wt = P.PRODUCTION_WEIGHT[grp]
        g = g.with_columns(prod_pct.alias("prod_pct"), prior_pct.alias("prior_pct"))
        quality = (
            pl.when(pl.col("prior_pct").is_null())
            .then(pl.col("prod_pct"))
            .otherwise(wt * pl.col("prod_pct").fill_null(0.5) + (1 - wt) * pl.col("prior_pct"))
        )
        g = g.with_columns(quality.alias("blend"))
        # the blend's own percentile among regular starters, so every group spreads over 0..1
        pool_blend = g.filter(pl.col("role") >= P.REGULAR_ROLE)["blend"]
        g = g.with_columns(
            _pct_against(g["blend"], pool_blend if len(pool_blend) else g["blend"]).alias(
                "quality_pct"
            )
        )
        parts.append(g)
    s = pl.concat(parts, how="diagonal_relaxed")
    mult = (
        ((pl.col("quality_pct") - P.REPLACEMENT_PCT) / (P.TOP_PCT - P.REPLACEMENT_PCT))
        .clip(0.0, P.MAX_MULTIPLIER)
        .fill_null(0.0)
    )
    role = (pl.col("role") / P.FULL_ROLE).clip(0.0, 1.0)
    top = pl.col("grp").replace_strict(P.TOP_STARTER_POINTS, default=0.0)
    return s.with_columns(
        mult.alias("multiplier"),
        (top * mult * role).alias("value_pts"),
    )


def group_means(pg: pl.DataFrame, before_season: int) -> dict[str, float]:
    """Each group's production mean per unit (dropback or game) over the `SEASONS_BACK` seasons
    before `before_season`: the shrinkage target, never the season being valued, and the same
    whatever range a build loads."""
    past = pg.filter(pl.col("season").is_between(before_season - P.SEASONS_BACK, before_season - 1))
    if past.is_empty():
        return {}
    m = past.group_by("grp").agg((pl.col("x").sum() / pl.col("n").sum()).alias("m"))
    return dict(zip(m["grp"].to_list(), m["m"].to_list(), strict=True))


def prior_scores(paths: Paths) -> pl.DataFrame:
    """Per (player, season): the larger cap share of contracts active that season, whether it's a
    rookie deal, and the draft pick. `score` turns these into a percentile within the group."""
    return contract_prior(paths).join(_draft(paths), on="gsis_id", how="left")


ROOKIE_TOP, ROOKIE_LAST = 0.85, 0.25  # a first pick ranks like an 85th-percentile veteran deal


def _prior_pct(g: pl.DataFrame) -> pl.Series:
    """The prior as a percentile within the group's slice: veterans by cap share among veterans,
    rookie deals by draft slot (first pick `ROOKIE_TOP`, last `ROOKIE_LAST`), else null."""
    vet = g.filter(~pl.col("rookie").fill_null(True) & pl.col("apy_cap_pct").is_not_null())
    vet_pct = _pct_against(g["apy_cap_pct"], vet["apy_cap_pct"])
    pick = g["draft_pick"].cast(pl.Float64)
    rookie_pct = (ROOKIE_TOP - (ROOKIE_TOP - ROOKIE_LAST) * (pick - 1) / 259).clip(
        ROOKIE_LAST, ROOKIE_TOP
    )
    rookie = g["rookie"].fill_null(False)
    out = []
    for r, v, k in zip(rookie.to_list(), vet_pct.to_list(), rookie_pct.to_list(), strict=True):
        out.append(k if r else v)
    return pl.Series(out, dtype=pl.Float64)


COLUMNS = [
    "season", "week", "gsis_id", "player", "team", "grp", "role", "games", "production",
    "prod_pct", "prior_pct", "quality_pct", "multiplier", "value_pts",
]  # fmt: skip


def build_values(paths: Paths, seasons: tuple[int, int]) -> pl.DataFrame:
    pg = player_games(paths, lo=seasons[0] - P.SEASONS_BACK)
    prior = prior_scores(paths)
    out = []
    for season, week in targets(pg, seasons).iter_rows():
        means = group_means(pg, season)
        sl = as_of(pg, season, week)
        if sl.is_empty():
            continue
        out.append(score(sl, means, prior).select(COLUMNS))
    return pl.concat(out).sort(
        "season", "week", "team", "grp", "value_pts", descending=[False, False, False, False, True]
    )


def out_path(paths: Paths) -> Path:
    return paths.marts / "derived" / "player_value.parquet"


def build(paths: Paths, seasons: tuple[int, int]) -> pl.DataFrame:
    """Compute and write `marts/derived/player_value.parquet` (derived: a full rewrite)."""
    df = build_values(paths, seasons)
    path = out_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_parquet(df, path)
    return df
