"""News family: countable facts from the narrative records (ADR 0032), live only.

Two team features, derived in code from a record's cited, roster-checked fields (schema v3), so the
news adjustment (`nfl.approaches.news`) reads facts, not moods:

- `news.qb_change_confirmed`: 1 when reporting names a starting QB (`qb_named_starter`) who is
  neither the franchise's primary passer in its previous game nor the depth chart's QB1 as of the
  record's `known_as_of` (the depth-chart disagreement, idea A6); 0 otherwise (nothing named, or the
  same man; also 0 when no reference QB is known, as nothing can be said to differ).
- `news.starters_ruled_out_new`: how many of the record's `starters_ruled_out` the injury report
  rows known before the record do not list as Out or Doubtful for that game. Rows without a
  timestamp count as known (the convention of `availability`'s value features); null when the
  injury table is absent.

Rows are stamped with the record's `known_as_of` (a lock only sees records before it), one set per
record, never backfilled. Records older than schema v3 emit nothing: they didn't ask. This is its
own family (not part of `narrative`) because `build.py` requires a family's features to carry its
name and the other agent reads `news.*`.
"""

from __future__ import annotations

import warnings
from datetime import datetime

import duckdb
import polars as pl

from nfl.config import Paths
from nfl.features import availability, store
from nfl.llm.checks import same_person
from nfl.llm.narrative import GameNarrative, load_records

SOURCE = "llm_news"
VERSION = "1"


def player_names(paths: Paths) -> dict[str, set[str]]:
    """gsis_id -> the names a player goes by (display name, first and last, football name)."""
    f = paths.curated_table("players")
    files = sorted(f.glob("*.parquet")) + sorted(f.glob("*/*.parquet"))
    if not files:
        return {}
    d = pl.read_parquet(files[0], columns=["gsis_id", "display_name", "first_name", "last_name", "football_name"])  # fmt: skip
    out: dict[str, set[str]] = {}
    for g, disp, first, last, fb in d.iter_rows():
        if g:
            out[g] = {n for n in (disp, f"{first} {last}" if first and last else None,
                                  f"{fb} {last}" if fb and last else None) if n}  # fmt: skip
    return out


def load_injuries(paths: Paths) -> pl.DataFrame | None:
    """(season, week, franchise, name, status, date_modified), or None without the table."""
    glob = f"{paths.curated_table('injuries').as_posix()}/*/*.parquet"
    if not list(paths.curated_table("injuries").glob("*/*.parquet")):
        return None
    d = (
        duckdb.connect()
        .sql(
            'select cast(season as bigint) as season, cast(week as bigint) as "week", team, '
            "full_name as name, report_status as status, timezone('UTC', date_modified) as date_modified "
            f"from read_parquet('{glob}', hive_partitioning=true, union_by_name=true)"
        )
        .pl()
    )
    d = d.with_columns(pl.col("date_modified").dt.replace_time_zone(None).cast(pl.Datetime("us")))
    return d.with_columns(availability._franchise("team").alias("franchise")).select(
        "season", "week", "franchise", "name", "status", "date_modified"
    )


def _rows(
    records: list[GameNarrative],
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    depth: pl.DataFrame | None,
    inj: pl.DataFrame | None,
    names: dict[str, set[str]],
    build_ts: datetime,
) -> pl.DataFrame:
    if inj is not None:  # naive UTC, null-safe (a table with no stamps at all is typed null)
        inj = inj.with_columns(pl.col("date_modified").cast(pl.Datetime("us")))
    gt = availability._game_teams(games, build_ts)
    prev = availability._prev_passer(gt, plays) if plays is not None else None
    team_of = {(r["game_id"], r["team"]): r for r in gt.iter_rows(named=True)}
    rows = []
    for rec in records:
        for side in (rec.home, rec.away):
            gtr = team_of.get((rec.game_id, side.team))
            if gtr is None:
                continue
            # the QB check: references as of the record, never as of the lock or the build
            refs: set[str] = set()
            if depth is not None and prev is not None:
                one = gt.filter((pl.col("game_id") == rec.game_id) & (pl.col("team") == side.team))
                one = one.with_columns(pl.lit(rec.known_as_of).cast(pl.Datetime("us")).alias("cutoff"))  # fmt: skip
                chart = availability._charts(one, depth).filter(pl.col("pos") == "QB").sort("ord")
                ids = chart["gsis_id"].head(1).to_list()
                ids += prev.filter((pl.col("game_id") == rec.game_id) & (pl.col("team") == side.team))["prev_passer"].drop_nulls().to_list()  # fmt: skip
                refs = {n for i in ids for n in names.get(i, ())}
            named = side.qb_named_starter
            qb = 1.0 if named and refs and not any(same_person(named, n) for n in refs) else 0.0
            rows.append((rec.game_id, side.team, "news.qb_change_confirmed", qb, rec.known_as_of))
            new = None
            if inj is not None:
                listed = inj.filter(
                    (pl.col("season") == rec.season) & (pl.col("week") == rec.week)
                    & (pl.col("franchise") == gtr["franchise"]) & pl.col("status").is_in(availability.OUT_STATUSES)
                    & (pl.col("date_modified").is_null() | (pl.col("date_modified") < rec.known_as_of))
                )["name"].drop_nulls().to_list()  # fmt: skip
                new = float(sum(not any(same_person(n, x) for x in listed) for n in side.starters_ruled_out))  # fmt: skip
            rows.append(
                (rec.game_id, side.team, "news.starters_ruled_out_new", new, rec.known_as_of)
            )
    if not rows:
        return pl.DataFrame(schema=store.FEATURE_SCHEMA)
    v = pl.DataFrame(rows, schema=["game_id", "team", "feature", "value", "known_as_of"], orient="row")  # fmt: skip
    return store.from_team_values(v, games, source=SOURCE, version=VERSION, build_ts=build_ts)


def build(paths: Paths, games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    kick = dict(zip(games["game_id"], games["kickoff_utc"].dt.replace_time_zone(None), strict=True))
    records = []
    for r in load_records(paths):
        if r.schema_version != "3":
            continue
        k = kick.get(r.game_id)
        if k is None or r.known_as_of >= k:
            warnings.warn(f"skipping news record {r.game_id} @ {r.known_as_of}: not before kickoff {k}", stacklevel=2)  # fmt: skip
            continue
        records.append(r)
    if not records:
        return pl.DataFrame(schema=store.FEATURE_SCHEMA)
    plays = depth = None
    try:
        _, depth, plays = availability.load_inputs(paths)
        seasons = {r.season for r in records}
        depth = (
            depth.filter(pl.col("season").is_in(seasons)) if "season" in depth.columns else depth
        )
    except Exception as e:  # noqa: BLE001  (no charts or plays on this machine: only the injury half)
        print(f"(news: no depth charts or plays: {type(e).__name__})")
    return _rows(records, games, plays, depth, load_injuries(paths), player_names(paths), build_ts)
