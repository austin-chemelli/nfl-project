"""M23.0: does recalibrating the Student's logits help, walk-forward? (ADR 0026)

Read-only. For each scored season S (2016-2025 by default), a calibration is fitted on the Student's
own walk-forward backfill predictions from seasons before S only, then applied to season S:

  identity            today's Student
  platt_N             logit' = a * logit + c, fitted on the last N seasons
  shift_N             logit' = logit + c, fitted on the last N seasons
  platt_hl_H          Platt on every earlier season, weighted 0.5 ** ((S - 1 - s) / H)

Reported per variant: log loss, paired difference against identity with a season-block bootstrap
90% CI, Brier, the spread slope (final margin on the mapped spread) and the mean spread minus the
mean margin. The market baseline is printed for scale.

    uv run python scripts/calibration_study.py [--from 2016] [--to 2025] [--reliability VARIANT]
"""

from __future__ import annotations

import argparse

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logit
from scipy.stats import norm

from nfl import catalog
from nfl.config import get_paths

SD_MARGIN = 13.5
EPS = 1e-6
BOOT = 2000
SEED = 20261108


def load(con) -> dict[str, np.ndarray]:
    df = con.sql(
        """
        select p.season, p.p_home, m.p_home p_mkt, g.result,
               case when g.result > 0 then 1.0 else 0.0 end y
        from predictions p
        join predictions m on m.game_id = p.game_id and m.model_id = 'market_baseline' and m.is_backfill
        join games g on g.game_id = p.game_id
        where p.model_id = 'student' and p.is_backfill and g.game_type = 'REG'
          and g.result is not null and g.result <> 0
        """
    ).pl()
    return {c: df[c].to_numpy().astype(float) for c in df.columns}


def _nll(eta, y, w):
    return float(np.sum(w * (np.logaddexp(0, eta) - y * eta)))


def fit(x, y, w, slope: bool) -> tuple[float, float]:
    if slope:
        res = minimize(lambda t: _nll(t[0] * x + t[1], y, w), [1.0, 0.0], method="L-BFGS-B")
        return float(res.x[0]), float(res.x[1])
    res = minimize(lambda t: _nll(x + t[0], y, w), [0.0], method="L-BFGS-B")
    return 1.0, float(res.x[0])


def variants() -> dict[str, dict]:
    v = {"identity": {}}
    for n in (3, 5, 10):
        v[f"platt_{n}"] = {"window": n, "slope": True}
        v[f"shift_{n}"] = {"window": n, "slope": False}
    for h in (3, 6):
        v[f"platt_hl_{h}"] = {"half_life": h, "slope": True}
    return v


def apply(d, spec: dict, seasons: list[int]) -> np.ndarray:
    """Calibrated p for every row of the scored seasons (others NaN)."""
    x = logit(np.clip(d["p_home"], EPS, 1 - EPS))
    out = np.full_like(x, np.nan)
    for s in seasons:
        rows = d["season"] == s
        if not spec:
            out[rows] = expit(x[rows])
            continue
        prior = d["season"] < s
        if "window" in spec:
            prior &= d["season"] >= s - spec["window"]
            w = np.ones(prior.sum())
        else:
            w = 0.5 ** ((s - 1 - d["season"][prior]) / spec["half_life"])
        a, c = fit(x[prior], d["y"][prior], w, spec["slope"])
        out[rows] = expit(a * x[rows] + c)
    return out


def ll(p, y):
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="s0", type=int, default=2016)
    ap.add_argument("--to", dest="s1", type=int, default=2025)
    ap.add_argument("--reliability", default=None)
    args = ap.parse_args()

    con = catalog.connect(get_paths(), only=["predictions", "games"])
    d = load(con)
    seasons = list(range(args.s0, args.s1 + 1))
    scored = np.isin(d["season"], seasons)
    y, res, sea = d["y"][scored], d["result"][scored], d["season"][scored]
    rng = np.random.default_rng(SEED)
    picks = [rng.choice(seasons, len(seasons)) for _ in range(BOOT)]
    idx = {s: np.where(sea == s)[0] for s in seasons}

    base = ll(apply(d, {}, seasons)[scored], y)
    print(f"games {scored.sum()}, seasons {args.s0}-{args.s1}; mean margin {res.mean():+.2f}")
    print(f"market baseline: log loss {ll(d['p_mkt'][scored], y).mean():.4f}\n")
    print(
        f"{'variant':12} {'log loss':>9} {'Δ vs Student':>26} {'Brier':>7} {'slope':>6} {'bias':>6}"
    )
    probs = {}
    for name, spec in variants().items():
        p = apply(d, spec, seasons)[scored]
        probs[name] = p
        l = ll(p, y)
        diff = l - base
        bs = [np.concatenate([diff[idx[s]] for s in pk]).mean() for pk in picks]
        lo, hi = np.percentile(bs, [5, 95])
        spread = norm.ppf(np.clip(p, EPS, 1 - EPS)) * SD_MARGIN
        slope = np.polyfit(spread, res, 1)[0]
        print(
            f"{name:12} {l.mean():9.4f} {diff.mean():+.4f} [{lo:+.4f}, {hi:+.4f}] "
            f"{np.mean((p - y) ** 2):7.4f} {slope:6.2f} {spread.mean() - res.mean():+6.2f}"
        )

    rel = args.reliability
    if rel:
        p = probs[rel]
        print(f"\nreliability, {rel} (bin: mean p, home win rate, n)")
        b = np.minimum((p * 10).astype(int), 9)
        for k in range(10):
            m = b == k
            if m.sum():
                print(
                    f"  {k / 10:.1f}-{(k + 1) / 10:.1f}: {p[m].mean():.3f} {y[m].mean():.3f} {m.sum()}"
                )


if __name__ == "__main__":
    main()
