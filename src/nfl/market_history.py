"""The market line's path before kickoff (ADR 0023, M20.2).

Per game, the consensus across books at every odds snapshot strictly before kickoff: the home spread
(nflverse sign, + = home favored), the total and the vig-free home win chance. Snapshots after kickoff
are in-play lines (the Sunday and Monday jobs run while games are under way) and never count.

A point needs `MIN_BOOKS` books quoting that market, else it's null: early in the week a game can sit
on one or two books, and a median of one is a book, not a market.

Moves are last minus first over a window, in the same sign: a spread move > 0 is toward the home
team, a total move > 0 is up. "First seen" is our first snapshot of the game, never "the opener":
our snapshots start when we start, not when books open (and only from 2026-10-26).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl

MIN_BOOKS = 3
DAY = timedelta(hours=24)
_KEYS = ["game_id", "snapshot_ts"]


def _books(lines: pl.DataFrame, market: str) -> pl.DataFrame:
    return (
        lines.filter(pl.col("market") == market)
        .group_by(_KEYS)
        .agg(pl.col("book").n_unique().alias(f"n_{market}"))
    )


def paths(lines: pl.DataFrame) -> pl.DataFrame:
    """One row per (game, pre-kickoff snapshot): snapshot_ts, spread_home, total, p_home, n_books.

    `lines` is `odds.read_lines` (it carries `kickoff_utc`)."""
    from nfl.odds import consensus

    schema = {"game_id": pl.Utf8, "snapshot_ts": pl.Datetime("us"), "spread_home": pl.Float64,
              "total": pl.Float64, "p_home": pl.Float64, "n_books": pl.UInt32}  # fmt: skip
    if lines.is_empty():
        return pl.DataFrame(schema=schema)
    pre = lines.filter(pl.col("snapshot_ts") < pl.col("kickoff_utc"))
    if pre.is_empty():
        return pl.DataFrame(schema=schema)
    c = consensus(pre)
    for m in ("h2h", "spreads", "totals"):
        c = c.join(_books(pre, m), on=_KEYS, how="left")
    ok = lambda m: pl.col(f"n_{m}").fill_null(0) >= MIN_BOOKS
    return (
        c.select(
            *_KEYS,
            pl.when(ok("spreads")).then(pl.col("spread_home")).alias("spread_home"),
            pl.when(ok("totals")).then(pl.col("total")).alias("total"),
            pl.when(ok("h2h")).then(pl.col("p_home_vigfree")).alias("p_home"),
            pl.max_horizontal("n_h2h", "n_spreads", "n_totals").cast(pl.UInt32).alias("n_books"),
        )
        .filter(pl.any_horizontal(pl.col("spread_home", "total", "p_home").is_not_null()))
        .sort(_KEYS)
    )


def _value_at(points: list[dict], key: str, at: datetime | None, last: bool) -> dict | None:
    """The first (or last) point with a value for `key`, at or after `at` when given."""
    seq = [p for p in points if p[key] is not None and (at is None or p["snapshot_ts"] >= at)]
    if not seq:
        return None
    return seq[-1] if last else seq[0]


def _move(points: list[dict], since: datetime | None) -> dict | None:
    """Last minus first over the points at or after `since` (all points when None), per measure."""
    out, hours = {}, None
    for key in ("spread_home", "total", "p_home"):
        a = _value_at(points, key, since, last=False)
        b = _value_at(points, key, since, last=True)
        if a is None or b is None or a is b:
            out[key] = None
            continue
        out[key] = round(b[key] - a[key], 4 if key == "p_home" else 2)
        hours = round((b["snapshot_ts"] - a["snapshot_ts"]).total_seconds() / 3600, 1)
    if all(v is None for v in out.values()):
        return None
    return {**out, "hours": hours}


def summary(points: list[dict], lock_ts: datetime | None) -> dict | None:
    """first_seen, the latest point, and moves since first seen, since the lock and over the last day.

    `points` are one game's rows of `paths`, oldest first. `since_lock` starts at the last snapshot at or
    before the lock (the line the lock saw), so it's the move the lock didn't know about."""
    if not points:
        return None
    latest = points[-1]["snapshot_ts"]
    lock_from = None
    if lock_ts is not None:
        before = [p["snapshot_ts"] for p in points if p["snapshot_ts"] <= lock_ts]
        lock_from = before[-1] if before else None
    return {
        "first_seen": points[0]["snapshot_ts"],
        "latest": latest,
        "n_points": len(points),
        "since_first": _move(points, None),
        "since_lock": _move(points, lock_from) if lock_from is not None else None,
        "last_day": _move(points, latest - DAY)
        if latest - DAY > points[0]["snapshot_ts"]
        else None,
    }
