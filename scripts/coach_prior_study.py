"""How much of a play-caller's past carries over, and when (M17.5, ADR 0021).

For each unit-season from 2017 and each tendency metric, predict the unit's within-season
percentile from (a) the caller's own prior, (b) the team's previous season, (c) a blend, split by
situation: same caller, same caller with a new quarterback, a caller who moved teams, a first-time
caller promoted from the same staff, a first-time caller from outside. Scores are mean absolute
error in percentile points. The blend weight is chosen leaving one season out, so the blend's MAE
isn't flattered by its own fit. Writes `data/coach_blend.json`, which the team files read.

  uv run python scripts/coach_prior_study.py [--out .notes/coach-prior-study.md]
"""

from __future__ import annotations

import argparse
import json

import polars as pl

from nfl import coaches
from nfl import staff_context as ctx
from nfl.config import get_paths

DECAYS = (0.5, 0.7, 0.85, 1.0)
WEIGHTS = [i / 10 for i in range(11)]
FIRST_TARGET = 2017
FIRST_TIME_FROM = 2020
MIN_CELL = 25  # unit-seasons behind a measured weight; a metric with fewer uses its situation's
BLEND_FILE = "src/nfl/data/coach_blend.json"
SITUATIONS = tuple(ctx.SITUATION_TEXT)


def cases(assign, labels, rates, decay) -> pl.DataFrame:
    """One row per (unit-season, metric): actual, caller prior (may be null), team's last season."""
    prev = rates.select(
        (pl.col("season") + 1).alias("season"), "team", "side", "metric",
        pl.col("pct").alias("team_prev"),
    )  # fmt: skip
    return (
        labels.join(rates, on=["season", "team", "side"])
        .join(prev, on=["season", "team", "side", "metric"], how="left")
        .join(ctx.caller_prior(assign, rates, decay), on=["season", "person", "side", "metric"],
              how="left")
        .filter(pl.col("team_prev").is_not_null())
    )  # fmt: skip


def mae(df: pl.DataFrame, expr: pl.Expr) -> float | None:
    v = df.select((expr - pl.col("pct")).abs().mean()).item()
    return None if v is None else round(v * 100, 1)


def best_weight(df: pl.DataFrame) -> float:
    errs = {w: df.select((w * pl.col("prior") + (1 - w) * pl.col("team_prev") - pl.col("pct"))
                         .abs().mean()).item() for w in WEIGHTS}  # fmt: skip
    return min(errs, key=errs.get)


def loso_blend(df: pl.DataFrame) -> tuple[float, float]:
    """The weight on all seasons, and the blend's MAE with each season scored by a weight fitted
    on the others."""
    errs = []
    for s in df["season"].unique().to_list():
        w = best_weight(df.filter(pl.col("season") != s))
        held = df.filter(pl.col("season") == s)
        errs.append(
            held.select((w * pl.col("prior") + (1 - w) * pl.col("team_prev") - pl.col("pct")).abs())
            .to_series()
        )
    return best_weight(df), round(pl.concat(errs).mean() * 100, 1)


def units(d: pl.DataFrame) -> int:
    return d.select("season", "team").unique().height


def cell(d: pl.DataFrame) -> dict | None:
    """Weight, held-out miss and the league-middle miss for one group of cases. Sizes count
    unit-seasons, not unit-by-metric rows."""
    have = d.filter(pl.col("prior").is_not_null())
    if units(have) >= MIN_CELL:
        weight, miss = loso_blend(have)
        return {"weight": weight, "miss": miss, "league_miss": mae(have, pl.lit(0.5)),
                "cases": units(have)}  # fmt: skip
    rest = d.filter(pl.col("prior").is_null())  # no past of his own: the team's last season alone
    if units(rest) >= MIN_CELL:
        return {"weight": 0.0, "miss": mae(rest, pl.col("team_prev")),
                "league_miss": mae(rest, pl.lit(0.5)), "cases": units(rest)}  # fmt: skip
    return None


def blend_table(c: pl.DataFrame) -> dict:
    """{side: {situation: {'*' or metric: cell}}}. Metric cells only where they have the cases."""
    out: dict = {}
    for side in ("off", "def"):
        for sit in SITUATIONS:
            d = c.filter((pl.col("side") == side) & (pl.col("situation") == sit))
            whole = cell(d)
            if whole is None:
                continue
            cells = {"*": whole}
            for (metric,), g in d.group_by(["metric"], maintain_order=True):
                if (one := cell(g)) is not None:
                    cells[metric] = one
            out.setdefault(side, {})[sit] = cells
    return out


def table(c: pl.DataFrame, title: str) -> list[str]:
    lines = [f"### {title}", "",
             ("| Side | Situation | Unit-seasons | Cases | Caller's past | Team's last season | "
              "League middle | Blend (held out) | Weight on caller |"),
             "|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for side in ("off", "def"):
        for sit in SITUATIONS:
            d = c.filter((pl.col("side") == side) & (pl.col("situation") == sit))
            if d.is_empty():
                continue
            have = d.filter(pl.col("prior").is_not_null())
            scored = units(have) >= MIN_CELL or units(have) > units(d) / 2
            same = have if scored else d  # every column on the same cases
            caller = mae(have, pl.col("prior")) if scored else None
            team = mae(same, pl.col("team_prev"))
            mid = mae(same, pl.lit(0.5))
            w, blend = loso_blend(have) if units(have) >= MIN_CELL else (None, None)
            lines.append(
                f"| {side} | {sit} | {units(same)} | {same.height} | {caller if caller is not None else '–'} "
                f"| {team} | {mid} | {blend if blend is not None else '–'} "
                f"| {w if w is not None else '–'} |"
            )
    return [*lines, ""]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".notes/coach-prior-study.md")
    args = ap.parse_args()
    paths = get_paths()
    assign = coaches.assignments()
    labels = ctx.unit_situations(assign, ctx.primary_qbs(paths)).filter(
        (pl.col("season") >= FIRST_TARGET) & (pl.col("season") < coaches.current_season())
        & ~pl.col("unsettled")
        # The table starts in 2016, so before this anyone with an older career looks first-time.
        & ((pl.col("season") >= FIRST_TIME_FROM) | ~pl.col("situation").str.ends_with("first_time"))
    )  # fmt: skip
    sets = {"Live set (weekly in season)": ctx.live_rates(paths),
            "Charted set (participation, one drop a year)": ctx.charted_rates(paths)}  # fmt: skip
    out = ["# Coach prior study (M17.5)", "",
           ("Generated by `scripts/coach_prior_study.py`. MAE in percentile points of the "
            "unit's within-season rank; lower is better. `Caller's past` and the blend cover cases "
            "where the caller has history."), "",
           "Situation counts: " + ", ".join(
               f"{r['situation']} {r['len']}" for r in
               labels.group_by("situation").len().sort("situation").to_dicts()), ""]  # fmt: skip
    for name, rates in sets.items():
        out += [f"## {name}", "", "Decay, same-caller cases and caller moved, MAE of the prior:", ""]
        for d in DECAYS:
            c = cases(assign, labels, rates, d)
            h = c.filter(pl.col("prior").is_not_null())
            same = h.filter(pl.col("situation").is_in(["same_caller", "same_caller_new_qb"]))
            moved = h.filter(pl.col("situation") == "moved_team")
            out.append(f"- {d}: same caller {mae(same, pl.col('prior'))}, "
                       f"moved {mae(moved, pl.col('prior'))}")  # fmt: skip
        out.append("")
        out += table(cases(assign, labels, rates, coaches.DECAY), f"At decay {coaches.DECAY}")
        per = cases(assign, labels, rates, coaches.DECAY).filter(pl.col("prior").is_not_null())
        rows = []
        for (side, metric), g in per.group_by(["side", "metric"], maintain_order=True):
            moved = g.filter(pl.col("situation") == "moved_team")
            if moved.height:  # `per` holds only cases with a prior, so both columns match
                rows.append((side, metric, moved.height, mae(moved, pl.col("prior")),
                             mae(moved, pl.col("team_prev"))))  # fmt: skip
        out += ["### Caller moved, by metric", "", "| Side | Metric | Cases | Caller's past | Team's last season |",
                "|---|---|---|---|---|"]  # fmt: skip
        out += [f"| {a} | {b} | {n} | {x} | {y} |" for a, b, n, x, y in sorted(rows)] + [""]
    keys = dict(zip(sets, ("live", "charted"), strict=True))
    blend = {keys[n]: blend_table(cases(assign, labels, r, coaches.DECAY)) for n, r in sets.items()}
    with open(BLEND_FILE, "w") as f:
        json.dump(blend, f, indent=1)
    text = "\n".join(out)
    with open(args.out, "w") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
