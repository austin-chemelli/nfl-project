"""`nfl features`: run every family builder and upsert into the store (architecture §3.3).

Builders get the full games frame (they need history for season-to-date and lookback values) and
their output is filtered to the requested seasons before writing. Families whose module isn't
present yet are skipped with a note, so the command works while builders are being added.
"""

from __future__ import annotations

import importlib
import time
from datetime import datetime

import polars as pl

from nfl.config import FIRST_SEASON, Paths, now_utc
from nfl.features import store

# Order matters only for readability of the report.
FAMILIES = [
    "strength",
    "environment",
    "form",
    "decisions",
    "front",
    "market",
    "availability",
    "narrative",
]


def builders(families: list[str] | None = None) -> dict[str, object]:
    out = {}
    for fam in families or FAMILIES:
        try:
            out[fam] = importlib.import_module(f"nfl.features.{fam}")
        except ModuleNotFoundError as e:
            if e.name != f"nfl.features.{fam}":
                raise
    return out


def build_all(
    paths: Paths,
    seasons: tuple[int, int] | None = None,
    families: list[str] | None = None,
    build_ts: datetime | None = None,
) -> pl.DataFrame:
    """Build and write. Returns a report frame: family, feature, rows, null_share, seconds."""
    build_ts = build_ts or now_utc()
    lo, hi = seasons or (FIRST_SEASON, 9999)
    games = store.games_frame(paths)
    report = []
    for fam, mod in builders(families).items():
        t0 = time.perf_counter()
        rows = mod.build(paths, games, build_ts)
        rows = rows.filter(pl.col("season").is_between(lo, hi))
        wrong = rows.filter(~pl.col("feature").str.starts_with(f"{fam}."))
        if not wrong.is_empty():
            raise ValueError(f"{fam} builder emitted foreign features: {wrong['feature'].unique()}")
        store.write_features(paths, rows)
        secs = time.perf_counter() - t0
        stats = rows.group_by("feature").agg(
            pl.len().alias("rows"), pl.col("value").null_count().alias("nulls")
        )
        for feat, n, nulls in stats.sort("feature").iter_rows():
            report.append((fam, feat, n, nulls / n if n else 0.0, secs))
    missing = sorted(set(families or FAMILIES) - set(builders(families)))
    return pl.DataFrame(
        report,
        schema=["family", "feature", "rows", "null_share", "seconds"],
        orient="row",
    ).with_columns(pl.lit(", ".join(missing)).alias("missing_builders"))
