"""Build your own approach: the precomputed composite matrix and the numpy evaluator (M5.8).

The matrix has one row per completed, non-tied game: the 15 group composites c_g, computed as the
fitted models compute them for that season (scaler and inner weights trained through season − 1),
the outcome, the vig-free market probability, moneylines, and context flags. Scoring a user's group
weights W is then a matrix multiply plus a walk-forward Platt calibration:

    logit_raw = Σ_g W_g c_g          p = σ(a_S · logit_raw + c_S),  (a_S, c_S) fitted on seasons < S

Composites: the Student's artifacts (student.persona, trained through S − 1) supply the 13 football
groups; `market` and `buzz` are not in the Student (ADR 0012), so their composites come from the
Sharp's artifact (sharp.persona, trained through S − 1) with the Sharp's own scaler. A group with no
usable members for a season (matchups and buzz today) has an all-zero composite and is listed in
`inactive`; its weight does nothing.

Warmup rows: seasons from the fit's `trained_from` (2002) through 2004 are in the matrix with
`warmup=1`, composites from the 2004 artifacts (the same models the 2005 backfill uses). They are
never scored; they only feed the Platt window for 2005, exactly as the backfill's Platt is fitted on
the training window. Without them the first scored season would calibrate on itself (marked
`in_sample`).

The market's own forecast (spread, moneyline probability) is never a composite or an input
(ADR 0013): `mkt_p` is the reference line the results are compared against. The `market` group is
"Market behavior" (line movement, public betting share; live only), capped at
MARKET_GROUP_CAP of a weight set's budget (`cap_market`); it is mostly live-only, so in the backtest
its composite is near zero.

Calibration is the honesty mechanism: any overall confidence a user's weights imply is replaced by
what history supports, so the scorecard does not reward or punish how loud the weights are. The
slope is constrained to a ≥ 0: a mirror-image set of weights does not get to look good by being
flipped.

Difference from the backfill (documented, measured by the consistency test): the backfill scores
season S with one model (trained through S − 1) and fits its Platt on that model's in-sample logits
over the training window; here the Platt window holds earlier seasons' logits from the composites
that were current for each of those seasons. Both calibrate on prior data only; the windows differ
slightly.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from nfl.approaches import fit
from nfl.approaches.schema import load_all
from nfl.config import FIRST_SCORED_SEASON, Paths
from nfl.features import market as market_features
from nfl.features import store
from nfl.features.groups import GROUPS, MARKET_GROUP_CAP
from nfl.grade import DIVERGENCE_BUCKETS
from nfl.ledger import EDGE_THRESHOLD

GROUP_IDS = list(GROUPS)
LAST_SEASON = 2025
BOOTSTRAP = 500
EPS = 1e-6
SCHEMA_VERSION = 1
HOME_GROUP_SOURCES = ("student.persona", "sharp.persona")  # first model with the group wins
PERSONA_IDS = ["traditionalist", "analyst", "sharp", "student"]

SPREAD_LABELS = ["Pick'em (under 3)", "Moderate (3 to 7)", "Big favorite (7+)"]
MONTH_LABELS = {9: "September", 10: "October", 11: "November", 12: "December", 13: "January+"}
FAV_LABELS = {1: "Home favorite", 0: "Pick'em line", -1: "Home underdog"}
DIV_LABELS = ["0-2.5", "2.5-5", "5-10", "10+"]


# ------------------------------------------------------------------------------------------ build


def _context(paths: Paths) -> pl.DataFrame:
    """Per game: market and context flags (nothing here depends on the fits)."""
    g = store.games_frame(paths)
    p = market_features._p_home(g).select("game_id", pl.col("p").alias("mkt_p"))
    spread = pl.col("spread_line").cast(pl.Float64)
    hour = pl.col("gametime").str.slice(0, 2).cast(pl.Int64, strict=False)
    month = pl.col("gameday").dt.month()
    return g.join(p, on="game_id", how="left").select(
        "game_id",
        spread.alias("spread"),
        pl.col("home_moneyline").cast(pl.Float64).alias("home_ml"),
        pl.col("away_moneyline").cast(pl.Float64).alias("away_ml"),
        pl.col("mkt_p"),
        pl.when(spread.is_null())
        .then(None)
        .when(spread.abs() < 3)
        .then(0)
        .when(spread.abs() < 7)
        .then(1)
        .otherwise(2)
        .cast(pl.Int8)
        .alias("spread_bucket"),
        (pl.col("result").abs() <= 3).cast(pl.Int8).alias("close"),
        (pl.col("result").abs() >= 14).cast(pl.Int8).alias("blowout"),
        pl.col("div_game").fill_null(0).cast(pl.Int8).alias("div_game"),
        (hour >= 19).fill_null(False).cast(pl.Int8).alias("primetime"),
        pl.col("roof").is_in(["dome", "closed"]).cast(pl.Int8).alias("dome"),
        pl.when(month <= 2).then(13).otherwise(month).cast(pl.Int8).alias("month"),
        pl.when(spread.is_null())
        .then(None)
        .when(spread > 0)
        .then(1)
        .when(spread < 0)
        .then(-1)
        .otherwise(0)
        .cast(pl.Int8)
        .alias("home_fav"),
        pl.col("result").cast(pl.Float64),
    )


def _composites(paths: Paths, df: pl.DataFrame, season: int, model_season: int) -> np.ndarray:
    """(n, 15) composites for `df` (one season's rows) using artifacts trained through model_season."""
    out = np.zeros((df.height, len(GROUP_IDS)))
    done: set[str] = set()
    for mid in HOME_GROUP_SOURCES:
        model = fit.load(paths, mid, model_season)
        z = model.scaler.transform(df)
        inner = model.meta["inner"]
        for j, gid in enumerate(GROUP_IDS):
            if gid in done or not inner.get(gid):
                continue
            v = fit._flat(model.features, {gid: inner[gid]}, {gid: 1.0})
            out[:, j] = z @ v
            done.add(gid)
    return out


def _weights_block(paths: Paths, first: int, last: int) -> dict:
    appr = load_all()
    personas = {}
    for pid in PERSONA_IDS:
        a = appr[pid]
        personas[pid] = {
            "name": a.name,
            "intercept": a.intercept.w,
            "W": {g: w.w for g, w in a.groups.items()},
        }
    student_fitted = {}
    for s in range(first, last + 1):
        m = fit.load(paths, "student.fitted", s - 1)
        student_fitted[str(s)] = {"intercept": m.intercept, "W": m.meta["group_weights"]}
    return {"personas": personas, "student_fitted": student_fitted}


def build_matrix(paths: Paths, write: bool = True) -> dict:
    """Compute the matrix; write marts/diy/matrix.parquet and marts/site/diy_matrix.json.
    Returns a summary dict (rows, seasons, files, inactive groups)."""
    first = FIRST_SCORED_SEASON
    probe = fit.load(paths, "student.persona", first - 1)
    warm_from = int(probe.meta["trained_from"])
    feats = sorted(
        {f for mid in HOME_GROUP_SOURCES for s in range(first, LAST_SEASON + 1)
         for f in fit.load(paths, mid, s - 1).features}
    )  # fmt: skip
    data = fit.load_dataset(paths, feats, (warm_from, LAST_SEASON))
    blocks = []
    for season in range(warm_from, LAST_SEASON + 1):
        rows = data.filter(pl.col("season") == season)
        if rows.is_empty():
            continue
        comp = _composites(paths, rows, season, max(season, first) - 1)
        block = rows.select("game_id", "season", "week", "y").with_columns(
            pl.lit(int(season < first)).cast(pl.Int8).alias("warmup"),
            *[pl.Series(f"c_{g}", comp[:, j]) for j, g in enumerate(GROUP_IDS)],
        )
        blocks.append(block)
    mat = (
        pl.concat(blocks)
        .join(_context(paths), on="game_id", how="left")
        .sort("season", "week", "game_id")
    )
    inactive = [
        g for g in GROUP_IDS if float(np.abs(mat.get_column(f"c_{g}").to_numpy()).max()) < 1e-12
    ]
    info = {
        "rows": mat.height,
        "scored_rows": int((mat["warmup"] == 0).sum()),
        "seasons": [first, LAST_SEASON],
        "warmup_from": warm_from,
        "inactive": inactive,
    }
    if write:
        info["season_files"] = build_seasons(paths, mat)
        d = paths.marts / "diy"
        d.mkdir(parents=True, exist_ok=True)
        mat.write_parquet(d / "matrix.parquet")
        paths.site.mkdir(parents=True, exist_ok=True)
        out = paths.site / "diy_matrix.json"
        out.write_text(
            json.dumps(to_json(mat, inactive, _weights_block(paths, first, LAST_SEASON)))
        )
        info |= {"parquet": str(d / "matrix.parquet"), "json": str(out),
                 "json_bytes": out.stat().st_size}  # fmt: skip
    return info


def build_seasons(paths: Paths, mat: pl.DataFrame | None = None) -> dict[str, int]:
    """Write marts/site/season_<yyyy>.json for each scored season (slim, column-oriented): per game
    id, week, teams, kickoff, result, home win, market p and the group composites (3 decimals).
    Returns {file name: bytes}."""
    if mat is None:
        mat = pl.read_parquet(paths.marts / "diy" / "matrix.parquet")
    g = store.games_frame(paths).select("game_id", "home_team", "away_team", "kickoff_utc")
    mat = mat.filter(pl.col("warmup") == 0).join(g, on="game_id", how="left")
    paths.site.mkdir(parents=True, exist_ok=True)
    sizes: dict[str, int] = {}
    for season in range(FIRST_SCORED_SEASON, LAST_SEASON + 1):
        rows = mat.filter(pl.col("season") == season).sort("week", "kickoff_utc", "game_id")
        if rows.is_empty():
            continue
        doc = {
            "version": SCHEMA_VERSION,
            "season": season,
            "groups": GROUP_IDS,
            "n": rows.height,
            "game_id": rows["game_id"].to_list(),
            "week": rows["week"].to_list(),
            "home": rows["home_team"].to_list(),
            "away": rows["away_team"].to_list(),
            "kickoff": [None if t is None else t.strftime("%Y-%m-%dT%H:%MZ") for t in rows["kickoff_utc"]],
            "result": [None if v is None else int(v) for v in rows["result"]],
            "home_won": [int(v) for v in rows["y"]],
            "market_p": [None if v is None else round(float(v), 4) for v in rows["mkt_p"]],
            "c": {k: [round(float(v), 3) for v in rows[f"c_{k}"]] for k in GROUP_IDS},
        }  # fmt: skip
        out = paths.site / f"season_{season}.json"
        out.write_text(json.dumps(doc, separators=(",", ":")))
        sizes[out.name] = out.stat().st_size
    return sizes


def to_json(mat: pl.DataFrame, inactive: list[str], weights: dict) -> dict:
    cols = {}
    for c in mat.columns:
        if c.startswith("c_"):
            continue
        s = mat.get_column(c)
        cols[c] = [None if v is None else (round(v, 4) if s.dtype.is_float() else v) for v in s]
    comp = {g: [round(float(v), 4) for v in mat.get_column(f"c_{g}").to_list()] for g in GROUP_IDS}
    return {
        "version": SCHEMA_VERSION,
        "groups": GROUP_IDS,
        "inactive": inactive,
        "first_scored": FIRST_SCORED_SEASON,
        "n": mat.height,
        "columns": cols,
        "c": comp,
    } | weights


# ---------------------------------------------------------------------------------------- prepare


def prepare(m: dict) -> dict:
    """JSON-shaped matrix (or an already prepared one) -> numpy arrays sorted by season."""
    if "_C" in m:
        return m
    cols = m["columns"]

    def arr(name, dtype=float):
        x = cols.get(name)
        if x is None:
            return np.full(len(cols["season"]), np.nan)
        return np.array([np.nan if v is None else v for v in x], dtype=dtype)

    season = np.asarray(cols["season"], dtype=int)
    groups = list(m["groups"])
    C = np.column_stack([np.asarray(m["c"][g], dtype=float) for g in groups])
    n = len(season)
    warm = (
        np.asarray(cols["warmup"], dtype=int) if "warmup" in cols else np.zeros(n, dtype=int)
    ).astype(bool)
    first = int(m.get("first_scored", season[~warm].min() if (~warm).any() else season.min()))
    out = {
        "_C": C,
        "groups": groups,
        "inactive": list(m.get("inactive", [])),
        "season": season,
        "warmup": warm,
        "y": arr("y"),
        "mkt": arr("mkt_p"),
        "result": arr("result"),
        "spread": arr("spread"),
        "home_ml": arr("home_ml"),
        "away_ml": arr("away_ml"),
        "game_id": np.asarray(cols.get("game_id", [str(i) for i in range(n)]), dtype=object),
        "week": arr("week"),
        "first_scored": first,
        "personas": m.get("personas", {}),
        "student_fitted": m.get("student_fitted", {}),
    }
    for k in ("spread_bucket", "close", "blowout", "div_game", "primetime", "dome", "month",
              "home_fav"):  # fmt: skip
        out[k] = arr(k)
    # sorted by season already (build sorts); starts[S] = first row index of season S
    order = np.argsort(season, kind="stable")
    if not np.array_equal(order, np.arange(n)):
        for k, v in list(out.items()):
            if isinstance(v, np.ndarray) and v.shape and v.shape[0] == n:
                out[k] = v[order]
    return out


def load_matrix(path: Path) -> dict:
    return prepare(json.loads(Path(path).read_text()))


# --------------------------------------------------------------------------------------- estimators


def _platt(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """p = σ(a·x + c), maximum likelihood by damped Newton, slope constrained to a >= 0."""
    if len(y) == 0:
        return 1.0, 0.0
    ybar = float(np.clip(y.mean(), 1e-6, 1 - 1e-6))
    c0 = float(np.log(ybar / (1 - ybar)))
    if float(np.std(x)) < 1e-12:
        return 0.0, c0
    t = np.array([1.0, 0.0])

    def nll(t):
        eta = t[0] * x + t[1]
        return float(np.sum(np.logaddexp(0.0, eta) - y * eta))

    cur = nll(t)
    for _ in range(30):
        eta = t[0] * x + t[1]
        p = 1.0 / (1.0 + np.exp(-eta))
        r = p - y
        g = np.array([r @ x, r.sum()])
        w = p * (1 - p)
        H = np.array([[(w * x) @ x, (w * x).sum()], [(w * x).sum(), w.sum()]])
        H += np.eye(2) * 1e-8
        step = np.linalg.solve(H, g)
        s = 1.0
        while s > 1e-4:
            cand = t - s * step
            val = nll(cand)
            if val <= cur + 1e-12:
                break
            s /= 2
        else:
            break
        done = abs(cur - val) < 1e-10
        t, cur = cand, val
        if done:
            break
    if t[0] < 0:
        return 0.0, c0
    return float(t[0]), float(t[1])


def walk_forward_platt(
    logit: np.ndarray, y: np.ndarray, season: np.ndarray, scored: list[int]
) -> tuple[np.ndarray, dict[int, tuple[float, float, bool]]]:
    """Calibrated logit per row. Season S uses only rows with season < S; if there are none the
    season calibrates on itself (flag True)."""
    out = logit.copy()
    params: dict[int, tuple[float, float, bool]] = {}
    for s in scored:
        mask = season == s
        prior = season < s
        in_sample = not prior.any()
        win = mask if in_sample else prior
        a, c = _platt(logit[win], y[win])
        out[mask] = a * logit[mask] + c
        params[s] = (a, c, in_sample)
    return out, params


def _raw_logit(P: dict, weights: dict) -> np.ndarray:
    """weights: {group: W} or {season: {group: W}} (per-season, e.g. the Student's refits)."""
    groups = P["groups"]
    if weights and all(isinstance(k, int | np.integer) or str(k).isdigit() for k in weights):
        out = np.zeros(len(P["season"]))
        for s, w in weights.items():
            wv = np.array([w.get(g, 0.0) for g in groups], dtype=float)
            mask = P["season"] == int(s)
            out[mask] = P["_C"][mask] @ wv
        # seasons without an entry (warmup) reuse the first available weights
        missing = ~np.isin(P["season"], [int(s) for s in weights])
        if missing.any():
            w = weights[min(weights, key=int)]
            out[missing] = P["_C"][missing] @ np.array([w.get(g, 0.0) for g in groups])
        return out
    wv = np.array([weights.get(g, 0.0) for g in groups], dtype=float)
    return P["_C"] @ wv


def cap_market(signed: dict[str, float]) -> tuple[dict[str, float], bool]:
    """Enforce ADR 0013: the Market behavior group gets at most MARKET_GROUP_CAP of the budget
    (sum of |weights|). Returns (weights with market scaled down if needed, whether it was)."""
    m = signed.get("market", 0.0)
    rest = sum(abs(v) for g, v in signed.items() if g != "market")
    limit = MARKET_GROUP_CAP / (1 - MARKET_GROUP_CAP) * rest
    if abs(m) <= limit + 1e-12:
        return dict(signed), False
    return signed | {"market": float(np.sign(m) * limit)}, True


def season_predictions(weights: dict, matrix: dict, season: int) -> dict:
    """Per-game calibrated p(home) for one season, exactly as `evaluate` computes it (Platt fitted
    on earlier seasons only). Returns game_id, p, calib_a, calib_c for that season's rows."""
    P = prepare(matrix)
    keep = P["season"] <= season
    raw = _raw_logit(P, weights)
    lg, params = walk_forward_platt(raw[keep], P["y"][keep], P["season"][keep], [season])
    idx = np.where(keep)[0]
    sel = P["season"][idx] == season
    a, c, _ = params[season]
    return {
        "game_id": P["game_id"][idx][sel],
        "p": 1.0 / (1.0 + np.exp(-lg[sel])),
        "calib_a": a,
        "calib_c": c,
    }


def _ll(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def _boot_ratio(num: np.ndarray, den: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    k = len(num)
    if k < 2:
        return float("nan"), float("nan")
    idx = rng.integers(0, k, size=(BOOTSTRAP, k))
    with np.errstate(invalid="ignore", divide="ignore"):
        b = num[idx].sum(1) / den[idx].sum(1)
    return float(np.nanquantile(b, 0.05)), float(np.nanquantile(b, 0.95))


# --------------------------------------------------------------------------------------- evaluate


def _bucket_table(label: str, codes: np.ndarray, names: dict, mask, ll, mll, has) -> list[dict]:
    rows = []
    for code, name in names.items():
        sel = mask & (codes == code)
        n = int(sel.sum())
        if not n:
            continue
        both = sel & has
        d = (ll - mll)[both]
        rows.append(
            {
                "group": label,
                "bucket": name,
                "n": n,
                "log_loss": float(ll[sel].mean()),
                "market_log_loss": float(mll[both].mean()) if both.any() else None,
                "delta": float(d.mean()) if len(d) else None,
                "delta_se": float(d.std(ddof=1) / np.sqrt(len(d))) if len(d) > 1 else None,
            }
        )
    return rows


def _top_games(
    P, rows: np.ndarray, p: np.ndarray, ll, mll, a: float, W: np.ndarray, worse: bool
) -> list[dict]:
    """The 3 games in `rows` that moved Δ the most, and the group that pushed hardest in each."""
    d = np.where(np.isnan(mll[rows]), 0.0, ll[rows] - mll[rows])
    order = np.argsort(-d if worse else d)[:3]
    out = []
    for o in order:
        i = rows[o]
        contrib = a * W * P["_C"][i]
        j = int(np.argmax(np.abs(contrib)))
        out.append(
            {
                "game_id": str(P["game_id"][i]),
                "week": int(P["week"][i]) if not np.isnan(P["week"][i]) else None,
                "home_won": int(P["y"][i]),
                "p": float(p[i]),
                "market_p": None if np.isnan(P["mkt"][i]) else float(P["mkt"][i]),
                "delta": float(d[o]),
                "group": P["groups"][j],
                "group_logit": float(contrib[j]),
            }
        )
    return out


def evaluate(weights: dict, matrix: dict, max_season: int | None = None, seed: int = 0) -> dict:
    """Score group weights over the matrix. See the module docstring for the method.

    weights    {group: W} or {season: {group: W}}; groups the matrix lacks are ignored
    max_season exclude later seasons from everything (the "hide the last 3 seasons" toggle)"""
    P = prepare(matrix)
    season, y = P["season"], P["y"]
    scored = sorted({int(s) for s in season[~P["warmup"]] if max_season is None or s <= max_season})
    use = ~P["warmup"] & np.isin(season, scored)
    keep = np.isin(season, scored) | (P["warmup"] & (season < (scored[0] if scored else 0)))
    raw = _raw_logit(P, weights)
    lg, params = walk_forward_platt(raw[keep], y[keep], season[keep], scored)
    logit = np.zeros_like(raw)
    logit[keep] = lg
    p = 1.0 / (1.0 + np.exp(-logit))
    ll = _ll(p, y)
    mkt = P["mkt"]
    has = ~np.isnan(mkt)
    mll = np.where(has, _ll(np.where(has, mkt, 0.5), y), np.nan)
    rng = np.random.default_rng(seed)

    n_s, ll_s, d_s, np_s = [], [], [], []
    seasons_out = []
    for s in scored:
        m = season == s
        mp = m & has
        n_s.append(m.sum())
        ll_s.append(ll[m].sum())
        d_s.append((ll - mll)[mp].sum())
        np_s.append(mp.sum())
        a, c, ins = params[s]
        seasons_out.append(
            {
                "season": s,
                "n": int(m.sum()),
                "log_loss": float(ll[m].mean()),
                "market_log_loss": float(mll[mp].mean()) if mp.any() else None,
                "delta": float((ll - mll)[mp].mean()) if mp.any() else None,
                "calib_a": a,
                "calib_c": c,
                "in_sample_calibration": ins,
            }
        )
    n_s, ll_s, d_s, np_s = (np.array(x, dtype=float) for x in (n_s, ll_s, d_s, np_s))
    lo, hi = _boot_ratio(ll_s, n_s, rng)
    dlo, dhi = _boot_ratio(d_s, np_s, rng)
    overall = {
        "n": int(n_s.sum()),
        "seasons": len(scored),
        "log_loss": float(ll_s.sum() / n_s.sum()) if n_s.sum() else None,
        "ll_lo": lo,
        "ll_hi": hi,
        "market_log_loss": float(mll[use & has].mean()) if (use & has).any() else None,
        "delta": float(d_s.sum() / np_s.sum()) if np_s.sum() else None,
        "d_lo": dlo,
        "d_hi": dhi,
    }

    # best and worst seasons, with the games that moved them
    W_vec = np.array([_season_weights(weights, s, P["groups"]) for s in scored])
    ranked = sorted((r for r in seasons_out if r["delta"] is not None), key=lambda r: r["delta"])
    for r in seasons_out:
        r["key_games"] = None
    best, worst = ranked[:3], ranked[-3:][::-1]
    for group, worse in ((best, False), (worst, True)):
        for r in group:
            k = scored.index(r["season"])
            rows = np.where(season == r["season"])[0]
            r["key_games"] = _top_games(P, rows, p, ll, mll, r["calib_a"], W_vec[k], worse)

    # aging: slope of delta against season
    ds = [(r["season"], r["delta"]) for r in seasons_out if r["delta"] is not None]
    aging = _aging(ds, rng)

    ctx = np.where(use)[0]
    m_use = use
    by_ctx = (
        _bucket_table("Spread size", P["spread_bucket"], dict(enumerate(SPREAD_LABELS)), m_use, ll, mll, has)
        + _bucket_table("Result (known after the fact)", P["close"], {1: "Close (within 3)"}, m_use, ll, mll, has)
        + _bucket_table("Result (known after the fact)", P["blowout"], {1: "Blowout (14+)"}, m_use, ll, mll, has)
        + _bucket_table("Division", P["div_game"], {1: "Division game", 0: "Non-division"}, m_use, ll, mll, has)
        + _bucket_table("Time slot", P["primetime"], {1: "Primetime", 0: "Day games"}, m_use, ll, mll, has)
        + _bucket_table("Roof", P["dome"], {1: "Dome / closed roof", 0: "Open air"}, m_use, ll, mll, has)
        + _bucket_table("Month", P["month"], MONTH_LABELS, m_use, ll, mll, has)
        + _bucket_table("Home side", P["home_fav"], FAV_LABELS, m_use, ll, mll, has)
    )  # fmt: skip
    del ctx

    return {
        "overall": overall,
        "seasons": seasons_out,
        "best": best,
        "worst": worst,
        "aging": aging,
        "by_context": by_ctx,
        "divergence": _divergence(p, mkt, y, ll, mll, use & has),
        "bets": _bets(p, mkt, y, P, use & has),
        "inactive": P["inactive"],
        "scored_seasons": scored,
        "first_season_in_sample": bool(params[scored[0]][2]) if scored else False,
    }


def _season_weights(weights: dict, s: int, groups: list[str]) -> np.ndarray:
    w = weights
    if w and all(isinstance(k, int | np.integer) or str(k).isdigit() for k in w):
        w = w.get(s) or w.get(str(s)) or w[min(w, key=int)]
    return np.array([w.get(g, 0.0) for g in groups], dtype=float)


def _aging(ds: list[tuple[int, float]], rng) -> dict:
    if len(ds) < 4:
        return {"slope": None, "slope_lo": None, "slope_hi": None, "sentence": "Too few seasons."}
    x = np.array([s for s, _ in ds], dtype=float)
    d = np.array([v for _, v in ds], dtype=float)

    def slope(x, d):
        xc = x - x.mean(axis=-1, keepdims=True)
        den = (xc**2).sum(-1)
        with np.errstate(invalid="ignore", divide="ignore"):
            return (xc * (d - d.mean(axis=-1, keepdims=True))).sum(-1) / den

    sl = float(slope(x, d))
    idx = rng.integers(0, len(x), size=(BOOTSTRAP, len(x)))
    b = slope(x[idx], d[idx])
    lo, hi = float(np.nanquantile(b, 0.05)), float(np.nanquantile(b, 0.95))
    dec = sl * 10
    if lo > 0:
        s = (f"Your weights have been fading relative to the market: Δ log loss is rising "
             f"{dec:+.3f} per decade (90% CI {lo * 10:+.3f} to {hi * 10:+.3f}).")  # fmt: skip
    elif hi < 0:
        s = (f"Your weights have been improving relative to the market: Δ log loss is falling "
             f"{dec:+.3f} per decade (90% CI {lo * 10:+.3f} to {hi * 10:+.3f}).")  # fmt: skip
    else:
        s = (f"No clear trend against the market: {dec:+.3f} per decade "
             f"(90% CI {lo * 10:+.3f} to {hi * 10:+.3f} includes zero).")  # fmt: skip
    return {"slope": sl, "slope_lo": lo, "slope_hi": hi, "per_decade": dec, "sentence": s}


def _divergence(p, mkt, y, ll, mll, sel) -> list[dict]:
    gap = np.abs(p - mkt)
    lean_home = p > mkt
    won = np.where(lean_home, y, 1 - y)
    exp = np.where(lean_home, mkt, 1 - mkt)
    edges = list(DIVERGENCE_BUCKETS) + [np.inf]
    out = []
    for i, name in enumerate(DIV_LABELS):
        s = sel & (gap >= edges[i]) & (gap < edges[i + 1])
        n = int(s.sum())
        out.append(
            {
                "bucket": name,
                "n": n,
                "lean_win_rate": float(won[s].mean()) if n else None,
                "market_expected_rate": float(exp[s].mean()) if n else None,
                "log_loss": float(ll[s].mean()) if n else None,
                "market_log_loss": float(mll[s].mean()) if n else None,
            }
        )
    return out


def _bets(p, mkt, y, P, sel) -> dict:
    """Flat 1-unit moneyline on the side the model likes more than the market, edge > 5 points."""
    edge = p - mkt
    home = edge > 0
    price = np.where(home, P["home_ml"], P["away_ml"])
    s = sel & (np.abs(edge) > EDGE_THRESHOLD) & ~np.isnan(price)
    won = np.where(home, y, 1 - y).astype(bool)
    payout = np.where(price > 0, price / 100.0, 100.0 / np.abs(np.where(price == 0, 1, price)))
    profit = np.where(won, payout, -1.0)
    n = int(s.sum())
    per_season = {}
    for sea in np.unique(P["season"][s]):
        per_season[int(sea)] = float(profit[s & (P["season"] == sea)].sum())
    return {
        "n": n,
        "wins": int(won[s].sum()),
        "losses": n - int(won[s].sum()),
        "units": float(profit[s].sum()),
        "roi": float(profit[s].mean()) if n else None,
        "by_season": per_season,
    }


# ---------------------------------------------------------------------------------------- fit_toward


def fit_toward(weights: dict, matrix: dict, lam: float = 1250.0, max_season: int | None = None):
    """Ridge on the composites over all scored seasons, shrunk toward the user's weights.

    The user's weights are first put on a logit scale (global Platt over the same games) so that
    "shrink toward you" is meaningful against the data's curvature; λ ≈ 0.22·n per composite
    (≈ 1250 here) means trust you and the data about equally. Returns the fitted group weights, the
    user's weights on the same scale, and both as signed shares of a 100-point budget."""
    P = prepare(matrix)
    use = ~P["warmup"] & (P["season"] <= (max_season or 10**9))
    groups = [g for g in P["groups"] if g not in P["inactive"]]
    cols = [P["groups"].index(g) for g in groups]
    z, y = P["_C"][use][:, cols], P["y"][use]
    w_user = np.array([weights.get(g, 0.0) for g in groups], dtype=float)
    a, c = _platt(z @ w_user, y)
    w0 = a * w_user
    b, w = fit.fit_ridge(z, y, w0, lam, b0=c)

    def share(v):
        tot = float(np.abs(v).sum())
        return {g: (100.0 * float(x) / tot if tot > 0 else 0.0) for g, x in zip(groups, v)}

    return {
        "weights": {g: float(x) for g, x in zip(groups, w)},
        "user_scaled": {g: float(x) for g, x in zip(groups, w0)},
        "intercept": b,
        "lam": lam,
        "shares": share(w),
        "user_shares": share(w0),
    }


# ------------------------------------------------------------------------------------ query string


def encode_weights(signed: dict[str, float]) -> str:
    """{group: signed points} -> 'quality:30,form:-10' (zeros dropped, matrix group order)."""
    parts = [f"{g}:{signed[g]:g}" for g in GROUP_IDS if signed.get(g)]
    return ",".join(parts)


def decode_weights(s: str | None) -> dict[str, float]:
    """Inverse of encode_weights; unknown groups and malformed pieces are ignored."""
    out: dict[str, float] = {}
    for part in (s or "").split(","):
        g, _, v = part.partition(":")
        if g in GROUPS:
            try:
                x = float(v)
            except ValueError:
                continue
            if np.isfinite(x):
                out[g] = max(-100.0, min(100.0, x))
    return out
