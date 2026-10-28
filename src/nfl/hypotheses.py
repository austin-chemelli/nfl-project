"""Hypotheses: does each feature predict winning, holding the other football features fixed?

One ridge logistic regression on every non-market, non-narrative feature (standardized, nulls = 0),
shrunk toward zero with the global fit's λ. Uncertainty comes from a bootstrap over whole seasons
(games within a season share weather, injuries and league trends, so seasons are the unit).
Each feature also gets its marginal fit (alone) so the page can contrast "on its own" with
"after the others". Writes marts/hypotheses.parquet and marts/site/hypotheses.json (M5.5).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import polars as pl
from scipy.special import expit

from nfl.approaches import fit
from nfl.approaches.engine import Scaler
from nfl.approaches.ensemble import EXCLUDED_FAMILIES, GLOBAL_ID
from nfl.approaches.schema import load_all
from nfl.config import Paths
from nfl.features import store
from nfl.features.groups import FEATURE_GROUP, GROUPS, MEMBERS

SCHEMA_VERSION = "2"
MATRIX = ("diy", "matrix.parquet")  # per-game group composites c_<group> (DIY approach)
FIRST_EVAL = 2005  # first season scored walk-forward (needs 3 seasons of history)
MIN_TRAIN = 300  # non-null training games before a one-feature model is trusted
MIN_COVER = 0.5  # share of the scored season's games that must have a value
MIN_EDGE_N = 50  # edge games a season needs to be named "strongest"/"weakest"
TINY_LAMBDA = 1e-3
SEASONS = (2002, 2025)
BOOTSTRAPS = 200
SEED = 20261027
DEFAULT_LAMBDA = 1000.0
MIN_EFFECT = 0.03  # logit per 1 SD: below this, even a clear interval is "weak"
LEAN_W = 0.15  # a persona "leans on" a group at |W| >= this
VERDICTS = ("matters", "weak", "no evidence")


def verdict(coef: float, lo: float, hi: float, se: float) -> str:
    excludes = lo > 0 or hi < 0
    if excludes and abs(coef) >= MIN_EFFECT:
        return "matters"
    if excludes or (se > 0 and abs(coef) > se):
        return "weak"
    return "no evidence"


def sentence(label: str, coef: float, lo: float, hi: float, sd: float) -> str:
    dp = 100 * (float(expit(coef)) - 0.5)
    excl = lo > 0 or hi < 0
    tail = "the 90% interval excludes zero" if excl else "the interval includes zero"
    return (
        f"A +1 SD edge in {label} (SD ≈ {sd:.3g}) is worth about {dp:+.1f} points of "
        f"win probability for the home side at a pick'em; {tail}."
    )


def pp_of(logit: float) -> float:
    """Win-probability points at a pick'em for a logit effect."""
    return 100 * (float(expit(logit)) - 0.5)


def fit_one(z: np.ndarray, y: np.ndarray, lam: float = TINY_LAMBDA) -> tuple[float, float]:
    """Logistic regression y ~ b + w·z by Newton's method (tiny ridge on w). Returns (b, w)."""
    ybar = float(np.clip(y.mean(), 1e-6, 1 - 1e-6))
    b, w = float(np.log(ybar / (1 - ybar))), 0.0
    for _ in range(30):
        p = expit(b + w * z)
        r = p - y
        v = p * (1 - p)
        g = np.array([r.sum(), z @ r + lam * w])
        h = np.array([[v.sum(), z @ v], [z @ v, (z * z) @ v + lam]])
        step = np.linalg.solve(h + 1e-12 * np.eye(2), g)
        b, w = b - step[0], w - step[1]
        if np.abs(step).max() < 1e-9:
            break
    return b, w


def _season_row(season, x, y, p_model, p_base, direction) -> dict:
    """Scores for one scored season: log loss vs baseline and the edge team's win rate."""
    ll_m, ll_b = fit.log_loss(p_model, y), fit.log_loss(p_base, y)
    ok = ~np.isnan(x) & (x != 0)
    n_edge = int(ok.sum())
    wins = int((((direction * x[ok]) > 0) == (y[ok] == 1)).sum())
    return {
        "season": int(season),
        "n_games": len(y),
        "n_edge": n_edge,
        "edge_wins": wins,
        "edge_win_rate": wins / n_edge if n_edge else None,
        "improvement": 100 * (ll_b - ll_m),
        "skill_pct": 100 * (1 - ll_m / ll_b),
        "_ll_m": ll_m,
        "_ll_b": ll_b,
    }


def by_season_one(
    x: np.ndarray, y: np.ndarray, seasons: np.ndarray, sign: int, game_level: bool = False
) -> dict:
    """Walk-forward: a one-feature logistic model trained on all earlier seasons, scored on each.

    The feature is standardized on the training window (nulls = 0). Baseline = the home win
    rate of the same training window. Returns {"series": [...], "pooled": {...}}."""
    x = np.asarray(x, dtype=float)
    rows = []
    for s in sorted(int(v) for v in np.unique(seasons) if v >= FIRST_EVAL):
        tr, te = seasons < s, seasons == s
        xt = x[tr]
        nn = ~np.isnan(xt)
        if nn.sum() < MIN_TRAIN or (~np.isnan(x[te])).mean() < MIN_COVER:
            continue
        mu, sd = float(xt[nn].mean()), float(xt[nn].std())
        sd = sd if sd > 1e-12 else 1.0
        ztr = np.where(nn, (xt - mu) / sd, 0.0)
        xe = x[te]
        zte = np.where(np.isnan(xe), 0.0, (xe - mu) / sd)
        b, w = fit_one(ztr, y[tr])
        p_base = np.full(int(te.sum()), float(np.clip(y[tr].mean(), 1e-6, 1 - 1e-6)))
        direction = sign if sign else (1 if w >= 0 else -1)
        view = np.where(np.isnan(xe), np.nan, zte if game_level else xe)
        rows.append(_season_row(s, view, y[te], expit(b + w * zte), p_base, direction))
    return {
        "series": [{k: v for k, v in r.items() if k[0] != "_"} for r in rows],
        "pooled": _pool(rows),
    }


def _pool(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    n = sum(r["n_games"] for r in rows)
    ll_m = sum(r["_ll_m"] * r["n_games"] for r in rows) / n
    ll_b = sum(r["_ll_b"] * r["n_games"] for r in rows) / n
    n_edge = sum(r["n_edge"] for r in rows)
    wins = sum(r["edge_wins"] for r in rows)
    rated = [r for r in rows if r["n_edge"] >= MIN_EDGE_N and r["edge_win_rate"] is not None]
    best = max(rated, key=lambda r: r["edge_win_rate"], default=None)
    worst = min(rated, key=lambda r: r["edge_win_rate"], default=None)
    return {
        "n_games": n,
        "n_edge": n_edge,
        "edge_win_rate": wins / n_edge if n_edge else None,
        "improvement": 100 * (ll_b - ll_m),
        "skill_pct": 100 * (1 - ll_m / ll_b),
        "first_season": rows[0]["season"],
        "last_season": rows[-1]["season"],
        "best_season": best["season"] if best else None,
        "worst_season": worst["season"] if worst else None,
    }


def season_sentence(label: str, pooled: dict | None, kind: str = "feature") -> str:
    if not pooled or pooled["edge_win_rate"] is None:
        return f"{label}: not enough history to score season by season."
    on = "on its own" if kind == "feature" else "as a group on its own"
    s = (
        f"{label} {on}: the team with the edge won {100 * pooled['edge_win_rate']:.0f}% of "
        f"games on average ({pooled['first_season']}-{pooled['last_season']})"
    )
    if pooled["best_season"] and pooled["worst_season"] != pooled["best_season"]:
        s += f"; strongest in {pooled['best_season']}, weakest in {pooled['worst_season']}"
    gain = pooled["improvement"]
    s += (
        f". Against always picking the home team at its historical rate it "
        f"{'improved' if gain >= 0 else 'worsened'} log loss by {abs(gain):.2f} points (x100)."
    )
    return s


def build_by_season(paths: Paths, data: pl.DataFrame, feats: list[str]) -> dict:
    items: dict[str, dict] = {}

    def add(key, kind, label, desc, unit, gid, sign, x, y, seasons, game_level):
        r = by_season_one(x, y, seasons, sign, game_level)
        if not r["series"]:
            return
        items[key] = {
            "kind": kind, "label": label, "description": desc, "unit": unit, "group": gid,
            "pooled": r["pooled"], "series": r["series"],
            "sentence": season_sentence(label, r["pooled"], kind),
        }  # fmt: skip

    y, seasons = data["y"].to_numpy(), data["season"].to_numpy()
    for f in feats:
        m = MEMBERS.get(f)
        gid = FEATURE_GROUP.get(f)
        gl = bool(gid and GROUPS[gid].game_level)
        add(f, "feature", m.label if m else label_of(f), m.description if m else "",
            m.unit if m else None, gid, m.sign if m else 0,
            data[f].cast(pl.Float64).to_numpy(), y, seasons, gl)  # fmt: skip
    mpath = paths.marts.joinpath(*MATRIX)
    if mpath.exists():
        mx = pl.read_parquet(mpath).sort("season", "week", "game_id")
        my, ms = mx["y"].to_numpy(), mx["season"].to_numpy()
        for gid, g in GROUPS.items():
            col = f"c_{gid}"
            if col not in mx.columns or all(
                f.split(".", 1)[0] in EXCLUDED_FAMILIES for f in g.features
            ):
                continue
            add(f"group:{gid}", "group", g.name, g.description, None, gid, 1,
                mx[col].cast(pl.Float64).to_numpy(), my, ms, False)  # fmt: skip
    return {"first_scored": FIRST_EVAL, "items": items}


def label_of(feature: str) -> str:
    return feature.split(".", 1)[1].replace("_", " ")


def analyze(
    z: np.ndarray,
    y: np.ndarray,
    seasons: np.ndarray,
    lam: float,
    n_boot: int = BOOTSTRAPS,
    seed: int = SEED,
) -> dict[str, np.ndarray]:
    """Joint ridge, season bootstrap and per-feature marginal fits on standardized z."""
    k = z.shape[1]
    zero = np.zeros(k)
    b0, w = fit.fit_ridge(z, y, zero, lam)
    uniq = np.unique(seasons)
    idx = {s: np.flatnonzero(seasons == s) for s in uniq}
    rng = np.random.default_rng(seed)
    boots = np.empty((n_boot, k))
    for i in range(n_boot):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        rows = np.concatenate([idx[s] for s in pick])
        boots[i] = fit.fit_ridge(z[rows], y[rows], zero, lam, b0=b0)[1]
    marg = np.array([fit.fit_ridge(z[:, [j]], y, np.zeros(1), lam)[1][0] for j in range(k)])
    return {
        "coef": w,
        "lo": np.percentile(boots, 5, axis=0),
        "hi": np.percentile(boots, 95, axis=0),
        "se": boots.std(axis=0, ddof=1),
        "marginal": marg,
    }


def chosen_lambda(paths: Paths) -> float:
    f = paths.marts / "fits" / f"{GLOBAL_ID}.fitted" / "2025.json"
    try:
        return float(json.loads(f.read_text())["meta"]["lambda"])
    except OSError, KeyError, ValueError:
        return DEFAULT_LAMBDA


def _personas() -> tuple[dict, dict]:
    """(per-group list of {id, w} with |w| >= LEAN_W, per-group mean |W| over all personas)."""
    approaches = [a for a in load_all().values() if a.groups]
    lean: dict[str, list[dict]] = {g: [] for g in GROUPS}
    belief: dict[str, float] = {}
    for g in GROUPS:
        ws = [a.groups[g].w if g in a.groups else 0.0 for a in approaches]
        belief[g] = float(np.mean(np.abs(ws))) if ws else 0.0
        for a, wv in zip(approaches, ws, strict=True):
            if abs(wv) >= LEAN_W:
                lean[g].append({"id": a.id, "name": a.name, "w": round(wv, 3)})
    return lean, belief


def build(paths: Paths, n_boot: int = BOOTSTRAPS) -> dict:
    known = set(store.read_features(paths).get_column("feature").unique().to_list())
    feats = sorted(f for f in known if f.split(".", 1)[0] not in EXCLUDED_FAMILIES)
    data = fit.load_dataset(paths, feats, SEASONS)
    feats = [f for f in feats if f in data.columns and data[f].is_not_null().any()]
    lam = chosen_lambda(paths)
    scaler = Scaler.fit(data, feats)
    z, y = scaler.transform(data), data["y"].to_numpy()
    res = analyze(z, y, data["season"].to_numpy(), lam, n_boot)
    lean, belief = _personas()

    rows = []
    for j, f in enumerate(feats):
        col = data[f]
        nn = data.filter(col.is_not_null())
        coef, lo, hi, se = (float(res[k][j]) for k in ("coef", "lo", "hi", "se"))
        sd = float(scaler.sd[j])
        gid = FEATURE_GROUP.get(f)
        mem = MEMBERS.get(f)
        lab = mem.label if mem else label_of(f)
        share = float(col.is_not_null().mean())
        first = int(nn["season"].min()) if nn.height else None
        rows.append(
            {
                "feature": f,
                "label": lab,
                "group": gid,
                "coef": coef,
                "lo": lo,
                "hi": hi,
                "se": se,
                "marginal": float(res["marginal"][j]),
                "verdict": verdict(coef, lo, hi, se),
                "description": mem.description if mem else "",
                "unit": mem.unit if mem else None,
                "effect_pp": pp_of(coef),
                "effect_lo_pp": pp_of(lo),
                "effect_hi_pp": pp_of(hi),
                "marginal_pp": pp_of(float(res["marginal"][j])),
                "delta_pts": pp_of(coef),
                "sd": sd,
                "sentence": sentence(lab, coef, lo, hi, sd),
                "first_season": first,
                "share_nonnull": share,
                "coverage": f"{first}+, {100 * share:.0f}% of games have a value"
                if first
                else "no data",
                "personas": lean.get(gid, []) if gid else [],
                "group_belief": belief.get(gid, 0.0) if gid else 0.0,
            }
        )
    rows.sort(key=lambda r: -abs(r["coef"]))

    out = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "trained_seasons": list(SEASONS),
        "lambda": lam,
        "n_games": data.height,
        "n_bootstrap": n_boot,
        "features": rows,
        "by_season": build_by_season(paths, data, feats),
    }
    paths.site.mkdir(parents=True, exist_ok=True)
    (paths.site / "hypotheses.json").write_text(json.dumps(out, indent=1))
    pl.DataFrame(rows, infer_schema_length=None).write_parquet(paths.marts / "hypotheses.parquet")
    counts = {v: sum(r["verdict"] == v for r in rows) for v in VERDICTS}
    return {"n_features": len(rows), "n_games": data.height, "lambda": lam, "verdicts": counts}
