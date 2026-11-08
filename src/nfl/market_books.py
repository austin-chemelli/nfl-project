"""Where the sportsbooks disagree (ADR 0024, M20.13).

The consensus (`odds.consensus`) is a median across books; this keeps each book's own line at a game's
latest snapshot before kickoff, so the site can show the spread of books and flag a game where they
disagree. Most weeks they sit within half a point (Weeks 8 and 9 of 2026: 23 of 30 games), so a flag
is rare by design (3 of those 30):

- the spread: books `SPREAD_GAP` points apart or more, or on both sides of a key number (3, 7 or
  pick'em, i.e. not agreeing on the favorite). A one-point gap on the same side (1 vs 2) is left
  alone: few games land between those numbers, so it's mostly a price difference;
- the total: books `TOTAL_GAP` points apart or more.

A book whose quote is older than `STALE` at the snapshot is left out: a line nobody refreshed isn't a
disagreement. Each market needs `MIN_BOOKS` fresh books, like the consensus path.

Spreads use the nflverse sign (+ = home favored), as everywhere on the site. The win chance per book is
its moneyline with the vig taken out (home over home + away implied).
"""

from __future__ import annotations

from datetime import timedelta

import polars as pl

from nfl.market_history import MIN_BOOKS

STALE = timedelta(hours=6)
SPREAD_GAP = 1.5
TOTAL_GAP = 1.5
KEY_SPREADS = (-7.0, -3.0, 0.0, 3.0, 7.0)


def _implied(price: pl.Expr) -> pl.Expr:
    return pl.when(price < 0).then(-price / (-price + 100)).otherwise(100 / (price + 100))


def _range(vals: list[float]) -> dict | None:
    if len(vals) < MIN_BOOKS:
        return None
    s = sorted(vals)
    n = len(s)
    med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return {"lo": s[0], "hi": s[-1], "median": med, "gap": round(s[-1] - s[0], 2)}


def crossed_key(lo: float, hi: float) -> float | None:
    """The key spread the books straddle (some on each side of it), nearest pick'em first."""
    for k in sorted(KEY_SPREADS, key=abs):
        if lo < k < hi:
            return k
    return None


def flags(spread: dict | None, total: dict | None) -> list[str]:
    out = []
    if spread is not None:
        if spread["gap"] >= SPREAD_GAP:
            out.append("spread_gap")
        if crossed_key(spread["lo"], spread["hi"]) is not None:
            out.append("spread_key")
    if total is not None and total["gap"] >= TOTAL_GAP:
        out.append("total_gap")
    return out


def by_game(lines: pl.DataFrame) -> dict[str, dict]:
    """Per game: each fresh book's line at the latest pre-kickoff snapshot, the range per market and
    the flags. `lines` is `odds.read_lines` (one row per book, market and side)."""
    if lines.is_empty():
        return {}
    pre = lines.filter(pl.col("snapshot_ts") < pl.col("kickoff_utc"))
    if pre.is_empty():
        return {}
    pre = pre.filter(pl.col("snapshot_ts") == pl.col("snapshot_ts").max().over("game_id"))
    updated = pl.col("book_last_update").str.to_datetime(time_zone="UTC", strict=False)
    pre = pre.with_columns(
        (pl.col("snapshot_ts") - updated.dt.replace_time_zone(None)).alias("_lag")
    )
    fresh = pre.filter(pl.col("_lag").is_null() | (pl.col("_lag") <= STALE))
    side = lambda m, s: (pl.col("market") == m) & (pl.col("side") == s)
    keys = ["game_id", "snapshot_ts", "book"]
    per_book = (
        fresh.group_by(keys)
        .agg(
            (-pl.col("point").filter(side("spreads", "home"))).first().alias("spread_home"),
            pl.col("price_american").filter(side("spreads", "home")).first().alias("home_price"),
            pl.col("price_american").filter(side("spreads", "away")).first().alias("away_price"),
            pl.col("point").filter(side("totals", "over")).first().alias("total"),
            pl.col("price_american").filter(side("totals", "over")).first().alias("over_price"),
            pl.col("price_american").filter(side("totals", "under")).first().alias("under_price"),
            _implied(pl.col("price_american")).filter(side("h2h", "home")).first().alias("_ih"),
            _implied(pl.col("price_american")).filter(side("h2h", "away")).first().alias("_ia"),
        )
        .with_columns((pl.col("_ih") / (pl.col("_ih") + pl.col("_ia"))).round(4).alias("p_home"))
        .drop("_ih", "_ia")
        .sort("game_id", "book")
    )
    stale = (
        pre.select("game_id", "book")
        .unique()
        .join(fresh.select("game_id", "book").unique(), on=["game_id", "book"], how="anti")
    )
    n_stale = {
        r["game_id"]: r["len"] for r in stale.group_by("game_id").len().iter_rows(named=True)
    }
    out: dict[str, dict] = {}
    for (gid,), g in per_book.group_by(["game_id"], maintain_order=True):
        # + 0.0 turns -0.0 (a pick'em negated) into 0.0
        rows = [{k: v + 0.0 if isinstance(v, float) else v for k, v in r.items()} for r in g.drop("game_id", "snapshot_ts").to_dicts()]  # fmt: skip
        spread = _range([r["spread_home"] for r in rows if r["spread_home"] is not None])
        total = _range([r["total"] for r in rows if r["total"] is not None])
        if spread is None and total is None:
            continue
        out[gid] = {
            "snapshot_ts": g["snapshot_ts"][0],
            "books": rows,
            "spread": spread,
            "total": total,
            "key": crossed_key(spread["lo"], spread["hi"]) if spread else None,
            "flags": flags(spread, total),
            "n_stale": n_stale.get(gid, 0),
        }
    return out
