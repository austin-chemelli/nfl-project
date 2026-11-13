"""How far each team is from full strength, week by week (ADR 0027, M24.7).

A team's **full-strength lineup** is, at each base-formation spot, the most valuable player the
depth chart has had as the starter there since March who is still on the roster. A player hurt in
camp (on IR before Week 1) still counts, and a backup who won the job is no loss. Each of those
starters is valued **as he was going into his last game** (his role from the games before it), so
a player out for weeks keeps the value he had rather than decaying with the injury game.

Each full-strength starter then has this week's status: on a reserve list (IR, PUP, from the weekly
roster), listed Out, Doubtful or Questionable on the report, before Friday's game statuses the
latest practice report (did not practice, limited) as a doubt that doesn't count against health
(a Wednesday DNP is often rest, and the rates we can measure are for the week's last practice),
inactive, or available. What he's expected to miss is value × (1 − P(plays)); the team's health is the share
of its full-strength value expected on the field. Each spot also carries the chart's next two men
there (who plays if he can't). The outlook assumes a player on IR returns the week he's eligible
(four team games after he went on it) and a player on the report the next week: a window, never a
date.

Context only: nothing here reaches a lock or a feature.
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from nfl.players import claims as C
from nfl.players import lineup as L
from nfl.players import status as S
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
        self._team_last: dict[tuple[int, int], dict[str, tuple[int, int]]] = {}

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
        tl = self.team_last(season, week)
        out = {}
        for r in last.iter_rows(named=True):
            g = (r["g"]["season"], r["g"]["week"])
            if tl.get(r["team"]) == g and r["gsis_id"] in now:
                out[r["gsis_id"]] = {**now[r["gsis_id"]], "valued_week": (season, week)}
                continue
            v, at = self.slice(*g).get(r["gsis_id"]), g
            if v is None:
                v, at = now.get(r["gsis_id"]), (season, week)
            if v is not None:
                out[r["gsis_id"]] = {**v, "valued_week": at}
        return out

    def team_last(self, season: int, week: int) -> dict[str, tuple[int, int]]:
        """team -> (season, week) of its last game before (season, week)."""
        if (season, week) not in self._team_last:
            t = (
                self.pg.filter(
                    (pl.col("season") < season)
                    | ((pl.col("season") == season) & (pl.col("week") < week))
                )
                .group_by("team")
                .agg(pl.struct("season", "week").sort_by("season", "week").last().alias("g"))
            )
            self._team_last[(season, week)] = {
                r["team"]: (r["g"]["season"], r["g"]["week"]) for r in t.iter_rows(named=True)
            }
        return self._team_last[(season, week)]


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
    d = d.sort("chart_dt", "pos_abb", "pos_slot", "pos_rank")
    top = d.group_by("chart_dt", "pos_abb", "pos_slot", maintain_order=True).first()
    # a WR is a starter at rank 1-3 among the WR spots (the chart ranks receivers across slots)
    wr = (
        d.filter(pl.col("pos_abb") == "WR")
        .sort("pos_rank")
        .group_by("chart_dt", maintain_order=True)
        .head(3)
    )
    both = pl.concat([top.filter(pl.col("pos_abb") != "WR"), wr], how="diagonal_relaxed")
    return (
        both.select("pos_abb", "gsis_id", pl.col("player_name").alias("player"))
        .unique(["pos_abb", "gsis_id"], keep="last", maintain_order=True)
        .sort("pos_abb", "gsis_id")
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


def _report(g: str, team: str, week: int, injuries: list[dict]) -> tuple[dict | None, dict | None]:
    """His row on this week's report with a game status, and (when none) one with a practice status
    that says he's hurt (did not practice, or limited)."""
    game = prac = None
    for i in injuries:
        if i["gsis_id"] != g or i["team"] != team or i["week"] != week:
            continue
        if i.get("status") in C.GAME_STATUSES:
            game = i
        elif i.get("practice") in S.PRACTICE:
            prac = i
    return game, (None if game else prac)


def absent(g: str, team: str, week: int, roster: dict, injuries: list[dict]) -> bool:
    """Not expected to play this week: a reserve list, a game status, did not practice, inactive."""
    ro = roster.get(g)
    if ro and (ro["status"] == "RES" or (ro["status"] == "INA" and ro["roster_week"] == week)):
        return True
    game, _ = _report(g, team, week, injuries)
    return game is not None


def chart_depth(depth: pl.DataFrame, team: str, cutoff: datetime) -> dict[tuple, list[tuple]]:
    """(pos_abb, pos_slot) -> [(gsis_id, player)] in rank order on the latest chart before the
    cutoff: the depth at each spot."""
    d = L.with_chart_dt(
        depth.filter((pl.col("team") == team) & pl.col("gsis_id").is_not_null())
    ).filter(pl.col("chart_dt") < cutoff)
    if d.is_empty():
        return {}
    d = d.filter(pl.col("chart_dt") == d["chart_dt"].max()).sort("pos_rank")
    out: dict[tuple, list[tuple]] = {}
    for r in d.iter_rows(named=True):
        out.setdefault((r["pos_abb"], r["pos_slot"]), []).append((r["gsis_id"], r["player_name"]))
    return out


def full_strength(
    spots: pl.DataFrame,
    cands: pl.DataFrame,
    values: dict[str, dict],
    roster: dict[str, dict],
    is_absent=lambda g: False,
) -> list[dict]:
    """Assign the most valuable players to the current chart's spots, each player once. The pool is
    the current starters plus earlier chart starters who are absent this week (and still on the
    roster): a healthy player the chart has moved down lost the job, he isn't a missing starter.
    `spots`: the current chart's starters (slot, unit, formation, pos_abb, gsis_id, player)."""
    current = {r["slot"]: r for r in spots.iter_rows(named=True)}
    by_abb: dict[str, list[str]] = {}
    for r in spots.iter_rows(named=True):
        by_abb.setdefault(r["pos_abb"], []).append(r["slot"])
    is_current = {(r["pos_abb"], r["gsis_id"]) for r in spots.iter_rows(named=True)}
    pool = [
        {"pos_abb": r["pos_abb"], "gsis_id": r["gsis_id"], "player": r["player"]}
        for r in spots.iter_rows(named=True)
    ] + [
        c
        for c in cands.iter_rows(named=True)
        if c["pos_abb"] in by_abb
        and (c["pos_abb"], c["gsis_id"]) not in is_current
        and roster.get(c["gsis_id"], {}).get("status") in ON_ROSTER
        and is_absent(c["gsis_id"])
    ]

    def worth(c: dict) -> float:
        v = values.get(c["gsis_id"])
        return v["value_pts"] if v and v.get("value_pts") is not None else -1.0

    # the most valuable first; on a tie the current starter, then a stable order
    pool.sort(key=lambda c: (-worth(c), (c["pos_abb"], c["gsis_id"]) not in is_current, c["gsis_id"]))  # fmt: skip
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
    out = []
    for abb, slots in by_abb.items():
        mine = [c for c in chosen if c["pos_abb"] == abb]
        if abb == "WR":
            # the room in value order (WR1 the most valuable); a chosen receiver who isn't a current
            # starter is paired with a current one who was left out
            cur_ids = [current[s]["gsis_id"] for s in sorted(slots)]
            left_out = [current[s]["player"] for s in sorted(slots) if current[s]["gsis_id"] not in {c["gsis_id"] for c in mine}]  # fmt: skip
            for slot, c in zip(sorted(slots), mine, strict=False):
                rep = None if c["gsis_id"] in cur_ids else (left_out.pop(0) if left_out else None)
                out.append({"slot": slot, "unit": current[slot]["unit"], "gsis_id": c["gsis_id"],
                            "player": c["player"], "replaced_by": rep})  # fmt: skip
            continue
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


def eligible_week(since: int | None, team_weeks: list[int] | None) -> int | None:
    """The week a player on IR since `since` may play again: after missing four of his team's games
    (byes don't count). None for IR from before the first game (camp: usually the season) or when
    the schedule runs out."""
    if since is None:
        return None
    if not team_weeks:
        return since + IR_GAMES
    if since <= min(team_weeks):
        return None
    later = sorted(w for w in team_weeks if w >= since)
    return later[IR_GAMES] if len(later) > IR_GAMES else None


def _status(
    g: str, team: str, week: int, roster: dict, injuries: list[dict], rates: dict,
    team_weeks: list[int] | None = None, reported: bool = True,
) -> dict:  # fmt: skip
    ro = roster.get(g)
    if ro and ro["status"] == "RES":
        since = ro["since"]
        code = ro["code"]
        eligible = eligible_week(since, team_weeks) if code == "R01" else None
        return {"status": RESERVE.get(code, "Reserve list"), "reserve": True, "p_play": 0.0,
                "since_week": since, "eligible_week": eligible}  # fmt: skip
    rep, prac = _report(g, team, week, injuries)
    if rep:
        p = 0.0 if rep["status"] == "Out" else C._rate(rates, rep["status"], rep.get("pos"))[0]
        return {"status": rep["status"], "reserve": False, "p_play": round(p, 4),
                "since_week": None, "eligible_week": None}  # fmt: skip
    # before Friday's game statuses a hurt practice is a doubt, not a number: the rates we can
    # measure are for the week's last practice, and a Wednesday DNP is often a rest day
    if prac and not reported:
        return {"status": S.PRACTICE[prac["practice"]], "reserve": False, "p_play": 1.0,
                "since_week": None, "eligible_week": None, "doubt": True}  # fmt: skip
    if ro and ro["status"] == "INA" and ro["roster_week"] == week:
        return {"status": "Inactive", "reserve": False, "p_play": 0.0, "since_week": None,
                "eligible_week": None}  # fmt: skip
    return {"status": None, "reserve": False, "p_play": 1.0, "since_week": None, "eligible_week": None}  # fmt: skip


def _no_doubt(st: dict) -> dict:
    return {"doubt": False, **st}


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
    team_weeks: list[int] | None = None,
) -> dict | None:
    """The team's full-strength starters going into `week`, each with value and status, and the
    totals: full-strength value, value expected to miss, health (share on the field), by group."""
    spots = L.starters(depth, team, cutoff)
    if spots.is_empty():
        return None
    cands = candidates(depth, team, season, cutoff)
    roster = roster_at(rosters, team, week)
    behind = chart_depth(depth, team, cutoff)
    slot_key = {r["slot"]: (r["pos_abb"], r["pos_slot"]) for r in spots.iter_rows(named=True)}
    ids = list({
        *cands["gsis_id"].to_list(), *spots["gsis_id"].to_list(),
        *(g for d in behind.values() for g, _ in d),
    })  # fmt: skip
    vals = values.at(season, week, ids)

    def val(g: str) -> float | None:
        v = vals.get(g)
        return round(float(v["value_pts"]), 2) if v and v["value_pts"] is not None else None

    # before the week's report has game statuses, a starter hurt this week still counts as healthy
    reported = any(
        i["team"] == team and i["week"] == week and i.get("status") in C.GAME_STATUSES
        for i in injuries
    )

    def status(g: str) -> dict:
        return _no_doubt(_status(g, team, week, roster, injuries, rates, team_weeks, reported))

    starters = []
    out_now = lambda g: absent(g, team, week, roster, injuries)
    lineup = full_strength(spots, cands, vals, roster, out_now)
    full_ids = {s["gsis_id"] for s in lineup}
    for s in lineup:
        v = vals.get(s["gsis_id"])
        value = val(s["gsis_id"])
        st = status(s["gsis_id"])
        missing = round(value * (1 - st["p_play"]), 2) if value is not None else None
        # the chart at this spot after him: who plays if he can't, and the next man up
        chain = [
            {"player": n, "value_pts": val(g), "status": status(g)["status"]}
            for g, n in behind.get(slot_key[s["slot"]], [])
            if g not in full_ids  # a full-strength starter elsewhere isn't depth here
        ][:2]
        starters.append({**s, "grp": v["grp"] if v else None, "value_pts": value, **st,
                         "missing_pts": missing, "depth": chain})  # fmt: skip
    order = {k: i for i, k in enumerate((*L.OFFENSE_ORDER, *L.DEFENSE_ORDER))}
    starters.sort(key=lambda s: (s["unit"] != "offense", order.get(s["slot"], 99)))
    return {"week": week, "reported": reported, **summarize(starters), "starters": starters}


def summarize(starters: list[dict]) -> dict:
    full = sum(s["value_pts"] or 0 for s in starters)
    miss = sum(s["missing_pts"] or 0 for s in starters)
    groups: dict[str, dict] = {}
    for s in starters:
        if s["value_pts"] is None:
            continue
        g = groups.setdefault(
            s["grp"], {"grp": s["grp"], "full_pts": 0.0, "missing_pts": 0.0, "doubt_pts": 0.0}
        )
        g["full_pts"] += s["value_pts"]
        g["missing_pts"] += s["missing_pts"] or 0
        g["doubt_pts"] += s["value_pts"] if s.get("doubt") else 0
    rows = [
        {**g, "full_pts": round(g["full_pts"], 2), "missing_pts": round(g["missing_pts"], 2),
         "doubt_pts": round(g["doubt_pts"], 2),
         "health": round(1 - g["missing_pts"] / g["full_pts"], 3) if g["full_pts"] else None}
        for g in groups.values()
    ]  # fmt: skip
    return {
        "full_pts": round(full, 2),
        "missing_pts": round(miss, 2),
        # starters who missed or were limited in practice before game statuses: value in doubt
        "doubt_pts": round(sum(s["value_pts"] or 0 for s in starters if s.get("doubt")), 2),
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
    depth_by = {k[0]: v for k, v in depth.partition_by("team", as_dict=True).items()}
    ros_by = {k[0]: v for k, v in rosters.partition_by("team", as_dict=True).items()} if not rosters.is_empty() else {}  # fmt: skip
    out: dict[str, dict] = {}
    for team in teams:
        tg = reg.filter((pl.col("home_team") == team) | (pl.col("away_team") == team)).sort("week")
        weeks = tg["week"].to_list()
        dep = depth_by.get(team, depth.clear())
        ros = ros_by.get(team, rosters.clear())
        inj = [i for i in injuries if i["team"] == team]
        by_week, nxt = [], None
        for g in tg.iter_rows(named=True):
            upcoming = g["kickoff_utc"] > now
            cutoff = now if upcoming else g["kickoff_utc"]
            tw = team_week(dep, team, season_, g["week"], cutoff, ros, inj, values, rates, weeks)
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
