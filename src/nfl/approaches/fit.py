"""Fitting: Platt calibration, shrink-to-persona ridge, walk-forward (architecture §3.4, ADR 0004).

Objective for the fitted flavor (sum over games, not mean):

    Σ [log(1 + e^η) − y·η] + λ‖w − w_persona‖²,   η = b + Z·w,   intercept b unpenalized

Z is standardized, so one feature's data curvature is ≈ 0.22·n (≈ 700 for 3,000 games): λ of that
order means "trust the persona as much as the data". The grid lives in each approach YAML.

Grouped approaches (ADR 0012): each group's composite c_g = Σ v_gf z_f uses inner weights v fitted
per group on the training window (ridge on that group's members only, λ = INNER_LAMBDA, shrunk
toward each member's declared sign × INNER_PRIOR so near-duplicate members don't flip signs against
each other), then rescaled so c_g has unit variance. Members with too little history (narrative, live-only) get
their declared sign at the group's mean fitted magnitude. Overrides in the YAML replace v for a
group (then rescaled). The persona flavor is W from the YAML; the fitted flavor is the ridge above on
the composites, shrunk toward W. Both are stored as flat effective weights w_f = W_g · v_gf, so
scoring, contributions and artifacts are unchanged; v and W go into the artifact's meta.

Walk-forward: a model scored on season S is trained on seasons [train_from, S−1] only. λ is chosen
by mean log loss over the validation seasons (each fit on earlier seasons only), then used for
every scored season. Artifacts: marts/fits/<model_id>/<trained_through>.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl
from scipy.optimize import minimize
from scipy.special import expit

from nfl.approaches.engine import NEUTRAL, Model, Scaler, gate, persona_model, venue_gate
from nfl.approaches.schema import Approach
from nfl.config import FIRST_SCORED_SEASON, Paths
from nfl.features import store
from nfl.features.groups import GROUPS, LIVE_PRIORS, REGISTRY_VERSION

VAL_SEASONS = (2022, 2023, 2024)
INNER_LAMBDA = (
    3000.0  # chosen 2026-10-27 on 2022-24 validation (100: 0.6280, 3000: 0.6231, equal: 0.6265)
)
INNER_PRIOR = 0.05  # inner weights shrink toward sign * INNER_PRIOR, not toward 0
# Public line (ADR 0004 amendment): ridge toward the persona with λ = PUBLIC_RIDGE × (data curvature
# per composite ≈ 0.22 n). Chosen 2026-10-27 so a persona moves about a quarter of the way toward what
# history supports (Traditionalist: 3.0 -> 10%, 1.0 -> 25%, 0.5 -> 39%, 0.25 -> 55%): biases stay
# visible, history still nudges them.
PUBLIC_RIDGE = 1.0
MIN_HISTORY = 200  # non-null training games before a member's inner weight is fitted
# Season decay for every fit inside fit_flavors: a game s seasons before the newest training season
# counts 0.5 ** (s / DECAY_HALF_LIFE). None = every season counts the same (the wave 2 behavior).
DECAY_HALF_LIFE: float | None = None
SYNTHETIC_LOCK = pl.duration(hours=1)


# ------------------------------------------------------------------------------------------ data


def load_dataset(paths: Paths, features: list[str], seasons: tuple[int, int]) -> pl.DataFrame:
    """One row per completed, non-tied game: game_id, season, week, y (home win), feature columns.

    Features are taken as of the synthetic lock (kickoff − 1h), the same rule live locks use."""
    games = store.games_frame(paths).filter(
        pl.col("season").is_between(*seasons)
        & pl.col("result").is_not_null()
        & (pl.col("result") != 0)
    )
    locks = games.select("game_id", (pl.col("kickoff_utc") - SYNTHETIC_LOCK).alias("lock_ts"))
    features = list(features) + ([NEUTRAL] if NEUTRAL not in features else [])
    fams = sorted({f.split(".", 1)[0] for f in features})
    feats = store.read_features(paths, seasons=seasons, families=fams)
    vec = store.game_vectors(store.as_of(feats, locks))
    wide = store.to_wide(vec, features)
    return (
        games.select(
            "game_id", "season", "week", (pl.col("result") > 0).cast(pl.Float64).alias("y")
        )
        .join(wide, on="game_id", how="left")
        .sort("season", "week", "game_id")
    )


# ------------------------------------------------------------------------------------- estimators


def _nll(eta: np.ndarray, y: np.ndarray, sw: np.ndarray | None = None) -> float:
    ll = np.logaddexp(0.0, eta) - y * eta
    return float(np.sum(ll if sw is None else sw * ll))


def season_weights(seasons: np.ndarray, half_life: float | None) -> np.ndarray | None:
    """Per-row fitting weights from DECAY_HALF_LIFE (None: unweighted), mean 1."""
    if half_life is None:
        return None
    w = 0.5 ** ((seasons.max() - seasons) / half_life)
    return w / w.mean()


def fit_platt(
    logit: np.ndarray, y: np.ndarray, sw: np.ndarray | None = None, g: np.ndarray | None = None
) -> tuple[float, float]:
    """p = σ(a·logit + c·g), maximum likelihood (g: the neutral-site gate, 1 = home field counts)."""
    g = np.ones(len(y)) if g is None else g

    def f(t):
        eta = t[0] * logit + t[1] * g
        r = expit(eta) - y
        if sw is not None:
            r = sw * r
        return _nll(eta, y, sw), np.array([r @ logit, r @ g])

    res = minimize(f, np.array([1.0, 0.0]), jac=True, method="L-BFGS-B")
    return float(res.x[0]), float(res.x[1])


SHIFT_SEASONS = {"shift_10": 10}  # calibration value -> training seasons the offset is fitted on


def fit_shift(
    logit: np.ndarray, y: np.ndarray, g: np.ndarray | None = None, sw: np.ndarray | None = None
) -> float:
    """The one offset c with p = σ(logit + c·g), maximum likelihood (ADR 0026, M23.1)."""
    g = np.ones(len(y)) if g is None else g

    def f(t):
        eta = logit + t[0] * g
        r = expit(eta) - y
        if sw is not None:
            r = sw * r
        return _nll(eta, y, sw), np.array([r @ g])

    res = minimize(f, np.array([0.0]), jac=True, method="L-BFGS-B")
    return float(res.x[0])


def fit_ridge(
    z: np.ndarray,
    y: np.ndarray,
    w0: np.ndarray,
    lam: float,
    b0: float = 0.0,
    sw: np.ndarray | None = None,
    g: np.ndarray | None = None,
) -> tuple[float, np.ndarray]:
    """Logistic regression with penalty λ‖w − w0‖² and a free intercept b·g. Returns (b, w).
    `sw`: optional per-row weights (mean 1, so λ keeps its scale); `g`: the neutral-site gate."""
    k = z.shape[1]
    g = np.ones(len(y)) if g is None else g

    def f(t):
        b, w = t[0], t[1:]
        eta = b * g + z @ w
        r = expit(eta) - y
        if sw is not None:
            r = sw * r
        d = w - w0
        val = _nll(eta, y, sw) + lam * float(d @ d)
        grad = np.concatenate([[r @ g], z.T @ r + 2.0 * lam * d])
        return val, grad

    res = minimize(f, np.concatenate([[b0], w0]).astype(float), jac=True, method="L-BFGS-B")
    if not res.success and k:
        raise RuntimeError(f"ridge fit did not converge: {res.message}")
    return float(res.x[0]), res.x[1:].copy()


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


# ---------------------------------------------------------------------------------------- flavors


@dataclass
class FitResult:
    persona: Model
    fitted: Model
    public: Model | None = None  # the one line shown publicly (ADR 0004 amendment)


def inner_weights(
    approach: Approach,
    train: pl.DataFrame,
    feats: list[str],
    z: np.ndarray,
    y: np.ndarray,
    sw: np.ndarray | None = None,
    g: np.ndarray | None = None,
) -> dict[str, dict[str, float]]:
    """Per group: {feature: v}, composite rescaled to unit variance on the training window."""
    col = {f: i for i, f in enumerate(feats)}
    out: dict[str, dict[str, float]] = {}
    for gid in approach.groups:
        group = GROUPS[gid]
        members = [m for m in group.members if m.feature in col]
        if not members:
            out[gid] = {}
            continue
        idx = [col[m.feature] for m in members]
        zg = z[:, idx]
        if gid in approach.overrides:
            v = np.array([approach.overrides[gid].get(m.feature, 0.0) for m in members])
        else:
            hist = np.array([train.get_column(m.feature).is_not_null().sum() for m in members])
            fitted = hist >= MIN_HISTORY
            prior = np.array([m.sign * INNER_PRIOR for m in members], dtype=float)
            v = np.zeros(len(members))
            if fitted.any():
                _, w = fit_ridge(zg[:, fitted], y, prior[fitted], INNER_LAMBDA, sw=sw, g=g)
                v[fitted] = w
            scale = float(np.mean(np.abs(v[fitted]))) if fitted.any() else 1.0
            for i, m in enumerate(members):
                if not fitted[i]:
                    v[i] = m.sign * (scale or 1.0)
        sd = float(np.std(zg @ v))
        if sd > 1e-9:
            v = v / sd
        elif np.any(v):
            v = v / float(np.linalg.norm(v))
        out[gid] = {m.feature: float(x) for m, x in zip(members, v, strict=True)}
    return out


def _flat(feats: list[str], inner: dict[str, dict[str, float]], W: dict[str, float]) -> np.ndarray:
    w = np.zeros(len(feats))
    col = {f: i for i, f in enumerate(feats)}
    for gid, v in inner.items():
        for f, x in v.items():
            w[col[f]] += W.get(gid, 0.0) * x
    return w


def fit_flavors(
    approach: Approach, train: pl.DataFrame, lam: float, trained_through: int
) -> FitResult:
    feats = [f for f in approach.features if f in train.columns]
    scaler = Scaler.fit(train, feats, priors=LIVE_PRIORS, min_n=MIN_HISTORY)
    z, y = scaler.transform(train), train.get_column("y").to_numpy()
    meta = {
        "approach": approach.id,
        "trained_from": int(train["season"].min()),
        "trained_through": trained_through,
        "n_games": train.height,
        "config_hash": config_hash(approach),
    }
    g = gate(train)
    z = venue_gate(z, feats, g)  # venue modifiers only shift home field: none at a neutral site
    if approach.grouped:
        res = _fit_grouped(approach, train, feats, scaler, z, y, lam, meta, g)
    else:
        res = _fit_flat(approach, train, feats, scaler, z, y, lam, meta, g)
    for m in (res.persona, res.fitted, res.public):
        if m is not None:
            m.neutral_gate = True
    return res


def _fit_flat(approach, train, feats, scaler, z, y, lam, meta, g) -> FitResult:
    seasons = train.get_column("season").to_numpy()
    sw = season_weights(seasons, DECAY_HALF_LIFE)

    persona = persona_model(approach, scaler)
    if approach.calibration == "platt":
        persona.calib_a, persona.calib_c = fit_platt(persona.raw_logit(z, g), y, sw, g)
    persona.meta = meta | {"flavor": "persona"}

    w0 = np.array([approach.weights[f].w for f in feats], dtype=float)
    if not approach.fit.shrink_to_persona:
        w0 = np.zeros_like(w0)
    b, w = fit_ridge(z, y, w0, lam, b0=approach.intercept.w, sw=sw, g=g)
    fitted = Model(
        model_id=f"{approach.id}.fitted",
        features=feats,
        intercept=b,
        weights=list(map(float, w)),
        scaler=scaler,
        meta=meta | {"flavor": "fitted", "lambda": lam},
    )
    return FitResult(persona, fitted, _public_from(approach, fitted, None, z, y, seasons, sw, g))


def _public_from(
    approach: Approach,
    fitted: Model,
    light: Model | None,
    z,
    y,
    seasons: np.ndarray,
    sw: np.ndarray | None = None,
    g: np.ndarray | None = None,
) -> Model:
    """The public line: `light` (calibrated) for personas, or the fitted model for public: fitted.
    `shift_10` re-fits only the offset on the last ten training seasons (`seasons` = each row's)."""
    src = fitted if (approach.public == "fitted" or light is None) else light
    pub = Model(
        model_id=approach.id,
        features=src.features,
        intercept=src.intercept,
        weights=list(src.weights),
        scaler=src.scaler,
        meta=dict(src.meta) | {"flavor": "public", "public": approach.public},
    )
    if src is light and approach.calibration == "platt":
        pub.calib_a, pub.calib_c = fit_platt(pub.raw_logit(z, g), y, sw, g)
    elif approach.calibration in SHIFT_SEASONS:
        recent = seasons > seasons.max() - SHIFT_SEASONS[approach.calibration]
        pub.calib_a = 1.0
        gg = np.ones(len(y)) if g is None else g
        ws = None if sw is None else sw[recent]
        pub.calib_c = fit_shift(pub.raw_logit(z, gg)[recent], y[recent], gg[recent], ws)
        pub.meta |= {"calibration": approach.calibration, "calib_seasons": int(recent.sum())}
    return pub


def _fit_grouped(approach, train, feats, scaler, z, y, lam, meta, g) -> FitResult:
    seasons = train.get_column("season").to_numpy()
    sw = season_weights(seasons, DECAY_HALF_LIFE)
    inner = inner_weights(approach, train, feats, z, y, sw, g)
    gids = [k for k in approach.groups if inner.get(k)]
    W_persona = {k: approach.groups[k].w for k in gids}
    gmeta = meta | {"registry_version": REGISTRY_VERSION, "inner": inner}

    w_p = _flat(feats, inner, W_persona)
    persona = Model(
        model_id=f"{approach.id}.persona",
        features=feats,
        intercept=approach.intercept.w,
        weights=list(map(float, w_p)),
        scaler=scaler,
        meta=gmeta | {"flavor": "persona", "group_weights": W_persona},
    )
    if approach.calibration == "platt":
        persona.calib_a, persona.calib_c = fit_platt(persona.raw_logit(z, g), y, sw, g)

    comp = np.column_stack([z @ _flat(feats, {k: inner[k]}, {k: 1.0}) for k in gids])
    W0 = (
        np.array([W_persona[k] for k in gids])
        if approach.fit.shrink_to_persona
        else np.zeros(len(gids))
    )
    b, W = fit_ridge(comp, y, W0, lam, b0=approach.intercept.w, sw=sw, g=g)
    W_fit = {k: float(x) for k, x in zip(gids, W, strict=True)}
    fitted = Model(
        model_id=f"{approach.id}.fitted",
        features=feats,
        intercept=b,
        weights=list(map(float, _flat(feats, inner, W_fit))),
        scaler=scaler,
        meta=gmeta | {"flavor": "fitted", "lambda": lam, "group_weights": W_fit},
    )
    # public "light" line: shrunk hard toward the persona (it keeps its biases), then calibrated
    lam_pub = PUBLIC_RIDGE * 0.22 * len(y)
    bl, Wl = fit_ridge(
        comp,
        y,
        np.array([W_persona[k] for k in gids]),
        lam_pub,
        b0=approach.intercept.w,
        sw=sw,
        g=g,
    )
    W_light = {k: float(x) for k, x in zip(gids, Wl, strict=True)}
    light = Model(
        model_id=approach.id,
        features=feats,
        intercept=bl,
        weights=list(map(float, _flat(feats, inner, W_light))),
        scaler=scaler,
        meta=gmeta
        | {"lambda": lam_pub, "group_weights": W_light, "persona_group_weights": W_persona},
    )
    return FitResult(persona, fitted, _public_from(approach, fitted, light, z, y, seasons, sw, g))


def config_hash(approach: Approach) -> str:
    import hashlib

    return hashlib.sha1(approach.model_dump_json().encode()).hexdigest()[:12]


def _score(model: Model, df: pl.DataFrame) -> np.ndarray:
    cols = ["game_id", *(c for c in model.inputs if c in df.columns)]
    return model.score(df.select(cols))["p_home"].to_numpy()


def select_lambda(
    approach: Approach, data: pl.DataFrame, val_seasons: tuple[int, ...] = VAL_SEASONS
) -> tuple[float, pl.DataFrame]:
    """Mean validation log loss per λ (each validation season fit on earlier seasons only)."""
    rows = []
    for lam in approach.fit.lambda_grid:
        losses, n = [], 0
        for s in val_seasons:
            train = data.filter(pl.col("season").is_between(approach.fit.train_from, s - 1))
            test = data.filter(pl.col("season") == s)
            if train.is_empty() or test.is_empty():
                continue
            m = fit_flavors(approach, train, lam, s - 1).fitted
            losses.append(log_loss(_score(m, test), test["y"].to_numpy()) * test.height)
            n += test.height
        rows.append((lam, sum(losses) / n if n else float("nan"), n))
    table = pl.DataFrame(rows, schema=["lambda", "val_log_loss", "n"], orient="row")
    best = table.drop_nans("val_log_loss").sort("val_log_loss")
    return float(best["lambda"][0]), table


def walk_forward(
    approach: Approach, data: pl.DataFrame, scored: tuple[int, int], lam: float
) -> dict[int, FitResult]:
    """season -> models trained through season − 1."""
    out = {}
    for s in range(scored[0], scored[1] + 1):
        train = data.filter(pl.col("season").is_between(approach.fit.train_from, s - 1))
        if train.height < 100:
            continue
        out[s] = fit_flavors(approach, train, lam, s - 1)
    return out


# -------------------------------------------------------------------------------------- artifacts


def artifact_path(paths: Paths, model_id: str, trained_through: int) -> Path:
    return paths.marts / "fits" / model_id / f"{trained_through}.json"


def save(paths: Paths, model: Model) -> Path:
    p = artifact_path(paths, model.model_id, model.meta["trained_through"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(model.to_dict(), indent=1))
    return p


def load(paths: Paths, model_id: str, trained_through: int) -> Model:
    return Model.from_dict(json.loads(artifact_path(paths, model_id, trained_through).read_text()))


def fit_approach(
    paths: Paths,
    approach: Approach,
    scored: tuple[int, int] = (FIRST_SCORED_SEASON, 2026),
    known: set[str] | None = None,
) -> pl.DataFrame:
    """Select λ, walk forward, save every artifact. Returns the λ table. `known` = features in the
    store (grouped approaches use whichever registry members exist)."""
    feats = approach.resolve(known) if known is not None else approach.features
    data = load_dataset(paths, feats, (approach.fit.train_from, scored[1] - 1))
    lam, table = select_lambda(approach, data)
    has_persona = approach.calibration != "none" or approach.fit.shrink_to_persona
    for res in walk_forward(approach, data, scored, lam).values():
        if has_persona:  # the global fit has no persona; its artifact is <id>.fitted only
            save(paths, res.persona)
        save(paths, res.fitted)  # diagnostic: "what history would change"
        if res.public is not None:
            save(paths, res.public)  # the public line, model_id = approach id
    return table.with_columns(
        pl.lit(approach.id).alias("approach"), (pl.col("lambda") == lam).alias("chosen")
    )
