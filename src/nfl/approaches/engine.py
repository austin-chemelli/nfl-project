"""Scoring engine (architecture §3.4).

    z        = standardized game vector (home - away for team features), nulls -> 0 (league average)
    logit    = a * (b0 + Σ w_f z_f) + c        (a, c: Platt calibration; identity when absent)
    p_home   = σ(logit)
    spread   = Φ⁻¹(p_home) · 13.5              (same Normal-margin convention as the market model)

Contributions are stored in final logit units: `home_field` = a·b0 + c and `<feature>` = a·w_f·z_f,
so they sum exactly to the logit. The UI's "why" waterfall reads them directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import polars as pl
from scipy.special import expit
from scipy.stats import norm

from nfl.approaches.schema import Approach

SD_MARGIN = 13.5
P_CLIP = 1e-6


@dataclass
class Scaler:
    features: list[str]
    mean: list[float]
    sd: list[float]

    @classmethod
    def fit(cls, wide: pl.DataFrame, features: list[str]) -> Scaler:
        mean, sd = [], []
        for f in features:
            col = wide.get_column(f).drop_nulls().cast(pl.Float64) if f in wide.columns else None
            if col is None or col.len() < 2:
                mean.append(0.0)
                sd.append(1.0)
                continue
            m, s = float(col.mean()), float(col.std())
            mean.append(m)
            sd.append(s if s and np.isfinite(s) and s > 1e-12 else 1.0)
        return cls(list(features), mean, sd)

    def transform(self, wide: pl.DataFrame) -> np.ndarray:
        cols = []
        for f, m, s in zip(self.features, self.mean, self.sd, strict=True):
            if f in wide.columns:
                x = wide.get_column(f).cast(pl.Float64).to_numpy()
                z = (x - m) / s
                cols.append(np.where(np.isnan(z), 0.0, z))
            else:
                cols.append(np.zeros(wide.height))
        return np.column_stack(cols) if cols else np.zeros((wide.height, 0))


@dataclass
class Model:
    """A scored line: one approach flavor, the global fit, or anything else linear in z."""

    model_id: str
    features: list[str]
    intercept: float
    weights: list[float]
    scaler: Scaler
    calib_a: float = 1.0
    calib_c: float = 0.0
    meta: dict = field(default_factory=dict)

    def raw_logit(self, z: np.ndarray) -> np.ndarray:
        return self.intercept + z @ np.asarray(self.weights, dtype=float)

    def score(self, wide: pl.DataFrame) -> pl.DataFrame:
        """wide: game_id + feature columns (store.to_wide). Returns game_id, p_home, spread_home,
        logit, contributions (JSON string, final logit units)."""
        z = self.scaler.transform(wide)
        w = np.asarray(self.weights, dtype=float)
        logit = self.calib_a * self.raw_logit(z) + self.calib_c
        p = np.clip(expit(logit), P_CLIP, 1 - P_CLIP)
        contrib = self.calib_a * z * w  # (n, k)
        base = self.calib_a * self.intercept + self.calib_c
        blobs = [
            json.dumps(
                {"home_field": round(base, 6)}
                | {f: round(float(v), 6) for f, v in zip(self.features, row, strict=True)}
            )
            for row in contrib
        ]
        return pl.DataFrame(
            {
                "game_id": wide.get_column("game_id"),
                "p_home": p,
                "spread_home": norm.ppf(p) * SD_MARGIN,
                "logit": logit,
                "contributions": blobs,
            }
        )

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "features": self.features,
            "intercept": self.intercept,
            "weights": list(map(float, self.weights)),
            "scaler": {"mean": self.scaler.mean, "sd": self.scaler.sd},
            "calib_a": self.calib_a,
            "calib_c": self.calib_c,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Model:
        return cls(
            model_id=d["model_id"],
            features=d["features"],
            intercept=d["intercept"],
            weights=d["weights"],
            scaler=Scaler(d["features"], d["scaler"]["mean"], d["scaler"]["sd"]),
            calib_a=d.get("calib_a", 1.0),
            calib_c=d.get("calib_c", 0.0),
            meta=d.get("meta", {}),
        )


def persona_model(approach: Approach, scaler: Scaler) -> Model:
    """The persona flavor before calibration: weights straight from the YAML."""
    if scaler.features != approach.features:
        raise ValueError("scaler features must match the approach's features, in order")
    return Model(
        model_id=f"{approach.id}.persona",
        features=approach.features,
        intercept=approach.intercept.w,
        weights=[approach.weights[f].w for f in approach.features],
        scaler=scaler,
    )
