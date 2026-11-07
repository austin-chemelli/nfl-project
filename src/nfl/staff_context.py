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
    # blitz_rate is left out: FTN's n_blitzers looks redefined in 2026 (league 0.320, the same as
    # five-plus rushers, against a 2 to 4 point gap every year before).
    "def": ["pass_rushers_5plus_rate", "box_8plus_vs_run_rate", "box_6minus_vs_run_rate"],
}  # fmt: skip
# Charted measures that the live set already shows week by week: no need to predict them.
ALSO_LIVE = {"shotgun_share", "blitz_rate"}
SITUATION_TEXT = {
    "same_caller": "Same play-caller as last season",
    "same_caller_new_qb": "Same play-caller, new starting quarterback",
    "took_over": "Took over the calls, already on this staff",
    "moved_team": "New play-caller, has called plays before",
    "promoted_first_time": "First year calling NFL plays, promoted from this staff",
    "outside_first_time": "First year calling NFL plays",
}


def _franchise(col: str = "team") -> pl.Expr:
    return pl.col(col).replace(TEAM_ALIASES)


def _ranked(df: pl.DataFrame) -> pl.DataFrame:
    """Adds `rank` (1 = the most of it, ties share) and `of` (teams with a value that season)."""
    g = ["season", "side", "metric"]
    return df.with_columns(
        pl.col("rate").rank("min", descending=True).over(g).cast(pl.Int64).alias("rank"),
        pl.len().over(g).cast(pl.Int64).alias("of"),
    ).select("season", "team", "side", "metric", "n", "rate", "pct", "rank", "of")


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
    return _ranked(
        t.with_columns(
            ((pl.col("raw_rate").rank("average").over(g) - 0.5) / pl.len().over(g)).alias("pct"),
            pl.col("raw_rate").alias("rate"),
        )
    )


def charted_rates(paths: Paths) -> pl.DataFrame:
    """Charted-set team-seasons, the same columns as `live_rates`."""
    rates = pl.read_parquet(paths.marts / "scheme_team_season.parquet")
    keep = [m for ms in SCHEME_METRICS.values() for m in ms]
    return _ranked(coaches.league_percentiles(rates).filter(pl.col("metric").is_in(keep)))


def primary_qbs(paths: Paths, season: int | None = None) -> dict[tuple[int, str], str]:
    """(season, franchise) -> the passer with the most dropbacks. Completed seasons come from the
    scheme mart; `season`, if given, from this season's plays."""
    q = pl.read_parquet(paths.marts / "scheme_qb_season.parquet").filter(pl.col("side") == "off")
    out = {
        (r["season"], TEAM_ALIASES.get(r["team"], r["team"])): r["passer_player_id"]
        for r in q.to_dicts()
    }
    if season is not None:
        plays = pl.scan_parquet(
            f"{paths.curated_table('plays').as_posix()}/season={season}/*.parquet"
        )
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


class Situations:
    """Labels a person in a unit for how much its past should carry over."""

    def __init__(self, assign: pl.DataFrame, qbs: dict, spells: pl.DataFrame | None = None):
        self.qbs = qbs
        self.rows = assign.sort("season").to_dicts()
        self.by = {(x["season"], x["team"], x["side"]): x for x in self.rows}
        s = coaches.load_spells() if spells is None else spells
        s = s.with_columns(_franchise())
        self.staff: dict[tuple[int, str], set[str]] = {}
        self.first_called: dict[tuple[str, str], int] = {}
        self.confirmed: dict[tuple[str, str], set[tuple[int, str]]] = {}
        for r in s.to_dicts():
            self.staff.setdefault((r["season"], r["team"]), set()).add(r["person"])
            if r["role"] in ("OFF_PC", "DEF_PC"):  # all spells: replaced callers still called
                side = "off" if r["role"] == "OFF_PC" else "def"
                self._called(r["person"], side, r["season"])
                if r["evidence"] in CONFIRMED:
                    self.confirmed.setdefault((r["person"], side), set()).add(
                        (r["season"], r["team"])
                    )
        for x in self.rows:
            self.staff.setdefault((x["season"], x["team"]), set()).add(x["person"])
            if x["source"] == "play_caller":
                self._called(x["person"], x["side"], x["season"])

    def _called(self, person: str, side: str, season: int) -> None:
        k = (person, side)
        self.first_called[k] = min(self.first_called.get(k, 9999), season)

    def label(self, season: int, team: str, side: str, who: str) -> str | None:
        """None without a previous season. A caller is first-time if no earlier season has him
        calling. On staff means named in the table for this team last season; assistants below
        coordinator aren't in it, so `moved_team` doesn't claim he's new to the team."""
        prev = self.by.get((season - 1, team, side))
        if prev is None:
            return None
        if who == prev["person"]:
            new_qb = side == "off" and self.qbs.get((season, team)) != self.qbs.get(
                (season - 1, team)
            )
            return "same_caller_new_qb" if new_qb else "same_caller"
        on_staff = who in self.staff.get((season - 1, team), set())
        if self.first_called.get((who, side), 9999) >= season:
            return "promoted_first_time" if on_staff else "outside_first_time"
        return "took_over" if on_staff else "moved_team"

    def public(self, season: int, team: str, side: str, who: str, label: str | None) -> str | None:
        """The label as a claim on the site. `label` uses unconfirmed seasons, which is right for
        picking a blend, but "same play-caller as last season" states last season's caller and "has
        called plays before" states a past: both need a source, or the label isn't shown."""
        held = self.confirmed.get((who, side), set())
        if label in ("same_caller", "same_caller_new_qb"):
            return label if (season - 1, team) in held else None
        if label in ("took_over", "moved_team"):
            return label if any(s < season for s, _ in held) else None
        return label


def unit_situations(
    assign: pl.DataFrame, qbs: dict, spells: pl.DataFrame | None = None
) -> pl.DataFrame:
    """Each unit-season with a previous season, labelled, for the study."""
    sit = Situations(assign, qbs, spells)
    out = []
    for x in sit.rows:
        label = sit.label(x["season"], x["team"], x["side"], x["person"])
        if label is None:
            continue
        prev = sit.by[(x["season"] - 1, x["team"], x["side"])]
        out.append({
            "season": x["season"], "team": x["team"], "side": x["side"], "person": x["person"],
            "situation": label,
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
                pl.col("pct").min().alias("prior_min"),
                pl.col("pct").max().alias("prior_max"),
                pl.col("season").min().alias("prior_first"),
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


def lean(exp: dict | None) -> str | None:
    """Which past the study says to trust for this row: the caller's, the team's, or both. None
    when the study's guess was little better than the league middle."""
    if not exp or exp["strength"] != "fair":
        return None
    w = exp["weight_on_caller"]
    return "caller" if w >= 0.6 else "team" if w <= 0.4 else "both"


TRAIT_EDGE = 0.3  # a trait sits at least this far from the league middle on average
MAX_TRAITS = 3


def traits(rows: list[dict]) -> list[dict]:
    """A caller's most consistent habits: measures where every past season sat on the same side of
    the league middle, at least two seasons, furthest from the middle first."""
    out = []
    for r in rows:
        p, lo, hi = r["prior"], r["prior_min"], r["prior_max"]
        if r["prior_seasons"] < 2 or abs(p - 0.5) < TRAIT_EDGE:
            continue
        if not (lo > 0.5 or hi < 0.5):
            continue
        out.append({"metric": r["metric"], "kind": r["kind"], "pct": round(p, 4),
                    "seasons": r["prior_seasons"], "first": r["prior_first"]})  # fmt: skip
    out.sort(key=lambda t: -abs(t["pct"] - 0.5))
    return out[:MAX_TRAITS]


def other_starter_weeks(games: pl.DataFrame, team: str) -> list[dict]:
    """Weeks someone other than the Week 1 starter started, from the schedule's QB names."""
    played = games.filter(pl.col("home_score").is_not_null())
    rows = []
    for side in ("home", "away"):
        g = played.filter(_franchise(f"{side}_team") == team)
        rows += [{"week": r["week"], "qb": r[f"{side}_qb_name"]} for r in g.to_dicts()]
    rows = sorted((r for r in rows if r["qb"]), key=lambda r: r["week"])
    return [r for r in rows if r["qb"] != rows[0]["qb"]]


def through_week(games: pl.DataFrame, team: str) -> int | None:
    """The latest regular-season week this team has played."""
    g = games.filter(
        pl.col("home_score").is_not_null()
        & (pl.col("week") <= 18)
        & ((_franchise("home_team") == team) | (_franchise("away_team") == team))
    )
    return None if g.is_empty() else int(g["week"].max())


def _spell(r: dict) -> dict:
    return {
        "role": r["role"], "name": r["person"], "start_week": r["start_week"],
        "end_week": r["end_week"], "evidence": r["evidence"],
        "confirmed": r["evidence"] in CONFIRMED, "source_url": r["source_url"],
    }  # fmt: skip


def _public(rows: list[dict]) -> list[dict]:
    """Titles, plus only the play-caller rows a source confirms (ADR 0021). The working notes in the
    table stay out of the site."""
    return [_spell(r) for r in rows if r["role"] not in ("OFF_PC", "DEF_PC")
            or r["evidence"] in CONFIRMED]  # fmt: skip


def career(spells: pl.DataFrame, person: str, side: str) -> list[dict]:
    """Confirmed calling spells as `{team, from, to}`, consecutive seasons on a team merged."""
    role = "OFF_PC" if side == "off" else "DEF_PC"
    held = (
        spells.filter(
            (pl.col("person") == person)
            & (pl.col("role") == role)
            & pl.col("evidence").is_in(CONFIRMED)
        )
        .select("season", "team")
        .unique()
        .sort("season")
    )
    out: list[dict] = []
    for r in held.to_dicts():
        if out and out[-1]["team"] == r["team"] and out[-1]["to"] == r["season"] - 1:
            out[-1]["to"] = r["season"]
        else:
            out.append({"team": r["team"], "from": r["season"], "to": r["season"]})
    return out


def replaced(rows: list[dict], change: dict) -> str | None:
    """Who held the job right before `change`, if the table can stand on it: a caller must be
    confirmed, and the same person moving between spells replaced nobody."""
    before = [
        r for r in rows if r["role"] == change["role"] and r["start_week"] < change["start_week"]
    ]
    if not before:
        return None
    prev = max(before, key=lambda r: r["start_week"])
    if prev["person"] == change["person"]:
        return None
    if prev["role"] in ("OFF_PC", "DEF_PC") and prev["evidence"] not in CONFIRMED:
        return None
    return prev["person"]


def _caller(spell: dict | None, coordinator: str | None, head_coach: str | None,
            situation: str | None) -> dict | None:  # fmt: skip
    """The name printed for a unit. An unconfirmed caller is never printed: the coordinator's title
    is what we can stand on, and with no coordinator there's no name."""
    confirmed = spell is not None and spell["evidence"] in CONFIRMED
    name = spell["person"] if confirmed else coordinator
    if name is None:
        return None
    return {
        "name": name,
        "confirmed": confirmed,
        "is_head_coach": confirmed and name == head_coach,
        "evidence": spell["evidence"] if confirmed else None,
        "source_url": spell["source_url"] if confirmed else None,
        "situation": situation,
        "situation_text": SITUATION_TEXT.get(situation) if situation else None,
    }


def _metric_rows(kind, side, sit, prior, rates, season, blend, label) -> list[dict]:
    """One entry per metric: expected, and the observed value where this season has one."""
    metrics = (
        LIVE[side] if kind == "live" else [m for m in SCHEME_METRICS[side] if m not in ALSO_LIVE]
    )
    out = []
    for m in metrics:
        p = prior.get(m) or {}
        prev = rates.get((season - 1, m))
        now = rates.get((season, m))
        exp = expected(
            p.get("prior"), prev["pct"] if prev else None,
            blend_cell(blend, kind, side, sit, m) if sit else None,
        )  # fmt: skip
        out.append({
            "metric": m, **label(m),
            "expected": exp,
            "caller_past": {"pct": round(p["prior"], 4), "seasons": p["prior_seasons"],
                            "first": p["prior_first"]} if p.get("prior") is not None else None,
            "lean": lean(exp) if p.get("prior") is not None else None,
            "caller_seasons": p.get("prior_seasons", 0),
            "caller_teams": p.get("prior_teams", []),
            "team_last": {"season": season - 1, "pct": round(prev["pct"], 4),
                          "rate": round(prev["rate"], 4), "rank": prev["rank"],
                          "of": prev["of"]} if prev else None,
            "observed": {"pct": round(now["pct"], 4), "rate": round(now["rate"], 4),
                         "n": now["n"], "rank": now["rank"], "of": now["of"]} if now else None,
        })  # fmt: skip
    return out


def team_files(paths: Paths, season: int, week: int, games: pl.DataFrame,
               metric_label) -> dict[str, dict]:  # fmt: skip
    """`site/team/<code>.json` bodies, keyed by team. `week` is the next week to be played.

    `metric_label(metric)` gives the live set's label and help; the charted set's come from
    `coaches.METRICS`."""
    assign = coaches.assignments()
    spells = coaches.load_spells().with_columns(_franchise())
    situations = Situations(assign, primary_qbs(paths, season))
    blend = load_blend()
    sets = {"live": live_rates(paths), "charted": charted_rates(paths)}
    priors = {
        k: caller_prior(assign, v).filter(pl.col("season") == season) for k, v in sets.items()
    }
    now = now_utc().isoformat()
    labels = {"live": metric_label, "charted": _charted_label}
    out = {}
    for team in sorted(spells.filter(pl.col("season") == season)["team"].unique().to_list()):
        at = coaches.staff_at(season, team, week, spells).to_dicts()
        titled = {r["role"]: r["person"] for r in reversed(at)}
        calling = {r["role"]: r for r in at if r["role"] in ("OFF_PC", "DEF_PC")}
        rows = spells.filter((pl.col("season") == season) & (pl.col("team") == team)).to_dicts()
        changes = sorted((r for r in rows if r["start_week"] > 1), key=lambda r: r["start_week"])
        moves = [
            {**_spell(r), "replaced": replaced(rows, r)}
            for r in changes
            if r["role"] not in ("OFF_PC", "DEF_PC") or r["evidence"] in CONFIRMED
        ]
        body: dict = {
            "schema_version": "1", "team": team, "season": season, "week": week,
            "through_week": through_week(games, team), "generated_at": now,
            "staff": {"current": _public(at), "changes": moves},
            "other_starter_weeks": other_starter_weeks(games, team),
            "units": {},
        }  # fmt: skip
        for side, title, pc in (("off", "OC", "OFF_PC"), ("def", "DC", "DEF_PC")):
            # Everything about a unit follows the person in force at `week`, and a person only when
            # confirmed: with none, the expected values are the team's last season alone.
            spell = calling.get(pc)
            who = spell["person"] if spell and spell["evidence"] in CONFIRMED else None
            sit = situations.label(season, team, side, who) if who else None
            shown = situations.public(season, team, side, who, sit) if who else None
            if shown in ("same_caller", "same_caller_new_qb") and spell["start_week"] > 1:
                shown = None  # he took the calls back in season: "same" hides the change
            caller = _caller(spell, titled.get(title), titled.get("HC"), shown)
            if caller:
                caller["career"] = career(spells, who, side) if who else []
                mine = [
                    {**r, "kind": k}
                    for k in sets
                    for r in priors[k]
                    .filter((pl.col("person") == who) & (pl.col("side") == side))
                    .to_dicts()
                    if not (k == "charted" and r["metric"] in ALSO_LIVE)
                    and r["metric"] in (LIVE[side] if k == "live" else SCHEME_METRICS[side])
                ] if who else []  # fmt: skip
                caller["traits"] = [{**t, **labels[t["kind"]](t["metric"])} for t in traits(mine)]
            block = {"caller": caller}
            for kind, rates in sets.items():
                mine = rates.filter((pl.col("team") == team) & (pl.col("side") == side))
                by_metric = {(r["season"], r["metric"]): r for r in mine.to_dicts()}
                prior = {}
                if who:
                    prior = {
                        r["metric"]: r
                        for r in priors[kind]
                        .filter((pl.col("person") == who) & (pl.col("side") == side))
                        .to_dicts()
                    }
                label = metric_label if kind == "live" else _charted_label
                block[kind] = _metric_rows(kind, side, sit, prior, by_metric, season, blend, label)
            body["units"][side] = block
        out[team] = body
    return out


def _charted_label(metric: str) -> dict:
    d = METRICS[metric]
    return {"label": d["label"], "help": d["help"], "unit": d["unit"], "lo": d["lo"], "hi": d["hi"]}
