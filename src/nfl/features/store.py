"""Feature store: one long, as-of stamped table (architecture §3.3).

Row = (season, week, game_id, side, feature, value, known_as_of, source, version).
  side         'home' | 'away' for team-level values, 'game' for game-level values
  feature      '<family>.<name>', e.g. 'environment.rest_days'
  known_as_of  when the value became knowable. Backtest rows: kickoff - BACKTEST_ASOF_OFFSET
               (synthetic; historical data is not bitemporal). Live rows: the build/snapshot time.

Layout: marts/features/season=YYYY/<family>.parquet. Writes are upserts on
(game_id, side, feature, known_as_of); a newer row whose value equals the latest stored value for
the same (game_id, side, feature) is skipped, so repeated live builds don't grow the store.

Builders should go through `from_team_values` / `from_game_values` so stamping is uniform.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import polars as pl

from nfl.config import FIRST_SEASON, Paths

# Synthetic locks for historical games are kickoff - 1h (predict.py); feature rows must be strictly
# earlier, so they are stamped kickoff - 2h.
BACKTEST_ASOF_OFFSET = timedelta(hours=2)

FEATURE_SCHEMA: dict[str, pl.DataType] = {
    "season": pl.Int64(),
    "week": pl.Int64(),
    "game_id": pl.Utf8(),
    "side": pl.Utf8(),
    "feature": pl.Utf8(),
    "value": pl.Float64(),
    "known_as_of": pl.Datetime("us"),
    "source": pl.Utf8(),
    "version": pl.Utf8(),
}
KEY = ["game_id", "side", "feature"]
SIDES = {"home", "away", "game"}
FEATURE_RX = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


# ---------------------------------------------------------------------------------------- inputs


def games_frame(paths: Paths, min_season: int = FIRST_SEASON) -> pl.DataFrame:
    """All curated game columns, ordered by kickoff. The shared input for every builder."""
    con = duckdb.connect()
    con.execute("set timezone='UTC'")
    glob = f"{paths.curated_table('games').as_posix()}/*/*.parquet"
    return con.sql(
        f"select * exclude (raw_snapshot_ts) from read_parquet('{glob}', hive_partitioning=true) "
        f"where season >= {min_season} order by kickoff_utc nulls last, game_id"
    ).pl()


def stamp(kickoff_utc: pl.Expr, build_ts: datetime) -> pl.Expr:
    """known_as_of rule: games already kicked off at build time get the synthetic backtest stamp;
    upcoming games get the build time (what was known when we computed it)."""
    build = pl.lit(build_ts.replace(tzinfo=None), dtype=pl.Datetime("us"))
    synthetic = kickoff_utc.cast(pl.Datetime("us")) - BACKTEST_ASOF_OFFSET
    return pl.when(kickoff_utc.is_not_null() & (synthetic < build)).then(synthetic).otherwise(build)


def _game_keys(games: pl.DataFrame) -> pl.DataFrame:
    return games.select(
        "game_id",
        pl.col("season").cast(pl.Int64),
        pl.col("week").cast(pl.Int64),
        "home_team",
        "away_team",
        pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us")),
    )


def from_team_values(
    values: pl.DataFrame,
    games: pl.DataFrame,
    *,
    source: str,
    version: str,
    build_ts: datetime,
) -> pl.DataFrame:
    """values: (game_id, team, feature, value) -> store rows with side = home/away.

    Rows whose team is neither the home nor the away team of that game are an error."""
    g = _game_keys(games)
    j = values.join(g, on="game_id", how="inner")
    side = (
        pl.when(pl.col("team") == pl.col("home_team"))
        .then(pl.lit("home"))
        .when(pl.col("team") == pl.col("away_team"))
        .then(pl.lit("away"))
    )
    j = j.with_columns(side.alias("side"))
    bad = j.filter(pl.col("side").is_null())
    if not bad.is_empty():
        raise ValueError(f"team not in game: {bad.select('game_id', 'team').head(3).rows()}")
    return _finish(j, source, version, build_ts)


def from_game_values(
    values: pl.DataFrame,
    games: pl.DataFrame,
    *,
    source: str,
    version: str,
    build_ts: datetime,
) -> pl.DataFrame:
    """values: (game_id, feature, value[, known_as_of]) -> store rows with side = 'game'.

    If `values` carries its own `known_as_of` (e.g. an odds snapshot time), it is kept as-is
    instead of the stamping rule; it must be strictly before kickoff."""
    j = values.join(_game_keys(games), on="game_id", how="inner").with_columns(
        pl.lit("game").alias("side")
    )
    return _finish(j, source, version, build_ts)


def _finish(j: pl.DataFrame, source: str, version: str, build_ts: datetime) -> pl.DataFrame:
    if "known_as_of" in j.columns:
        kao = pl.col("known_as_of").cast(pl.Datetime("us"))
        late = j.filter(kao >= pl.col("kickoff_utc"))
        if not late.is_empty():
            raise ValueError(
                f"explicit known_as_of at/after kickoff: {late['game_id'].head(3).to_list()}"
            )
    else:
        kao = stamp(pl.col("kickoff_utc"), build_ts)
    out = j.with_columns(
        pl.col("value").cast(pl.Float64),
        kao.alias("known_as_of"),
        pl.lit(source).alias("source"),
        pl.lit(version).alias("version"),
    ).select(list(FEATURE_SCHEMA))
    validate(out)
    return out.cast(FEATURE_SCHEMA)


# ------------------------------------------------------------------------------------ validation


def family_of(feature: str) -> str:
    return feature.split(".", 1)[0]


def validate(df: pl.DataFrame) -> None:
    missing = set(FEATURE_SCHEMA) - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    names = df.get_column("feature").unique().to_list()
    bad = [n for n in names if not FEATURE_RX.match(n or "")]
    if bad:
        raise ValueError(f"feature names must be '<family>.<name>': {bad[:5]}")
    sides = set(df.get_column("side").unique().to_list()) - SIDES
    if sides:
        raise ValueError(f"bad side values: {sides}")
    if df.get_column("known_as_of").null_count():
        raise ValueError("known_as_of may not be null")
    mixed = (
        df.with_columns((pl.col("side") == "game").alias("is_game"))
        .group_by("feature")
        .agg(pl.col("is_game").n_unique().alias("k"))
        .filter(pl.col("k") > 1)
    )
    if not mixed.is_empty():
        raise ValueError(f"features mix team and game sides: {mixed['feature'].to_list()}")
    dup = df.group_by([*KEY, "known_as_of"]).len().filter(pl.col("len") > 1)
    if not dup.is_empty():
        raise ValueError(f"duplicate (game_id, side, feature, known_as_of): {dup.head(3).rows()}")


# --------------------------------------------------------------------------------- write / read


def _root(paths: Paths) -> Path:
    return paths.marts / "features"


def _file(paths: Paths, season: int, family: str) -> Path:
    return _root(paths) / f"season={season}" / f"{family}.parquet"


def _same(a: float | None, b: float | None) -> bool:
    if a is None or b is None or (isinstance(a, float) and math.isnan(a)):
        return a is None and b is None
    return abs(a - b) <= 1e-12 * max(1.0, abs(a), abs(b))


def write_features(paths: Paths, df: pl.DataFrame) -> int:
    """Upsert rows into the store, one file per (season, family). Returns rows written (new or
    replaced). See module docstring for the dedup rule."""
    if df.is_empty():
        return 0
    validate(df)
    df = df.cast(FEATURE_SCHEMA)
    written = 0
    fam = df.with_columns(pl.col("feature").str.split(".").list.first().alias("_family"))
    for (season, family), part in fam.group_by(["season", "_family"], maintain_order=True):
        part = part.drop("_family")
        f = _file(paths, int(season), str(family))
        if f.exists():
            old = pl.read_parquet(f).cast(FEATURE_SCHEMA)
            # drop new rows that repeat the latest stored value for their key at a later as-of
            latest = (
                old.sort("known_as_of")
                .group_by(KEY)
                .agg(pl.col("known_as_of").last().alias("_ts"), pl.col("value").last().alias("_v"))
            )
            cand = part.join(latest, on=KEY, how="left")
            keep = [
                not (ts is not None and kao > ts and _same(v, ov))
                for kao, ts, v, ov in cand.select("known_as_of", "_ts", "value", "_v").iter_rows()
            ]
            part = cand.filter(pl.Series(keep)).drop("_ts", "_v")
            old = old.join(part.select([*KEY, "known_as_of"]), on=[*KEY, "known_as_of"], how="anti")
            merged = pl.concat([old, part])
        else:
            merged = part
        written += part.height
        f.parent.mkdir(parents=True, exist_ok=True)
        merged.sort(["game_id", "feature", "side", "known_as_of"]).write_parquet(f)
    return written


def read_features(
    paths: Paths,
    seasons: tuple[int, int] | None = None,
    families: list[str] | None = None,
) -> pl.DataFrame:
    root = _root(paths)
    files = sorted(root.glob("season=*/*.parquet"))
    if seasons:
        lo, hi = seasons
        files = [f for f in files if lo <= int(f.parent.name.split("=", 1)[1]) <= hi]
    if families:
        files = [f for f in files if f.stem in set(families)]
    if not files:
        return pl.DataFrame(schema=FEATURE_SCHEMA)
    return pl.concat([pl.read_parquet(f).cast(FEATURE_SCHEMA) for f in files])


# ------------------------------------------------------------------------------- as-of / vectors


def as_of(df: pl.DataFrame, lock_ts: datetime | pl.DataFrame) -> pl.DataFrame:
    """Latest row per (game_id, side, feature) with known_as_of strictly before the lock.

    lock_ts: one datetime for every game, or a frame (game_id, lock_ts) for per-game locks
    (backfill). Games missing from the frame are dropped."""
    if isinstance(lock_ts, datetime):
        cut = pl.lit(lock_ts.replace(tzinfo=None), dtype=pl.Datetime("us"))
        x = df.filter(pl.col("known_as_of") < cut)
    else:
        locks = lock_ts.select("game_id", pl.col("lock_ts").cast(pl.Datetime("us")))
        x = df.join(locks, on="game_id", how="inner").filter(
            pl.col("known_as_of") < pl.col("lock_ts")
        )
        x = x.drop("lock_ts")
    return x.sort("known_as_of").group_by(KEY, maintain_order=True).last()


def game_vectors(df: pl.DataFrame) -> pl.DataFrame:
    """As-of rows -> one value per (game_id, feature): home - away for team features (null if either
    side is null or missing), the value itself for game features. Long: (game_id, feature, value)."""
    team = df.filter(pl.col("side") != "game")
    wide = team.pivot(
        on="side", index=["game_id", "feature"], values="value", aggregate_function="first"
    )
    for s in ("home", "away"):
        if s not in wide.columns:
            wide = wide.with_columns(pl.lit(None, dtype=pl.Float64).alias(s))
    diff = wide.select("game_id", "feature", (pl.col("home") - pl.col("away")).alias("value"))
    game = df.filter(pl.col("side") == "game").select("game_id", "feature", "value")
    return pl.concat([diff, game]).sort("game_id", "feature")


def to_wide(vectors: pl.DataFrame, features: list[str]) -> pl.DataFrame:
    """(game_id, feature, value) -> one row per game, one column per requested feature (in order).
    Features absent from the store become all-null columns, so callers always get the same shape."""
    if vectors.is_empty():
        return pl.DataFrame(schema={"game_id": pl.Utf8, **{f: pl.Float64 for f in features}})
    w = vectors.filter(pl.col("feature").is_in(features)).pivot(
        on="feature", index="game_id", values="value", aggregate_function="first"
    )
    games = vectors.select("game_id").unique()
    w = games.join(w, on="game_id", how="left") if w.width > 1 else games
    for f in features:
        if f not in w.columns:
            w = w.with_columns(pl.lit(None, dtype=pl.Float64).alias(f))
    return w.select("game_id", *[pl.col(f).cast(pl.Float64) for f in features]).sort("game_id")
