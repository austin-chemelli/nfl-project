"""Model round 3 audit (ADR 0031): every design choice of the Student, measured.

Read-only: nothing is written under marts/. Each variant is walked forward in memory with
`nfl.approaches.shadow` (the code path `nfl fit` uses) and paired against today's Student on the
same data, 2016 onward, season-block bootstrap 90% CI.

    uv run python scripts/approaches_audit.py design      # fitting choices
    uv run python scripts/approaches_audit.py features    # candidate members, one at a time
    uv run python scripts/approaches_audit.py --out .notes/approaches-audit/   (tables as csv)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

from nfl.approaches import shadow
from nfl.approaches.run import known_features
from nfl.approaches.schema import Approach, FitSpec, Weight, load_all
from nfl.config import get_paths
from nfl.features.groups import GROUPS


def student() -> Approach:
    return load_all()["student"]


def with_fit(a: Approach, **kw) -> Approach:
    return a.model_copy(update={"fit": FitSpec(**(a.fit.model_dump() | kw))})


def without_group(a: Approach, gid: str) -> Approach:
    groups = {g: w for g, w in a.groups.items() if g != gid}
    ov = {g: v for g, v in a.overrides.items() if g != gid}
    return a.model_copy(update={"groups": groups, "overrides": ov})


def flat(a: Approach, known: set[str]) -> Approach:
    """Every member of the Student's groups as its own weight, ridge toward 0: no groups."""
    feats = [f for f in a.resolve(known) if not f.startswith(("market.", "narrative."))]
    return Approach(
        id="flat",
        name="flat",
        blurb="no groups",
        emphasis=[],
        calibration="none",
        public="fitted",
        intercept=Weight(w=0.0, why="fitted"),
        weights={f: Weight(w=0.0, why="fitted") for f in feats},
        fit=FitSpec(shrink_to_persona=False, lambda_grid=[10.0, 100.0, 1000.0, 3000.0]),
    )


def design(paths, known: set[str]) -> list[dict]:
    st = student()
    feats = st.resolve(known)
    data = shadow.dataset(paths, feats)
    base = shadow.backtest(st, data)
    rows = []

    def run(name: str, a: Approach, why: str, lam=None, **kn):
        with shadow.knobs(**kn):
            bt = shadow.backtest(a, data, lam=lam)
        r = shadow.paired(bt, base) | {"variant": name, "why": why, "lam": float(bt["lam"][0])}
        r["ll_2005"] = shadow.log_loss(bt)
        rows.append(r)
        print(json.dumps({k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()}))

    run("today", st, "today's Student (Platt is a no-op on public: fitted)")
    run("shift_10", st.model_copy(update={"calibration": "shift_10"}), "Student v2's calibration")
    for tf in (2006, 2010):
        run(f"train_from_{tf}", with_fit(st, train_from=tf), "shorter history")
    for hl in (4, 8, 12):
        run(f"decay_{hl}", st, f"season weights, half-life {hl}", DECAY_HALF_LIFE=hl)
    for hl in (8,):
        run(f"decay_{hl}+shift", st.model_copy(update={"calibration": "shift_10"}), "both",
            DECAY_HALF_LIFE=hl)  # fmt: skip
    for lam in (1.0, 100.0, 1000.0):
        run(f"lambda_{lam:g}", st, "fixed group-level λ", lam=lam)
    run("no_persona_prior", with_fit(st, shrink_to_persona=False), "ridge toward 0, not 0.1")
    for il in (300.0, 1000.0, 10000.0):
        run(f"inner_lambda_{il:g}", st, "inner ridge λ (3000 today)", INNER_LAMBDA=il)
    run("inner_prior_0", st, "inner weights shrink toward 0", INNER_PRIOR=0.0)
    run("flat", flat(st, known), "no groups: one ridge over every member")
    for gid in st.groups:
        if gid == "market":
            continue
        run(f"drop_{gid}", without_group(st, gid), f"without {GROUPS[gid].name}")
    return rows


def M(f: str, sign: int):
    from nfl.features.groups import Member

    return Member(f, sign, f, "index", f)


# candidate member changes: name -> (add, drop, weighted groups, extra approach groups)
VENUE_OLD = {"environment.temp_c", "environment.wind_kph"}
FEATURE_VARIANTS = {
    "weather": ({"venue_weather": [M("weather.temp_f", 1), M("weather.wind_mph", -1)]}, VENUE_OLD),
    "venue_neutral_only": ({}, {"environment.div_game", "environment.primetime",
                                "environment.is_dome", "environment.is_turf"}),
    "epa_off_noto": ({"offense": [M("strength.epa_off_noto", 1)]}, set()),
    "epa_def_noto": ({"defense": [M("strength.epa_def_noto", -1)]}, set()),
    "takeaway_rate": ({"defense": [M("strength.takeaway_rate", 1)]}, set()),
    "fum_luck": ({"quality": [M("strength.fum_luck", -1)]}, set()),
    "one_score_luck": ({"quality": [M("decisions.one_score_luck", -1)]}, set()),
    "value_lost": ({"health": [M("availability.value_lost", -1)]}, set()),
    "ol_weakest": ({"health": [M("availability.ol_weakest", 1)]}, set()),
    "net_edge_in_offense": ({"offense": [M("matchup.net_edge_pg", 1)]}, set()),
}  # fmt: skip


def features(paths, known: set[str], base_cal: str = "platt") -> list[dict]:
    st = student()
    extra = sorted(
        {m.feature for a, _ in FEATURE_VARIANTS.values() for ms in a.values() for m in ms}
    )
    data = shadow.dataset(paths, [*st.resolve(known), *[f for f in extra if f in known]])
    base = shadow.backtest(st, data)
    rows = []

    def run(name, a, add, drop, weighted=None, why=""):
        with shadow.registry(add, drop, weighted):
            bt = shadow.backtest(a, data)
        r = shadow.paired(bt, base) | {"variant": name, "why": why, "lam": float(bt["lam"][0])}
        r["ll_2005"] = shadow.log_loss(bt)
        r["p22"] = shadow.paired(bt, base, seasons_from=2022)["delta"]
        rows.append(r)
        print(json.dumps({k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()}))

    for name, (add, drop) in FEATURE_VARIANTS.items():
        if any(m.feature not in known for ms in add.values() for m in ms):
            print("skip (not stored)", name)
            continue
        run(name, st, add, drop)
    if "matchup.net_edge_pg" in known:
        a = st.model_copy(update={"groups": st.groups | {"matchups": Weight(w=0.1, why="test")}})
        run("matchups_group", a, {"matchups": [M("matchup.net_edge_pg", 1)]},
            {m.feature for m in GROUPS["matchups"].members}, {"matchups"})  # fmt: skip
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["design", "features"])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    paths = get_paths()
    known = known_features(paths)
    rows = design(paths, known) if args.what == "design" else features(paths, known)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(rows).write_csv(args.out / f"{args.what}.csv")


if __name__ == "__main__":
    main()
