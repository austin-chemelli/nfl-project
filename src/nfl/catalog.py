"""One SQL surface over every table (ADR 0025): DuckDB views over the parquet files, built per process.

    from nfl.catalog import connect
    con = connect(paths)
    con.sql("select * from features_asof(timestamp '2026-11-05 13:00') where game_id = ?", ...)

or `uv run nfl sql "select ..."`. The views read the files as they are; nothing is copied, cached or
written, so the catalog is never a second source of truth. Build it again to see newer files.

A table is a set of parquet files: curated tables are hive-partitioned by season; a mart is either one
file (`marts/<name>.parquet`) or a folder of parts (`marts/<name>/**/*.parquet`), and the view reads
both, so a mart can move to one file per append without changing a reader. A derived table is a SQL
model's output (`marts/derived/<name>.parquet`, built by `nfl models build`). A table with no files yet
gets no view (`missing()` lists them).

Point in time (ADR 0005): `features_asof(ts)` is `store.as_of` in SQL, the latest row per
(game_id, side, feature) with `known_as_of` strictly before `ts`; `game_vectors(ts)` is
`store.game_vectors` over it (home minus away for team features, the value for game features).
Tests hold both equal to the Polars versions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from nfl.config import Paths


@dataclass(frozen=True)
class Table:
    name: str
    layer: str  # curated | features | derived | mart
    about: str


TABLES: tuple[Table, ...] = (
    Table("games", "curated", "one row per game: teams, kickoff, scores, schedule lines, stadium, referee"),
    Table("plays", "curated", "nflverse play-by-play joined to FTN charting where it exists"),
    Table("lines", "curated", "every sportsbook's quote at every odds snapshot (one row per book, market, side)"),
    Table("injuries", "curated", "weekly injury reports"),
    Table("depth_charts", "curated", "depth charts (timestamped from 2025)"),
    Table("participation", "curated", "per-play personnel and coverage (past seasons only)"),
    Table("player_weeks", "curated", "per player and week: passing, rushing, receiving, defense (player_id is the gsis id)"),
    Table("snap_counts", "curated", "snaps and share per player and game, 2012+ (keyed by pfr_player_id)"),
    Table("pfr_pass", "curated", "PFR advanced passing by week, 2018+: drops, bad throws, pressure"),
    Table("pfr_rush", "curated", "PFR advanced rushing by week, 2018+: yards before and after contact"),
    Table("pfr_rec", "curated", "PFR advanced receiving by week, 2018+: drops, broken tackles"),
    Table("pfr_def", "curated", "PFR advanced defense by week, 2018+: coverage targets, pressures"),
    Table("players", "curated", "every player: gsis, pfr, espn ids, position, draft, birth date"),
    Table("contracts", "curated", "contracts from Over The Cap: value, APY, cap share (gsis_id)"),
    Table("draft_picks", "curated", "every draft pick with career summary (gsis_id, pfr_player_id)"),
    Table("features", "features", "the feature store, long and as-of stamped: use features_asof(ts)"),
    Table("predictions", "mart", "every forecast, live and backfill (append-only)"),
    Table("bets", "mart", "paper bets at each lock (append-only)"),
    Table("bets_settled", "mart", "paper bets with results and closing-line value"),
    Table("graded", "mart", "predictions joined to results and the market"),
    Table("scorecard", "mart", "per-approach scores"),
    Table("summary", "mart", "scorecard summary with intervals"),
    Table("reliability", "mart", "calibration bins"),
    Table("divergence", "mart", "results by size of disagreement with the market"),
    Table("ledger_summary", "mart", "paper-bet ledger by approach"),
    Table("strong_calls", "mart", "disagreements with the market recorded at lock (append-only)"),
    Table("totals", "mart", "the Student's point total at each lock (append-only)"),
    Table("previews", "mart", "preview scores between locks, never graded (append-only)"),
    Table("tendencies", "mart", "team x situation x metric rates"),
    Table("hypotheses", "mart", "per-feature coefficients and verdicts"),
    Table("elo_ratings", "mart", "Elo ratings by game"),
    Table("coach_priors", "mart", "coach priors"),
    Table("coach_profiles", "mart", "coach profiles"),
    Table("scheme_team_season", "mart", "scheme rates by team-season"),
    Table("scheme_qb_season", "mart", "scheme rates by quarterback-season"),
    Table("audit", "mart", "null rates per table and column"),
    Table("llm_calls", "mart", "one row per local-model request"),
    Table("candidates", "mart", "the candidates ledger: every second-level candidate's gates and verdict (append-only)"),
    Table("team_week", "derived", "SQL model: plays aggregated per season, week, game, team and side (off/def)"),
)  # fmt: skip

BY_NAME = {t.name: t for t in TABLES}

_MACROS = """
create or replace macro features_asof(ts) as table
    select * exclude (_rn) from (
        select *, row_number() over (
            partition by game_id, side, feature order by known_as_of desc
        ) as _rn
        from features
        where known_as_of < cast(ts as timestamp)
    )
    where _rn = 1;

create or replace macro game_vectors(ts) as table
    with a as (select * from features_asof(ts))
    select game_id, feature,
        max(value) filter (where side = 'home') - max(value) filter (where side = 'away') as value
    from a where side <> 'game' group by game_id, feature
    union all
    select game_id, feature, value from a where side = 'game';
"""


def files(paths: Paths, t: Table) -> list[Path]:
    """The parquet files behind a table, sorted (empty when it doesn't exist yet)."""
    if t.layer == "curated":  # by season, or one file for the tables that have no seasons
        d = paths.curated_table(t.name)
        return sorted(d.glob("season=*/*.parquet")) or sorted(d.glob("*.parquet"))
    if t.layer == "features":
        return sorted((paths.marts / "features").glob("season=*/*.parquet"))
    if t.layer == "derived":
        f = paths.marts / "derived" / f"{t.name}.parquet"
        return [f] if f.exists() else []
    single = paths.marts / f"{t.name}.parquet"
    parts = (
        sorted((paths.marts / t.name).rglob("*.parquet")) if (paths.marts / t.name).is_dir() else []
    )
    return ([single] if single.exists() else []) + parts


def _sql_list(fs: list[Path]) -> str:
    return "[" + ", ".join("'" + f.as_posix().replace("'", "''") + "'" for f in fs) + "]"


def connect(
    paths: Paths, only: list[str] | None = None, con: duckdb.DuckDBPyConnection | None = None
) -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB connection with a view per table that has files (`only` limits which), and
    the point-in-time macros when `features` is among them. UTC session time zone."""
    con = con or duckdb.connect()
    con.execute("set timezone='UTC'")
    for t in TABLES:
        if only is not None and t.name not in only:
            continue
        fs = files(paths, t)
        if not fs:
            continue
        hive = "true" if t.layer in ("curated", "features") else "false"
        con.execute(
            f'create or replace view "{t.name}" as select * from read_parquet('
            f"{_sql_list(fs)}, hive_partitioning={hive}, union_by_name=true)"
        )
        if t.name == "features":
            con.execute(_MACROS)
    return con


def missing(paths: Paths) -> list[str]:
    """Tables in the registry with no files under this data root."""
    return [t.name for t in TABLES if not files(paths, t)]


def describe(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Each view: name, rows, columns, what it is."""
    out = []
    for (name,) in con.sql(
        "select view_name from duckdb_views() where not internal order by 1"
    ).fetchall():
        rows = con.sql(f'select count(*) from "{name}"').fetchall()[0][0]
        cols = [r[0] for r in con.sql(f'describe "{name}"').fetchall()]
        about = BY_NAME[name].about if name in BY_NAME else ""
        out.append({"name": name, "rows": rows, "columns": cols, "about": about})
    return out
