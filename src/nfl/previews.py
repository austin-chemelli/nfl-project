"""Preview scores between locks (ADR 0023, M20.5): what each approach says today, never graded.

Every daily pass scores the upcoming games with the same locked artifacts the next lock will use,
on features as of now, and appends to `marts/previews.parquet` (game_id, model_id, scored_at,
p_home, spread_home). Nothing here is a prediction of record: previews never reach
`predictions.parquet`, grading, the tracker, the retro, the recap or the README (a test guards it).
The game page shows the latest one beside the locked pick, labelled "preview, not locked".
"""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl

from nfl.config import Paths, current_season, now_utc

FILE = "previews.parquet"
HORIZON = timedelta(days=9)  # this week's games and the start of next week's
SCHEMA = {"game_id": pl.Utf8, "model_id": pl.Utf8, "scored_at": pl.Datetime("us"),
          "p_home": pl.Float64, "spread_home": pl.Float64}  # fmt: skip


def score(paths: Paths, now: datetime | None = None, season: int | None = None) -> pl.DataFrame:
    """Every upcoming game within `HORIZON`, scored by every locked approach. Empty if none."""
    from nfl import lock
    from nfl.features import store

    now = (now or now_utc()).replace(tzinfo=None, microsecond=0)
    season = season or current_season()
    games = store.games_frame(paths).filter(pl.col("season") == season)
    kick = pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us"))
    slate = games.filter((kick > now) & (kick <= now + HORIZON))
    if slate.is_empty():
        return pl.DataFrame(schema=SCHEMA)
    models, _missing = lock.load_models(paths, season - 1)
    feats = store.read_features(paths, seasons=(season, season))
    rows = []
    for s in lock.score_approaches(models, feats, slate, now):
        rows.append(s.frame.select("game_id", "p_home", "spread_home").with_columns(
            pl.lit(s.model_id).alias("model_id"), pl.lit(now, dtype=pl.Datetime("us")).alias("scored_at")))  # fmt: skip
    return pl.concat(rows).select(list(SCHEMA)).cast(SCHEMA)


def append(paths: Paths, frame: pl.DataFrame) -> int:
    """Append-only, like the predictions: rows are never edited."""
    if frame.is_empty():
        return 0
    f = paths.marts / FILE
    old = pl.read_parquet(f) if f.exists() else pl.DataFrame(schema=SCHEMA)
    pl.concat([old.cast(SCHEMA), frame.cast(SCHEMA)]).write_parquet(f)
    return frame.height


def latest(paths: Paths) -> pl.DataFrame:
    """The latest preview per (game, model)."""
    f = paths.marts / FILE
    if not f.exists():
        return pl.DataFrame(schema=SCHEMA)
    return pl.read_parquet(f).sort("scored_at").group_by("game_id", "model_id").last()


def run(paths: Paths) -> int:
    return append(paths, score(paths))
