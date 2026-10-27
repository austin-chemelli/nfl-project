"""`nfl fit` and `nfl predict --backfill` for the approaches.

fit_all     selects λ and writes walk-forward artifacts for every approach config and the global fit.
backfill    scores every completed game in the scored seasons with the models trained through the
            previous season, at the synthetic lock (kickoff − 1h, is_backfill=true), plus the
            ensemble. Backfill rows are derived, not the public record: re-running replaces the
            backfill rows of the same model_ids. Live rows (is_backfill=false) are never touched.
"""

from __future__ import annotations

import subprocess

import polars as pl

from nfl.approaches import ensemble, fit
from nfl.approaches.schema import Approach, check_features, load_all
from nfl.config import FIRST_SCORED_SEASON, Paths
from nfl.features import store
from nfl.predict import PRED_SCHEMA, append_rows


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except OSError, subprocess.CalledProcessError:
        return "nogit"


def known_features(paths: Paths) -> set[str]:
    return set(store.read_features(paths).get_column("feature").unique().to_list())


def scored_approaches(paths: Paths) -> list[Approach]:
    known = known_features(paths)
    out = []
    for a in load_all().values():
        if a.id == "narrative":  # live-only, persona flavor, never fitted (M6.5)
            continue
        if not a.grouped:
            check_features(a, known)
        out.append(a)
    return [*out, ensemble.global_approach(known)]


def fit_all(paths: Paths, scored: tuple[int, int] = (FIRST_SCORED_SEASON, 2026)) -> pl.DataFrame:
    known = known_features(paths)
    tables = [fit.fit_approach(paths, a, scored, known) for a in scored_approaches(paths)]
    return pl.concat(tables)


def backfill(paths: Paths, scored: tuple[int, int] = (FIRST_SCORED_SEASON, 2025)) -> int:
    approaches = scored_approaches(paths)
    sha = git_sha()
    rows = []
    model_ids: set[str] = set()
    games = store.games_frame(paths).filter(
        pl.col("season").is_between(*scored) & pl.col("result").is_not_null()
    )
    for season in range(scored[0], scored[1] + 1):
        g = games.filter(pl.col("season") == season)
        if g.is_empty():
            continue
        members = []
        # every completed game, ties included (grading drops ties); features as of the lock
        locks = g.select("game_id", (pl.col("kickoff_utc") - fit.SYNTHETIC_LOCK).alias("lock_ts"))
        vec = store.game_vectors(store.as_of(store.read_features(paths, (season, season)), locks))
        for a in approaches:
            flavors = ["fitted"] if a.id == ensemble.GLOBAL_ID else ["persona", "fitted"]
            for flavor in flavors:
                mid = a.id if a.id == ensemble.GLOBAL_ID else f"{a.id}.{flavor}"
                model = fit.load(paths, f"{a.id}.{flavor}", season - 1)
                # the artifact's own feature list: grouped approaches resolve against the store
                wide = g.select("game_id").join(
                    store.to_wide(vec, model.features), on="game_id", how="left"
                )
                scored_df = model.score(wide)
                if flavor == "fitted" and a.id != ensemble.GLOBAL_ID and not a.shadow:
                    members.append(scored_df)
                version = f"{sha}+{model.meta.get('config_hash', '')}"
                rows.append(_rows(g, scored_df, mid, version))
                model_ids.add(mid)
        if members:
            rows.append(_rows(g, ensemble.combine(members), ensemble.ENSEMBLE_ID, sha))
            model_ids.add(ensemble.ENSEMBLE_ID)
    new = pl.concat(rows) if rows else pl.DataFrame(schema=PRED_SCHEMA)
    return append_rows(paths, new, replace_backfill_for=model_ids)


def _rows(games: pl.DataFrame, scored: pl.DataFrame, model_id: str, version: str) -> pl.DataFrame:
    return (
        games.select(
            "game_id",
            pl.col("season").cast(pl.Int64),
            pl.col("week").cast(pl.Int64),
            (pl.col("kickoff_utc") - fit.SYNTHETIC_LOCK).alias("lock_ts"),
            "total_line",
        )
        .join(scored, on="game_id")
        .select(
            "game_id",
            "season",
            "week",
            pl.lit(model_id).alias("model_id"),
            pl.lit(version).alias("model_version"),
            pl.col("lock_ts").cast(pl.Datetime("us")),
            pl.lit("features").alias("data_snapshot_ts"),
            "p_home",
            "spread_home",
            pl.col("total_line").cast(pl.Float64).alias("total"),
            pl.lit(13.5).alias("sd_margin"),
            pl.lit(True).alias("is_backfill"),
            pl.lit("backfill").alias("slot"),
            "contributions",
        )
        .cast(PRED_SCHEMA)
    )
