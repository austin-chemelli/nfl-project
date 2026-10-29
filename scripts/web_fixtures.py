"""Trimmed copies of the site JSON for the web app's tests (web/src/test/fixtures/site/).

Run after a contract change: `uv run python scripts/web_fixtures.py`. Keeps the fixtures small
(a week's slate, two games, a few coaches, a slice of the build-your-own matrix) so they can be
checked in, while staying real output of `nfl site`.

Parity fixtures for the TypeScript evaluator (web/src/diy/): `uv run python scripts/web_fixtures.py --diy`
writes web/src/test/fixtures/diy/parity.json: a small matrix (warmup 2002-2004 plus scored 2005-2009
of the real diy_matrix.json) and the expected outputs of nfl.approaches.diy.evaluate,
season_predictions, fit_toward, cap_market, encode_weights and decode_weights on fixed weight sets.
`--diy` leaves fixtures/site alone, and the default run leaves fixtures/diy alone.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

import numpy as np

from nfl.approaches import diy
from nfl.config import get_paths

FIXTURES = Path(__file__).resolve().parents[1] / "web" / "src" / "test" / "fixtures"
OUT = FIXTURES / "site"
OUT_DIY = FIXTURES / "diy"
DIY_SEASONS = (
    2002,
    2009,
)  # warmup 2002-2004 + scored 2005-2009: enough history for walk-forward Platt
DIY_MAX_SEASON = 2007  # the "hide recent seasons" case
WEEK = 8
GAMES = ["2026_08_CAR_GB"]  # has a narrative record
N_DIY = 400  # matrix rows kept (most recent seasons)
N_PEOPLE = 6


def _load(src: Path, name: str) -> dict:
    return json.loads((src / name).read_text())


def _dump(obj: dict, name: str) -> None:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")) + "\n")


def _slice_columns(d: dict, keys: list[str], idx: slice) -> None:
    for k in keys:
        d[k] = d[k][idx]


def main() -> None:
    src = get_paths().site
    if OUT.exists():
        shutil.rmtree(OUT)

    _dump(_load(src, "meta.json"), "meta.json")

    slate = _load(src, f"slate_2026_{WEEK:02d}.json")
    _dump(slate, f"slate_2026_{WEEK:02d}.json")
    others = [
        g["game_id"] for g in slate["games"] if g["game_id"] not in GAMES and g["result"] is None
    ]
    for gid in GAMES + others[:1]:
        _dump(_load(src, f"game/{gid}.json"), f"game/{gid}.json")

    _dump(_load(src, "tracker.json"), "tracker.json")

    hyp = _load(src, "hypotheses.json")
    hyp["features"] = hyp["features"][:12]
    keep = list(hyp["by_season"]["items"])[:8]
    hyp["by_season"]["items"] = {k: hyp["by_season"]["items"][k] for k in keep}
    _dump(hyp, "hypotheses.json")

    coaches = _load(src, "coaches.json")
    coaches["people"] = coaches["people"][:N_PEOPLE]
    _dump(coaches, "coaches.json")

    diy = _load(src, "diy_matrix.json")
    idx = slice(-N_DIY, None)
    _slice_columns(diy["columns"], list(diy["columns"]), idx)
    _slice_columns(diy["c"], list(diy["c"]), idx)
    diy["n"] = len(diy["columns"]["game_id"])
    _dump(diy, "diy_matrix.json")

    season = _load(src, "season_2025.json")
    _dump(season, "season_2025.json")

    audit = _load(src, "audit.json")
    audit["null_rates"] = audit.get("null_rates", [])[:40]
    _dump(audit, "audit.json")

    total = sum(p.stat().st_size for p in OUT.rglob("*.json"))
    print(f"wrote {len(list(OUT.rglob('*.json')))} fixtures to {OUT} ({total / 1024:.0f} KB)")


def _clean(x):
    """JSON-safe: numpy -> python, NaN/inf -> None, dict keys -> str."""
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_clean(v) for v in x]
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    if isinstance(x, np.generic):
        return _clean(x.item())
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def _diy_matrix(src: Path) -> dict:
    m = _load(src, "diy_matrix.json")
    lo, hi = DIY_SEASONS
    seasons = m["columns"]["season"]
    keep = [i for i, s in enumerate(seasons) if lo <= s <= hi]
    for k in m["columns"]:
        m["columns"][k] = [m["columns"][k][i] for i in keep]
    for k in m["c"]:
        m["c"][k] = [m["c"][k][i] for i in keep]
    m["n"] = len(keep)
    m["student_fitted"] = {s: v for s, v in m["student_fitted"].items() if int(s) <= hi}
    return m


def _extras(w: dict, P: dict, max_season: int | None) -> dict:
    """Accuracy and reliability bins (not part of diy.evaluate; the page adds them), computed the
    long way from the same walk-forward logits so the TypeScript version has a reference."""
    season = P["season"]
    scored = sorted({int(s) for s in season[~P["warmup"]] if max_season is None or s <= max_season})
    use = ~P["warmup"] & np.isin(season, scored)
    keep = np.isin(season, scored) | (P["warmup"] & (season < scored[0]))
    raw = diy._raw_logit(P, w)
    lg, _ = diy.walk_forward_platt(raw[keep], P["y"][keep], season[keep], scored)
    logit = np.zeros_like(raw)
    logit[keep] = lg
    p = 1 / (1 + np.exp(-logit))
    y, mkt = P["y"], P["mkt"]
    has = ~np.isnan(mkt)
    sel = use & has
    bins = np.minimum((p[use] * 10).astype(int), 9)
    rel = [
        {"bin": b, "n": int((bins == b).sum()), "mean_p": float(p[use][bins == b].mean()),
         "hit_rate": float(y[use][bins == b].mean())}
        for b in range(10) if (bins == b).any()
    ]  # fmt: skip
    return {
        "accuracy": float(((p[use] >= 0.5) == (y[use] == 1)).mean()),
        "market_accuracy": float(((mkt[sel] >= 0.5) == (y[sel] == 1)).mean()),
        "n_market": int(sel.sum()),
        "reliability": rel,
    }


def diy_main() -> None:
    """Expected outputs of the Python evaluator on fixed weight sets (see the module docstring)."""
    m = _diy_matrix(get_paths().site)
    P = diy.prepare(m)
    active = [g for g in m["groups"] if g not in m["inactive"]]
    pers = {k: v["W"] for k, v in m["personas"].items()}
    student_by_season = {s: v["W"] for s, v in m["student_fitted"].items()}
    even = {g: 50.0 for g in active}
    sets: dict[str, dict] = {
        "even": even,
        "traditionalist": pers["traditionalist"],
        "analyst": pers["analyst"],
        "sharp": pers["sharp"],
        "student_persona": pers["student"],
        "single_group": {"quality": 80.0},
        "contrarian_mix": {"quality": 60.0, "form": -40.0, "quarterback": 25.5, "health": -10.0},
        "market_over_cap": {"quality": 50.0, "offense": 20.0, "market": 60.0},
        "fractional": {"quality": 33.3333333, "defense": 12.5, "coaching": -7.25},
    }
    cases = []

    def run(
        name: str, signed: dict, per_season: bool = False, max_season: int | None = None
    ) -> None:
        if per_season:
            w = signed
            capped, hit = None, None
        else:
            capped, hit = diy.cap_market(signed)
            tot = sum(abs(v) for v in capped.values()) or 1.0
            w = {g: v / tot for g, v in capped.items()}
        ev = diy.evaluate(w, m, max_season=max_season)
        # the bootstrap generator differs between numpy and the browser: CIs are not compared
        for k in ("ll_lo", "ll_hi", "d_lo", "d_hi"):
            ev["overall"].pop(k)
        for k in ("slope_lo", "slope_hi", "sentence", "per_decade"):
            ev["aging"].pop(k, None)
        season = max_season or DIY_SEASONS[1]
        sp = diy.season_predictions(w, m, season)
        case = {
            "name": name,
            "signed": None if per_season else signed,
            "encoded": None if per_season else diy.encode_weights(signed),
            "capped": capped,
            "market_capped": hit,
            "weights": w,
            "max_season": max_season,
            "evaluate": ev,
            "extras": _extras(w, P, max_season),
            "season": {
                "season": season,
                "game_id": sp["game_id"],
                "p": sp["p"],
                "a": sp["calib_a"],
                "c": sp["calib_c"],
            },
        }
        if not per_season and sum(abs(v) for v in w.values()):
            case["fit_toward"] = diy.fit_toward(w, m, max_season=max_season)
        cases.append(case)

    for name, signed in sets.items():
        run(name, signed)
    run("student_fitted", student_by_season, per_season=True)
    run("even_hidden", even, max_season=DIY_MAX_SEASON)
    run("analyst_hidden", pers["analyst"], max_season=DIY_MAX_SEASON)

    caps = [
        {"quality": 50.0, "offense": 20.0, "market": 60.0},
        {"quality": 50.0, "market": -90.0},
        {"quality": 80.0, "market": 20.0},
        {"market": 40.0},
        {"quality": -30.0, "form": 10.0, "market": 5.0},
    ]
    decode = [
        "quality:30,form:-10",
        "quality:30,bogus:5,market:abc,buzz:1e3,health:-250,offense",
        "",
        "quality:inf,form:nan,coaching:12.5,,stakes:-0",
        "quality:1e-05,defense:123456789",
    ]
    doc = {
        "group_ids": diy.GROUP_IDS,
        "market_cap": diy.MARKET_GROUP_CAP,
        "seasons": list(DIY_SEASONS),
        "cap_market": [{"signed": c, "out": list(diy.cap_market(c))} for c in caps],
        "decode": [{"s": s, "out": diy.decode_weights(s)} for s in decode],
        "cases": cases,
    }
    OUT_DIY.mkdir(parents=True, exist_ok=True)
    (OUT_DIY / "matrix.json").write_text(json.dumps(m, separators=(",", ":")) + "\n")
    (OUT_DIY / "parity.json").write_text(json.dumps(_clean(doc), separators=(",", ":")) + "\n")
    total = sum(p.stat().st_size for p in OUT_DIY.glob("*.json"))
    print(f"wrote diy parity fixtures to {OUT_DIY} ({total / 1024:.0f} KB, {m['n']} matrix rows)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--diy", action="store_true", help="write the evaluator parity fixtures instead"
    )
    if ap.parse_args().diy:
        diy_main()
    else:
        main()
