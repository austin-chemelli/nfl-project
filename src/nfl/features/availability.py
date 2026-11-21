"""Availability features: who is missing, and is the real quarterback playing (architecture §3.3).

Inputs: the weekly injury report (curated `injuries`), depth charts (curated `depth_charts`, two
formats) and plays (primary passer of each team's previous game).

Depth charts
  weekly (<= 2024): rows per (season, week, club_code); rank-1 players have `depth_team == '1'`.
  timestamped (2025+): snapshots keyed by `dt`; rank-1 players have `pos_rank == 1`. For a game we use
  the latest snapshot strictly before the game's `known_as_of` stamp (kickoff - 2h for completed
  games, build time for upcoming ones), so nothing published after the stamp can leak in.

Position mapping (both formats reduce to one canonical set via POS_MAP)
  QB; RB (HB); FB; WR; TE; T (T/OT/LT/RT); G (G/OG/LG/RG); C; DE (DE/LDE/RDE/EDGE); DT (DT/NT/LDT/
  RDT/DL); OLB (OLB/WLB/SLB); LB (ILB/MLB/LB/LILB/RILB); CB (CB/LCB/RCB); NB (nickel; the weekly
  format lists it as position CB with depth_position NB); S (S/FS/SS/DB).
  Special teams are not starters: K, PK, P, H, LS, KO, PR, KR are dropped, so a returner listed at
  RB/WR/CB only counts at his offense/defense slot. A player listed twice counts once.
  "Top" CB / WR: the first-listed rank-1 CB (NB excluded) / WR (file order for weekly charts,
  `pos_slot` for timestamped ones). The charts carry no quality ranking, so first-listed is a proxy.

Weights (injury_impact): status Out/Doubtful x1.0, Questionable x0.5, anything else 0, times
  QB 5; T, DE, OLB 2; top CB 2; top WR 2; every other rank-1 starter 1.

Coverage: the injury report exists 2009+. A game-team with no report row for its (season, week)
gets null for every injury-derived feature (an empty report is not "zero injuries"); a team-week
without a depth chart gets null for the chart-derived ones. qb_change needs only the depth chart
and the previous game's passer.

Franchise relocations are folded for matching (OAK->LV, SD->LAC, STL->LA); rows are keyed by the
team code printed on the game.
"""

from __future__ import annotations

import logging
from datetime import datetime

import duckdb
import polars as pl

from nfl.config import Paths
from nfl.features import store
from nfl.models.elo import TEAM_ALIASES

log = logging.getLogger(__name__)

SOURCE = "injuries"
VERSION = "1"
FEATURES = (
    "availability.qb1_out",
    "availability.qb_change",
    "availability.starters_out",
    "availability.injury_impact",
    "availability.ol_starters_out",
    "availability.report_count",
    "availability.value_lost",
    "availability.ol_weakest",
)

POS_MAP: dict[str, str | None] = {
    "QB": "QB",
    "RB": "RB",
    "HB": "RB",
    "FB": "FB",
    "WR": "WR",
    "TE": "TE",
    "T": "T",
    "OT": "T",
    "LT": "T",
    "RT": "T",
    "G": "G",
    "OG": "G",
    "LG": "G",
    "RG": "G",
    "C": "C",
    "DE": "DE",
    "LDE": "DE",
    "RDE": "DE",
    "EDGE": "DE",
    "DT": "DT",
    "NT": "DT",
    "LDT": "DT",
    "RDT": "DT",
    "DL": "DT",
    "OLB": "OLB",
    "WLB": "OLB",
    "SLB": "OLB",
    "ILB": "LB",
    "MLB": "LB",
    "LB": "LB",
    "LILB": "LB",
    "RILB": "LB",
    "CB": "CB",
    "LCB": "CB",
    "RCB": "CB",
    "NB": "NB",
    "S": "S",
    "FS": "S",
    "SS": "S",
    "DB": "S",
}
_REPORT_GROUP = {  # injury-report position -> group, as `players.status.POS_GROUP`
    "QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE", "T": "OL", "G": "OL", "C": "OL",
    "DE": "DL", "DT": "DL", "LB": "LB", "CB": "DB", "S": "DB",
}  # fmt: skip
SPECIAL_TEAMS = ["K", "PK", "P", "H", "LS", "KO", "PR", "KR"]
OL = ["C", "G", "T"]
WEIGHT = {"QB": 5.0, "T": 2.0, "DE": 2.0, "OLB": 2.0}
TOP_WEIGHTED = {"CB": 2.0, "WR": 2.0}  # only the first-listed starter at these positions
OUT_STATUSES = ["Out", "Doubtful"]
# chart position -> the injury report's position group (`players.status.POS_GROUP`), the fallback
# when the report row carries no position
CHART_GROUP = {
    "QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE", "T": "OL", "G": "OL", "C": "OL",
    "DE": "DL", "DT": "DL", "OLB": "LB", "LB": "LB", "CB": "DB", "NB": "DB", "S": "DB",
}  # fmt: skip
ERA_FROM = 2016  # status_to_play's eras: Probable dropped, Questionable redefined
EXPECTED_TO_PLAY_BELOW = 0.5  # ol_weakest skips a starter more likely out than in

_DEPTH_COLS = {
    "season": pl.Int64,
    "week": pl.Int64,
    "club_code": pl.Utf8,
    "depth_team": pl.Utf8,
    "depth_position": pl.Utf8,
    "position": pl.Utf8,
    "gsis_id": pl.Utf8,
    "dt": pl.Utf8,
    "team": pl.Utf8,
    "pos_abb": pl.Utf8,
    "pos_rank": pl.Int64,
    "pos_slot": pl.Int64,
}
_DT_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _franchise(col: str) -> pl.Expr:
    return pl.col(col).replace(TEAM_ALIASES)


def _canon_pos(col: str) -> pl.Expr:
    return pl.col(col).str.to_uppercase().replace_strict(POS_MAP, default=None)


# ---------------------------------------------------------------------------------- loading


def load_depth(paths: Paths) -> pl.DataFrame:
    cols = ", ".join(
        f'cast({c} as {"bigint" if t is pl.Int64 else "varchar"}) as "{c}"'
        for c, t in _DEPTH_COLS.items()
    )
    table = f"{paths.curated_table('depth_charts').as_posix()}/*/*.parquet"
    return (
        duckdb.connect()
        .sql(
            f"select {cols} from read_parquet('{table}', hive_partitioning=true, union_by_name=true)"
        )
        .pl()
    )


def load_inputs(paths: Paths) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    con = duckdb.connect()

    def glob(t: str) -> str:
        return f"{paths.curated_table(t).as_posix()}/*/*.parquet"

    inj = con.sql(
        'select cast(season as bigint) as season, cast(week as bigint) as "week", team, gsis_id, '
        "report_status, timezone('UTC', date_modified) as date_modified, position "
        "from read_parquet('" + glob("injuries") + "', hive_partitioning=true, union_by_name=true)"
    ).pl()
    depth = load_depth(paths)
    plays = con.sql(
        "select game_id, posteam, passer_player_id from read_parquet('"
        + glob("plays")
        + "', hive_partitioning=true) where qb_dropback = 1 and passer_player_id is not null "
        "and posteam is not null"
    ).pl()
    return inj, depth, plays


# --------------------------------------------------------------------------------- core


def _game_teams(games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    """One row per (game, team as printed): season, week, franchise, kickoff, chart cutoff."""
    g = games.select(
        "game_id",
        pl.col("season").cast(pl.Int64),
        pl.col("week").cast(pl.Int64),
        pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us")).alias("kickoff"),
        "home_team",
        "away_team",
    )
    long = pl.concat(
        [
            g.select("game_id", "season", "week", "kickoff", pl.col("home_team").alias("team")),
            g.select("game_id", "season", "week", "kickoff", pl.col("away_team").alias("team")),
        ]
    )
    return long.with_columns(
        _franchise("team").alias("franchise"),
        store.stamp(pl.col("kickoff"), build_ts).alias("cutoff"),
    )


def _starters(depth: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Rank-1 starters of both formats: (weekly, timestamped).

    weekly: season, week, franchise, gsis_id, pos, ord.  timestamped: franchise, chart_dt, gsis_id,
    pos, ord. `ord` is the listing order within a chart (lower = listed first)."""
    d = depth
    for c, t in _DEPTH_COLS.items():
        if c not in d.columns:
            d = d.with_columns(pl.lit(None, dtype=t).alias(c))
    d = d.select(list(_DEPTH_COLS)).with_row_index("row")
    weekly = (
        d.filter(
            pl.col("dt").is_null()
            & pl.col("week").is_not_null()
            & (pl.col("depth_team") == "1")
            & pl.col("gsis_id").is_not_null()
        )
        .with_columns(
            pl.when((pl.col("position") == "CB") & (pl.col("depth_position") == "NB"))
            .then(pl.lit("NB"))
            .otherwise(_canon_pos("position"))
            .alias("pos")
        )
        .filter(
            pl.col("pos").is_not_null()
            & ~pl.col("depth_position").str.to_uppercase().is_in(SPECIAL_TEAMS)
        )
        .select(
            "season",
            "week",
            _franchise("club_code").alias("franchise"),
            "gsis_id",
            "pos",
            pl.col("row").cast(pl.Int64).alias("ord"),
        )
    )
    stamped = (
        d.filter(
            pl.col("dt").is_not_null() & (pl.col("pos_rank") == 1) & pl.col("gsis_id").is_not_null()
        )
        .with_columns(
            _canon_pos("pos_abb").alias("pos"),
            pl.col("dt").str.to_datetime(_DT_FMT, time_unit="us").alias("chart_dt"),
        )
        .filter(pl.col("pos").is_not_null())
        .select(
            _franchise("team").alias("franchise"),
            "chart_dt",
            "gsis_id",
            "pos",
            pl.col("pos_slot").fill_null(0).alias("ord"),
        )
    )
    return weekly, stamped


def _charts(gt: pl.DataFrame, depth: pl.DataFrame) -> pl.DataFrame:
    """Rank-1 starters for each game-team: (game_id, team, gsis_id, pos, ord), one row per player."""
    weekly, stamped = _starters(depth)
    a = gt.join(weekly, on=["season", "week", "franchise"], how="inner").select(
        "game_id", "team", "gsis_id", "pos", "ord"
    )
    snaps = stamped.select("franchise", "chart_dt").unique().sort("chart_dt")
    pick = (
        gt.join(a.select("game_id", "team").unique(), on=["game_id", "team"], how="anti")
        .sort("cutoff")
        .join_asof(
            snaps,
            left_on="cutoff",
            right_on="chart_dt",
            by="franchise",
            strategy="backward",
            allow_exact_matches=False,
            check_sortedness=False,
        )
        .filter(pl.col("chart_dt").is_not_null())
    )
    b = pick.join(stamped, on=["franchise", "chart_dt"], how="inner").select(
        "game_id", "team", "gsis_id", "pos", "ord"
    )
    out = pl.concat([a, b]).sort("game_id", "team", "ord")
    return out.unique(["game_id", "team", "gsis_id"], keep="first", maintain_order=True)


def _chart_aggregates(gt: pl.DataFrame, charts: pl.DataFrame, inj: pl.DataFrame) -> pl.DataFrame:
    sev = (
        inj.filter(pl.col("gsis_id").is_not_null())
        .with_columns(
            _franchise("team").alias("franchise"),
            pl.when(pl.col("report_status").is_in(OUT_STATUSES))
            .then(1.0)
            .when(pl.col("report_status") == "Questionable")
            .then(0.5)
            .otherwise(0.0)
            .alias("sev"),
        )
        .group_by("season", "week", "franchise", "gsis_id")
        .agg(pl.col("sev").max())
    )
    s = (
        charts.join(
            gt.select("game_id", "team", "season", "week", "franchise"), on=["game_id", "team"]
        )
        .join(sev, on=["season", "week", "franchise", "gsis_id"], how="left")
        .with_columns(pl.col("sev").fill_null(0.0))
        .with_columns(
            (pl.col("sev") == 1.0).alias("out"),
            (pl.col("ord").rank("ordinal").over("game_id", "team", "pos") == 1).alias("first"),
        )
        .with_columns(
            pl.when(pl.col("first") & pl.col("pos").is_in(list(TOP_WEIGHTED)))
            .then(pl.col("pos").replace_strict(TOP_WEIGHTED, default=1.0))
            .otherwise(pl.col("pos").replace_strict(WEIGHT, default=1.0))
            .alias("w")
        )
    )
    qb = (
        s.filter(pl.col("pos") == "QB")
        .sort("ord")
        .group_by("game_id", "team", maintain_order=True)
        .agg(pl.col("gsis_id").first().alias("qb1"), pl.col("out").first().alias("qb1_out"))
    )
    agg = s.group_by("game_id", "team").agg(
        pl.lit(True).alias("has_chart"),
        pl.col("out").sum().cast(pl.Float64).alias("starters_out"),
        (pl.col("w") * pl.col("sev")).sum().alias("injury_impact"),
        (pl.col("out") & pl.col("pos").is_in(OL)).sum().cast(pl.Float64).alias("ol_starters_out"),
    )
    return agg.join(qb, on=["game_id", "team"], how="left")


def load_value_inputs(paths: Paths) -> tuple[pl.DataFrame | None, pl.DataFrame | None]:
    """(player values, status-to-play rates) from `marts/derived/`, or None for a missing table
    (the player features are then null; build them with `nfl players value` / `nfl players status`)."""
    from nfl.players import status as status_mod
    from nfl.players import value as value_mod

    vp, rp = value_mod.out_path(paths), status_mod.out_path(paths)
    values = (
        pl.read_parquet(vp, columns=["season", "week", "gsis_id", "value_pts"])
        if vp.exists()
        else None
    )
    rates = pl.read_parquet(rp) if rp.exists() else None
    if values is None or rates is None:
        log.warning("availability: %s missing; value_lost and ol_weakest are null", vp.name)
    return values, rates


def _value_features(
    gt: pl.DataFrame,
    charts: pl.DataFrame,
    inj: pl.DataFrame,
    values: pl.DataFrame,
    rates: pl.DataFrame,
) -> pl.DataFrame:
    """(game_id, team, value_lost, ol_weakest, values_ready) for each game-team with a chart."""
    ctx = gt.select("game_id", "team", "season", "week", "franchise", "cutoff")
    key = pl.col("season") * 100 + pl.col("week")
    v = (
        values.select(
            pl.col("gsis_id"),
            (pl.col("season").cast(pl.Int64) * 100 + pl.col("week").cast(pl.Int64)).alias("vkey"),
            pl.col("value_pts").fill_null(0.0).alias("value"),
        )
        .unique(["gsis_id", "vkey"], keep="first")
        .sort("vkey")
    )
    first_slice = v["vkey"].min() if v.height else None
    # the report rows a lock could see: stamped before the game's cutoff (no stamp: kept)
    if "date_modified" not in inj.columns:
        inj = inj.with_columns(pl.lit(None, dtype=pl.Datetime("us")).alias("date_modified"))
    if "position" not in inj.columns:
        inj = inj.with_columns(pl.lit(None, dtype=pl.Utf8).alias("position"))
    r = rates.select("era", "status", "pos_group", (1.0 - pl.col("rate")).alias("p_out"))
    rep = (
        inj.filter(pl.col("gsis_id").is_not_null())
        .with_columns(_franchise("team").alias("franchise"))
        .select(
            "season", "week", "franchise", "gsis_id", "report_status", "position", "date_modified"
        )
        .join(ctx, on=["season", "week", "franchise"])
        .filter(pl.col("date_modified").is_null() | (pl.col("date_modified") < pl.col("cutoff")))
        .select(
            "game_id",
            "team",
            "gsis_id",
            pl.col("report_status").alias("status"),
            pl.col("position")
            .str.to_uppercase()
            .replace_strict(_REPORT_GROUP, default=None)
            .alias("rep_group"),
            pl.when(pl.col("season") >= ERA_FROM)
            .then(pl.lit(f"{ERA_FROM}+"))
            .otherwise(pl.lit("2013-2015"))
            .alias("era"),
        )
    )
    c = (
        charts.join(ctx, on=["game_id", "team"])
        .with_columns(pl.col("pos").replace_strict(CHART_GROUP, default=None).alias("chart_group"))
        .join(rep, on=["game_id", "team", "gsis_id"], how="left")
        .with_columns(
            pl.coalesce("rep_group", "chart_group").alias("pos_group"),
            pl.when(pl.col("season") >= ERA_FROM)
            .then(pl.lit(f"{ERA_FROM}+"))
            .otherwise(pl.lit("2013-2015"))
            .alias("era"),
            key.alias("gkey"),
        )
    )
    # P(does not play): the group's rate, else the status's "all" rate; no status or no rate: 0
    c = (
        c.join(r.rename({"p_out": "p_grp"}), on=["era", "status", "pos_group"], how="left")
        .join(
            r.filter(pl.col("pos_group") == "all").drop("pos_group").rename({"p_out": "p_all"}),
            on=["era", "status"],
            how="left",
        )
        .with_columns(pl.coalesce("p_grp", "p_all").fill_null(0.0).alias("p_out"))
        # a player listed twice (two report rows): the larger chance out
        .group_by("game_id", "team", "gsis_id", "pos", "gkey", maintain_order=True)
        .agg(pl.col("p_out").max())
        .sort("gkey")
        .join_asof(
            v,
            left_on="gkey",
            right_on="vkey",
            by="gsis_id",
            strategy="backward",
            allow_exact_matches=False,
            check_sortedness=False,
        )
        .with_columns(pl.col("value").fill_null(0.0))
    )
    ready = pl.lit(first_slice is not None) & (pl.col("gkey") > (first_slice or 0))
    return c.group_by("game_id", "team").agg(
        (pl.col("value") * pl.col("p_out")).sum().alias("value_lost"),
        pl.col("value")
        .filter(pl.col("pos").is_in(OL) & (pl.col("p_out") < EXPECTED_TO_PLAY_BELOW))
        .min()
        .alias("ol_weakest"),
        ready.first().alias("values_ready"),
    )


def _prev_passer(gt: pl.DataFrame, plays: pl.DataFrame) -> pl.DataFrame:
    """Primary passer (most dropbacks) of the franchise's latest earlier game with plays."""
    primary = (
        plays.with_columns(_franchise("posteam").alias("franchise"))
        .group_by("game_id", "franchise", "passer_player_id")
        .len()
        .sort(["len", "passer_player_id"], descending=[True, False])
        .group_by("game_id", "franchise", maintain_order=True)
        .agg(pl.col("passer_player_id").first().alias("prev_passer"))
    )
    done = (
        gt.filter(pl.col("kickoff").is_not_null())
        .join(primary, on=["game_id", "franchise"])
        .select("franchise", pl.col("kickoff").alias("done_at"), "prev_passer")
        .sort("done_at")
    )
    left = gt.filter(pl.col("kickoff").is_not_null()).sort("kickoff")
    return left.join_asof(
        done,
        left_on="kickoff",
        right_on="done_at",
        by="franchise",
        strategy="backward",
        allow_exact_matches=False,
        check_sortedness=False,
    ).select("game_id", "team", "prev_passer")


def charted_qb1(games: pl.DataFrame, depth: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    """(game_id, team, qb1): each game-team's charted starter, the same lookup `compute` uses."""
    gt = _game_teams(games, build_ts)
    return (
        _charts(gt, depth)
        .filter(pl.col("pos") == "QB")
        .sort("ord")
        .group_by("game_id", "team", maintain_order=True)
        .agg(pl.col("gsis_id").first().alias("qb1"))
    )


def charted_starters(games: pl.DataFrame, depth: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    """(game_id, team, gsis_id): everyone listed first at a position for each game-team, special
    teams excluded, from the same lookup `compute` uses."""
    return (
        _charts(_game_teams(games, build_ts), depth).select("game_id", "team", "gsis_id").unique()
    )


def compute(
    games: pl.DataFrame,
    injuries: pl.DataFrame,
    depth: pl.DataFrame,
    plays: pl.DataFrame,
    build_ts: datetime,
    values: pl.DataFrame | None = None,
    rates: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Pure core. Returns (game_id, team, feature, value) for every game-team and feature."""
    gt = _game_teams(games, build_ts)
    charts = _charts(gt, depth)
    agg = _chart_aggregates(gt, charts, injuries)
    reports = (
        injuries.with_columns(_franchise("team").alias("franchise"))
        .group_by("season", "week", "franchise")
        .agg(
            pl.lit(True).alias("has_report"),
            # game statuses only: 'Probable' was abolished in 2016, so counting it would make
            # pre-2016 reports look twice as long
            pl.col("gsis_id")
            .filter(pl.col("report_status").is_in(["Out", "Doubtful", "Questionable"]))
            .n_unique()
            .cast(pl.Float64)
            .alias("report_count"),
        )
    )
    if values is not None and rates is not None:
        vf = _value_features(gt, charts, injuries, values, rates)
    else:
        vf = pl.DataFrame(
            schema={
                "game_id": gt.schema["game_id"],
                "team": gt.schema["team"],
                "value_lost": pl.Float64,
                "ol_weakest": pl.Float64,
                "values_ready": pl.Boolean,
            }
        )
    j = (
        gt.join(agg, on=["game_id", "team"], how="left")
        .join(vf, on=["game_id", "team"], how="left")
        .join(reports, on=["season", "week", "franchise"], how="left")
        .join(_prev_passer(gt, plays), on=["game_id", "team"], how="left")
    )
    ok = pl.col("has_report").fill_null(False) & pl.col("has_chart").fill_null(False)

    def gated(c: str) -> pl.Expr:
        return pl.when(ok).then(pl.col(c).cast(pl.Float64)).otherwise(None)

    wide = j.select(
        "game_id",
        "team",
        pl.when(ok & pl.col("qb1").is_not_null())
        .then(pl.col("qb1_out").cast(pl.Float64))
        .otherwise(None)
        .alias("availability.qb1_out"),
        pl.when(pl.col("qb1").is_not_null() & pl.col("prev_passer").is_not_null())
        .then((pl.col("qb1") != pl.col("prev_passer")).cast(pl.Float64))
        .otherwise(None)
        .alias("availability.qb_change"),
        gated("starters_out").alias("availability.starters_out"),
        gated("injury_impact").alias("availability.injury_impact"),
        gated("ol_starters_out").alias("availability.ol_starters_out"),
        pl.col("report_count").cast(pl.Float64).alias("availability.report_count"),
        pl.when(ok & pl.col("values_ready").fill_null(False))
        .then(pl.col("value_lost"))
        .otherwise(None)
        .alias("availability.value_lost"),
        pl.when(ok & pl.col("values_ready").fill_null(False))
        .then(pl.col("ol_weakest"))
        .otherwise(None)
        .alias("availability.ol_weakest"),
    )
    return wide.unpivot(index=["game_id", "team"], variable_name="feature", value_name="value")


def build(paths: Paths, games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    inj, depth, plays = load_inputs(paths)
    pv, rates = load_value_inputs(paths)
    values = compute(games, inj, depth, plays, build_ts, pv, rates)
    return store.from_team_values(values, games, source=SOURCE, version=VERSION, build_ts=build_ts)
