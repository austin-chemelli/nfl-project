"""The betting study (ADR 0033, M29.1): what our own history says about betting NFL games.

Every table is computed here from `history.sides()` (moneylines from 2006, schedule lines that are
roughly closing) and the walk-forward backfill rows of the approaches. `run()` returns one dict of
tables; `nfl betting study` writes it as JSON (and the public "Betting math" page reads a subset
through `site.py`). The model whose chances drive the model-dependent tables is a parameter, so a
new Student reruns the study with one command; every output names the model version it used.

Numbers are ROI per 1 unit staked (profit / stake). Ranges are 90% normal intervals on the mean.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from itertools import combinations

import numpy as np
import polars as pl

from nfl.betting import history, prices, rules
from nfl.betting.rules import BANDS

TRAIN_END = 2015  # first half 2006-2015, second half 2016-2025: a pattern must hold in both
Z90 = 1.645
SEED = 20261120

GAP_BUCKETS = [
    (0.0, 0.025, "0-2.5"),
    (0.025, 0.05, "2.5-5"),
    (0.05, 0.10, "5-10"),
    (0.10, 1.0, "10+"),
]


def _band_expr(col: str = "p_mkt") -> pl.Expr:
    e = pl.lit(None, dtype=pl.Utf8)
    for lo, hi, key, *_ in reversed(BANDS):
        e = pl.when((pl.col(col) >= lo) & (pl.col(col) < hi)).then(pl.lit(key)).otherwise(e)
    return e


def _gap_expr(col: str = "gap") -> pl.Expr:
    e = pl.lit(None, dtype=pl.Utf8)
    for lo, hi, key in reversed(GAP_BUCKETS):
        e = pl.when((pl.col(col) >= lo) & (pl.col(col) < hi)).then(pl.lit(key)).otherwise(e)
    return e


def _period() -> pl.Expr:
    return (
        pl.when(pl.col("season") <= TRAIN_END)
        .then(pl.lit("2006-2015"))
        .when(pl.col("season") <= 2025)
        .then(pl.lit("2016-2025"))
        .otherwise(pl.lit("2026"))
    )


def _roi_aggs(profit: str = "profit") -> list[pl.Expr]:
    p = pl.col(profit)
    return [
        pl.len().alias("n"),
        p.mean().alias("roi"),
        (p.mean() - Z90 * p.std() / pl.len().sqrt()).alias("roi_lo"),
        (p.mean() + Z90 * p.std() / pl.len().sqrt()).alias("roi_hi"),
    ]


def _rows(df: pl.DataFrame, nd: int = 4) -> list[dict]:
    out = []
    for r in df.iter_rows(named=True):
        out.append({k: (round(v, nd) if isinstance(v, float) else v) for k, v in r.items()})
    return out


def _hist(s: pl.DataFrame) -> pl.DataFrame:
    """Finished history only (the current season counts as its own period)."""
    return s.filter(pl.col("won").is_not_null())


# 1. price ---------------------------------------------------------------------------------------


def by_price(s: pl.DataFrame) -> dict:
    """Bet every side in a price band at the closing-ish moneyline. Win rate against the vig-free
    chance (the favorite-long shot bias) and the return, all years and per half."""
    d = _hist(s).filter(pl.col("season") <= 2025).with_columns(_band_expr().alias("band"))
    aggs = [
        *_roi_aggs(),
        pl.col("won").mean().alias("win_rate"),
        pl.col("p_mkt").mean().alias("p_mkt"),
        (1 / (1 + pl.col("win_units"))).mean().alias("breakeven"),
        pl.col("price").median().alias("median_price"),
    ]
    allyrs = d.group_by("band").agg(aggs)
    halves = (
        d.with_columns(_period().alias("period"))
        .group_by("band", "period")
        .agg(pl.col("profit").mean().alias("roi"), pl.len().alias("n"))
        .pivot(on="period", index="band", values=["roi", "n"])
    )
    out = allyrs.join(halves, on="band", how="left").with_columns(
        (pl.col("win_rate") - pl.col("p_mkt")).alias("bias")
    )
    order = {b[2]: i for i, b in enumerate(BANDS)}
    meta = {b[2]: {"label": b[3], "prices": b[4]} for b in BANDS}
    rows = sorted(_rows(out), key=lambda r: order[r["band"]])
    for r in rows:
        r |= meta[r["band"]]
    # the vig split: how the book's cut falls on favorites vs underdogs (implied minus vig-free)
    vig = (
        d.with_columns((1 / (1 + pl.col("win_units")) - pl.col("p_mkt")).alias("vig_share"))
        .group_by("band")
        .agg(pl.col("vig_share").mean())
    )
    for r in rows:
        v = vig.filter(pl.col("band") == r["band"])["vig_share"]
        r["vig_points"] = round(float(v[0]), 4) if len(v) else None
    return {"bands": rows, "seasons": [int(d["season"].min()), int(d["season"].max())]}


# 2. the model against the market ---------------------------------------------------------------


def lean_sides(s: pl.DataFrame, model: str) -> pl.DataFrame:
    """Per game, the side `model` rates above the market (one row per game), with gap = model
    chance minus vig-free market chance for that side (> 0)."""
    m = f"p_{model}"
    return (
        s.filter(pl.col(m).is_not_null())
        .with_columns((pl.col(m) - pl.col("p_mkt")).alias("gap"))
        .filter(pl.col("gap") > 0)
    )


def by_gap(s: pl.DataFrame, models: tuple[str, ...]) -> list[dict]:
    """Bet the side the model likes more than the market, by size of the gap and by whether that
    side is the market's favorite or underdog."""
    out = []
    for model in models:
        d = _hist(lean_sides(s, model)).filter(pl.col("season") <= 2025)
        t = (
            d.with_columns(
                _gap_expr().alias("gap_bucket"),
                pl.when(pl.col("fav"))
                .then(pl.lit("favorite"))
                .otherwise(pl.lit("underdog"))
                .alias("direction"),
                _period().alias("period"),
            )
            .group_by("gap_bucket", "direction")
            .agg(
                *_roi_aggs(),
                pl.col("profit").filter(pl.col("period") == "2006-2015").mean().alias("roi_first"),
                pl.col("profit").filter(pl.col("period") == "2016-2025").mean().alias("roi_second"),
                pl.col("won").mean().alias("win_rate"),
                pl.col("p_mkt").mean().alias("p_mkt"),
            )
            .with_columns(pl.lit(model).alias("model"))
            .sort("direction", "gap_bucket")
        )
        out += _rows(t)
    return out


def agreement(s: pl.DataFrame, models: tuple[str, ...], min_gap: float = 0.02) -> list[dict]:
    """How many approaches lean the same side against the market (each by at least min_gap)."""
    d = _hist(s).filter(pl.col("season") <= 2025)
    leans = sum(((pl.col(f"p_{m}") - pl.col("p_mkt")) >= min_gap).cast(pl.Int32) for m in models)
    d = d.with_columns(leans.alias("n_lean"), _period().alias("period"))
    t = (
        d.filter(pl.col("n_lean") >= 1)
        .with_columns(
            pl.when(pl.col("fav"))
            .then(pl.lit("favorite"))
            .otherwise(pl.lit("underdog"))
            .alias("direction")
        )
        .group_by("n_lean", "direction")
        .agg(
            *_roi_aggs(),
            pl.col("profit").filter(pl.col("period") == "2006-2015").mean().alias("roi_first"),
            pl.col("profit").filter(pl.col("period") == "2016-2025").mean().alias("roi_second"),
        )
        .sort("direction", "n_lean")
    )
    return _rows(t)


def pick_winners(s: pl.DataFrame, model: str) -> list[dict]:
    """Bet the model's pick to win (its chance above 50%) in every game, by the market's price."""
    m = f"p_{model}"
    d = (
        _hist(s)
        .filter((pl.col("season") <= 2025) & (pl.col(m) > 0.5))
        .with_columns(_band_expr().alias("band"))
    )
    t = d.group_by("band").agg(*_roi_aggs(), pl.col("won").mean().alias("win_rate"))
    tot = d.select(*_roi_aggs(), pl.col("won").mean().alias("win_rate")).with_columns(
        pl.lit("all").alias("band")
    )
    order = {b[2]: i for i, b in enumerate(BANDS)} | {"all": 99}
    return sorted(_rows(pl.concat([t, tot.select(t.columns)])), key=lambda r: order[r["band"]])


# 3. walk-forward rule search ---------------------------------------------------------------------


def _rule_family(models: tuple[str, ...]) -> list[dict]:
    rules = []
    for model in (*models, "mean"):
        for direction in ("any", "favorite", "underdog"):
            for min_gap in (0.02, 0.05, 0.08, 0.10):
                for band in ("all", "no_long", "near_coin"):
                    rules.append(
                        {"model": model, "direction": direction, "min_gap": min_gap, "band": band}
                    )
    return rules


def _apply_rule(s: pl.DataFrame, r: dict) -> pl.DataFrame:
    d = lean_sides(s, r["model"]).filter(pl.col("gap") >= r["min_gap"])
    if r["direction"] == "favorite":
        d = d.filter(pl.col("fav"))
    elif r["direction"] == "underdog":
        d = d.filter(~pl.col("fav"))
    if r["band"] == "no_long":
        d = d.filter(pl.col("p_mkt") >= 0.30)
    elif r["band"] == "near_coin":
        d = d.filter(pl.col("p_mkt").is_between(0.35, 0.65))
    return d


def walk_forward(s: pl.DataFrame, models: tuple[str, ...], first_test: int = 2011) -> dict:
    """Each season, pick the rule with the best return on every earlier season (at least 150 bets)
    and bet it that season. The honest version of "find what works": the result is what the
    searching would actually have earned."""
    d = _hist(s).with_columns((sum(pl.col(f"p_{m}") for m in models) / len(models)).alias("p_mean"))
    rules = _rule_family(models)
    per_rule = []
    for i, r in enumerate(rules):
        b = _apply_rule(d, r)
        per_rule.append(
            b.group_by("season")
            .agg(pl.col("profit").sum().alias("u"), pl.len().alias("n"))
            .with_columns(pl.lit(i).alias("rule"))
        )
    tab = pl.concat(per_rule)
    last = int(d["season"].max())
    picks, bets = [], []
    for season in range(first_test, last + 1):
        past = (
            tab.filter(pl.col("season") < season)
            .group_by("rule")
            .agg(pl.col("u").sum(), pl.col("n").sum())
            .filter(pl.col("n") >= 150)
            .with_columns((pl.col("u") / pl.col("n")).alias("roi"))
            .sort("roi", "rule", descending=[True, False])
        )
        if past.is_empty():  # not enough history for any rule yet: no bet that season
            continue
        best = int(past["rule"][0])
        now = tab.filter((pl.col("season") == season) & (pl.col("rule") == best))
        u = float(now["u"].sum()) if not now.is_empty() else 0.0
        n = int(now["n"].sum()) if not now.is_empty() else 0
        picks.append(
            {"season": season, "rule": rules[best], "past_roi": round(float(past["roi"][0]), 4),
             "bets": n, "units": round(u, 2), "roi": round(u / n, 4) if n else None}
        )  # fmt: skip
        bets.append((u, n))
    u_tot = sum(u for u, _ in bets)
    n_tot = sum(n for _, n in bets)
    full = (
        tab.filter(pl.col("season") <= 2025).group_by("rule")
        .agg(pl.col("u").sum(), pl.col("n").sum())
        .with_columns((pl.col("u") / pl.col("n")).alias("roi"))
    )  # fmt: skip
    halves = (
        tab.with_columns(pl.when(pl.col("season") <= TRAIN_END).then(1).otherwise(2).alias("h"))
        .filter(pl.col("season") <= 2025)
        .group_by("rule", "h").agg((pl.col("u").sum() / pl.col("n").sum()).alias("roi"), pl.col("n").sum())
        .pivot(on="h", index="rule", values=["roi", "n"])
    )  # fmt: skip
    for c in ("roi_1", "roi_2", "n_1", "n_2"):  # a history inside one half has no other half
        if c not in halves.columns:
            halves = halves.with_columns(pl.lit(None, dtype=pl.Float64).alias(c))
    both_pos = halves.filter((pl.col("roi_1") > 0) & (pl.col("roi_2") > 0) & (pl.col("n_1") >= 150) & (pl.col("n_2") >= 150))  # fmt: skip
    positive = [
        rules[i] | {"roi_first": round(a, 4), "roi_second": round(b, 4)}
        for i, a, b in both_pos.select("rule", "roi_1", "roi_2").iter_rows()
    ]
    return {
        "rules_tried": len(rules),
        "seasons": picks,
        "walk_forward_roi": round(u_tot / n_tot, 4) if n_tot else None,
        "walk_forward_bets": n_tot,
        "best_in_hindsight_roi": round(float(full["roi"].max()), 4),
        "median_rule_roi": round(float(full["roi"].median()), 4),
        "rules_positive_in_both_halves": positive,
    }


# 4. parlays ------------------------------------------------------------------------------------


def parlays(s: pl.DataFrame, model: str, legs: tuple[int, ...] = (1, 2, 3, 4),
            per_week: int = 400) -> dict:  # fmt: skip
    """Singles against parlays built from the same picks: each week, the model's picks to win in
    games priced between -400 and +185 (the "pick winners" bettor), every k-leg combination (or
    a random sample of them). Ties drop out of a parlay (that leg pays 1.0), as books settle them."""
    rng = np.random.default_rng(SEED)
    m = f"p_{model}"
    d = _hist(s).filter(
        (pl.col("season") <= 2025) & (pl.col(m) > 0.5) & pl.col("p_mkt").is_between(0.35, 0.80)
    )
    dec = (1 + d["win_units"]).to_numpy()
    won = d["won"].to_numpy()
    pm = d["p_mkt"].to_numpy()
    wk = (d["season"] * 100 + d["week"]).to_numpy()
    season_of = d["season"].to_numpy()
    out = {}
    for k in legs:
        payoff, fair, seasons = [], [], []
        for w in np.unique(wk):
            idx = np.flatnonzero(wk == w)
            if len(idx) < k:
                continue
            combos = list(combinations(idx, k)) if math.comb(len(idx), k) <= per_week else [
                tuple(rng.choice(idx, k, replace=False)) for _ in range(per_week)]  # fmt: skip
            for c in combos:
                c = np.array(c)
                legs_dec = np.where(won[c] == 0.5, 1.0, dec[c])
                hit = np.all(won[c] > 0)
                payoff.append((np.prod(legs_dec) if hit else 0.0) - 1)
                fair.append(np.prod(pm[c]))
                seasons.append(season_of[c[0]])
        payoff = np.array(payoff)
        out[k] = {
            "legs": k,
            "n": len(payoff),
            "roi": round(float(payoff.mean()), 4),
            "roi_lo": round(float(payoff.mean() - Z90 * payoff.std() / math.sqrt(len(payoff))), 4),
            "roi_hi": round(float(payoff.mean() + Z90 * payoff.std() / math.sqrt(len(payoff))), 4),
            "sd_per_bet": round(float(payoff.std()), 3),
            "hit_rate": round(float((payoff > -1).mean()), 4),
            "market_hit_rate": round(float(np.mean(fair)), 4),
            "_payoff": payoff,
            "_season": np.array(seasons),
        }
    # chance of a losing season: 3 bets a week for 18 weeks, each a k-leg ticket at 1 unit,
    # tickets drawn from that k's pool (bootstrap)
    for k, r in out.items():
        pool = r.pop("_payoff")
        r.pop("_season")
        sims = rng.choice(pool, size=(20000, 54)).sum(axis=1)
        r["p_losing_season"] = round(float((sims < 0).mean()), 3)
        r["p_season_down_10u"] = round(float((sims <= -10).mean()), 3)
        r["median_season_units"] = round(float(np.median(sims)), 2)
    single = out[1]["roi"]
    for k, r in out.items():
        r["compounded_single_roi"] = round((1 + single) ** k - 1, 4)  # what independence predicts
    return {"model": model, "by_legs": list(out.values())}


def vig_compounding(hold_rates: tuple[float, ...] = (0.0455, 0.025)) -> list[dict]:
    """Expected return of a fair-coin parlay at standard prices: the cut multiplies with each leg."""
    rows = []
    for h in hold_rates:
        per_leg = 1 / (1 + h) - 1  # a fair 50/50 leg at a price with hold h
        for k in range(1, 7):
            rows.append({"hold": h, "legs": k, "roi": round((1 + per_leg) ** k - 1, 4)})
    return rows


# 5. stake sizing ---------------------------------------------------------------------------------


def _weekly_bets(
    s: pl.DataFrame, model: str, per_week: int, w_by_season: dict[int, float] | None
) -> list[list[tuple]]:
    """Per (season, week), the `per_week` sides the model likes most against the market,
    as (p_model_for_kelly, decimal_odds, won). With `w_by_season`, the chance is the logit blend
    of guide.blend with that season's walk-forward weight (fitted on earlier seasons only)."""
    d = lean_sides(_hist(s), model).filter(pl.col("season").is_between(2011, 2025))
    if w_by_season is None:
        pk = pl.col(f"p_{model}")
    else:
        lm = (pl.col("p_mkt") / (1 - pl.col("p_mkt"))).log()
        lx = (pl.col(f"p_{model}") / (1 - pl.col(f"p_{model}"))).log()
        w = pl.col("season").replace_strict(w_by_season, default=0.0, return_dtype=pl.Float64)
        pk = 1 / (1 + (-(lm + w * (lx - lm))).exp())
    d = d.with_columns(pk.alias("pk"), (1 + pl.col("win_units")).alias("dec"))
    weeks = []
    for (_season, _week), g in d.sort("season", "week").group_by(
        ["season", "week"], maintain_order=True
    ):
        g = g.sort("gap", descending=True).head(per_week)
        weeks.append(list(g.select("pk", "dec", "won").iter_rows()))
    return weeks


def staking(
    s: pl.DataFrame, model: str, w_by_season: dict[int, float], n_sims: int = 4000
) -> list[dict]:
    """Bankroll paths over an 18-week season for flat stakes and fractions of Kelly, at 3, 6 and
    10 bets a week. Weeks are resampled from 2011-2025 (bootstrap), stakes are set from the
    bankroll at the start of each week. Kelly is computed two ways: on the model's own chance,
    and on the chance shrunk toward the market by each season's walk-forward blend weight."""
    rng = np.random.default_rng(SEED)
    rows = []
    for per_week in (3, 6, 10):
        raw = _weekly_bets(s, model, per_week, None)
        shrunk = _weekly_bets(s, model, per_week, w_by_season)
        strategies = [
            ("flat_1", "Flat 1% of the starting bankroll", raw, ("flat", 0.01)),
            ("flat_2", "Flat 2%", raw, ("flat", 0.02)),
            ("flat_5", "Flat 5%", raw, ("flat", 0.05)),
            ("kelly_full", "Full Kelly on the model's chance", raw, ("kelly", 1.0)),
            ("kelly_half", "Half Kelly on the model's chance", raw, ("kelly", 0.5)),
            ("kelly_quarter", "Quarter Kelly on the model's chance", raw, ("kelly", 0.25)),
            (
                "kelly_shrunk",
                "Kelly on the chance shrunk toward the market",
                shrunk,
                ("kelly", 1.0),
            ),
        ]
        idx = rng.integers(0, len(raw), size=(n_sims, 18))
        for key, label, weeks, (kind, frac) in strategies:
            ends, halved, bets_placed, staked = [], 0, 0, 0.0
            for sim in idx:
                bank, low = 1.0, 1.0
                for wi in sim:
                    stakes = []
                    for pk, dec, won in weeks[wi]:
                        if kind == "flat":
                            st = frac
                        else:
                            st = frac * max(0.0, (pk * dec - 1) / (dec - 1)) * bank
                        stakes.append((min(st, bank / max(1, len(weeks[wi]))), dec, won))
                    for st, dec, won in stakes:
                        if st <= 0:
                            continue
                        bets_placed += 1
                        staked += st
                        bank += st * (dec - 1) if won == 1 else (-st if won == 0 else 0.0)
                    low = min(low, bank)
                ends.append(bank)
                halved += low <= 0.5
            ends = np.array(ends)
            rows.append({
                "bets_per_week": per_week, "strategy": key, "label": label,
                "median_end": round(float(np.median(ends)), 3),
                "p5_end": round(float(np.percentile(ends, 5)), 3),
                "p95_end": round(float(np.percentile(ends, 95)), 3),
                "p_lose_half": round(halved / n_sims, 3),
                "p_down": round(float((ends < 1).mean()), 3),
                "avg_stake_pct": round(100 * staked / max(1, bets_placed), 2),
                "bets_per_season": round(bets_placed / n_sims, 1),
            })  # fmt: skip
    return rows


def blend_weight(s: pl.DataFrame, model: str, upto: int) -> float:
    """The weight w in logit(p) = logit(p_mkt) + w·(logit(p_model) − logit(p_mkt)) that minimizes
    log loss on seasons through `upto`: how much of the model's disagreement history says to keep.
    One row per game (the home side)."""
    d = (
        _hist(s)
        .filter((pl.col("side") == "home") & (pl.col("season") <= upto) & (pl.col("won") != 0.5))
        .select("p_mkt", f"p_{model}", "won")
        .drop_nulls()
    )
    lm = np.log(d["p_mkt"] / (1 - d["p_mkt"])).to_numpy()
    lx = np.log(d[f"p_{model}"] / (1 - d[f"p_{model}"])).to_numpy()
    y = d["won"].to_numpy()
    best, best_ll = 0.0, math.inf
    for w in np.linspace(-0.5, 1.0, 151):
        p = 1 / (1 + np.exp(-(lm + w * (lx - lm))))
        ll = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
        if ll < best_ll:
            best, best_ll = float(w), ll
    return round(best, 2)


def blend_path(s: pl.DataFrame, model: str) -> list[dict]:
    """The walk-forward blend weight per season: fitted on every earlier season."""
    last = int(_hist(s)["season"].max())
    return [{"season": y, "w": blend_weight(s, model, y - 1)} for y in range(2010, last + 1)]


# 6. spreads and totals ---------------------------------------------------------------------------


def spreads_totals(games: pl.DataFrame, model: str) -> dict:
    """The "targeted" candidates on spreads and totals. Prices default to -110 where missing."""
    g = games.filter((pl.col("season") <= 2025) & pl.col("result").is_not_null())

    def win_units(col: str) -> pl.Expr:
        o = pl.col(col).cast(pl.Float64).fill_null(-110.0)
        return pl.when(o > 0).then(o / 100).otherwise(100 / -o)

    # ATS on the model's spread vs the market's (side the model likes; + = home favored)
    sm = pl.col(f"s_{model}")
    ats = (
        g.filter(sm.is_not_null())
        .with_columns((sm - pl.col("spread_line")).alias("sdiff"))
        .with_columns(
            pl.when(pl.col("sdiff") > 0).then(pl.col("result") - pl.col("spread_line"))
            .otherwise(pl.col("spread_line") - pl.col("result")).alias("cover"),
            pl.when(pl.col("sdiff") > 0).then(win_units("home_spread_odds"))
            .otherwise(win_units("away_spread_odds")).alias("wu"),
            pl.col("sdiff").abs().alias("adiff"),
        )
        .with_columns(
            pl.when(pl.col("cover") > 0).then(pl.col("wu")).when(pl.col("cover") < 0).then(-1.0)
            .otherwise(0.0).alias("profit"),
            pl.when(pl.col("adiff") < 1.5).then(pl.lit("<1.5")).when(pl.col("adiff") < 3)
            .then(pl.lit("1.5-3")).when(pl.col("adiff") < 5).then(pl.lit("3-5")).otherwise(pl.lit("5+"))
            .alias("bucket"),
            _period().alias("period"),
        )
    )  # fmt: skip
    ats_t = (
        ats.group_by("bucket")
        .agg(
            *_roi_aggs(),
            pl.col("profit").filter(pl.col("period") == "2006-2015").mean().alias("roi_first"),
            pl.col("profit").filter(pl.col("period") == "2016-2025").mean().alias("roi_second"),
        )
        .sort("bucket")
    )
    # wind: unders in outdoor games with recorded wind >= 15 mph (observed, not forecast)
    tot = g.filter(pl.col("total_line").is_not_null()).with_columns(
        (pl.col("total") - pl.col("total_line")).alias("over_by"),
        win_units("under_odds").alias("wu_u"),
        _period().alias("period"),
        (pl.col("roof").is_in(["outdoors", "open"]) & (pl.col("wind") >= 15)).alias("windy"),
    )
    under = tot.with_columns(
        pl.when(pl.col("over_by") < 0).then(pl.col("wu_u")).when(pl.col("over_by") > 0)
        .then(-1.0).otherwise(0.0).alias("profit")
    )  # fmt: skip
    wind_t = (
        under.group_by("windy")
        .agg(
            *_roi_aggs(),
            pl.col("profit").filter(pl.col("period") == "2006-2015").mean().alias("roi_first"),
            pl.col("profit").filter(pl.col("period") == "2016-2025").mean().alias("roi_second"),
        )
        .sort("windy")
    )
    # key numbers: how often the final margin lands exactly on 3, 7, 10, 6, 4 (spreads near them)
    margins = g.with_columns(pl.col("result").abs().alias("m"))
    n = margins.height
    keys = [
        {"margin": k, "share": round(margins.filter(pl.col("m") == k).height / n, 4)}
        for k in (1, 2, 3, 4, 6, 7, 10, 14)
    ]
    near3 = g.filter(pl.col("spread_line").abs().is_between(2.5, 3.5))
    on3 = near3.filter(pl.col("result").abs() == 3).height / max(1, near3.height)
    return {
        "ats_by_disagreement": _rows(ats_t),
        "unders_wind_15": _rows(wind_t),
        "key_margins": keys,
        "lands_on_3_when_spread_near_3": round(on3, 4),
        "games": n,
        "rules_tried": 4 + 2,  # four ATS buckets, windy vs not
    }


def _five_year(d: pl.DataFrame) -> list[dict]:
    return _rows(
        d.with_columns((pl.col("season") // 5 * 5).alias("from"))
        .group_by("from").agg(pl.len().alias("n"), pl.col("profit").mean().alias("roi")).sort("from")
    )  # fmt: skip


def targeted_bar(games: pl.DataFrame, model: str) -> list[dict]:
    """The bar a spread or total must clear to be a "targeted" bet (ADR 0033): (1) ahead in both
    halves, (2) the 90% range above zero over all years, (3) ahead over 2021-2025, (4) a
    neighbouring version of the condition points the same way (a real effect doesn't flip sign
    one step over). Prices default to -110."""
    g = games.filter((pl.col("season") <= 2025) & pl.col("result").is_not_null())

    def wu(col: str) -> pl.Expr:
        o = pl.col(col).cast(pl.Float64).fill_null(-110.0)
        return pl.when(o > 0).then(o / 100).otherwise(100 / -o)

    def under(k: int, below: int = 999) -> pl.DataFrame:
        return g.filter(
            pl.col("roof").is_in(["outdoors", "open"]) & pl.col("wind").is_between(k, below, closed="left")
            & pl.col("total_line").is_not_null()
        ).with_columns(
            pl.when(pl.col("total") < pl.col("total_line")).then(wu("under_odds"))
            .when(pl.col("total") > pl.col("total_line")).then(-1.0).otherwise(0.0).alias("profit")
        )  # fmt: skip

    def ats(lo: float, hi: float) -> pl.DataFrame:
        sm = pl.col(f"s_{model}")
        return (
            g.filter(sm.is_not_null())
            .with_columns((sm - pl.col("spread_line")).alias("d"))
            .filter(pl.col("d").abs().is_between(lo, hi, closed="left"))
            .with_columns(
                pl.when(pl.col("d") > 0).then(pl.col("result") - pl.col("spread_line"))
                .otherwise(pl.col("spread_line") - pl.col("result")).alias("c"),
                pl.when(pl.col("d") > 0).then(wu("home_spread_odds")).otherwise(wu("away_spread_odds")).alias("w"),
            )
            .with_columns(
                pl.when(pl.col("c") > 0).then(pl.col("w")).when(pl.col("c") < 0).then(-1.0)
                .otherwise(0.0).alias("profit")
            )
        )  # fmt: skip

    cands = [
        (
            "under_wind_15",
            "Under when the recorded wind is 15 mph or more (outdoors)",
            under(15),
            under(10, 15),  # the disjoint step below, not a superset of the rule
        ),
        (
            "ats_gap_5",
            f"The side of the spread the {model} likes by 5+ points",
            ats(5, 99),
            ats(3, 5),
        ),
    ]
    out = []
    for key, label, d, neighbour in cands:
        n = d.height
        roi = float(d["profit"].mean())
        lo = roi - Z90 * float(d["profit"].std()) / math.sqrt(n)
        first = float(d.filter(pl.col("season") <= TRAIN_END)["profit"].mean())
        second = float(d.filter(pl.col("season") > TRAIN_END)["profit"].mean())
        recent = d.filter(pl.col("season") >= 2021)
        rec = float(recent["profit"].mean())
        nb = float(neighbour["profit"].mean())
        checks = {"both_halves": first > 0 and second > 0, "range_above_zero": lo > 0,
                  "recent": rec > 0, "neighbour_agrees": nb > 0}  # fmt: skip
        out.append({
            "key": key, "label": label, "n": n, "roi": round(roi, 4), "roi_lo": round(lo, 4),
            "roi_first": round(first, 4), "roi_second": round(second, 4),
            "roi_2021_2025": round(rec, 4), "n_2021_2025": recent.height,
            "neighbour_roi": round(nb, 4), "checks": checks, "passes": all(checks.values()),
            "by_five_years": _five_year(d),
        })  # fmt: skip
    return out


def _rule_stats(g: pl.DataFrame) -> dict:
    n = g.height
    if n == 0:
        return {"n": 0}
    p = g["profit"]
    roi, se = float(p.mean()), float(p.std() or 0) / math.sqrt(n)
    half = lambda lo, hi: g.filter(pl.col("season").is_between(lo, hi))["profit"]
    h1, h2, rec = half(2006, TRAIN_END), half(TRAIN_END + 1, 2025), half(2021, 2025)
    per_season = g.group_by("season").agg(pl.col("profit").sum())
    return {
        "n": n, "roi": round(roi, 4), "roi_lo": round(roi - Z90 * se, 4), "roi_hi": round(roi + Z90 * se, 4),
        "roi_first": round(float(h1.mean()), 4) if len(h1) else None,
        "roi_second": round(float(h2.mean()), 4) if len(h2) else None,
        "roi_2021_2025": round(float(rec.mean()), 4) if len(rec) else None, "n_2021_2025": len(rec),
        "win_rate": round(float(g["won"].mean()), 4),
        "seasons_up": per_season.filter(pl.col("profit") > 0).height, "seasons": per_season.height,
        "per_week": round(n / g.group_by("season", "week").len().height, 1),
    }  # fmt: skip


def side_rules(s: pl.DataFrame, model: str) -> dict:
    """The card's rules (`rules.side_view`) on 2006-2025, every side of every game: what betting
    each view returned at the closing-ish moneyline, per half and over 2021-2025. The gap limits
    (LEAN_MIN, LEAN_MAX) were read off this same history, so `lean_dog` also gets the targeted bar
    with a neighbouring condition (a lean of 0 to LEAN_MIN on the same underdogs)."""
    m = f"p_{model}"
    d = (
        _hist(s).filter((pl.col("season") <= 2025) & pl.col(m).is_not_null())
        .with_columns((pl.col(m) - pl.col("p_mkt")).alias("gap"), _band_expr().alias("band"))
    )  # fmt: skip
    views = [rules.side_view(a, b) for a, b in zip(d[m], d["p_mkt"], strict=True)]
    d = d.with_columns(
        pl.Series("view", [v[0] for v in views]), pl.Series("why", [v[1] for v in views])
    )
    groups = {
        "target": d.filter(pl.col("view") == "target"),
        "lean_dog": d.filter(pl.col("why") == "lean_dog"),
        "lean": d.filter(pl.col("why") == "lean"),
        "avoid": d.filter(pl.col("view") == "avoid"),
        "mid_fav": d.filter(pl.col("why") == "mid_fav"),
        "long": d.filter(pl.col("why") == "long"),
        "big_gap": d.filter(pl.col("why") == "big_gap"),
        "no_view": d.filter(pl.col("why") == "no_view"),
    }
    out = {k: _rule_stats(g) for k, g in groups.items()}
    # the model's own pick to win, whatever the price: the naive way to use a model
    out["model_pick"] = _rule_stats(d.filter(pl.col(m) > 0.5))
    ld = out["lean_dog"]
    nb = _rule_stats(
        d.filter(
            (pl.col("band") == "dog") & pl.col("gap").is_between(0, rules.LEAN_MIN, closed="left")
        )
    )
    checks = {
        "both_halves": (ld.get("roi_first") or 0) > 0 and (ld.get("roi_second") or 0) > 0,
        "range_above_zero": (ld.get("roi_lo") or 0) > 0,
        "recent": (ld.get("roi_2021_2025") or 0) > 0,
        "neighbour_agrees": (nb.get("roi") or 0) > 0,
    }  # fmt: skip
    out["lean_dog_bar"] = {"neighbour_roi": nb.get("roi"), "neighbour_n": nb.get("n"),
                           "checks": checks, "passes": all(checks.values())}  # fmt: skip
    # the week's targets: the MAX_TARGETS best non-avoid sides each week, ranked by their cell's
    # shrunk return. In sample (cells from all of 2006-2025) and walk-forward (cells from the
    # seasons before, from 2011), the honest version.
    d = d.with_columns(pl.Series("cell", [rules.cell_of(x) for x in d["gap"]]))
    table = cell_table(d)
    out["cells"] = [{"band": b, "cell": c} | v for (b, c), v in sorted(table.items())]
    out["ranked"] = _rule_stats(_ranked(d, table))
    wf = [_ranked(d.filter(pl.col("season") == yr), cell_table(d.filter(pl.col("season") < yr)))
          for yr in range(2011, 2026)]  # fmt: skip
    out["ranked_walk_forward"] = _rule_stats(pl.concat(wf)) | {"from": 2011}
    out["rest"] = _rule_stats(
        d.filter(pl.col("view") != "avoid").join(_ranked(d, table).select("game_id", "side"),
                                                 on=["game_id", "side"], how="anti")
    )  # fmt: skip
    out["limits"] = {"lean_min": rules.LEAN_MIN, "lean_max": rules.LEAN_MAX,
                     "max_targets": rules.MAX_TARGETS, "shrink_k": rules.SHRINK_K,
                     "grades": [{"min": lo, "grade": g} for lo, g in rules.GRADES]}  # fmt: skip
    return out


def cell_table(d: pl.DataFrame) -> dict[tuple[str, str], dict]:
    """(band, cell) -> n, roi and the shrunk score (n·roi + K·overall) / (n + K)."""
    if d.is_empty():
        return {}
    overall = float(d["profit"].mean())
    k = rules.SHRINK_K
    t = d.group_by("band", "cell").agg(pl.len().alias("n"), pl.col("profit").mean().alias("roi"))
    return {
        (r["band"], r["cell"]): {"n": r["n"], "roi": round(r["roi"], 4),
                                 "score": round((r["n"] * r["roi"] + k * overall) / (r["n"] + k), 4)}
        for r in t.iter_rows(named=True)
    }  # fmt: skip


def side_score(table: dict, band: str, cell: str) -> float | None:
    v = table.get((band, cell))
    return None if v is None else v["score"]


def _ranked(d: pl.DataFrame, table: dict) -> pl.DataFrame:
    """The MAX_TARGETS best non-avoid sides of each week by their cell's score."""
    if d.is_empty() or not table:
        return d.head(0).with_columns(pl.lit(None, dtype=pl.Float64).alias("score"))
    sc = pl.DataFrame([{"band": b, "cell": c, "score": v["score"]} for (b, c), v in table.items()])
    return (
        d.filter((pl.col("view") != "avoid") & pl.col("cell").is_in(list(rules.ELIGIBLE_CELLS)))
        .join(sc, on=["band", "cell"], how="inner")
        .sort("score", "gap", descending=True)
        .group_by("season", "week", maintain_order=True).head(rules.MAX_TARGETS)
        .select(*d.columns, "score")  # group_by().head() moves the keys first; keep one layout
    )  # fmt: skip


# 7. fees, worse prices, exchanges ----------------------------------------------------------------


def fees(s: pl.DataFrame, model: str) -> list[dict]:
    """What each way of buying the same bets returns: the sportsbook price, the same price minus
    10 or 20 cents, an exchange contract at the vig-free chance plus a Kalshi-style taker fee
    (0.07·p·(1−p) per $1 contract) and a 1-cent spread, and flat extra fees of 2% and 4%."""
    d = _hist(s).filter(pl.col("season") <= 2025)
    pools = {
        "every_favorite": d.filter(pl.col("fav")),
        "every_underdog": d.filter(~pl.col("fav") & (pl.col("p_mkt") < 0.5)),
        "model_picks": d.filter(pl.col(f"p_{model}") > 0.5),
        "model_leans_5": lean_sides(d, model).filter(pl.col("gap") >= 0.05),
    }
    rows = []
    for name, p in pools.items():
        price = p["price"].to_numpy()
        won = p["won"].to_numpy()
        pm = p["p_mkt"].to_numpy()

        def roi(dec, won=won):
            pay = np.where(won == 1, dec - 1, np.where(won == 0, -1.0, 0.0))
            return round(float(pay.mean()), 4)

        dec_book = np.array([prices.decimal(x) for x in price])
        cost = np.clip(pm + 0.01, 0.01, 0.99)
        dec_ex = 1 / (cost + 0.07 * cost * (1 - cost))
        rows.append({
            "pool": name, "n": len(price),
            "book": roi(dec_book),
            "book_minus_10c": roi(np.array([prices.decimal(prices.shade(x, 10)) for x in price])),
            "book_minus_20c": roi(np.array([prices.decimal(prices.shade(x, 20)) for x in price])),
            "exchange": roi(dec_ex),
            "fee_2pct": round(roi(dec_book) - 0.02, 4),
            "fee_4pct": round(roi(dec_book) - 0.04, 4),
        })  # fmt: skip
    return rows


def kalshi_fee_table() -> list[dict]:
    """The taker fee as a share of the stake by contract price: largest on long shots."""
    return [
        {"price_cents": c, "fee_pct_of_stake": round(100 * 0.07 * (1 - c / 100), 2),
         "american_equiv": round(prices.exchange_price(c / 100))}
        for c in (20, 35, 50, 65, 80, 90)
    ]  # fmt: skip


# 8. live lines: shopping and the closing line ----------------------------------------------------


US_BOOKS = ("draftkings", "fanduel", "betmgm", "betrivers")  # state-licensed US books in our feed


def _shopping(ml: pl.DataFrame, lines: pl.DataFrame) -> dict:
    """Expected return of a moneyline at the best, median and worst book, each priced against the
    vig-free consensus of every book at that snapshot (the fair chance)."""
    from nfl import odds

    dec = (
        pl.when(pl.col("price_american") > 0)
        .then(1 + pl.col("price_american") / 100)
        .otherwise(1 + 100 / -pl.col("price_american"))
    )
    fair = odds.consensus(lines).select("game_id", "snapshot_ts", "p_home_vigfree")
    t = (
        ml.with_columns(dec.alias("dec"))
        .group_by("game_id", "snapshot_ts", "side")
        .agg(pl.col("dec").max().alias("best"), pl.col("dec").median().alias("med"),
             pl.col("dec").min().alias("worst"), pl.len().alias("books"))
        .filter(pl.col("books") >= 3)
        .join(fair, on=["game_id", "snapshot_ts"])
        .with_columns(pl.when(pl.col("side") == "home").then("p_home_vigfree")
                      .otherwise(1 - pl.col("p_home_vigfree")).alias("fair"))
    )  # fmt: skip
    if t.is_empty():
        return {}
    return {
        "prices": t.height,
        "ev_best": round(float((t["best"] * t["fair"] - 1).mean()), 4),
        "ev_median": round(float((t["med"] * t["fair"] - 1).mean()), 4),
        "ev_worst": round(float((t["worst"] * t["fair"] - 1).mean()), 4),
        "best_beats_fair_share": round(float(((t["best"] * t["fair"] - 1) > 0).mean()), 3),
    }


def live_lines(paths, model: str) -> dict:
    """From our own 2026 snapshots: how much the best book beats the median book, and how the
    vig-free chance moved from each lock to the close on the side the model leaned."""
    from nfl import odds
    from nfl.predict import existing

    lines = odds.read_lines(paths)
    if lines.is_empty():
        return {}
    ml = lines.filter((pl.col("market") == "h2h") & (pl.col("snapshot_ts") < pl.col("kickoff_utc")))
    dec = (
        pl.when(pl.col("price_american") > 0)
        .then(1 + pl.col("price_american") / 100)
        .otherwise(1 + 100 / -pl.col("price_american"))
    )
    shop_us = _shopping(ml.filter(pl.col("book").is_in(list(US_BOOKS))), lines)
    shop = (
        ml.with_columns(dec.alias("dec"))
        .group_by("game_id", "snapshot_ts", "side")
        .agg(
            pl.col("dec").max().alias("best"),
            pl.col("dec").median().alias("med"),
            pl.len().alias("books"),
        )
        .filter(pl.col("books") >= 4)
        .with_columns(((pl.col("best") / pl.col("med")) - 1).alias("gain"))
    )
    shop_out = {"us_books": list(US_BOOKS), "us": shop_us}
    if not shop.is_empty():
        shop_out |= {
            "snapshots": int(shop.select("game_id", "snapshot_ts").unique().height),
            "best_vs_median_return": round(float(shop["gain"].mean()), 4),
            "best_vs_median_return_p90": round(float(shop["gain"].quantile(0.9)), 4),
        }
    # CLV of the model's lean at each live lock
    cons = odds.consensus(lines).filter(pl.col("p_home_vigfree").is_not_null())
    kick = lines.select("game_id", "kickoff_utc").unique()
    close = (
        cons.join(kick, on="game_id").filter(pl.col("snapshot_ts") < pl.col("kickoff_utc"))
        .sort("snapshot_ts").group_by("game_id").last().select("game_id", pl.col("p_home_vigfree").alias("p_close"))
    )  # fmt: skip
    played = kick.filter(pl.col("kickoff_utc") < datetime.now(UTC).replace(tzinfo=None))["game_id"]
    preds = existing(paths).filter(
        (pl.col("model_id") == model)
        & ~pl.col("is_backfill")
        & pl.col("game_id").is_in(played.to_list())
    )  # only games that kicked off: their last snapshot is the close
    at_lock = (
        preds.sort("lock_ts")
        .join_asof(cons.sort("snapshot_ts"), left_on="lock_ts", right_on="snapshot_ts", by="game_id", strategy="backward", check_sortedness=False)
        .filter(pl.col("p_home_vigfree").is_not_null())
        .join(close, on="game_id")
        .with_columns(pl.when(pl.col("p_home") > pl.col("p_home_vigfree")).then(1.0).otherwise(-1.0).alias("dir"))
        .with_columns(((pl.col("p_close") - pl.col("p_home_vigfree")) * pl.col("dir")).alias("clv"),
                      ((pl.col("p_home") - pl.col("p_home_vigfree")).abs()).alias("gap"))
    )  # fmt: skip
    return shop_out | {
        "clv_games": at_lock.height,
        "clv_mean_points": round(100 * float(at_lock["clv"].mean()), 2) if at_lock.height else None,
        "clv_positive_share": round(float((at_lock["clv"] > 0).mean()), 3) if at_lock.height else None,
        "clv_mean_points_gap5": round(100 * float(at_lock.filter(pl.col("gap") >= 0.05)["clv"].mean()), 2)
        if at_lock.filter(pl.col("gap") >= 0.05).height else None,
        "clv_games_gap5": at_lock.filter(pl.col("gap") >= 0.05).height,
    }  # fmt: skip


# -------------------------------------------------------------------------------------------------


def run(paths, model: str = "student", models: tuple[str, ...] = history.APPROACHES) -> dict:
    allm = tuple(dict.fromkeys((*models, model)))
    games = history.game_table(paths, allm)
    s = history.sides(games, allm)
    w = blend_weight(s, model, 2025)
    path = blend_path(s, model)
    return {
        "model": model,
        "model_versions": history.model_versions(paths, allm),
        "games": games.filter(pl.col("season") <= 2025).height,
        "seasons": [history.FIRST_SEASON, 2025],
        "price": by_price(s),
        "pick_winners": pick_winners(s, model),
        "gap": by_gap(s, allm),
        "agreement": agreement(s, models),
        "walk_forward": walk_forward(s, models),
        "blend": {"w_through_2025": w, "path": path},
        "parlays": parlays(s, model),
        "vig_compounding": vig_compounding(),
        "staking": staking(s, model, {r["season"]: r["w"] for r in path}),
        "spreads_totals": spreads_totals(games, model),
        "targeted": targeted_bar(games, model),
        "rules": side_rules(s, model),
        "fees": fees(s, model),
        "kalshi_fee": kalshi_fee_table(),
        "live": live_lines(paths, model),
    }
