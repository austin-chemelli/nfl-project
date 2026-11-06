"""What to expect from a team's play-callers this season (ADR 0021, M17.5, M17.6).

Two sets of tendencies. The live set (FTN and pbp rates in marts/tendencies.parquet) exists week by
week, so a unit shows "so far" against what was expected. The charted set (participation: personnel,
coverage, time to throw, pressure) arrives once a year, so in season it's a prediction only; the
observed value joins it after the spring drop.

Expected = weight * the caller's own past + (1 - weight) * the team's last season, both within-season
percentiles. The weights and error sizes come from scripts/coach_prior_study.py, per set, side,
situation and, where there are enough cases, metric (`data/coach_blend.json`).
"""

from __future__ import annotations

import json
from importlib import resources

import polars as pl

from nfl import coaches
from nfl.coaches import CONFIRMED, DECAY, METRICS, SCHEME_METRICS
from nfl.config import Paths, now_utc
from nfl.models.elo import TEAM_ALIASES

MIN_LIVE_N = 100  # plays behind a team-season rate on the live set
# The blend must beat always guessing the league middle by this much (percentile points) to be
# called anything better than a weak read.
WEAK_MARGIN = 3.0

LIVE: dict[str, list[str]] = {
    "off": ["pass_rate", "shotgun_rate", "no_huddle_rate", "motion_rate", "play_action_rate",
            "rpo_rate", "screen_rate", "under_center_rate"],
    "def": ["blitz_rate", "pass_rushers_5plus_rate", "box_8plus_vs_run_rate",
            "box_6minus_vs_run_rate"],
}  # fmt: skip
SITUATION_TEXT = {
    "same_caller": "Same play-caller as last season",
    "same_caller_new_qb": "Same play-caller, new starting quarterback",
    "moved_team": "New here, has called plays elsewhere",
    "promoted_first_time": "First year calling plays, promoted from this staff",
    "outside_first_time": "First year calling plays",
}


def _franchise(col: str = "team") -> pl.Expr:
    return pl.col(col).replace(TEAM_ALIASES)


def live_rates(paths: Paths) -> pl.DataFrame:
    """Live-set team-seasons: season, team, side, metric, n, rate, pct (within-season percentile)."""
    t = pl.read_parquet(paths.marts / "tendencies.parquet").filter(
        (pl.col("situation") == "all")
        & (pl.col("season") >= 2016)
        & (pl.col("n") >= MIN_LIVE_N)
        & pl.col("raw_rate").is_not_null()
    )
    t = pl.concat(
        [t.filter((pl.col("side") == s) & pl.col("metric").is_in(ms)) for s, ms in LIVE.items()]
    ).with_columns(_franchise())
    g = ["season", "side", "metric"]
    return t.with_columns(
        ((pl.col("raw_rate").rank("average").over(g) - 0.5) / pl.len().over(g)).alias("pct"),
        pl.col("raw_rate").alias("rate"),
    ).select("season", "team", "side", "metric", "n", "rate", "pct")


def charted_rates(paths: Paths) -> pl.DataFrame:
    """Charted-set team-seasons, the same columns as `live_rates`."""
    rates = pl.read_parquet(paths.marts / "scheme_team_season.parquet")
    keep = [m for ms in SCHEME_METRICS.values() for m in ms]
    return (
        coaches.league_percentiles(rates)
        .filter(pl.col("metric").is_in(keep))
        .select("season", "team", "side", "metric", "n", "rate", "pct")
    )


def primary_qbs(paths: Paths, season: int | None = None) -> dict[tuple[int, str], str]:
    """(season, franchise) -> the passer with the most dropbacks. Completed seasons come from the
    scheme mart; `season`, if given, from this season's plays."""
    q = pl.read_parquet(paths.marts / "scheme_qb_season.parquet").filter(pl.col("side") == "off")
    out = {
        (r["season"], TEAM_ALIASES.get(r["team"], r["team"])): r["passer_player_id"]
        for r in q.to_dicts()
    }
    if season is not None:
        plays = pl.scan_parquet(f"{paths.curated_table('plays').as_posix()}/season={season}/*.parquet")
        top = (
            plays.filter((pl.col("qb_dropback") == 1) & pl.col("passer_player_id").is_not_null())
            .group_by("posteam", "passer_player_id")
            .len()
            .collect()
            .sort("len", descending=True)
            .unique(subset="posteam", keep="first", maintain_order=True)
        )
        for r in top.to_dicts():
            out[(season, TEAM_ALIASES.get(r["posteam"], r["posteam"]))] = r["passer_player_id"]
    return out


def unit_situations(assign: pl.DataFrame, qbs: dict) -> pl.DataFrame:
    """Each unit-season with a previous season, labelled for how much its past should carry over.

    A caller is first-time if no earlier season has him as a named play-caller. `promoted` means he
    held the unit's coordinator title on this team the season before."""
    rows = assign.sort("season").to_dicts()
    by = {(x["season"], x["team"], x["side"]): x for x in rows}
    spells = coaches.load_spells().with_columns(_franchise())
    coords = {
        (r["season"], r["team"], r["role"]): r["person"]
        for r in spells.filter(pl.col("role").is_in(["OC", "DC"])).to_dicts()
    }
    first_called: dict[tuple[str, str], int] = {}
    for x in rows:
        if x["source"] == "play_caller":
            k = (x["person"], x["side"])
            first_called[k] = min(first_called.get(k, 9999), x["season"])
    out = []
    for x in rows:
        s, t, side, who = x["season"], x["team"], x["side"], x["person"]
        prev = by.get((s - 1, t, side))
        if prev is None:
            continue
        if who == prev["person"]:
            new_qb = side == "off" and qbs.get((s, t)) != qbs.get((s - 1, t))
            label = "same_caller_new_qb" if new_qb else "same_caller"
        elif first_called.get((who, side), 9999) >= s:
            title = "OC" if side == "off" else "DC"
            promoted = coords.get((s - 1, t, title)) == who
            label = "promoted_first_time" if promoted else "outside_first_time"
        else:
            label = "moved_team"
        out.append({
            "season": s, "team": t, "side": side, "person": who, "situation": label,
            "unsettled": bool(x["changed_midseason"] or prev["changed_midseason"]),
        })  # fmt: skip
    return pl.DataFrame(out)


def caller_prior(assign: pl.DataFrame, rates: pl.DataFrame, decay: float = DECAY) -> pl.DataFrame:
    """Recency-weighted mean percentile of each person's past units, per target season."""
    rows = assign.select("person", "side", "season", "team").join(
        rates, on=["season", "team", "side"]
    )
    targets = sorted({*rows["season"].to_list(), *assign["season"].to_list()})
    parts = []
    for target in targets:
        past = rows.filter(pl.col("season") < target)
        if past.is_empty():
            continue
        parts.append(
            past.with_columns((decay ** (target - 1 - pl.col("season"))).alias("w"))
            .group_by("person", "side", "metric")
            .agg(
                ((pl.col("pct") * pl.col("w")).sum() / pl.col("w").sum()).alias("prior"),
                pl.col("season").n_unique().alias("prior_seasons"),
                pl.col("team").unique(maintain_order=True).alias("prior_teams"),
            )
            .with_columns(pl.lit(target).alias("season"))
        )
    return pl.concat(parts)


def load_blend() -> dict:
    return json.loads(resources.files("nfl.data").joinpath("coach_blend.json").read_text())


def blend_cell(blend: dict, kind: str, side: str, situation: str, metric: str) -> dict | None:
    cells = blend.get(kind, {}).get(side, {}).get(situation)
    return None if cells is None else cells.get(metric, cells.get("*"))


def expected(prior: float | None, team_prev: float | None, cell: dict | None) -> dict | None:
    """The expected percentile, its typical miss and how far to trust it.

    With no past of his own it's the team's last season alone; with no team season, his past."""
    if prior is None and team_prev is None:
        return None
    if prior is None or team_prev is None or cell is None:
        weight = 1.0 if team_prev is None else 0.0
        if cell is None and prior is not None and team_prev is not None:
            weight = 0.5
    else:
        weight = cell["weight"]
    value = weight * (prior or 0.0) + (1 - weight) * (team_prev or 0.0)
    miss = cell["miss"] if cell else None
    league = cell["league_miss"] if cell else None
    weak = miss is None or league is None or league - miss < WEAK_MARGIN or prior is None
    return {
        "pct": round(value, 4),
        "miss": round(miss / 100, 4) if miss is not None else None,
        "weight_on_caller": weight,
        "strength": "weak" if weak else "fair",
    }


def backup_weeks(games: pl.DataFrame, team: str) -> list[dict]:
    """Weeks a team's starter wasn't its most frequent starter, from the schedule's QB names."""
    played = games.filter(pl.col("home_score").is_not_null())
    rows = []
    for side in ("home", "away"):
        g = played.filter(_franchise(f"{side}_team") == team)
        rows += [{"week": r["week"], "qb": r[f"{side}_qb_name"]} for r in g.to_dicts()]
    rows = [r for r in rows if r["qb"]]
    if not rows:
        return []
    names = [r["qb"] for r in rows]
    main = max(set(names), key=names.count)
    return sorted((r for r in rows if r["qb"] != main), key=lambda r: r["week"])


def _spell(r: dict) -> dict:
    return {
        "role": r["role"], "name": r["person"], "start_week": r["start_week"],
        "end_week": r["end_week"], "evidence": r["evidence"],
        "confirmed": r["evidence"] in CONFIRMED, "source_url": r["source_url"], "note": r["note"],
    }  # fmt: skip


def _caller(side: str, unit: dict | None, situation: dict | None, coordinator: str | None,
            head_coach: str | None, spell: dict | None) -> dict | None:  # fmt: skip
    if unit is None:
        return None
    confirmed = spell is not None and spell["evidence"] in CONFIRMED
    # An unconfirmed caller is never printed as one: the coordinator's title is what we can stand on.
    name = unit["person"] if confirmed else (coordinator or unit["person"])
    return {
        "name": name,
        "confirmed": confirmed,
        "is_head_coach": confirmed and name == head_coach,
        "evidence": spell["evidence"] if spell else None,
        "source_url": spell["source_url"] if spell else None,
        "situation": situation["situation"] if situation else None,
        "situation_text": SITUATION_TEXT.get(situation["situation"]) if situation else None,
    }


def _metric_rows(kind, side, unit, situation, prior, rates, season, blend, label) -> list[dict]:
    """One entry per metric: expected, and the observed value where this season has one."""
    metrics = LIVE[side] if kind == "live" else SCHEME_METRICS[side]
    out = []
    for m in metrics:
        p = prior.get(m) or {}
        prev = rates.get((season - 1, m))
        now = rates.get((season, m))
        sit = situation["situation"] if situation else None
        exp = expected(
            p.get("prior"), prev["pct"] if prev else None,
            blend_cell(blend, kind, side, sit, m) if sit else None,
        )  # fmt: skip
        out.append({
            "metric": m, **label(m),
            "expected": exp,
            "caller_seasons": p.get("prior_seasons", 0),
            "caller_teams": p.get("prior_teams", []),
            "team_last": {"season": season - 1, "pct": round(prev["pct"], 4),
                          "rate": round(prev["rate"], 4)} if prev else None,
            "observed": {"pct": round(now["pct"], 4), "rate": round(now["rate"], 4),
                         "n": now["n"]} if now else None,
        })  # fmt: skip
    return out


def team_files(paths: Paths, season: int, week: int, games: pl.DataFrame,
               metric_label) -> dict[str, dict]:  # fmt: skip
    """`site/team/<code>.json` bodies, keyed by team. `week` is the next week to be played.

    `metric_label(metric)` gives the live set's label and help; the charted set's come from
    `coaches.METRICS`."""
    assign = coaches.assignments()
    spells = coaches.load_spells().with_columns(_franchise())
    labels = unit_situations(assign, primary_qbs(paths, season))
    blend = load_blend()
    sets = {"live": live_rates(paths), "charted": charted_rates(paths)}
    priors = {
        k: caller_prior(assign, v).filter(pl.col("season") == season) for k, v in sets.items()
    }
    now = now_utc().isoformat()
    teams = sorted(assign.filter(pl.col("season") == season)["team"].unique().to_list())
    out = {}
    for team in teams:
        at = coaches.staff_at(season, team, week, spells).to_dicts()
        titled = {r["role"]: r["person"] for r in reversed(at)}
        calling = {r["role"]: r for r in at if r["role"] in ("OFF_PC", "DEF_PC")}
        body: dict = {
            "team": team, "season": season, "week": week, "generated_at": now,
            "staff": {"current": [_spell(r) for r in at],
                      "changes": [_spell(r) for r in spells.filter(
                          (pl.col("season") == season) & (pl.col("team") == team)
                          & (pl.col("start_week") > 1)).sort("start_week").to_dicts()]},
            "backup_weeks": backup_weeks(games, team),
            "units": {},
        }  # fmt: skip
        for side, title, pc in (("off", "OC", "OFF_PC"), ("def", "DC", "DEF_PC")):
            u = assign.filter(
                (pl.col("season") == season) & (pl.col("team") == team) & (pl.col("side") == side)
            ).to_dicts()
            unit = u[0] if u else None
            sit = labels.filter(
                (pl.col("season") == season) & (pl.col("team") == team) & (pl.col("side") == side)
            ).to_dicts()
            situation = sit[0] if sit else None
            block = {"caller": _caller(side, unit, situation, titled.get(title), titled.get("HC"),
                                       calling.get(pc))}  # fmt: skip
            for kind, rates in sets.items():
                mine = rates.filter((pl.col("team") == team) & (pl.col("side") == side))
                by_metric = {(r["season"], r["metric"]): r for r in mine.to_dicts()}
                prior = {}
                if unit:
                    prior = {
                        r["metric"]: r
                        for r in priors[kind]
                        .filter((pl.col("person") == unit["person"]) & (pl.col("side") == side))
                        .to_dicts()
                    }
                label = metric_label if kind == "live" else _charted_label
                block[kind] = _metric_rows(kind, side, unit, situation, prior, by_metric, season,
                                           blend, label)  # fmt: skip
            body["units"][side] = block
        out[team] = body
    return out


def _charted_label(metric: str) -> dict:
    d = METRICS[metric]
    return {"label": d["label"], "help": d["help"]}
