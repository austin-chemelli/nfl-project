"""Approach configs (architecture §3.4, ADR 0003/0004/0012).

An approach is a persona: an intercept (home-field belief) plus either
- `groups:` a weight per feature group (ADR 0012; logit units per 1 SD of the group's unit-variance
  composite), with optional `overrides:` of a group's inner weights; or
- `weights:` a weight per feature (the original flat form; still valid, e.g. for tests).
Features outside the approach's groups/weights are invisible to it, in both flavors. Every persona
weight carries a one-line `why` so the UI can explain it and Austin can tweak it in the YAML.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from nfl.features.groups import GROUPS, MARKET_GROUP_CAP, MARKET_LEVEL
from nfl.features.store import FEATURE_RX

CONFIG_DIR = Path(__file__).parent / "configs"
FAMILIES = {
    "strength",
    "environment",
    "form",
    "decisions",
    "front",
    "market",
    "availability",
    "scheme",
    "matchup",
    "narrative",
}
ID_RX = re.compile(r"^[a-z][a-z0-9_]*$")


class Weight(BaseModel):
    w: float
    why: str = Field(min_length=3)


class FitSpec(BaseModel):
    shrink_to_persona: bool = True
    lambda_grid: list[float] = [1.0, 10.0, 100.0, 1000.0, 10000.0]
    train_from: int = 2002  # config.FIRST_TRAIN_SEASON: Elo and priors warm up from 1999


class Approach(BaseModel):
    id: str
    name: str
    blurb: str
    emphasis: list[str]  # families (flat form) or group ids (grouped form)
    calibration: Literal["platt", "none"] = "platt"
    shadow: bool = False  # scored and shown, but excluded from the ensemble and headline scorecard
    # ADR 0004 amendment: the one public line. "light" = persona weights lightly fitted + calibrated;
    # "fitted" = the walk-forward fitted weights (the Student, whose identity is the data).
    public: Literal["light", "fitted"] = "light"
    intercept: Weight
    weights: dict[str, Weight] = {}
    groups: dict[str, Weight] = {}
    overrides: dict[str, dict[str, float]] = {}
    fit: FitSpec = FitSpec()

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not ID_RX.match(v):
            raise ValueError(f"bad approach id {v!r}")
        return v

    @field_validator("weights")
    @classmethod
    def _names(cls, v: dict[str, Weight]) -> dict[str, Weight]:
        bad = [k for k in v if not FEATURE_RX.match(k) or k.split(".", 1)[0] not in FAMILIES]
        if bad:
            raise ValueError(f"bad feature names: {bad}")
        return v

    @field_validator("groups")
    @classmethod
    def _group_ids(cls, v: dict[str, Weight]) -> dict[str, Weight]:
        unknown = sorted(set(v) - set(GROUPS))
        if unknown:
            raise ValueError(f"unknown groups: {unknown}")
        return v

    @model_validator(mode="after")
    def _shape(self) -> Approach:
        level = sorted(set(self.weights) & MARKET_LEVEL)
        level += sorted(f for ov in self.overrides.values() for f in ov if f in MARKET_LEVEL)
        if level:
            raise ValueError(
                f"the market's forecast is never an approach input (ADR 0013): {level}"
            )
        if "market" in self.groups:
            total = sum(abs(w.w) for w in self.groups.values())
            share = abs(self.groups["market"].w) / total if total else 0.0
            if share > MARKET_GROUP_CAP + 1e-9:
                raise ValueError(
                    f"Market behavior is {share:.0%} of the budget; the cap is {MARKET_GROUP_CAP:.0%} (ADR 0013)"
                )
        if bool(self.weights) == bool(self.groups):
            raise ValueError("give exactly one of `weights:` (flat) or `groups:` (grouped)")
        if self.groups:
            missing = set(self.emphasis) - set(self.groups)
            if missing:
                raise ValueError(f"emphasized groups have no weights: {sorted(missing)}")
            for gid, ov in self.overrides.items():
                if gid not in self.groups:
                    raise ValueError(f"override for a group the approach doesn't weigh: {gid}")
                stray = set(ov) - set(GROUPS[gid].features)
                if stray:
                    raise ValueError(f"override features not in group {gid}: {sorted(stray)}")
        else:
            unknown = set(self.emphasis) - FAMILIES
            if unknown:
                raise ValueError(f"unknown families in emphasis: {sorted(unknown)}")
            fams = {k.split(".", 1)[0] for k in self.weights}
            missing = set(self.emphasis) - fams
            if missing:
                raise ValueError(f"emphasized families have no weights: {sorted(missing)}")
            if self.overrides:
                raise ValueError("`overrides:` only applies to grouped approaches")
        return self

    @property
    def grouped(self) -> bool:
        return bool(self.groups)

    @property
    def features(self) -> list[str]:
        """Every feature the approach can see. Grouped: all registry members of its groups,
        including planned ones not built yet (see `resolve`)."""
        if self.grouped:
            return [f for gid in self.groups for f in GROUPS[gid].features]
        return list(self.weights)

    def resolve(self, known: set[str]) -> list[str]:
        """Features to use given what the store has. Flat approaches must have all of theirs;
        grouped ones use whichever registry members exist."""
        if not self.grouped:
            check_features(self, known)
            return list(self.weights)
        return [f for f in self.features if f in known]

    def family_weight(self) -> dict[str, float]:
        """Flat: sum of |w| per family. Grouped: |W| per group. The persona's attention split."""
        if self.grouped:
            return {gid: abs(w.w) for gid, w in self.groups.items()}
        out: dict[str, float] = {}
        for k, wt in self.weights.items():
            f = k.split(".", 1)[0]
            out[f] = out.get(f, 0.0) + abs(wt.w)
        return out


def load_approach(path: Path) -> Approach:
    a = Approach.model_validate(yaml.safe_load(path.read_text()))
    if a.id != path.stem:
        raise ValueError(f"{path.name}: id {a.id!r} must match the file name")
    return a


def load_all(config_dir: Path = CONFIG_DIR) -> dict[str, Approach]:
    return {a.id: a for a in (load_approach(p) for p in sorted(config_dir.glob("*.yaml")))}


def check_features(approach: Approach, known: set[str]) -> None:
    """Fail loudly if an approach weights a feature the store doesn't have."""
    missing = sorted(set(approach.features) - known)
    if missing:
        raise ValueError(f"{approach.id}: features not in the store: {missing}")
