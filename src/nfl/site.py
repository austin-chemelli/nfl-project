"""`nfl site`: the JSON contract every UI page reads (M5.1, architecture §3.7).

Streamlit (P1) and the React site (P2) read only these files, never parquet, so the contract is the
product boundary. Everything lands in marts/site/:

  meta.json                  schema version, generation time, data freshness, model registry
                             (labels, kinds), approaches (blurb, persona + fitted group weights),
                             the group registry
  slate_<season>_<ww>.json   one week: per game the market and every model's p_home / spread with a
                             status: 'locked' (a real lock before kickoff), 'backfill' (completed
                             game, frozen fits, synthetic lock), or 'preview' (upcoming, scored now,
                             not a lock)
  game/<game_id>.json        one game: the slate row plus per-model contributions by group and
                             feature, home/away feature values, tendencies, injuries, narrative
  tracker.json               seasons scorecard, current-season cumulative log loss by week, backtest
                             summary with CIs, reliability bins, divergence buckets, ledger, weeks
                             tracked live
  audit.json                 data freshness and null-rate audit

Numbers are rounded for display (4 decimals for probabilities); parquet keeps full precision.

Contract v2 (2026-10-27, `.notes/ui-feedback.md`): one model per approach (`<approach>`, ADR 0004
amendment); no log-odds anywhere: contributions are **points of win probability** (pp, how much the
home win probability would drop without that piece, so they add up only approximately); a team's
**edge** in a group is a percentile of all matchups 2005–2025; persona weights are **shares of a
100-point attention budget**; every feature and group ships a label, description and unit in
meta.json for hover help and formatting.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import polars as pl

from nfl.config import Paths, current_season, now_utc
from nfl.features import store
from nfl.features.groups import FEATURE_GROUP, GROUPS, HEADINGS, REGISTRY_VERSION

SCHEMA_VERSION = "2"  # v2 2026-10-27: one line per approach; no log-odds; descriptions + units
PREVIEW = "preview"
LOCKED = "locked"
BACKFILL = "backfill"

REFERENCE = {"market_baseline": "Market", "elo_v0": "Elo", "home_naive": "Home team 57%"}
SPECIAL = {"ensemble": "Ensemble", "global": "Global fit (all features)"}
TENDENCY_SITUATIONS = ["all", "early_down", "third_down", "red_zone"]

# Labels for the tendency metrics (contract v2.1, 2026-10-28; previously hard-coded in the Streamlit
# page). `pair` links an offense metric to the defense metric it faces, for side-by-side charts.
TENDENCY_METRICS: dict[str, dict] = {
    "pass_rate": {"side": "off", "label": "Pass rate", "unit": "pct", "pair": "pass_rate_faced",
                  "help": "Share of plays that are passes (including sacks and scrambles)."},
    "pass_rate_faced": {"side": "def", "label": "Pass rate faced", "unit": "pct", "pair": "pass_rate",
                        "help": "Share of opponent plays that are passes."},
    "success_rate": {"side": "off", "label": "Success rate", "unit": "pct", "pair": "success_rate_allowed",
                     "help": "Share of plays that improve the scoring outlook (EPA above zero)."},
    "success_rate_allowed": {"side": "def", "label": "Success rate allowed", "unit": "pct", "pair": "success_rate",
                             "help": "Share of opponent plays that improve their scoring outlook; lower is better."},
    "epa_per_play": {"side": "off", "label": "EPA per play", "unit": "epa", "pair": "epa_per_play_allowed",
                     "help": "Expected points added per play; around 0 is average."},
    "epa_per_play_allowed": {"side": "def", "label": "EPA allowed per play", "unit": "epa", "pair": "epa_per_play",
                             "help": "Expected points the defense allows per play; lower is better."},
    "motion_rate": {"side": "off", "label": "Pre-snap motion", "unit": "pct", "pair": None,
                    "help": "Share of plays with a player in motion before the snap (FTN charting)."},
    "play_action_rate": {"side": "off", "label": "Play-action", "unit": "pct", "pair": None,
                         "help": "Share of passes with a play-action fake (FTN charting)."},
    "rpo_rate": {"side": "off", "label": "RPO rate", "unit": "pct", "pair": None,
                 "help": "Share of plays that are run-pass options (FTN charting)."},
    "screen_rate": {"side": "off", "label": "Screen rate", "unit": "pct", "pair": None,
                    "help": "Share of passes that are screens (FTN charting)."},
    "shotgun_rate": {"side": "off", "label": "Shotgun rate", "unit": "pct", "pair": None,
                     "help": "Share of plays with the QB in shotgun."},
    "under_center_rate": {"side": "off", "label": "Under center", "unit": "pct", "pair": None,
                          "help": "Share of plays with the QB under center (FTN charting)."},
    "no_huddle_rate": {"side": "off", "label": "No-huddle rate", "unit": "pct", "pair": None,
                       "help": "Share of plays run without a huddle."},
    "fourth_down_go_rate": {"side": "off", "label": "4th-down go rate", "unit": "pct", "pair": None,
                            "help": "Share of 4th downs the offense goes for it rather than punting or kicking."},
    "blitz_rate": {"side": "def", "label": "Blitz rate", "unit": "pct", "pair": None,
                   "help": "Share of opponent dropbacks with at least one blitzer (FTN charting)."},
    "pass_rushers_5plus_rate": {"side": "def", "label": "5+ pass rushers", "unit": "pct", "pair": None,
                                "help": "Share of opponent dropbacks with five or more rushers (FTN charting)."},
    "box_8plus_vs_run_rate": {"side": "def", "label": "8+ in the box vs runs", "unit": "pct", "pair": None,
                              "help": "Share of opponent runs faced with 8 or more defenders in the box."},
    "box_6minus_vs_run_rate": {"side": "def", "label": "Light box vs runs", "unit": "pct", "pair": None,
                               "help": "Share of opponent runs faced with 6 or fewer defenders in the box."},
}  # fmt: skip
TENDENCY_SITUATION_LABELS = {
    "all": "All plays", "early_down": "Early downs", "third_down": "Third down", "red_zone": "Red zone",
}  # fmt: skip


# ---------------------------------------------------------------------------------------- helpers


def _r(x, nd: int = 4):
    if x is None:
        return None
    try:
        return round(float(x), nd)
    except TypeError, ValueError:
        return x


def _ts(x: datetime | None) -> str | None:
    return None if x is None else x.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=str))


def _read(paths: Paths, name: str) -> pl.DataFrame:
    f = paths.marts / f"{name}.parquet"
    return pl.read_parquet(f) if f.exists() else pl.DataFrame()


# --------------------------------------------------------------------------------------- registry


def model_registry() -> dict[str, dict]:
    from nfl.approaches.schema import load_all

    reg = {mid: {"label": lab, "kind": "reference"} for mid, lab in REFERENCE.items()}
    reg |= {mid: {"label": lab, "kind": mid} for mid, lab in SPECIAL.items()}
    for a in load_all().values():
        if a.id == "narrative":
            continue
        reg[a.id] = {"label": a.name, "kind": "approach", "approach": a.id}
    return reg


def _shares(W: dict[str, float]) -> dict[str, float]:
    """Signed share (%) of a 100-point attention budget."""
    tot = sum(abs(v) for v in W.values())
    return {g: _r(100 * v / tot, 1) for g, v in W.items()} if tot else {}


def _shifted(persona: dict, public: dict) -> float | None:
    """Attention points (of 100) that light fitting moved between groups: Σ|public − persona| / 2."""
    P, L = _shares(persona), _shares(public)
    if not (P and L):
        return None
    return _r(sum(abs((L.get(g) or 0) - (P.get(g) or 0)) for g in set(P) | set(L)) / 2, 1)


def approaches_meta(paths: Paths, season: int) -> list[dict]:
    """Per approach: blurb, attention budget (persona), the public line's budget after light fitting,
    what history alone would choose, and how confident the persona is relative to history."""
    from nfl.approaches import fit
    from nfl.approaches.schema import load_all

    out = []
    for a in load_all().values():
        if a.id == "narrative":
            continue
        persona = {g: w.w for g, w in a.groups.items()}
        public, history, confidence = {}, {}, None
        try:
            pub = fit.load(paths, a.id, season - 1)
            hist = fit.load(paths, f"{a.id}.fitted", season - 1)
            public = pub.meta.get("group_weights", {})
            history = hist.meta.get("group_weights", {})
            # Platt slope a on the public line: a < 1 means the persona's raw confidence is too high
            confidence = _r(pub.calib_a, 3)
        except FileNotFoundError:
            pass
        out.append(
            {
                "id": a.id,
                "name": a.name,
                "blurb": a.blurb,
                "emphasis": a.emphasis,
                "public_line": a.public,
                "home_field_why": a.intercept.why,
                "why": {g: w.why for g, w in a.groups.items()},
                "persona_share": _shares(persona),
                "history_shifted_points": _shifted(persona, public),
                "public_share": _shares(public),
                "history_share": _shares(history),
                "overrides": a.overrides,
                "calibration_scale": confidence,
                "trained_through": season - 1,
            }
        )
    return out


def groups_meta() -> dict:
    from nfl.features.groups import UNITS

    return {
        "registry_version": REGISTRY_VERSION,
        "headings": HEADINGS,
        "units": UNITS,
        "groups": [
            {
                "id": g.id,
                "name": g.name,
                "heading": g.heading,
                "meaning": g.meaning,
                "description": g.description,
                "game_level": g.game_level,
                "members": [
                    {"feature": m.feature, "sign": m.sign, "adv": m.adv, "label": m.label,
                     "unit": m.unit, "description": m.description}
                    for m in g.members
                ],
            }
            for g in GROUPS.values()
        ],
    }  # fmt: skip


def freshness(paths: Paths) -> dict:
    out = {}
    for d in sorted(paths.raw.glob("*")):
        snaps = sorted(p.name.split("=", 1)[1] for p in d.glob("snapshot_ts=*"))
        if snaps:
            out[d.name] = snaps[-1]
    odds = sorted(
        p.name.split("=", 1)[1]
        for p in (paths.root / "raw" / "odds_api" / "live").glob("snapshot_ts=*")
    )
    if odds:
        out["odds_api"] = odds[-1]
    return out


# ------------------------------------------------------------------------------------ predictions


def best_rows(paths: Paths, games: pl.DataFrame, now: datetime) -> pl.DataFrame:
    """One row per (game, model): the last lock before kickoff, else the backfill row. Adds status."""
    preds = _read(paths, "predictions")
    if preds.is_empty():
        return preds
    kick = games.select(
        "game_id", pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us"))
    )
    p = preds.join(kick, on="game_id").filter(pl.col("lock_ts") < pl.col("kickoff_utc"))
    live = p.filter(~pl.col("is_backfill")).sort("lock_ts").group_by("game_id", "model_id").last()
    back = p.filter(pl.col("is_backfill")).sort("lock_ts").group_by("game_id", "model_id").last()
    back = back.join(live.select("game_id", "model_id"), on=["game_id", "model_id"], how="anti")
    return pl.concat(
        [
            live.with_columns(pl.lit(LOCKED).alias("status")),
            back.with_columns(pl.lit(BACKFILL).alias("status")),
        ],
        how="vertical_relaxed",
    )


def preview_rows(
    paths: Paths, games: pl.DataFrame, slate: pl.DataFrame, now: datetime
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Score upcoming games without a lock, as of now. Returns (rows like predictions, market)."""
    from nfl import lock

    if slate.is_empty():
        return pl.DataFrame(), pl.DataFrame()
    season = int(slate["season"][0])
    feats = store.read_features(paths, seasons=(season, season))
    models, _missing = lock.load_models(paths, season - 1)
    market = lock.market_at(feats, slate, now)
    scored = lock.score_approaches(models, feats, slate, now) + lock.score_reference(
        games, slate, market
    )
    rows = []
    for s in scored:
        f = s.frame
        if "contributions" not in f.columns:
            f = f.with_columns(pl.lit(None, dtype=pl.Utf8).alias("contributions"))
        rows.append(
            f.select("game_id", "p_home", "spread_home", "contributions").with_columns(
                pl.lit(s.model_id).alias("model_id"),
                pl.lit(now, dtype=pl.Datetime("us")).alias("lock_ts"),
                pl.lit(PREVIEW).alias("status"),
            )
        )
    return (pl.concat(rows) if rows else pl.DataFrame()), market


def _market_by_game(paths: Paths, games: pl.DataFrame, now: datetime) -> pl.DataFrame:
    """The market per game: the latest feature rows before kickoff (completed) or now (upcoming)."""
    from nfl import lock

    season = int(games["season"].max())
    feats = store.read_features(paths, seasons=(season, season), families=["market"])
    out = []
    g = games.with_columns(pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us")))
    locks = g.select(
        "game_id",
        pl.min_horizontal(pl.col("kickoff_utc"), pl.lit(now, dtype=pl.Datetime("us"))).alias(
            "lock_ts"
        ),
    )
    for (lts,), part in locks.group_by(["lock_ts"]):
        out.append(
            lock.market_at(feats, g.filter(pl.col("game_id").is_in(part["game_id"].to_list())), lts)
        )
    return (
        pl.concat([o for o in out if not o.is_empty()])
        if any(not o.is_empty() for o in out)
        else pl.DataFrame()
    )


# ------------------------------------------------------------------------------------------ build


def build(paths: Paths, season: int | None = None) -> dict:
    t0 = time.perf_counter()
    season = season or current_season()
    now = now_utc().replace(tzinfo=None, microsecond=0)
    site = paths.site
    games = (
        store.games_frame(paths)
        .filter(pl.col("season") == season)
        .with_columns(pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us")))
    )
    reg = model_registry()

    rows = best_rows(paths, games, now)
    have = (
        rows.select("game_id").unique()
        if not rows.is_empty()
        else pl.DataFrame(schema={"game_id": pl.Utf8})
    )
    upcoming = games.filter(
        (pl.col("kickoff_utc") > now) & ~pl.col("game_id").is_in(have["game_id"].to_list())
    )
    # preview only the next two weeks: further out, nothing has been built for those games yet
    if not upcoming.is_empty():
        first = int(upcoming["week"].min())
        upcoming = upcoming.filter(pl.col("week") <= first + 1)
    prev, _ = preview_rows(paths, games, upcoming, now)
    allrows = pl.concat(
        [r.select("game_id", "model_id", "p_home", "spread_home", "contributions", "lock_ts", "status")
         for r in (rows, prev) if not r.is_empty()],
        how="vertical_relaxed",
    ) if (not rows.is_empty() or not prev.is_empty()) else pl.DataFrame()  # fmt: skip
    market = _market_by_game(paths, games, now)

    feats = store.read_features(paths, seasons=(season, season))
    tend = _read(paths, "tendencies")
    injuries = _injuries(paths, season)
    from nfl.llm.narrative import load_records

    narr = {r.game_id: r for r in load_records(paths, (season, season))}
    edges = group_edges(paths, games, feats, season, now)

    n_weeks = 0
    for (week,), wk in games.group_by(["week"], maintain_order=True):
        wk = wk.sort("kickoff_utc", "game_id")
        slate_games = []
        for g in wk.iter_rows(named=True):
            row = _game_row(g, allrows, market, reg)
            slate_games.append(row)
            detail = row | _game_detail(g, allrows, feats, tend, injuries, narr, now, edges)
            _write(site / "game" / f"{g['game_id']}.json", detail)
        _write(
            site / f"slate_{season}_{int(week):02d}.json",
            {"schema_version": SCHEMA_VERSION, "season": season, "week": int(week),
             "generated_at": _ts(now), "games": slate_games},
        )  # fmt: skip
        n_weeks += 1

    current_week = (
        int(games.filter(pl.col("kickoff_utc") > now)["week"].min())
        if not games.filter(pl.col("kickoff_utc") > now).is_empty()
        else int(games["week"].max())
    )
    _write(
        site / "meta.json",
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _ts(now),
            "season": season,
            "current_week": current_week,
            "weeks": sorted(int(w) for w in games["week"].unique().to_list()),
            "freshness": freshness(paths),
            "models": reg,
            "approaches": approaches_meta(paths, season),
            "groups": groups_meta(),
            "tendency_metrics": TENDENCY_METRICS,
            "tendency_situations": TENDENCY_SITUATION_LABELS,
            "last_lock": _last_lock(paths),
        },
    )
    _write(site / "tracker.json", tracker(paths, season, reg))
    _write(site / "audit.json", audit(paths))
    return {"weeks": n_weeks, "games": games.height, "seconds": round(time.perf_counter() - t0, 1)}


def group_edges(
    paths: Paths, games: pl.DataFrame, feats: pl.DataFrame, season: int, now: datetime
) -> dict[str, dict]:
    """Per game and group: which team has the edge and how big it is, as a percentile of all
    matchup edges 2005–2025 (|composite| rank), using the same composites as the DIY page."""
    import numpy as np

    from nfl.approaches import diy

    mfile = paths.marts / "diy" / "matrix.parquet"
    if not mfile.exists() or games.is_empty():
        return {}
    ref = pl.read_parquet(mfile).filter(~pl.col("warmup").cast(pl.Boolean))
    locks = games.select(
        "game_id",
        pl.min_horizontal(pl.col("kickoff_utc"), pl.lit(now, dtype=pl.Datetime("us"))).alias(
            "lock_ts"
        ),
    )
    vec = store.game_vectors(store.as_of(feats, locks))
    allf = sorted(vec["feature"].unique().to_list())
    wide = games.select("game_id").join(store.to_wide(vec, allf), on="game_id", how="left")
    try:
        comp = diy._composites(paths, wide, season, season - 1)
    except FileNotFoundError:
        return {}
    out: dict[str, dict] = {}
    teams = dict(
        zip(games["game_id"], zip(games["home_team"], games["away_team"], strict=True), strict=True)
    )
    for j, gid_group in enumerate(diy.GROUP_IDS):
        col = f"c_{gid_group}"
        if col not in ref.columns:
            continue
        r = np.sort(np.abs(ref[col].to_numpy()))
        if not r.any():
            continue  # live-only group (no history)
        for i, gid in enumerate(wide["game_id"].to_list()):
            c = float(comp[i, j])
            pct = 100.0 * np.searchsorted(r, abs(c), side="right") / len(r)
            home, away = teams[gid]
            out.setdefault(gid, {})[gid_group] = {
                "favors": None if abs(c) < 1e-9 else (home if c > 0 else away),
                "strength_pct": _r(pct, 0),
            }
    return out


def _last_lock(paths: Paths) -> dict | None:
    p = _read(paths, "predictions")
    if p.is_empty():
        return None
    live = p.filter(~pl.col("is_backfill"))
    if live.is_empty():
        return None
    r = live.sort("lock_ts").row(-1, named=True)
    return {
        "lock_ts": _ts(r["lock_ts"]),
        "season": r["season"],
        "week": r["week"],
        "slot": r["slot"],
    }


def _game_row(g: dict, allrows: pl.DataFrame, market: pl.DataFrame, reg: dict) -> dict:
    gid = g["game_id"]
    mk = market.filter(pl.col("game_id") == gid) if not market.is_empty() else pl.DataFrame()
    m = mk.row(0, named=True) if mk.height else None
    models = {}
    if not allrows.is_empty():
        for r in allrows.filter(pl.col("game_id") == gid).iter_rows(named=True):
            if r["model_id"] not in reg:
                continue
            p = r["p_home"]
            models[r["model_id"]] = {
                "p_home": _r(p),
                "spread_home": _r(r["spread_home"], 1),
                "status": r["status"],
                "lock_ts": _ts(r["lock_ts"]),
                "divergence": _r(p - m["p_home"])
                if (m and m["p_home"] is not None and p is not None)
                else None,
            }
    result = g.get("result")
    return {
        "game_id": gid,
        "season": g["season"],
        "week": g["week"],
        "kickoff_utc": _ts(g["kickoff_utc"]),
        "away": g["away_team"],
        "home": g["home_team"],
        "stadium": g.get("stadium"),
        "roof": g.get("roof"),
        "neutral_site": (g.get("location") or "Home") != "Home",
        "away_qb": g.get("away_qb_name"),
        "home_qb": g.get("home_qb_name"),
        "result": None if result is None else {"home_score": g.get("home_score"), "away_score": g.get("away_score"), "margin": result},
        "market": None if m is None else {
            "p_home": _r(m["p_home"]), "spread_home": _r(m["spread_home"], 1), "total": _r(m["total"], 1),
            "as_of": _ts(m["as_of"]), "source": m["source"],
        },
        "models": models,
    }  # fmt: skip


def _pp(total_logit: float, piece: float) -> float:
    """Points of home win probability this piece is worth: p(with it) − p(without it), ×100."""
    from scipy.special import expit

    return _r(100 * (expit(total_logit) - expit(total_logit - piece)), 1)


def _contributions_pp(c: dict) -> dict:
    """Per-model breakdown in win-probability points. Pieces interact, so they add up only
    approximately to the model's distance from 50%."""
    from scipy.special import expit

    L = sum(c.values())
    by_group: dict[str, dict] = {}
    for f, v in c.items():
        if f == "home_field":
            continue
        grp = FEATURE_GROUP.get(f, "other")
        d = by_group.setdefault(grp, {"_logit": 0.0, "features": {}})
        d["_logit"] += v
        d["features"][f] = _pp(L, v)
    for d in by_group.values():
        d["pp"] = _pp(L, d.pop("_logit"))
        d["features"] = {f: x for f, x in d["features"].items() if x}
    return {
        "p_home": _r(expit(L)),
        "home_field_pp": _pp(L, c.get("home_field", 0.0)),
        "groups": by_group,
    }


def _game_detail(g, allrows, feats, tend, injuries, narr, now, edges=None) -> dict:
    gid = g["game_id"]
    contrib = {}
    if not allrows.is_empty():
        for r in allrows.filter(
            (pl.col("game_id") == gid) & pl.col("contributions").is_not_null()
        ).iter_rows(named=True):
            contrib[r["model_id"]] = _contributions_pp(json.loads(r["contributions"]))
    # feature values as known at the game's lock (kickoff for completed, now for upcoming)
    cut = min(g["kickoff_utc"], now)
    fv = store.as_of(feats.filter(pl.col("game_id") == gid), cut)
    values: dict[str, dict] = {}
    for r in fv.iter_rows(named=True):
        d = values.setdefault(r["feature"], {"group": FEATURE_GROUP.get(r["feature"])})
        d[r["side"]] = _r(r["value"])
    return {
        "contributions": contrib,
        "edges": (edges or {}).get(gid, {}),
        "features": values,
        "tendencies": _tendencies(tend, g),
        "injuries": [
            i
            for i in injuries
            if i["week"] == g["week"] and i["team"] in (g["home_team"], g["away_team"])
        ],
        "narrative": json.loads(narr[gid].model_dump_json()) if gid in narr else None,
    }


_LEAGUE_CACHE: dict[int, dict] = {}


def _league_rates(tend: pl.DataFrame, season: int) -> dict:
    """(side, situation, metric) -> play-weighted league average rate for the season."""
    if season not in _LEAGUE_CACHE:
        lg = (
            tend.filter(pl.col("season") == season)
            .group_by("side", "situation", "metric")
            .agg(((pl.col("rate") * pl.col("n")).sum() / pl.col("n").sum()).alias("lg"))
        )
        _LEAGUE_CACHE[season] = {
            (r["side"], r["situation"], r["metric"]): r["lg"] for r in lg.iter_rows(named=True)
        }
    return _LEAGUE_CACHE[season]


def _tendencies(tend: pl.DataFrame, g: dict) -> list[dict]:
    if tend.is_empty():
        return []
    from nfl.models.elo import TEAM_ALIASES

    teams = {g["home_team"]: "home", g["away_team"]: "away"}
    canon = {TEAM_ALIASES.get(t, t): side for t, side in teams.items()}
    league = _league_rates(tend, g["season"])
    t = tend.filter(
        (pl.col("season") == g["season"]) & pl.col("situation").is_in(TENDENCY_SITUATIONS)
        & pl.col("team").replace(TEAM_ALIASES).is_in(list(canon))
    )  # fmt: skip
    return [
        {"team_side": canon[TEAM_ALIASES.get(r["team"], r["team"])],
         "side": r["side"], "situation": r["situation"], "metric": r["metric"],
         "rate": _r(r["rate"]), "raw_rate": _r(r.get("raw_rate")), "n": r["n"],
         "league_rate": _r(league.get((r["side"], r["situation"], r["metric"])))}
        for r in t.iter_rows(named=True)
    ]  # fmt: skip


def _injuries(paths: Paths, season: int) -> list[dict]:
    import duckdb

    d = paths.curated_table("injuries") / f"season={season}"
    if not d.exists():
        return []
    df = duckdb.sql(
        f"select week, team, full_name, position, report_status, practice_status, report_primary_injury "
        f"from read_parquet('{d.as_posix()}/*.parquet') where report_status is not null"
    ).pl()
    return [
        {"week": r["week"], "team": r["team"], "player": r["full_name"], "pos": r["position"],
         "status": r["report_status"], "practice": r["practice_status"], "injury": r["report_primary_injury"]}
        for r in df.iter_rows(named=True)
    ]  # fmt: skip


# ---------------------------------------------------------------------------------------- tracker


def tracker(paths: Paths, season: int, reg: dict) -> dict:
    sc = _read(paths, "scorecard")
    graded = _read(paths, "graded")
    summ = _read(paths, "summary")
    rel = _read(paths, "reliability")
    div = _read(paths, "divergence")
    led = _read(paths, "ledger_summary")
    out: dict = {"schema_version": SCHEMA_VERSION, "season": season}
    if not sc.is_empty():
        s = sc.filter((pl.col("scope") == "season") & pl.col("model_id").is_in(list(reg)))
        out["seasons"] = [
            {"season": r["season"], "model_id": r["model_id"], "n": r["n_games"], "log_loss": _r(r["log_loss"]),
             "brier": _r(r["brier"]), "ece": _r(r.get("ece")), "spread_mae": _r(r["spread_mae"], 2)}
            for r in s.sort("season", "model_id").iter_rows(named=True)
        ]  # fmt: skip
    if not graded.is_empty():
        cur = graded.filter((pl.col("season") == season) & pl.col("model_id").is_in(list(reg)))
        wk = (
            cur.group_by("model_id", "week").agg(pl.col("log_loss").sum().alias("s"), pl.len().alias("n"),
                                                 (~pl.col("is_backfill")).any().alias("live"))
            .sort("model_id", "week")
            .with_columns((pl.col("s").cum_sum() / pl.col("n").cum_sum()).over("model_id").alias("cum"))
        )  # fmt: skip
        out["current_season"] = [
            {"model_id": r["model_id"], "week": r["week"], "n": r["n"], "cum_log_loss": _r(r["cum"]), "live": r["live"]}
            for r in wk.iter_rows(named=True)
        ]  # fmt: skip
        live = graded.filter(~pl.col("is_backfill"))
        out["weeks_tracked"] = {
            r["model_id"]: r["weeks"]
            for r in live.group_by("model_id").agg(pl.concat_str(["season", "week"]).n_unique().alias("weeks")).iter_rows(named=True)
        }  # fmt: skip
    if not summ.is_empty():
        out["backtest"] = [
            {k: (_r(v) if isinstance(v, float) else v) for k, v in r.items()}
            for r in summ.filter(pl.col("model_id").is_in(list(reg))).iter_rows(named=True)
        ]
    if not rel.is_empty():
        agg = (
            rel.filter(pl.col("model_id").is_in(list(reg)))
            .group_by("model_id", "bin")
            .agg(pl.col("n").sum(), ((pl.col("mean_p") * pl.col("n")).sum() / pl.col("n").sum()).alias("mean_p"),
                 ((pl.col("hit_rate") * pl.col("n")).sum() / pl.col("n").sum()).alias("hit_rate"))
            .sort("model_id", "bin")
        )  # fmt: skip
        out["reliability"] = [
            {"model_id": r["model_id"], "bin": int(r["bin"]), "n": r["n"], "mean_p": _r(r["mean_p"]), "hit_rate": _r(r["hit_rate"])}
            for r in agg.iter_rows(named=True)
        ]  # fmt: skip
    if not div.is_empty():
        out["divergence"] = [
            {k: (_r(v) if isinstance(v, float) else v) for k, v in r.items()}
            for r in div.filter(pl.col("model_id").is_in(list(reg))).iter_rows(named=True)
        ]
    if not led.is_empty():
        agg = (
            led.group_by("model_id", "is_backfill")
            .agg(pl.col("bets").sum(), pl.col("wins").sum(), pl.col("losses").sum(), pl.col("pushes").sum(),
                 pl.col("units").sum(), (pl.col("mean_clv") * pl.col("n_clv")).sum().alias("clv_sum"),
                 pl.col("n_clv").sum())
            .with_columns((pl.col("units") / pl.col("bets")).alias("roi"),
                          pl.when(pl.col("n_clv") > 0).then(pl.col("clv_sum") / pl.col("n_clv")).alias("clv"))
        )  # fmt: skip
        out["ledger"] = [
            {"model_id": r["model_id"], "kind": BACKFILL if r["is_backfill"] else "live", "bets": r["bets"],
             "wins": r["wins"], "losses": r["losses"], "pushes": r["pushes"], "units": _r(r["units"], 2),
             "roi": _r(r["roi"]), "clv": _r(r["clv"])}
            for r in agg.filter(pl.col("model_id").is_in(list(reg))).iter_rows(named=True)
        ]  # fmt: skip
    return out


def audit(paths: Paths) -> dict:
    a = _read(paths, "audit")
    out = {"schema_version": SCHEMA_VERSION, "freshness": freshness(paths)}
    if not a.is_empty():
        out["null_rates"] = [
            {k: (_r(v) if isinstance(v, float) else v) for k, v in r.items()}
            for r in a.iter_rows(named=True)
        ]
    return out
