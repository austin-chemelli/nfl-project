"""Coordinator / play-caller table (2016-2026), one row per (season, team).

The CSV is hand-researched (see .notes/coordinators-validation.md); empty cells mean "not
established", never a guess.
"""

from __future__ import annotations

import json
import math
from importlib import resources

import polars as pl

from nfl.config import Paths, current_season, now_utc
from nfl.models.elo import TEAM_ALIASES

_SCHEMA = {
    "season": pl.Int64,
    "team": pl.Utf8,
    "head_coach": pl.Utf8,
    "offensive_coordinator": pl.Utf8,
    "defensive_coordinator": pl.Utf8,
    "off_play_caller": pl.Utf8,
    "def_play_caller": pl.Utf8,
    "changed_midseason": pl.Boolean,
    "notes": pl.Utf8,
    "source_url": pl.Utf8,
}
_PERSON_COLS = [
    "head_coach",
    "offensive_coordinator",
    "defensive_coordinator",
    "off_play_caller",
    "def_play_caller",
]


def load_coordinators() -> pl.DataFrame:
    """All season-team rows; empty cells are null."""
    data = resources.files("nfl.data").joinpath("coordinators.csv").read_bytes()
    return pl.read_csv(data, schema_overrides=_SCHEMA).with_columns(
        pl.col(pl.Utf8).replace("", None)
    )


def coordinator_seasons(name: str) -> pl.DataFrame:
    """Every season-team where `name` (case-insensitive exact match) was OC, DC, or play-caller."""
    needle = name.strip().casefold()
    df = load_coordinators()
    role = (
        pl.when(pl.col("offensive_coordinator").str.to_lowercase() == needle)
        .then(pl.lit("OC"))
        .when(pl.col("defensive_coordinator").str.to_lowercase() == needle)
        .then(pl.lit("DC"))
        .when(pl.col("off_play_caller").str.to_lowercase() == needle)
        .then(pl.lit("off_play_caller"))
        .otherwise(pl.lit("def_play_caller"))
    )
    hit = pl.any_horizontal(*(pl.col(c).str.to_lowercase() == needle for c in _PERSON_COLS[1:]))
    return df.filter(hit).with_columns(role.alias("role")).sort("season", "team")


# ------------------------------------------------------------------------------------- profiles
# Scheme profiles (M1.16, M5.14). A "profile" is what a person's unit did in the seasons he held a
# job, measured against that season's league: the charting provider changed in 2023 (league man
# rate 0.29 in 2022, 0.42 in 2023, 0.49 in 2024, 0.31 in 2025) and coverage exists only from 2018,
# so raw rates are never averaged across seasons. Everything below works on within-season
# percentiles (and deviations from that season's league mean).


DECAY = 0.7  # recency weight per season back (the latest completed season counts 1)
MIN_N = 50  # plays behind a team-season rate, else the rate is treated as missing
CONSISTENT = 0.12  # mean spread (std of percentile across seasons) at or under: "very consistent"
MIXED = 0.20  # at or under: "fairly consistent"; above: "changes a lot"
MIN_SEASONS_CONSISTENCY = 3


def _metric(side, label, kind, noun, hi, lo, help_, unit="pct"):
    return {
        "side": side, "label": label, "kind": kind, "noun": noun, "hi": hi, "lo": lo,
        "help": help_, "unit": unit,
    }  # fmt: skip


# kind 'scheme' = what the unit chose to do; 'result' = how it fared (EPA per play, scheme-adjacent)
METRICS: dict[str, dict] = {
    "pers_11_share": _metric(
        "off",
        "11 personnel (3 WR)",
        "scheme",
        "11 personnel",
        "more",
        "less",
        "Share of offensive snaps with 1 back, 1 tight end and 3 receivers.",
    ),
    "pers_12_share": _metric(
        "off",
        "12 personnel (2 TE)",
        "scheme",
        "12 personnel",
        "more",
        "less",
        "Share of offensive snaps with 1 back, 2 tight ends and 2 receivers.",
    ),
    "pers_heavy_share": _metric(
        "off",
        "Heavy sets",
        "scheme",
        "heavy personnel (2+ TE or 2+ RB)",
        "more",
        "less",
        "Share of snaps with two or more tight ends or two or more backs.",
    ),
    "shotgun_share": _metric(
        "off",
        "Shotgun",
        "scheme",
        "shotgun",
        "more",
        "less",
        "Share of offensive snaps taken from shotgun or pistol.",
    ),
    "time_to_throw": _metric(
        "off",
        "Time to throw",
        "scheme",
        "time to throw",
        "longer",
        "shorter",
        "Average seconds from snap to throw on charted dropbacks. Mixes the QB, the protection "
        "and the play design.",
        unit="seconds",
    ),
    "pressure_allowed_rate": _metric(
        "off",
        "Pressure allowed",
        "scheme",
        "pressure allowed",
        "more",
        "less",
        "Share of charted dropbacks where the QB was pressured.",
    ),
    "epa_vs_man": _metric(
        "off",
        "EPA/dropback vs man",
        "result",
        "EPA per dropback against man coverage",
        "higher",
        "lower",
        "Expected points added per dropback against man coverage (2018+ charting).",
        unit="epa",
    ),
    "epa_vs_zone": _metric(
        "off",
        "EPA/dropback vs zone",
        "result",
        "EPA per dropback against zone coverage",
        "higher",
        "lower",
        "Expected points added per dropback against zone coverage (2018+ charting).",
        unit="epa",
    ),
    "epa_vs_pressure": _metric(
        "off",
        "EPA/dropback under pressure",
        "result",
        "EPA per dropback under pressure",
        "higher",
        "lower",
        "Expected points added per dropback when the QB was pressured.",
        unit="epa",
    ),
    "man_rate": _metric(
        "def",
        "Man coverage",
        "scheme",
        "man coverage",
        "more",
        "less",
        "Share of charted dropbacks defended in man coverage (2018+). Compare within a season "
        "only: the charting provider changed in 2023.",
    ),
    "two_high_rate": _metric(
        "def",
        "Two-high shells",
        "scheme",
        "two-high safety shells",
        "more",
        "less",
        "Share of charted dropbacks with two safeties deep at the snap (2018+).",
    ),
    "blitz_rate": _metric(
        "def",
        "Five-plus rushers",
        "scheme",
        "five-plus pass rushers",
        "more",
        "less",
        "Share of dropbacks with five or more pass rushers.",
    ),
    "pressure_rate": _metric(
        "def",
        "Pressure rate",
        "scheme",
        "pressure",
        "more",
        "less",
        "Share of charted dropbacks where the defense pressured the QB.",
    ),
    "epa_allowed_vs_11": _metric(
        "def",
        "EPA allowed vs 11 personnel",
        "result",
        "EPA allowed against 11 personnel",
        "more",
        "less",
        "Expected points per play allowed against three-receiver sets.",
        unit="epa",
    ),
    "epa_allowed_vs_heavy": _metric(
        "def",
        "EPA allowed vs heavy sets",
        "result",
        "EPA allowed against heavy sets",
        "more",
        "less",
        "Expected points per play allowed against 2+ tight end or 2+ back sets.",
        unit="epa",
    ),
    "epa_allowed_man": _metric(
        "def",
        "EPA allowed in man",
        "result",
        "EPA allowed in man coverage",
        "more",
        "less",
        "Expected points per dropback allowed when in man coverage.",
        unit="epa",
    ),
    "epa_allowed_zone": _metric(
        "def",
        "EPA allowed in zone",
        "result",
        "EPA allowed in zone coverage",
        "more",
        "less",
        "Expected points per dropback allowed when in zone coverage.",
        unit="epa",
    ),
}
SCHEME_METRICS = {s: [m for m, d in METRICS.items() if d["side"] == s and d["kind"] == "scheme"]
                  for s in ("off", "def")}  # fmt: skip
ROLE_LABEL = {"off": "offensive play-caller", "def": "defensive play-caller"}


def _canon(team: pl.Expr) -> pl.Expr:
    return team.replace(TEAM_ALIASES)


def assignments() -> pl.DataFrame:
    """One row per (season, team, side): the person whose scheme that unit ran.

    Offense uses `off_play_caller` when present, else the OC; defense `def_play_caller`, else the
    DC. `source` says which ('play_caller' | 'coordinator'). `team` is the franchise code (OAK->LV,
    SD->LAC, STL->LA); `team_printed` keeps the CSV's code. Mid-season changes use the CSV's
    end-of-season person. Units with nobody established are dropped."""
    df = load_coordinators()
    parts = []
    for side, caller, coord in (
        ("off", "off_play_caller", "offensive_coordinator"),
        ("def", "def_play_caller", "defensive_coordinator"),
    ):
        parts.append(
            df.select(
                "season",
                _canon(pl.col("team")).alias("team"),
                pl.col("team").alias("team_printed"),
                pl.lit(side).alias("side"),
                pl.coalesce(caller, coord).alias("person"),
                pl.when(pl.col(caller).is_not_null())
                .then(pl.lit("play_caller"))
                .otherwise(pl.lit("coordinator"))
                .alias("source"),
                pl.col("head_coach"),
                pl.col("changed_midseason"),
            )
        )
    return pl.concat(parts).filter(pl.col("person").is_not_null()).sort("season", "team", "side")


def league_percentiles(rates: pl.DataFrame) -> pl.DataFrame:
    """Team-season rates with within-season percentile and league mean.

    pct = (mid-rank - 0.5) / N among teams with n >= MIN_N that season, so 0..1 exclusive and a
    tie sits in the middle. Only METRICS are kept. Teams are canonicalised to franchises."""
    r = (
        rates.filter(pl.col("metric").is_in(list(METRICS)) & (pl.col("n") >= MIN_N))
        .filter(pl.col("rate").is_not_null() & pl.col("rate").is_not_nan())
        .with_columns(_canon(pl.col("team")).alias("team"))
    )
    g = ["season", "side", "metric"]
    return r.with_columns(
        ((pl.col("rate").rank("average").over(g) - 0.5) / pl.len().over(g)).alias("pct"),
        pl.col("rate").mean().over(g).alias("league_mean"),
    ).select("season", "team", "side", "metric", "n", "rate", "pct", "league_mean")


def profile_rows(paths: Paths) -> pl.DataFrame:
    """Per person-season-metric: the unit's rate, within-season percentile and deviation from the
    league mean. Columns: person, side, source, season, team, metric, n, rate, pct, league_mean,
    dev. Units without a rate for a metric simply have no row for it."""
    rates = pl.read_parquet(paths.marts / "scheme_team_season.parquet")
    lp = league_percentiles(rates)
    return (
        assignments()
        .join(lp, on=["season", "team", "side"], how="inner")
        .with_columns((pl.col("rate") - pl.col("league_mean")).alias("dev"))
        .select("person", "side", "source", "season", "team", "metric", "n", "rate", "pct",
                "league_mean", "dev", "team_printed", "head_coach")
        .sort("person", "side", "season", "metric")
    )  # fmt: skip


def consistency_label(spread: float | None, n_seasons: int) -> str | None:
    if spread is None or n_seasons < MIN_SEASONS_CONSISTENCY:
        return None
    if spread <= CONSISTENT:
        return "very consistent"
    if spread <= MIXED:
        return "fairly consistent"
    return "changes a lot"


def priors(rows: pl.DataFrame, target: int) -> pl.DataFrame:
    """Profile of each (person, side, metric) from seasons strictly before `target`.

    prior_pct / prior_dev: recency-weighted (DECAY ** (target - 1 - season)) mean of the
    within-season percentile / deviation from the league mean, over seasons with a rate.
    spread: std (population) of that metric's percentile across those seasons (needs >= 2).
    Also n_seasons, first/last season, teams (comma list in order held)."""
    past = rows.filter(pl.col("season") < target)
    if past.is_empty():
        return pl.DataFrame(
            schema={"person": pl.Utf8, "side": pl.Utf8, "metric": pl.Utf8, "prior_pct": pl.Float64,
                    "prior_dev": pl.Float64, "spread": pl.Float64, "n_metric_seasons": pl.UInt32,
                    "target": pl.Int64}
        )  # fmt: skip
    w = (DECAY ** (target - 1 - pl.col("season"))).alias("w")
    out = (
        past.with_columns(w)
        .group_by("person", "side", "metric")
        .agg(
            ((pl.col("pct") * pl.col("w")).sum() / pl.col("w").sum()).alias("prior_pct"),
            ((pl.col("dev") * pl.col("w")).sum() / pl.col("w").sum()).alias("prior_dev"),
            pl.when(pl.len() >= 2).then(pl.col("pct").std(ddof=0)).alias("spread"),
            pl.len().alias("n_metric_seasons"),
        )
    )
    return out.with_columns(pl.lit(target).alias("target"))


def person_summary(rows: pl.DataFrame, target: int) -> pl.DataFrame:
    """Per (person, side) before `target`: seasons held, first/last, teams, n_teams, mean play count,
    and `spread` = mean over the side's scheme metrics of the across-season percentile spread."""
    past = rows.filter(pl.col("season") < target)
    # a season counts if the unit has any rate that season
    seasons = past.select("person", "side", "season", "team").unique()
    base = (
        seasons.sort("season")
        .group_by("person", "side", maintain_order=True)
        .agg(
            pl.col("season").n_unique().alias("n_seasons"),
            pl.col("season").min().alias("first_season"),
            pl.col("season").max().alias("last_season"),
            pl.col("team").unique(maintain_order=True).alias("teams"),
        )
        .with_columns(pl.col("teams").list.len().alias("n_teams"))
    )
    p = priors(rows, target)
    scheme = p.filter(pl.col("metric").is_in([m for ms in SCHEME_METRICS.values() for m in ms]))
    sp = scheme.group_by("person", "side").agg(pl.col("spread").mean().alias("spread"))
    out = base.join(sp, on=["person", "side"], how="left")
    return out.with_columns(
        pl.struct("spread", "n_seasons")
        .map_elements(
            lambda s: consistency_label(s["spread"], s["n_seasons"]), return_dtype=pl.Utf8
        )
        .alias("consistency"),
        pl.lit(target).alias("target"),
    )


# --------------------------------------------------------------------------------- site / sentences


def _r(x, nd: int = 4):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), nd)


def _span(n_seasons: int, first: int, n_teams: int) -> str:
    teams = f"{n_teams} team" + ("s" if n_teams != 1 else "")
    return (
        f"{n_seasons} season{'s' if n_seasons != 1 else ''} of history since {first} across {teams}"
    )


def sentence(name: str, role: str, prior: dict | None, season: int) -> str:
    """Plain-language headline for one person's prior profile (what `prior_pct`s say)."""
    if not prior or not prior.get("n_seasons"):
        return (
            f"{role} {name} has no participation history yet; {season} tendencies come only "
            "from news (see the game page narrative)."
        )
    pcts = {m: v["pct"] for m, v in prior["metrics"].items()
            if METRICS[m]["kind"] == "scheme" and v["pct"] is not None}  # fmt: skip
    n = prior["n_seasons"]
    seasons = f"the last {n} seasons" if n > 1 else "one season of data"
    cons = prior.get("consistency")
    tail = f"; {cons}" if cons else "; too few seasons to judge consistency"
    if not pcts:
        return f"{role} {name}: not enough charted plays in {seasons} to profile.{''}"
    m = max(pcts, key=lambda k: abs(pcts[k] - 0.5))
    p = pcts[m]
    d = METRICS[m]
    if abs(p - 0.5) < 0.15:
        return (
            f"{role} {name} sits near the league average on everything we track over {seasons}"
            f"{tail}."
        )
    word, share = (d["hi"], p) if p >= 0.5 else (d["lo"], 1 - p)
    return (
        f"{role} {name} has shown {word} {d['noun']} than {share * 100:.0f}% of the league over "
        f"{seasons}{tail}."
    )


def _prior_block(pr: pl.DataFrame, sm: pl.DataFrame, person: str, side: str) -> dict | None:
    s = sm.filter((pl.col("person") == person) & (pl.col("side") == side))
    if s.is_empty():
        return None
    r = s.row(0, named=True)
    ms = {
        x["metric"]: {"pct": _r(x["prior_pct"]), "dev": _r(x["prior_dev"]),
                      "spread": _r(x["spread"]), "seasons": x["n_metric_seasons"]}
        for x in pr.filter((pl.col("person") == person) & (pl.col("side") == side)).to_dicts()
    }  # fmt: skip
    return {
        "n_seasons": r["n_seasons"], "first_season": r["first_season"],
        "last_season": r["last_season"], "teams": r["teams"], "n_teams": r["n_teams"],
        "spread": _r(r["spread"]), "consistency": r["consistency"], "target": r["target"],
        "history": _span(r["n_seasons"], r["first_season"], r["n_teams"]), "metrics": ms,
    }  # fmt: skip


def _summary(pr, sm, person: str, side: str, current: int) -> dict | None:
    block = _prior_block(pr, sm, person, side)
    if block is None:
        return None
    block["sentence"] = sentence(person, ROLE_LABEL[side].capitalize(), block, current)
    return block


def _qb_lookup(paths: Paths) -> dict[tuple[int, str], dict]:
    f = paths.marts / "scheme_qb_season.parquet"
    if not f.exists():
        return {}
    q = pl.read_parquet(f).filter(pl.col("side") == "off")
    out = {}
    for x in q.to_dicts():
        out[(x["season"], TEAM_ALIASES.get(x["team"], x["team"]))] = {
            "name": x["passer_player_name"], "dropbacks": x["qb_dropbacks"],
            "epa": _r(x["epa_all"]),
        }  # fmt: skip
    return out


def build_profiles(paths: Paths, current: int | None = None) -> dict:
    """Write marts/coach_profiles.parquet and marts/site/coaches.json. Returns a small report."""
    current = current or max(current_season(), int(load_coordinators()["season"].max()))
    rows = profile_rows(paths)
    pr = priors(rows, current)
    sm = person_summary(rows, current)
    qb = _qb_lookup(paths)

    paths.marts.mkdir(parents=True, exist_ok=True)
    rows.drop("head_coach").write_parquet(paths.marts / "coach_profiles.parquet")
    pr.write_parquet(paths.marts / "coach_priors.parquet")

    assign = assignments()
    people = []
    for (person,), grp in rows.group_by(["person"], maintain_order=True):
        sides = []
        for side in ("off", "def"):
            g = grp.filter(pl.col("side") == side)
            if g.is_empty():
                continue
            seasons = []
            for (season, team), sg in g.group_by(["season", "team"], maintain_order=True):
                first = sg.row(0, named=True)
                seasons.append({
                    "season": season, "team": team, "source": first["source"],
                    "partial": season >= current,
                    "qb": qb.get((season, team)) if side == "off" else None,
                    "metrics": {x["metric"]: {"rate": _r(x["rate"]), "pct": _r(x["pct"]),
                                              "n": x["n"], "league": _r(x["league_mean"])}
                                for x in sg.to_dicts()},
                })  # fmt: skip
            sides.append(
                {
                    "side": side,
                    "role": ROLE_LABEL[side],
                    "seasons": sorted(seasons, key=lambda s: s["season"]),
                    "summary": _summary(pr, sm, person, side, current),
                }
            )
        people.append({"name": person, "sides": sides})

    cur = assign.filter(pl.col("season") == current)
    hc = load_coordinators().filter(pl.col("season") == current)
    teams = {}
    for h in hc.to_dicts():
        t = TEAM_ALIASES.get(h["team"], h["team"])
        block = {"head_coach": h["head_coach"], "team_printed": h["team"], "off": None, "def": None}
        for side in ("off", "def"):
            a = cur.filter((pl.col("team") == t) & (pl.col("side") == side))
            if a.is_empty():
                continue
            r = a.row(0, named=True)
            prior = _prior_block(pr, sm, r["person"], side)
            block[side] = {
                "name": r["person"], "source": r["source"],
                "is_head_coach": r["person"] == h["head_coach"],
                "has_history": prior is not None,
                "prior": prior,
                "sentence": sentence(r["person"], ROLE_LABEL[side].capitalize(), prior, current),
            }  # fmt: skip
        teams[t] = block

    league: dict = {}
    for x in (
        rows.select("season", "side", "metric", "league_mean").unique().sort("season").to_dicts()
    ):
        league.setdefault(str(x["season"]), {}).setdefault(x["side"], {})[x["metric"]] = _r(
            x["league_mean"]
        )
    obj = {
        "generated_at": now_utc().isoformat(),
        "current_season": current,
        "decay": DECAY,
        "metrics": METRICS,
        "consistency_thresholds": {"very": CONSISTENT, "fairly": MIXED},
        "note": (
            "Percentiles are within-season vs the league. Coverage data starts 2018; the "
            "charting provider changed in 2023, so man and two-high rates shift league-wide."
        ),
        "people": people,
        "teams": teams,
        "league": league,
    }
    out = paths.site / "coaches.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(obj, indent=1, default=str))
    return {"rows": rows.height, "people": len(people), "teams": len(teams), "path": str(out)}  # fmt: skip
