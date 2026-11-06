"""Which measures say anything about a team's playoff chances beyond its record? (Similar seasons
round 2, .notes/plans/similar-insights.md; the flag list in nfl/league/similar.py comes from this.)
Read-only: reads curated games, the feature store and site/teams.json (for each measure's
direction) under DATA_ROOT and prints Markdown. Never writes under DATA_ROOT.

Method. Teams at 6, 8, 10 and 12 games played, 2002 to 2025. A team is "flagged" on a measure when
it sits in the measure's worst quarter (best quarter for the second table; the low end if the
measure has no direction), judged against that season's teams at the same games played, since EPA levels drift over the years. The effect is the
flagged teams' rate minus the other teams' rate among teams with the same games played and wins,
weighted by the flagged teams in each cell, in points. Intervals: season bootstrap (whole seasons
resampled, 300 draws, fixed seeds). Pooled table: Benjamini-Hochberg at 10% across measures on the
made-the-playoffs effect ("*"). Split-half table: 2002-13 against 2014-25 for the shortlisted
measures. "deep" is reaching a conference game.

Usage: uv run python scripts/league_flags.py DATA_ROOT
"""

from __future__ import annotations

import argparse
import json
from math import erf, sqrt
from pathlib import Path

import numpy as np
import polars as pl

from nfl.config import Paths
from nfl.features import store

GAMES_AT = (6, 8, 10, 12)
FIRST, LAST = 2002, 2025
DRAWS = 300
SEED_POOLED, SEED_SPLIT = 7, 11
BH_Q = 0.10
CUTS = ((2002, 2013), (2014, 2025))
ROUND = {"WC": 1, "DIV": 2, "CON": 3, "SB": 4}
# (measure, end, label) for the split-half table: the shortlist, kept and rejected.
SHORTLIST = (
    ("strength.epa_off_adj", "lo", "RED offense"),
    ("strength.qb_epa", "lo", "RED qb"),
    ("strength.pythag_win_pct", "lo", "RED scoring margin"),
    ("strength.luck", "hi", "RED luck high"),
    ("strength.elo_pre", "hi", "GREEN long-run"),
    ("strength.qb_epa", "hi", "GREEN qb"),
    ("strength.epa_off_adj", "hi", "GREEN offense"),
    ("strength.point_diff_pg", "hi", "GREEN margin"),
    ("strength.luck", "lo", "GREEN unlucky"),
    ("strength.epa_def", "lo", "OK defense"),
    ("decisions.turnover_margin_pg", "lo", "OK turnovers"),
    ("form.last3_win_pct", "lo", "OK last 3"),
    ("form.epa_trend", "lo", "OK trend"),
    ("form.streak", "lo", "OK streak"),
    ("strength.st_epa_pg", "lo", "OK special teams"),
    ("strength.epa_rush_off", "lo", "OK rushing off"),
)  # fmt: skip


def load(root: Path):
    paths = Paths(root)
    teams = json.loads((root / "marts/site/teams.json").read_text())
    better = {f["id"]: f["better"] for f in teams["features"]}
    g = store.games_frame(paths).filter((pl.col("season") >= FIRST) & (pl.col("season") <= LAST))
    reg = g.filter(pl.col("game_type") == "REG").with_columns(
        pl.col("kickoff_utc").dt.replace_time_zone(None)
    )
    reached: dict[tuple[int, str], int] = {}
    for r in g.filter(pl.col("game_type") != "REG").iter_rows(named=True):
        for t in (r["home_team"], r["away_team"]):
            k = (r["season"], t)
            reached[k] = max(reached.get(k, 0), ROUND[r["game_type"]])
    side = lambda a, b, s: reg.select(
        "season", "game_id", "kickoff_utc",
        pl.col(f"{a}_team").alias("team"), pl.lit(s).alias("side"),
        pl.col(f"{a}_score").alias("pf"), pl.col(f"{b}_score").alias("pa"),
    )  # fmt: skip
    long = pl.concat([side("home", "away", "home"), side("away", "home", "away")])
    long = long.sort("season", "team", "kickoff_utc", "game_id").with_columns(
        pl.int_range(pl.len()).over("season", "team").alias("idx"),
        (
            (pl.col("pf") > pl.col("pa")).cast(pl.Float64)
            + 0.5 * (pl.col("pf") == pl.col("pa")).cast(pl.Float64)
        ).alias("w"),
    )
    long = long.with_columns(
        (pl.col("w").cum_sum().over("season", "team") - pl.col("w")).round(0).alias("wb")
    )
    feats = (
        store.read_features(paths, seasons=(FIRST, LAST))
        .filter(pl.col("feature").is_in(list(better)) & pl.col("side").is_in(["home", "away"]))
        .select("game_id", "side", "feature", "value")
    )
    wide = feats.pivot(on="feature", index=["game_id", "side"], values="value", aggregate_function="first")  # fmt: skip
    tab = long.join(wide, on=["game_id", "side"], how="left")
    parts = [tab.filter(pl.col("idx") == n).with_columns(pl.lit(n).alias("n")) for n in GAMES_AT]
    a = pl.concat(parts).with_columns(
        pl.struct("season", "team")
        .map_elements(lambda r: reached.get((r["season"], r["team"]), 0), return_dtype=pl.Int64)
        .alias("rnd")
    )
    a = a.with_columns(
        (pl.col("rnd") > 0).cast(pl.Float64).alias("made"),
        (pl.col("rnd") >= 3).cast(pl.Float64).alias("deep"),
    )
    ids = [c for c in wide.columns if c not in ("game_id", "side")]
    return a, ids, better


def _prep(d: pl.DataFrame, f: str, end: str, better: dict):
    sign = -1.0 if better[f] == "lower" else 1.0
    d = d.select("season", "n", "wb", "made", "deep", pl.col(f).alias("v")).drop_nulls("v")
    d = d.with_columns((pl.col("v") * sign).alias("x"))
    d = d.with_columns(pl.col("x").rank("average").over("n", "season").alias("r"), pl.len().over("n", "season").alias("c"))  # fmt: skip
    frac = (d["r"] / d["c"]).to_numpy()
    top = ((d["c"] - d["r"] + 1) / d["c"]).to_numpy()
    lo = frac <= 0.25 if end == "lo" else top <= 0.25
    return d, lo, (d["n"] * 100 + d["wb"]).to_numpy()


def _est(cell, lo, v, ix) -> float:
    c, flagged, vv = cell[ix], lo[ix], v[ix]
    num = den = 0.0
    for k in np.unique(c):
        m = c == k
        a, b = m & flagged, m & ~flagged
        if a.sum() and b.sum():
            num += a.sum() * (vv[a].mean() - vv[b].mean())
            den += a.sum()
    return num / den if den else 0.0


def effect(d, lo, cell, y: str, rng) -> tuple[float, float, float, float]:
    """(estimate, standard error, 2.5%, 97.5%) of the same-record effect on outcome y."""
    v, sea = d[y].to_numpy(), d["season"].to_numpy()
    seasons = np.unique(sea)
    by = {s: np.flatnonzero(sea == s) for s in seasons}
    est = _est(cell, lo, v, np.arange(len(cell)))
    b = np.array([
        _est(cell, lo, v, np.concatenate([by[s] for s in rng.choice(seasons, len(seasons))]))
        for _ in range(DRAWS)
    ])  # fmt: skip
    return est, b.std(ddof=1), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def bh(pvals: list[float]) -> set[int]:
    """Indexes kept by Benjamini-Hochberg at BH_Q."""
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m, last = len(pvals), 0
    for k, i in enumerate(order, 1):
        if pvals[i] <= BH_Q * k / m:
            last = k
    return set(order[:last])


def pooled(a, ids, better) -> list[str]:
    rng = np.random.default_rng(SEED_POOLED)
    out = []
    for end, title in (
        ("lo", "Worst quarter on the measure (low end if neutral) against same-record peers"),
        ("hi", "Best quarter on the measure (high end if neutral) against same-record peers"),
    ):
        rows = []
        for f in ids:
            if a[f].drop_nulls().len() < 0.8 * a.height:
                continue
            d, lo, cell = _prep(a, f, end, better)
            made, deep = effect(d, lo, cell, "made", rng), effect(d, lo, cell, "deep", rng)
            rows.append((f, made, deep))
        p = [2 * (1 - 0.5 * (1 + erf(abs(m[0] / m[1]) / sqrt(2)))) if m[1] > 0 else 1.0 for _, m, _ in rows]  # fmt: skip
        keep = bh(p)
        out += [
            f"\n#### {title}\n",
            "Points of playoff chance (made) and of reaching a conference game (deep), 95% season-bootstrap interval. `*` = survives Benjamini-Hochberg at 10% across measures.\n",
            "| | made | 95% | deep | 95% | measure | better |",
            "|---|---|---|---|---|---|---|",
        ]
        for i in sorted(range(len(rows)), key=lambda i: rows[i][1][0]):
            f, m, dp = rows[i]
            out.append(
                f"| {'*' if i in keep else ''} | {m[0] * 100:+.1f} | [{m[2] * 100:+.1f}, {m[3] * 100:+.1f}] "
                f"| {dp[0] * 100:+.1f} | [{dp[2] * 100:+.1f}, {dp[3] * 100:+.1f}] | `{f}` | {better[f]} |"
            )
    return out


def split(a, better) -> list[str]:
    rng = np.random.default_rng(SEED_SPLIT)
    out = [
        "\n#### Split half (2002-13 against 2014-25)\n",
        "| measure | end | made 2002-13 | made 2014-25 | deep 2002-13 | deep 2014-25 |",
        "|---|---|---|---|---|---|",
    ]
    for f, end, lab in SHORTLIST:
        if f not in a.columns:
            continue
        cells = []
        for y in ("made", "deep"):
            for lo_s, hi_s in CUTS:
                d, lo, cell = _prep(
                    a.filter(pl.col("season").is_between(lo_s, hi_s)), f, end, better
                )
                e = effect(d, lo, cell, y, rng)
                cells.append(f"{e[0] * 100:+.1f} [{e[2] * 100:+.1f}, {e[3] * 100:+.1f}]")
        out.append(f"| {lab} (`{f}`) | {end} | " + " | ".join(cells) + " |")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root", type=Path, help="data root with curated/ and marts/ (read only)")
    root = ap.parse_args().root
    a, ids, better = load(root)
    print(
        f"Teams at {GAMES_AT} games, {FIRST}-{LAST}: {a.height} team-seasons, {len(ids)} measures."
    )
    print("\n".join(pooled(a, ids, better)))
    print("\n".join(split(a, better)))


if __name__ == "__main__":
    main()
