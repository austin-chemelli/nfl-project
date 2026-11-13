"""How far each team is from full strength, week by week (ADR 0027, M24.7).

A team's **full-strength lineup** is, at each base-formation spot, the most valuable player the
depth chart has had as the starter there since March who is still on the roster. A player hurt in
camp (on IR before Week 1) still counts, and a backup who won the job is no loss. Each of those
starters is valued **as he was going into his last game** (his role from the games before it), so
a player out for weeks keeps the value he had rather than decaying with the injury game.

Each full-strength starter then has this week's status: on a reserve list (IR, PUP, from the weekly
roster), listed Out, Doubtful or Questionable on the report, inactive, or available. What he's
expected to miss is value × (1 − P(plays)); the team's health is the share of its full-strength
value expected on the field. The outlook assumes a player on IR returns the week he's eligible
(four games after he went on it) and a player on the report the next week: a window, never a date.

Context only: nothing here reaches a lock or a feature.
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from nfl.players import claims as C
from nfl.players import lineup as L
from nfl.players import value as V

SEASON_CHARTS_FROM = "03-01"  # the offseason chart: a player hurt in camp was the starter here
ON_ROSTER = ("ACT", "INA", "RES", "EXE")
IR_GAMES = 4  # a player on IR misses at least four games
RESERVE = {
    "R01": "IR",
    "R48": "IR, designated to return",
    "R04": "PUP",
}
OUTLOOK_WEEKS = 4


# ------------------------------------------------------------------------------- healthy values


class HealthyValues:
    """Each player's value going into his last game before (season, week): the current value when
    he played his team's last game, else the value as of the week of his last game (whose role comes
    from the games before it, so the game he was hurt in doesn't count)."""

    def __init__(self, pg: pl.DataFrame, prior: pl.DataFrame):
        self.pg, self.prior = pg, prior
        self._slices: dict[tuple[int, int], dict[str, dict]] = {}

    def slice(self, season: int, week: int) -> dict[str, dict]:
        key = (season, week)
        if key not in self._slices:
            sl = V.as_of(self.pg, season, week)
            df = (
                V.score(sl, V.group_means(self.pg, season), self.prior) if not sl.is_empty() else sl
            )
            self._slices[key] = {r["gsis_id"]: r for r in df.iter_rows(named=True)}
        return self._slices[key]

    def at(self, season: int, week: int, ids: list[str]) -> dict[str, dict]:
        now = self.slice(season, week)
        before = self.pg.filter(
            pl.col("gsis_id").is_in(ids)
            & (
                (pl.col("season") < season)
                | ((pl.col("season") == season) & (pl.col("week") < week))
            )
        )
        last = before.group_by("gsis_id").agg(
            pl.struct("season", "week").sort_by("season", "week").last().alias("g"),
            pl.col("team").sort_by("season", "week").last(),
        )
        team_last = (
            self.pg.filter(
                (pl.col("season") < season)
                | ((pl.col("season") == season) & (pl.col("week") < week))
            )
            .group_by("team")
            .agg(pl.struct("season", "week").sort_by("season", "week").last().alias("g"))
        )
        tl = {
            r["team"]: (r["g"]["season"], r["g"]["week"]) for r in team_last.iter_rows(named=True)
        }
        out = {}
        for r in last.iter_rows(named=True):
            g = (r["g"]["season"], r["g"]["week"])
            v = now.get(r["gsis_id"]) if tl.get(r["team"]) == g else None
            if v is None:
                v = self.slice(*g).get(r["gsis_id"]) or now.get(r["gsis_id"])
            if v is not None:
                out[r["gsis_id"]] = {**v, "valued_week": g}
        return out


# ------------------------------------------------------------------------------ full strength


def _base(depth: pl.DataFrame, team: str, season: int, cutoff: datetime) -> pl.DataFrame:
    d = depth.filter(
        (pl.col("team") == team)
        & pl.col("dt").is_not_null()
        & (pl.col("pos_grp") != "Special Teams")
        & ~pl.col("pos_abb").is_in(L.EXTRA)
        & pl.col("gsis_id").is_not_null()
    )
    d = L.with_chart_dt(d)
    since = datetime.fromisoformat(f"{season}-{SEASON_CHARTS_FROM}")
    return d.filter((pl.col("chart_dt") >= since) & (pl.col("chart_dt") < cutoff))


def candidates(depth: pl.DataFrame, team: str, season: int, cutoff: datetime) -> pl.DataFrame:
    """Every (pos_abb, gsis_id, player) the chart has had as a starter since March: the top rank
    at a spot on any chart before the cutoff."""
    d = _base(depth, team, season, cutoff)
    if d.is_empty():
        return pl.DataFrame(schema={"pos_abb": pl.Utf8, "gsis_id": pl.Utf8, "player": pl.Utf8})
    top = d.sort("pos_rank").group_by("chart_dt", "pos_abb", "pos_slot").first()
    # a WR is a starter at rank 1-3 among the WR spots (the chart ranks receivers across slots)
    wr = (
        d.filter(pl.col("pos_abb") == "WR")
        .sort("pos_rank")
        .group_by("chart_dt", maintain_order=True)
        .head(3)
    )
    both = pl.concat([top.filter(pl.col("pos_abb") != "WR"), wr], how="diagonal_relaxed")
    return both.select("pos_abb", "gsis_id", pl.col("player_name").alias("player")).unique(
        ["pos_abb", "gsis_id"]
    )


def roster_at(rosters: pl.DataFrame, team: str, week: int) -> dict[str, dict]:
    """gsis_id -> {status, code, since} on the team's latest roster at or before `week`; `since`
    is the first week of an unbroken reserve stretch."""
    r = rosters.filter((pl.col("team") == team) & (pl.col("week") <= week))
    if r.is_empty():
        return {}
    wk = r["week"].max()
    now = r.filter(pl.col("week") == wk)
    out = {}
    for x in now.iter_rows(named=True):
        since = None
        if x["status"] == "RES":
            hist = r.filter(pl.col("gsis_id") == x["gsis_id"]).sort("week", descending=True)
            since = wk
            for h in hist.iter_rows(named=True):
                if h["status"] != "RES":
                    break
                since = h["week"]
        out[x["gsis_id"]] = {
            "status": x["status"], "code": x["status_description_abbr"], "since": since,
            "roster_week": wk,
        }  # fmt: skip
    return out


def full_strength(
    spots: pl.DataFrame, cands: pl.DataFrame, values: dict[str, dict], roster: dict[str, dict]
) -> list[dict]:
    """Assign the most valuable candidates to the current chart's spots, each player once.
    `spots`: the current chart's starters (slot, unit, formation, pos_abb, gsis_id, player)."""
    current = {r["slot"]: r for r in spots.iter_rows(named=True)}
    by_abb: dict[str, list[str]] = {}
    for r in spots.iter_rows(named=True):
        by_abb.setdefault(r["pos_abb"], []).append(r["slot"])
    on = (
        (lambda g: g in roster and roster[g]["status"] in ON_ROSTER) if roster else (lambda g: True)
    )
    pool = [
        c for c in cands.iter_rows(named=True) if c["pos_abb"] in by_abb and on(c["gsis_id"])
    ] + [
        {"pos_abb": r["pos_abb"], "gsis_id": r["gsis_id"], "player": r["player"]}
        for r in spots.iter_rows(named=True)
    ]

    def worth(c: dict) -> float:
        v = values.get(c["gsis_id"])
        return v["value_pts"] if v and v.get("value_pts") is not None else -1.0

    # the most valuable first; among unvalued, the current starter keeps his spot
    is_current = {(r["pos_abb"], r["gsis_id"]) for r in spots.iter_rows(named=True)}
    pool.sort(key=lambda c: (-worth(c), (c["pos_abb"], c["gsis_id"]) not in is_current))
    taken: set[str] = set()
    filled: dict[str, int] = {}
    chosen: list[dict] = []
    for c in pool:
        slots = by_abb[c["pos_abb"]]
        if c["gsis_id"] in taken or filled.get(c["pos_abb"], 0) >= len(slots):
            continue
        taken.add(c["gsis_id"])
        filled[c["pos_abb"]] = filled.get(c["pos_abb"], 0) + 1
        chosen.append(c)
    # slots: a WR room in value order (WR1 the most valuable), single spots by their own name
    out = []
    for abb, slots in by_abb.items():
        mine = [c for c in chosen if c["pos_abb"] == abb]
        if abb == "WR":
            slots = sorted(slots)
        else:
            # keep a current starter in his own spot
            mine.sort(key=lambda c: next((i for i, s in enumerate(slots) if current[s]["gsis_id"] == c["gsis_id"]), 99))  # fmt: skip
        for slot, c in zip(slots, mine, strict=False):
            cur = current[slot]
            out.append({
                "slot": slot, "unit": cur["unit"], "gsis_id": c["gsis_id"], "player": c["player"],
                "replaced_by": None if cur["gsis_id"] == c["gsis_id"] else cur["player"],
            })  # fmt: skip
    return out


# ----------------------------------------------------------------------------------- one week


def _status(g: str, team: str, week: int, roster: dict, injuries: list[dict], rates: dict) -> dict:
    ro = roster.get(g)
    if ro and ro["status"] == "RES":
        since = ro["since"]
        code = ro["code"]
        eligible = since + IR_GAMES if code == "R01" and since else None
        return {"status": RESERVE.get(code, "Reserve list"), "reserve": True, "p_play": 0.0,
                "since_week": since, "eligible_week": eligible}  # fmt: skip
    rep = next(
        (
            i
            for i in injuries
            if i["gsis_id"] == g
            and i["team"] == team
            and i["week"] == week
            and i["status"] in C.GAME_STATUSES
        ),
        None,
    )
    if rep:
        p = 0.0 if rep["status"] == "Out" else C._rate(rates, rep["status"], rep.get("pos"))[0]
        return {"status": rep["status"], "reserve": False, "p_play": round(p, 4),
                "since_week": None, "eligible_week": None}  # fmt: skip
    if ro and ro["status"] == "INA" and ro["roster_week"] == week:
        return {"status": "Inactive", "reserve": False, "p_play": 0.0, "since_week": None,
                "eligible_week": None}  # fmt: skip
    return {"status": None, "reserve": False, "p_play": 1.0, "since_week": None, "eligible_week": None}  # fmt: skip


def team_week(
    depth: pl.DataFrame,
    team: str,
    season: int,
    week: int,
    cutoff: datetime,
    rosters: pl.DataFrame,
    injuries: list[dict],
    values: HealthyValues,
    rates: dict,
) -> dict | None:
    """The team's full-strength starters going into `week`, each with value and status, and the
    totals: full-strength value, value expected to miss, health (share on the field), by group."""
    spots = L.starters(depth, team, cutoff)
    if spots.is_empty():
        return None
    cands = candidates(depth, team, season, cutoff)
    roster = roster_at(rosters, team, week)
    ids = list({*cands["gsis_id"].to_list(), *spots["gsis_id"].to_list()})
    vals = values.at(season, week, ids)
    starters = []
    for s in full_strength(spots, cands, vals, roster):
        v = vals.get(s["gsis_id"])
        value = round(float(v["value_pts"]), 2) if v and v["value_pts"] is not None else None
        st = _status(s["gsis_id"], team, week, roster, injuries, rates)
        missing = round(value * (1 - st["p_play"]), 2) if value is not None else None
        starters.append({**s, "grp": v["grp"] if v else None, "value_pts": value, **st,
                         "missing_pts": missing})  # fmt: skip
    return {"week": week, **summarize(starters), "starters": starters}


def summarize(starters: list[dict]) -> dict:
    full = sum(s["value_pts"] or 0 for s in starters)
    miss = sum(s["missing_pts"] or 0 for s in starters)
    groups: dict[str, dict] = {}
    for s in starters:
        if s["value_pts"] is None:
            continue
        g = groups.setdefault(s["grp"], {"grp": s["grp"], "full_pts": 0.0, "missing_pts": 0.0})
        g["full_pts"] += s["value_pts"]
        g["missing_pts"] += s["missing_pts"] or 0
    rows = [
        {**g, "full_pts": round(g["full_pts"], 2), "missing_pts": round(g["missing_pts"], 2),
         "health": round(1 - g["missing_pts"] / g["full_pts"], 3) if g["full_pts"] else None}
        for g in groups.values()
    ]  # fmt: skip
    return {
        "full_pts": round(full, 2),
        "missing_pts": round(miss, 2),
        "health": round(1 - miss / full, 3) if full else None,
        "groups": sorted(rows, key=lambda g: -g["full_pts"]),
    }


def outlook(now: dict, weeks: list[int]) -> list[dict]:
    """Health for the coming weeks if each player returns when he can: IR at his eligible week, a
    player on the report the week after; a player already past his IR window, or on another reserve
    list, stays out (no window known)."""
    out = []
    for w in weeks:
        rows = []
        for s in now["starters"]:
            back = (
                s["status"] is None
                or (not s["reserve"] and w > now["week"])
                # eligible already and still out: no window known, so he stays out
                or (
                    s["eligible_week"] is not None
                    and s["eligible_week"] > now["week"]
                    and w >= s["eligible_week"]
                )
                or (s["status"] == RESERVE["R48"] and w > now["week"])
            )
            p = 1.0 if back else s["p_play"]
            rows.append({**s, "missing_pts": round((s["value_pts"] or 0) * (1 - p), 2)
                         if s["value_pts"] is not None else None})  # fmt: skip
        t = summarize(rows)
        out.append({"week": w, "health": t["health"], "missing_pts": t["missing_pts"]})
    return out


def season(
    games: pl.DataFrame,
    depth: pl.DataFrame,
    rosters: pl.DataFrame,
    injuries: list[dict],
    values: HealthyValues,
    rates: dict,
    now: datetime,
    season_: int,
) -> dict[str, dict]:
    """team -> {now, by_week, outlook}: health going into each regular-season game the team has
    played this season, the next one (`now`), and the outlook for the weeks after it."""
    reg = games.filter(pl.col("game_type") == "REG") if "game_type" in games.columns else games
    teams = sorted({*reg["home_team"].to_list(), *reg["away_team"].to_list()})
    depth = L.with_chart_dt(depth)
    out: dict[str, dict] = {}
    for team in teams:
        tg = reg.filter((pl.col("home_team") == team) | (pl.col("away_team") == team)).sort("week")
        by_week, nxt = [], None
        for g in tg.iter_rows(named=True):
            upcoming = g["kickoff_utc"] > now
            cutoff = now if upcoming else g["kickoff_utc"]
            tw = team_week(depth, team, season_, g["week"], cutoff, rosters, injuries, values, rates)  # fmt: skip
            if tw is None:
                continue
            if upcoming:
                nxt = tw
                break
            by_week.append({k: tw[k] for k in ("week", "health", "missing_pts", "full_pts")})
        if nxt is None:
            continue
        later = [w for w in tg["week"].to_list() if w > nxt["week"]][:OUTLOOK_WEEKS]
        out[team] = {"now": nxt, "by_week": by_week, "outlook": outlook(nxt, later)}
    return out
