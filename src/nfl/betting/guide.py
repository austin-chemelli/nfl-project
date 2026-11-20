"""The weekly betting card and its record (ADR 0033, M29.2). Pure functions over frames the site
build already holds; sentences are templates filled from the study's numbers (no LLM).

Rules (guide v1), each from the study (`.notes/hub/plans/betting-study.md`):
- Moneyline singles on the headline model's pick to win. Never parlays.
- "look": the pick is priced about -185 or shorter (market's fair chance 65%+) and the model rates
  it at least as likely as the market does. At most MAX_LOOKS a week, cheapest prices first.
- "fun": coin flips (45-55%), the model's upset picks, and favorites the model rates below the
  market: they cost about the cut.
- "skip": -120 to -185 favorites and anything priced +185 or longer: the costliest bands.
- A targeted total (the under) only when the forecast wind is WIND_MPH+ at an open-air stadium.
  Spreads: nothing clears the bar.
- The price needed: the break-even price of the blended chance (market + w × the model's
  disagreement, w fitted on every earlier season), in American odds and in exchange cents after a
  Kalshi-style taker fee.
- Stake: STAKE_PCT of the reader's bankroll a bet (the page does the arithmetic).
"""

from __future__ import annotations

import math
from datetime import datetime

import polars as pl

from nfl.betting import prices
from nfl.betting.study import BANDS, US_BOOKS

RULE_VERSION = "guide-v1"
LOOK_MIN_P = 0.65
MAX_LOOKS = 4
WIND_MPH = 15
STAKE_PCT = 0.01
EXCHANGE_FEE = 0.07
APPROACHES = ("traditionalist", "analyst", "sharp", "student")
OPEN_AIR = ("outdoors", "open")


def band_of(p: float) -> str:
    for lo, hi, key, *_ in BANDS:
        if lo <= p < hi:
            return key
    return BANDS[0][2]


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


def verdict(p_model: float, p_market: float) -> str:
    """'look' | 'fun' | 'skip' for the model's pick (p_model > 0.5), by the pick's price band."""
    band = band_of(p_market)
    if band in ("heavy_fav", "big_fav"):
        return "look" if p_model >= p_market else "fun"
    if band in ("coin", "dog"):
        return "fun"
    return "skip"


def _band_stats(study: dict) -> dict[str, dict]:
    return {b["band"]: b for b in study["price"]["bands"]}


def _pctf(x: float | None) -> str:
    if x is None:
        return "–"
    s = f"{abs(100 * x):.1f}%"
    return ("+" if x > 0 else "−" if x < 0 else "") + s


def reason(v: str, band: str, study: dict, model_name: str, p_model: float, p_market: float) -> str:
    """One sentence, from the study's numbers."""
    b = _band_stats(study).get(band, {})
    roi, n = _pctf(b.get("roi")), b.get("n")
    since = study["seasons"][0]
    if v == "look":
        return (f"{b.get('label', 'Favorite')} ({b.get('prices', '')}): the least costly prices there are, "
                f"{roi} since {since} ({n:,} bets).")  # fmt: skip
    if band in ("heavy_fav", "big_fav"):
        return (f"A {b.get('label', '').lower()} the {model_name} rates below the market "
                f"({100 * p_model:.0f}% against {100 * p_market:.0f}%): no reason to lay a big price.")  # fmt: skip
    if band == "coin":
        return f"A coin flip: you pay the cut and nothing else ({roi} since {since})."
    if band == "dog":
        picks = {r["band"]: r for r in study.get("pick_winners", [])}.get("dog", {})
        return (f"The {model_name}'s upset pick; its upset picks at these prices returned "
                f"{_pctf(picks.get('roi'))} since {since} ({picks.get('n', 0):,}), about the cut.")  # fmt: skip
    if band == "fav":
        return (f"Favorites at {b.get('prices')} are the costliest prices short of long shots: "
                f"{roi} since {since}, in both halves of the history.")  # fmt: skip
    return f"{b.get('label', 'Long shot')} ({b.get('prices', '')}): {roi} since {since}."


def market_now(lines: pl.DataFrame, now: datetime) -> tuple[pl.DataFrame, pl.DataFrame]:
    """The latest pre-kickoff consensus per game at or before `now`, and, at that snapshot, the
    best moneyline per side among the licensed US books (never an offshore book)."""
    from nfl import odds

    if lines.is_empty():
        return pl.DataFrame(), pl.DataFrame()
    pre = lines.filter(
        (pl.col("snapshot_ts") <= now) & (pl.col("snapshot_ts") < pl.col("kickoff_utc"))
    )
    if pre.is_empty():
        return pl.DataFrame(), pl.DataFrame()
    cons = odds.consensus(pre).sort("snapshot_ts").group_by("game_id").last()
    best = (
        pre.filter((pl.col("market") == "h2h") & pl.col("book").is_in(list(US_BOOKS)))
        .join(cons.select("game_id", "snapshot_ts"), on=["game_id", "snapshot_ts"])
        .with_columns(pl.col("price_american").map_elements(prices.decimal, return_dtype=pl.Float64).alias("dec"))
        .sort("dec", descending=True)
        .group_by("game_id", "side")
        .first()
        .select("game_id", "side", "book", "price_american")
    )  # fmt: skip
    return cons, best


def _total_under(lines: pl.DataFrame, game_id: str, snapshot_ts) -> dict | None:
    t = lines.filter(
        (pl.col("game_id") == game_id) & (pl.col("snapshot_ts") == snapshot_ts)
        & (pl.col("market") == "totals") & (pl.col("side") == "under")
    )  # fmt: skip
    if t.is_empty():
        return None
    us = t.filter(pl.col("book").is_in(list(US_BOOKS)))
    pick = (us if not us.is_empty() else t).with_columns(
        pl.col("price_american").map_elements(prices.decimal, return_dtype=pl.Float64).alias("dec")
    )
    line = float(pick["point"].median())
    at = (
        pick.filter(pl.col("point") == pick["point"].max())
        .sort("dec", descending=True)
        .row(0, named=True)
    )
    return {"line": line, "best_point": at["point"], "best_price": at["price_american"],
            "best_book": at["book"] if at["book"] in US_BOOKS else None}  # fmt: skip


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
    cons, best = market_now(lines, now)
    w = float(study["blend"]["path"][-1]["w"]) if study.get("blend") else 0.0
    order = [b[2] for b in BANDS]
    out = []
    for g in wk.iter_rows(named=True):
        gid = g["game_id"]
        rows = allrows.filter(pl.col("game_id") == gid) if not allrows.is_empty() else allrows
        p = {r["model_id"]: r for r in rows.iter_rows(named=True)} if not rows.is_empty() else {}
        m = cons.filter(pl.col("game_id") == gid) if not cons.is_empty() else cons
        mk = m.row(0, named=True) if not m.is_empty() else None
        started = g["kickoff_utc"] <= now
        item: dict = {
            "game_id": gid, "kickoff_utc": g["kickoff_utc"].isoformat() + "Z", "away": g["away_team"],
            "home": g["home_team"], "started": started, "roof": g.get("roof"),
            "verdict": None, "reason": None, "pick": None, "market": None, "best": None,
            "needed": None, "clears": None, "agree": None, "total": None,
            "model_status": p.get(headline, {}).get("status"),
        }  # fmt: skip
        hp = p.get(headline, {}).get("p_home")
        if mk is not None and mk.get("p_home_vigfree") is not None:
            item["market"] = {
                "as_of": mk["snapshot_ts"].isoformat() + "Z", "p_home": round(mk["p_home_vigfree"], 4),
                "home_ml": mk["home_ml"], "away_ml": mk["away_ml"],
                "spread_home": mk.get("spread_home"), "total": mk.get("total"),
            }  # fmt: skip
        if hp is not None and item["market"] is not None:
            side = "home" if hp >= 0.5 else "away"
            pm = mk["p_home_vigfree"] if side == "home" else 1 - mk["p_home_vigfree"]
            px = hp if side == "home" else 1 - hp
            pb = blend(pm, px, w)
            band = band_of(pm)
            v = verdict(px, pm)
            team = g["home_team"] if side == "home" else g["away_team"]
            agree = sum(
                1 for a in APPROACHES
                if a in p and p[a]["p_home"] is not None and ((p[a]["p_home"] >= 0.5) == (side == "home"))
            )  # fmt: skip
            item |= {
                "pick": {"side": side, "team": team, "p_model": round(px, 4), "p_market": round(pm, 4),
                         "p_blend": round(pb, 4), "band": band},
                "verdict": v,
                "reason": reason(v, band, study, model_name, px, pm),
                "needed": {"american": round(prices.breakeven_price(pb)), "cents": round(exchange_max_cents(pb), 1)},
                "agree": agree,
            }  # fmt: skip
            b = (
                best.filter((pl.col("game_id") == gid) & (pl.col("side") == side))
                if not best.is_empty()
                else best
            )
            if not b.is_empty():
                br = b.row(0, named=True)
                item["best"] = {"price": br["price_american"], "book": br["book"]}
                item["clears"] = prices.ev(pb, br["price_american"]) >= 0
        mph = wind.get(gid)
        if (
            mph is not None
            and (g.get("roof") in OPEN_AIR or g.get("roof") is None)
            and mph >= WIND_MPH
        ):
            under = _total_under(lines, gid, mk["snapshot_ts"]) if mk is not None else None
            tb = next((t for t in study.get("targeted", []) if t["key"] == "under_wind_15"), {})
            item["total"] = {
                "side": "under", "wind_mph": round(mph), "line": under["line"] if under else (mk or {}).get("total"),
                "best": {"point": under["best_point"], "price": under["best_price"], "book": under["best_book"]} if under else None,
                "needed": {"american": -110},
                "reason": (f"Forecast wind {round(mph)} mph in the open air: unders in 15+ mph wind returned "
                           f"{_pctf(tb.get('roi'))} since {study['seasons'][0]} ({tb.get('n', 0)} games), "
                           "measured on the wind at kickoff, so the real edge is smaller."),
            }  # fmt: skip
        if started:
            item["verdict"] = "started" if item["verdict"] is not None else None
        out.append(item)
    # at most MAX_LOOKS: cheapest band first, then the best price against the needed price
    looks = [x for x in out if x["verdict"] == "look"]
    looks.sort(key=lambda x: (order.index(x["pick"]["band"]), x["kickoff_utc"]))
    for x in looks[MAX_LOOKS:]:
        x["verdict"] = "fun"
        x["reason"] += f" Left off the short list: the card keeps {MAX_LOOKS} a week."
    return {"week": week, "games": out, "blend_w": w}


# ---------------------------------------------------------------- record of the card at the locks


def live_record(paths, season: int, study: dict, headline: str = "student") -> dict:
    """The card's verdicts at each live lock of `season`, graded: what following it would have
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
    rows = grade_at_locks(p, cons)
    df = pl.DataFrame(rows)
    if df.is_empty():
        return empty
    summ = (
        df.group_by("verdict")
        .agg(pl.len().alias("bets"), (pl.col("won") == 1).sum().alias("wins"), (pl.col("won") == 0).sum().alias("losses"),
             pl.col("units").sum().round(2).alias("units"), pl.col("units").mean().round(4).alias("roi"))
        .sort("verdict")
    )  # fmt: skip
    return {"rule_version": RULE_VERSION, "rows": rows, "summary": summ.to_dicts()}


def grade_at_locks(p: pl.DataFrame, cons: pl.DataFrame) -> list[dict]:
    """Pure. p: one lock row per game (game_id, week, lock_ts, p_home, result); cons: consensus
    snapshots (game_id, snapshot_ts, p_home_vigfree, home_ml, away_ml). The card at each lock uses
    only the latest snapshot at or before the lock, priced there."""
    cons = cons.filter(pl.col("p_home_vigfree").is_not_null()).sort("snapshot_ts")
    at = p.sort("lock_ts").join_asof(
        cons, left_on="lock_ts", right_on="snapshot_ts", by="game_id", strategy="backward", check_sortedness=False
    ).filter(pl.col("p_home_vigfree").is_not_null() & pl.col("result").is_not_null())  # fmt: skip
    rows = []
    for r in at.iter_rows(named=True):
        side = "home" if r["p_home"] >= 0.5 else "away"
        pm = r["p_home_vigfree"] if side == "home" else 1 - r["p_home_vigfree"]
        px = r["p_home"] if side == "home" else 1 - r["p_home"]
        price = r["home_ml"] if side == "home" else r["away_ml"]
        if price is None:
            continue
        margin = r["result"] if side == "home" else -r["result"]
        won = 1.0 if margin > 0 else 0.0 if margin < 0 else 0.5
        units = (prices.decimal(price) - 1) if won == 1 else (-1.0 if won == 0 else 0.0)
        rows.append({"game_id": r["game_id"], "week": r["week"], "verdict": verdict(px, pm), "side": side,
                     "price": price, "won": won, "units": round(units, 3)})  # fmt: skip
    return rows


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
                "home_ml": cr["home_ml"], "away_ml": cr["away_ml"],
                "spread_home": cr.get("spread_home"), "total": cr.get("total"),
            },
        })  # fmt: skip
    return out
