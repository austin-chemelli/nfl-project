"""The weekly betting card and its record (ADR 0033, M29.2). Pure functions over frames the site
build already holds; sentences are templates filled from the study's numbers (no LLM).

The card (guide v1) shows every game of the week with both teams. Each side sits in a history cell
(price band x where the Student stands against the market, `rules.cell_of`):
- Avoid: -120 to -185, +185 or longer, or the Student 6+ points above the market (`rules.side_view`).
- Target: the week's rules.MAX_TARGETS best of the rest, ranked by their cell's shrunk return since
  2006 (the study's `rules.cells`), graded A/B/C. There is always a list.
- The windy under: a total, only when the forecast wind is WIND_MPH+ in the open air.
- The price needed: the break-even price of the blended chance (market + w x the model's
  disagreement, w fitted on every earlier season), in American odds and in exchange cents after a
  Kalshi-style taker fee. Singles only; stake STAKE_PCT of the reader's bankroll.
"""

from __future__ import annotations

import math
from datetime import datetime

import polars as pl

from nfl.betting import prices, rules
from nfl.betting.rules import band_of

RULE_VERSION = "guide-v1"
WIND_MPH = 15
STAKE_PCT = 0.01
EXCHANGE_FEE = 0.07
APPROACHES = ("traditionalist", "analyst", "sharp", "student")
OPEN_AIR = ("outdoors", "open")
MAX_TARGETS = rules.MAX_TARGETS


def _price(x: float | None) -> float | None:
    """Consensus prices are medians in decimal odds; round off the float noise (-619.9999...)."""
    return None if x is None else float(round(x))


def blend(p_market: float, p_model: float, w: float) -> float:
    """logit(p) = logit(market) + w·(logit(model) − logit(market))."""
    lm = math.log(p_market / (1 - p_market))
    lx = math.log(p_model / (1 - p_model))
    return 1 / (1 + math.exp(-(lm + w * (lx - lm))))


def exchange_max_cents(p: float, fee: float = EXCHANGE_FEE) -> float:
    """The highest contract price c (in cents) whose cost with the taker fee, c + fee·c·(1−c),
    is still no more than the win chance p: the most to pay on an exchange to break even."""
    a, b = fee, -(1 + fee)
    c = (-b - math.sqrt(b * b - 4 * a * p)) / (2 * a)
    return 100 * c


def _pctf(x: float | None) -> str:
    if x is None:
        return "–"
    s = f"{abs(100 * x):.1f}%"
    return ("+" if x > 0 else "−" if x < 0 else "") + s


def _am(x: float | None) -> str:
    return "–" if x is None else (f"+{x:.0f}" if x > 0 else f"{x:.0f}")


LABELS = {  # 2-4 words, the card's tag for each kind of side
    ("heavy_fav", "lean"): "Big favorite, Student likes", ("heavy_fav", "same"): "Big favorite, Student agrees",
    ("big_fav", "lean"): "Favorite, Student likes", ("big_fav", "same"): "Favorite, Student agrees",
    ("coin", "lean"): "Coin flip, Student leans", ("coin", "same"): "Coin flip",
    ("dog", "lean"): "Underdog the Student likes", ("dog", "same"): "Underdog, Student agrees",
}  # fmt: skip
AVOID_LABELS = {"mid_fav": "Pricey favorite", "long": "Long shot", "big_gap": "Model too far off"}


def label(band: str, cell: str, why: str) -> str:
    if why in AVOID_LABELS:
        return AVOID_LABELS[why]
    if (band, cell) in LABELS:
        return LABELS[(band, cell)]
    return {"lean": "Student leans this way", "below": "Student likes it less"}.get(
        cell, "Fair price"
    )


def reason(why: str, cell_stats: dict | None, study: dict, model_name: str, p_model: float,
           p_market: float) -> str:  # fmt: skip
    """One short sentence, from the study's numbers."""
    r = study.get("rules", {})
    since = study["seasons"][0]
    pts = round(100 * (p_model - p_market))
    if why == "mid_fav":
        return f"−120 to −185 favorites lost {_pctf(r.get('mid_fav', {}).get('roi'))[1:]} a bet since {since}."
    if why == "long":
        return f"Long shots lost {_pctf(r.get('long', {}).get('roi'))[1:]} a bet since {since}."
    if why == "big_gap":
        return f"{model_name} is {pts} points above the market; the market usually knows why."
    if not cell_stats:
        return "Little history for bets like this."
    roi = cell_stats["roi"]
    word = "won" if roi > 0 else "lost"
    return f"Bets like this {word} {abs(100 * roi):.1f}% a bet since {since} ({cell_stats['n']:,} bets)."


def _cells(study: dict) -> dict[tuple[str, str], dict]:
    return {(c["band"], c["cell"]): c for c in study.get("rules", {}).get("cells", [])}


def market_now(lines: pl.DataFrame, now: datetime) -> pl.DataFrame:
    """The latest pre-kickoff consensus per game at or before `now`."""
    from nfl import odds

    if lines.is_empty():
        return pl.DataFrame()
    pre = lines.filter(
        (pl.col("snapshot_ts") <= now) & (pl.col("snapshot_ts") < pl.col("kickoff_utc"))
    )
    if pre.is_empty():
        return pl.DataFrame()
    return odds.consensus(pre).sort("snapshot_ts").group_by("game_id").last()


def card(
    games: pl.DataFrame,
    allrows: pl.DataFrame,
    lines: pl.DataFrame,
    wind: dict[str, float],
    study: dict,
    week: int,
    now: datetime,
    headline: str = "student",
    model_name: str = "Student",
) -> dict:
    """The week's card. `games`: the season with a tz-naive kickoff; `allrows`: the site's display
    rows (game_id, model_id, p_home, status); `wind`: game_id -> latest forecast mph."""
    wk = games.filter(pl.col("week") == week).sort("kickoff_utc", "game_id")
    cons = market_now(lines, now)
    w = float(study["blend"]["path"][-1]["w"]) if study.get("blend") else 0.0
    cells = _cells(study)
    out = []
    for g in wk.iter_rows(named=True):
        gid = g["game_id"]
        rows = allrows.filter(pl.col("game_id") == gid) if not allrows.is_empty() else allrows
        p = {r["model_id"]: r for r in rows.iter_rows(named=True)} if not rows.is_empty() else {}
        m = cons.filter(pl.col("game_id") == gid) if not cons.is_empty() else cons
        mk = m.row(0, named=True) if not m.is_empty() else None
        item: dict = {
            "game_id": gid, "kickoff_utc": g["kickoff_utc"].isoformat() + "Z", "away": g["away_team"],
            "home": g["home_team"], "started": g["kickoff_utc"] <= now, "roof": g.get("roof"),
            "market": None, "sides": [], "total": None, "model_status": p.get(headline, {}).get("status"),
        }  # fmt: skip
        hp = p.get(headline, {}).get("p_home")
        if mk is not None and mk.get("p_home_vigfree") is not None:
            item["market"] = {
                "as_of": mk["snapshot_ts"].isoformat() + "Z", "p_home": round(mk["p_home_vigfree"], 4),
                "home_ml": _price(mk["home_ml"]), "away_ml": _price(mk["away_ml"]),
                "spread_home": mk.get("spread_home"), "total": mk.get("total"),
            }  # fmt: skip
        if hp is not None and item["market"] is not None:
            for side in ("away", "home"):
                pm = mk["p_home_vigfree"] if side == "home" else 1 - mk["p_home_vigfree"]
                px = hp if side == "home" else 1 - hp
                pb = blend(pm, px, w)
                team = g[f"{side}_team"]
                price = item["market"][f"{side}_ml"]
                view, why = rules.side_view(px, pm)
                band, cell = band_of(pm), rules.cell_of(px - pm)
                cs = cells.get((band, cell))
                agree = sum(
                    1 for a in APPROACHES
                    if a in p and p[a]["p_home"] is not None and ((p[a]["p_home"] >= 0.5) == (side == "home"))
                )  # fmt: skip
                item["sides"].append({
                    "side": side, "team": team, "price": price, "p_model": round(px, 4),
                    "p_market": round(pm, 4), "p_blend": round(pb, 4), "gap": round(px - pm, 4),
                    "band": band, "cell": cell, "score": None if cs is None else cs["score"],
                    "grade": rules.grade(None if cs is None else cs["score"]),
                    "label": label(band, cell, why),
                    "reason": reason(why, cs, study, model_name, px, pm),
                    "view": view, "why": why, "agree": agree,
                    "model_pick": px > 0.5,
                    "needed": {"american": round(prices.breakeven_price(pb)), "cents": round(exchange_max_cents(pb), 1)},
                    "clears": None if price is None else prices.ev(pb, price) >= 0,
                })  # fmt: skip
        mph = wind.get(gid)
        if (
            mph is not None
            and (g.get("roof") in OPEN_AIR or g.get("roof") is None)
            and mph >= WIND_MPH
        ):
            tb = next((t for t in study.get("targeted", []) if t["key"] == "under_wind_15"), {})
            item["total"] = {
                "side": "under", "wind_mph": round(mph), "line": (item["market"] or {}).get("total"),
                "needed": {"american": -110},
                "label": "Windy under",
                "reason": (f"{round(mph)} mph wind forecast. Unders in 15+ mph wind won {_pctf(tb.get('roi'))[1:]} "
                           f"a bet since {study['seasons'][0]} ({tb.get('n', 0)} games)."),
            }  # fmt: skip
        out.append(item)
    # the week's MAX_TARGETS best non-avoid sides by their cell's history, counted over every game
    # including those already played, so the list doesn't change once a game kicks off
    flat = []
    for it in out:
        for x in it["sides"]:  # the same dicts, so the ranking writes through to the card
            x["_k"] = it["kickoff_utc"]
            flat.append(x)
    rules.pick_targets(flat, _rank_key)
    for x in flat:
        del x["_k"]
    return {"week": week, "games": out, "blend_w": w}


def _rank_key(x: dict) -> tuple:
    return (-(x["score"] if x.get("score") is not None else -9.0), -x["gap"], x.get("_k", ""))


# ---------------------------------------------------------------- record of the card at the locks


def live_record(paths, season: int, study: dict, headline: str = "student") -> dict:
    """The card's views at each live lock of `season`, graded: what following it would have
    returned at the consensus price at the lock (1 unit a bet). Derived from append-only inputs
    (lock rows, odds snapshots), so a rerun reproduces it."""
    from nfl import odds
    from nfl.features.store import games_frame
    from nfl.predict import existing

    g = (
        games_frame(paths)
        .filter(pl.col("season") == season)
        .with_columns(pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us")))
    )
    p = (
        existing(paths).filter((pl.col("model_id") == headline) & ~pl.col("is_backfill") & (pl.col("season") == season))
        .join(g.select("game_id", "kickoff_utc", "result"), on="game_id")
        .filter(pl.col("lock_ts") < pl.col("kickoff_utc"))
        .sort("lock_ts").group_by("game_id").last()
    )  # fmt: skip
    lines = odds.read_lines(paths, (season, season))
    empty = {"rule_version": RULE_VERSION, "rows": [], "summary": []}
    if p.is_empty() or lines.is_empty():
        return empty
    cons = odds.consensus(lines)
    rows = grade_at_locks(p, cons, _cells(study))
    df = pl.DataFrame(rows)
    if df.is_empty():
        return empty
    summ = (
        df.group_by("view")
        .agg(pl.len().alias("bets"), (pl.col("won") == 1).sum().alias("wins"), (pl.col("won") == 0).sum().alias("losses"),
             pl.col("units").sum().round(2).alias("units"), pl.col("units").mean().round(4).alias("roi"))
        .sort("view")
    )  # fmt: skip
    return {"rule_version": RULE_VERSION, "rows": rows, "summary": summ.to_dicts()}


def grade_at_locks(p: pl.DataFrame, cons: pl.DataFrame, cells: dict | None = None) -> list[dict]:
    """Pure. p: one lock row per game (game_id, week, lock_ts, p_home, result); cons: consensus
    snapshots (game_id, snapshot_ts, p_home_vigfree, home_ml, away_ml). Each side's view at each
    lock uses only the latest snapshot at or before the lock, priced there; 'none' sides are
    left out. Targets are the week's best by `cells` (the study's history table), as on the card."""
    cells = cells or {}
    cons = cons.filter(pl.col("p_home_vigfree").is_not_null()).sort("snapshot_ts")
    at = p.sort("lock_ts").join_asof(
        cons, left_on="lock_ts", right_on="snapshot_ts", by="game_id", strategy="backward", check_sortedness=False
    ).filter(pl.col("p_home_vigfree").is_not_null() & pl.col("result").is_not_null())  # fmt: skip
    rows = []
    for r in at.iter_rows(named=True):
        for side in ("home", "away"):
            pm = r["p_home_vigfree"] if side == "home" else 1 - r["p_home_vigfree"]
            px = r["p_home"] if side == "home" else 1 - r["p_home"]
            price = r["home_ml"] if side == "home" else r["away_ml"]
            if price is None:
                continue
            view, why = rules.side_view(px, pm)
            cs = cells.get((band_of(pm), rules.cell_of(px - pm)))
            margin = r["result"] if side == "home" else -r["result"]
            won = 1.0 if margin > 0 else 0.0 if margin < 0 else 0.5
            units = (prices.decimal(price) - 1) if won == 1 else (-1.0 if won == 0 else 0.0)
            rows.append({"game_id": r["game_id"], "week": r["week"], "view": view, "why": why, "side": side,
                         "price": round(price), "won": won, "units": round(units, 3),
                         "score": None if cs is None else cs["score"], "gap": px - pm,
                         "cell": rules.cell_of(px - pm),
                         "_k": str(r.get("kickoff_utc") or r["lock_ts"])})  # fmt: skip
    for wk in {r["week"] for r in rows}:  # the week's targets, as on the card
        rules.pick_targets([r for r in rows if r["week"] == wk], _rank_key)
    keep = ("game_id", "week", "view", "why", "side", "price", "won", "units")
    return [{k: r[k] for k in keep} for r in rows if r["view"] != "none"]


def closing_map(games: pl.DataFrame, lines: pl.DataFrame) -> list[dict]:
    """Every game of the season with its final score and our last pre-kickoff consensus: what the
    bet log grades against (result, and closing-line value)."""
    from nfl import odds

    close = pl.DataFrame()
    if not lines.is_empty():
        pre = lines.filter(pl.col("snapshot_ts") < pl.col("kickoff_utc"))
        if not pre.is_empty():
            close = odds.consensus(pre).sort("snapshot_ts").group_by("game_id").last()
    out = []
    for g in games.sort("kickoff_utc", "game_id").iter_rows(named=True):
        c = close.filter(pl.col("game_id") == g["game_id"]) if not close.is_empty() else close
        cr = c.row(0, named=True) if not c.is_empty() else None
        out.append({
            "game_id": g["game_id"], "week": g["week"], "kickoff_utc": g["kickoff_utc"].isoformat() + "Z",
            "away": g["away_team"], "home": g["home_team"],
            "home_score": g.get("home_score"), "away_score": g.get("away_score"),
            "close": None if cr is None else {
                "as_of": cr["snapshot_ts"].isoformat() + "Z",
                "p_home": None if cr["p_home_vigfree"] is None else round(cr["p_home_vigfree"], 4),
                "home_ml": _price(cr["home_ml"]), "away_ml": _price(cr["away_ml"]),
                "spread_home": cr.get("spread_home"), "total": cr.get("total"),
            },
        })  # fmt: skip
    return out
