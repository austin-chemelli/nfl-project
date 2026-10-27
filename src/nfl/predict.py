"""Produce prediction rows for every game in the requested seasons, walk-forward.

Rows go to marts/predictions.parquet (append-only). Historical games get one synthetic lock
(kickoff - 1h, is_backfill=true) and are never re-predicted; upcoming games get a new row per run
with lock_ts = now, so repeated lock runs are preserved as separate rows.
"""

from __future__ import annotations

from datetime import timedelta

import duckdb
import polars as pl

from nfl.config import FIRST_SEASON, Paths, now_utc
from nfl.models import elo as elo_model
from nfl.models import market, naive

PRED_SCHEMA = {
    "game_id": pl.Utf8,
    "season": pl.Int64,
    "week": pl.Int64,
    "model_id": pl.Utf8,
    "model_version": pl.Utf8,
    "lock_ts": pl.Datetime("us"),
    "data_snapshot_ts": pl.Utf8,
    "p_home": pl.Float64,
    "spread_home": pl.Float64,
    "total": pl.Float64,
    "sd_margin": pl.Float64,
    "is_backfill": pl.Boolean,
    "slot": pl.Utf8,  # 'backfill' | 'thu' | 'sat' | null for POC rows
    "contributions": pl.Utf8,  # JSON, final logit units (approaches only)
}


def load_games(paths: Paths) -> pl.DataFrame:
    con = duckdb.connect()
    return con.sql(
        f"""select game_id, season, game_type, week, kickoff_utc, home_team, away_team, result, total,
                   spread_line, total_line, home_moneyline, away_moneyline, location, raw_snapshot_ts
            from read_parquet('{paths.curated_table("games").as_posix()}/*/*.parquet', hive_partitioning=true)
            where season >= {FIRST_SEASON} order by kickoff_utc nulls last, game_id"""
    ).pl()


def existing(paths: Paths) -> pl.DataFrame:
    """Stored predictions with every PRED_SCHEMA column (older files lack slot/contributions)."""
    f = paths.marts / "predictions.parquet"
    if not f.exists():
        return pl.DataFrame(schema=PRED_SCHEMA)
    df = pl.read_parquet(f)
    for c, t in PRED_SCHEMA.items():
        if c not in df.columns:
            df = df.with_columns(pl.lit(None, dtype=t).alias(c))
    return df.select(list(PRED_SCHEMA)).cast(PRED_SCHEMA)


def append_rows(
    paths: Paths, new: pl.DataFrame, replace_backfill_for: set[str] | None = None
) -> int:
    """Append prediction rows. Backfill rows (synthetic, derived) of the given model_ids are replaced;
    live rows are never modified or dropped."""
    prev = existing(paths)
    if replace_backfill_for:
        prev = prev.filter(
            ~(pl.col("is_backfill") & pl.col("model_id").is_in(sorted(replace_backfill_for)))
        )
    out = pl.concat([prev, new.select(list(PRED_SCHEMA)).cast(PRED_SCHEMA)])
    paths.marts.mkdir(parents=True, exist_ok=True)
    out.write_parquet(paths.marts / "predictions.parquet")
    return new.height


def predict(paths: Paths, seasons: tuple[int, int] | None) -> int:
    lo, hi = seasons or (2025, 2026)
    games = load_games(paths)
    prev = existing(paths)
    done_backfill = set(
        prev.filter(pl.col("is_backfill"))
        .select(pl.concat_str(["game_id", pl.lit("|"), "model_id"]))
        .to_series()
    )
    now = now_utc().replace(tzinfo=None)
    elo = elo_model.Elo()
    rows: list[dict] = []

    for g in games.iter_rows(named=True):
        elo.new_season(g["season"])
        kickoff = g["kickoff_utc"]
        played = g["result"] is not None
        in_range = lo <= g["season"] <= hi
        neutral = (g["location"] or "Home") != "Home"
        if in_range and (played or (kickoff is not None and kickoff > now - timedelta(hours=4))):
            lock_ts = (kickoff - timedelta(hours=1)) if played and kickoff else now
            preds = {
                market.MODEL_ID: (
                    market.MODEL_VERSION,
                    market.predict(
                        g["spread_line"], g["total_line"], g["home_moneyline"], g["away_moneyline"]
                    ),
                ),
                elo_model.MODEL_ID: (
                    elo_model.MODEL_VERSION,
                    elo.predict(g["home_team"], g["away_team"], neutral),
                ),
                naive.MODEL_ID: (naive.MODEL_VERSION, naive.predict(g["total_line"])),
            }
            for model_id, (version, p) in preds.items():
                if p is None or (played and f"{g['game_id']}|{model_id}" in done_backfill):
                    continue
                total = p["total"] if p["total"] is not None else g["total_line"]
                rows.append(
                    {
                        "game_id": g["game_id"],
                        "season": g["season"],
                        "week": g["week"],
                        "model_id": model_id,
                        "model_version": version,
                        "lock_ts": lock_ts,
                        "data_snapshot_ts": g["raw_snapshot_ts"],
                        "p_home": p["p_home"],
                        "spread_home": p["spread_home"],
                        "total": total,
                        "sd_margin": p["sd_margin"],
                        "is_backfill": played,
                    }
                )
        if played:
            elo.update(g["home_team"], g["away_team"], g["result"], neutral)

    for r in rows:
        r.setdefault("slot", "backfill" if r["is_backfill"] else None)
        r.setdefault("contributions", None)
    new = pl.DataFrame(rows, schema=PRED_SCHEMA) if rows else pl.DataFrame(schema=PRED_SCHEMA)
    append_rows(paths, new)
    # current Elo ratings for the UI
    pl.DataFrame({"team": list(elo.ratings), "elo": list(elo.ratings.values())}).sort(
        "elo", descending=True
    ).write_parquet(paths.marts / "elo_ratings.parquet")
    return new.height
