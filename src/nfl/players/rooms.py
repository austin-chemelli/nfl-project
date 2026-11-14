"""How strong each position room is (M24.7 round 3, PR B): a league rank per team and room from this
season's games, and an estimate of the rank now, with the room's injuries.

Each room has two or three stats from play-by-play and PFR's advanced game stats, each signed so
higher is better and turned into a z-score across the 32 teams. A room's grade is the mean of its
z-scores, ranked 1-32 with a label. It is how the room has played this season, injuries included:
a room that lost its best player in Week 3 is graded on the games without him too.

The estimate now (decision 4a of the round-3 plan): the room's available share of spot weight
(team health, the same weights as the team's percentage) pulls its grade toward a replacement
level, `z_now = h * z + (1 - h) * Z_REPLACEMENT`, then ranks against every room's full grade.
An elite room losing its two key receivers falls far; a weak room has little room to fall.
Context only: nothing here reaches a line.
"""

from __future__ import annotations

import duckdb
import polars as pl

from nfl.players import priors as P

Z_REPLACEMENT = -1.5  # a room of backups grades like the league's worst few rooms
MIN_GAMES = 3  # fewer games than this and a team gets no grade
LABELS = ((6, "elite"), (14, "good"), (24, "average"), (32, "weak"))  # rank at most -> label

# room -> [(key, label, higher is better)]; values computed in `stats`
STATS: dict[str, list[tuple[str, str, bool]]] = {
    "QB": [("qb_epa", "EPA per dropback", True), ("qb_success", "success rate on dropbacks", True)],
    "OL": [
        ("ol_pressure", "pressure rate allowed", False),
        ("ol_sack", "sack rate allowed", False),
        ("ol_ybc", "rush yards before contact per carry", True),
    ],
    "RB": [("rb_epa", "EPA per carry", True), ("rb_success", "success rate per carry", True)],
    "WR": [("wr_epa", "EPA per target", True), ("wr_success", "success rate per target", True)],
    "TE": [("te_epa", "EPA per target", True), ("te_success", "success rate per target", True)],
    "EDGE": [("edge_pressure", "edge pressures per opponent dropback", True), ("edge_sack", "edge sacks per opponent dropback", True)],
    "DL": [("dl_pressure", "interior pressures per opponent dropback", True), ("dl_ybc", "opponent yards before contact per carry", False)],
    "LB": [("lb_rush_epa", "opponent EPA per rush", False), ("lb_missed", "linebacker missed-tackle rate", False)],
    "CB": [("cb_ypt", "yards allowed per target", False), ("cb_cmp", "completion rate allowed", False)],
    "S": [("s_ypt", "yards allowed per target", False), ("s_missed", "safety missed-tackle rate", False)],
}  # fmt: skip


def _pos_case(col: str) -> str:
    whens = " ".join(f"when '{k}' then '{v}'" for k, v in P.POSITION_GROUP.items())
    return f"case {col} {whens} else null end"


def _group_sql() -> str:
    """gsis_id / pfr_id -> position group, PFF position first (as the value model)."""
    return (
        "select gsis_id, pfr_id, coalesce("
        f"{_pos_case('pff_position')}, {_pos_case('ngs_position')}, {_pos_case('position')}) as grp "
        "from players"
    )


# The skill rooms are graded on their full-strength starters' own plays, this season and last (last
# season counts LAST_SEASON), wherever they played: a room's receivers are who they are, and four
# healthy games of team targets are too few. The line and the defense use team stats.
PLAYER_ROOMS = ("QB", "RB", "WR", "TE")
LAST_SEASON = 0.5
# a room's plays are shrunk toward the league's: this many league-average plays are added to its own
SHRINK = {"QB": 200, "RB": 100, "WR": 100, "TE": 60}


def player_rooms(
    con: duckdb.DuckDBPyConnection, season: int, starters: dict[str, list[dict]]
) -> dict[str, dict]:
    """team -> room -> {plays, stat: value} for `PLAYER_ROOMS`, from each team's full-strength
    starters (`gsis_id`, `grp`) and their regular-season plays in `season` and the one before."""
    rows = [(t, s["gsis_id"], s["grp"]) for t, ss in starters.items() for s in ss
            if s.get("gsis_id") and s.get("grp") in PLAYER_ROOMS]  # fmt: skip
    if not rows:
        return {}
    who = pl.DataFrame(rows, schema=["team", "gsis_id", "grp"], orient="row")  # noqa: F841  read by duckdb
    q = f"""
    with p as (select *, case when season = {season} then 1.0 else {LAST_SEASON} end as w from plays
               where season in ({season - 1}, {season}) and season_type = 'REG'
               and coalesce(special_teams_play, 0) = 0 and epa is not null),
    x as (
      select who.team, who.grp, p.w, p.qb_epa as epa, p.success from who join p
        on who.grp = 'QB' and p.qb_dropback = 1 and p.passer_player_id = who.gsis_id
      union all
      select who.team, who.grp, p.w, p.epa, p.success from who join p
        on who.grp = 'RB' and p.rush = 1 and p.rusher_player_id = who.gsis_id
      union all
      select who.team, who.grp, p.w, p.epa, p.success from who join p
        on who.grp in ('WR', 'TE') and p.pass = 1 and p.receiver_player_id = who.gsis_id
    )
    select team, grp, sum(w)::double as n, sum(w * epa)::double as epa, sum(w * success)::double as success,
           count(*) as plays
    from x group by 1, 2
    """
    df = con.sql(q).pl()
    out: dict[str, dict] = {}
    for (grp,), d in df.partition_by("grp", as_dict=True).items():
        n, k = d["n"].sum(), SHRINK[grp]
        mean = {c: d[c].sum() / n for c in ("epa", "success")}
        for r in d.iter_rows(named=True):
            vals = {f"{grp.lower()}_{c}": (r[c] + k * mean[c]) / (r["n"] + k) for c in mean}
            out.setdefault(r["team"], {})[grp] = {"plays": r["plays"], **vals}
    return out


# stat -> (numerator, denominator) columns of `week_sums`
RATIO: dict[str, tuple[str, str]] = {
    "qb_epa": ("qb_epa", "dropbacks"), "qb_success": ("qb_success", "dropbacks"),
    "ol_sack": ("sacks", "dropbacks"), "ol_pressure": ("pressured", "dropbacks"), "ol_ybc": ("ybc", "carries"),
    "rb_epa": ("rb_epa", "rb_rushes"), "rb_yac": ("rb_yac", "rb_carries"),
    "wr_epa": ("wr_epa", "wr_targets"), "wr_success": ("wr_success", "wr_targets"),
    "te_epa": ("te_epa", "te_targets"), "te_success": ("te_success", "te_targets"),
    "edge_pressure": ("edge_p", "opp_dropbacks"), "edge_sack": ("edge_s", "opp_dropbacks"),
    "dl_pressure": ("dl_p", "opp_dropbacks"), "dl_ybc": ("opp_ybc", "opp_carries"),
    "lb_rush_epa": ("opp_rush_epa", "opp_rushes"), "lb_missed": ("lb_missed", "lb_chances"),
    "cb_ypt": ("cb_yds", "cb_targets"), "cb_cmp": ("cb_cmp", "cb_targets"),
    "s_ypt": ("s_yds", "s_targets"), "s_missed": ("s_missed", "s_chances"),
}  # fmt: skip


def week_sums(con: duckdb.DuckDBPyConnection, season: int) -> pl.DataFrame:
    """One row per team and regular-season week played: the sums behind every stat in `RATIO`."""
    q = f"""
    with grp as ({_group_sql()}),
    p as (select * from plays where season = {season} and season_type = 'REG'
          and posteam is not null and coalesce(special_teams_play, 0) = 0 and epa is not null),
    gm as (select distinct posteam as team, week from p),
    off as (select p.posteam as team, p.week,
              count(*) filter (where qb_dropback = 1) as dropbacks,
              sum(qb_epa) filter (where qb_dropback = 1) as qb_epa,
              sum(success) filter (where qb_dropback = 1) as qb_success,
              sum(sack) filter (where qb_dropback = 1) as sacks,
              count(*) filter (where rush = 1 and r.grp = 'RB') as rb_rushes,
              sum(epa) filter (where rush = 1 and r.grp = 'RB') as rb_epa,
              count(*) filter (where pass = 1 and c.grp = 'WR') as wr_targets,
              sum(epa) filter (where pass = 1 and c.grp = 'WR') as wr_epa,
              sum(success) filter (where pass = 1 and c.grp = 'WR') as wr_success,
              count(*) filter (where pass = 1 and c.grp = 'TE') as te_targets,
              sum(epa) filter (where pass = 1 and c.grp = 'TE') as te_epa,
              sum(success) filter (where pass = 1 and c.grp = 'TE') as te_success
            from p left join grp r on r.gsis_id = p.rusher_player_id
                   left join grp c on c.gsis_id = p.receiver_player_id
            group by 1, 2),
    def as (select defteam as team, week,
              count(*) filter (where qb_dropback = 1) as opp_dropbacks,
              count(*) filter (where rush = 1) as opp_rushes,
              sum(epa) filter (where rush = 1) as opp_rush_epa
            from p group by 1, 2),
    pp as (select team, week, sum(times_pressured) as pressured from pfr_pass
           where season = {season} and game_type = 'REG' group by 1, 2),
    rr as (select r.team, r.opponent, r.week, r.carries, r.rushing_yards_before_contact as ybc,
                  r.rushing_yards_after_contact as yac, g.grp
           from pfr_rush r left join grp g on g.pfr_id = r.pfr_player_id
           where r.season = {season} and r.game_type = 'REG'),
    ry as (select team, week, sum(ybc) as ybc, sum(carries) as carries,
                  sum(yac) filter (where grp = 'RB') as rb_yac,
                  sum(carries) filter (where grp = 'RB') as rb_carries
           from rr group by 1, 2),
    ory as (select opponent as team, week, sum(ybc) as opp_ybc, sum(carries) as opp_carries
            from rr group by 1, 2),
    dd as (select d.team, d.week, g.grp, d.def_pressures as pr, d.def_sacks as sk,
                  d.def_targets as tg, d.def_completions_allowed as cm, d.def_yards_allowed as yd,
                  d.def_missed_tackles as mt, d.def_tackles_combined as tk
           from pfr_def d left join grp g on g.pfr_id = d.pfr_player_id
           where d.season = {season} and d.game_type = 'REG'),
    dw as (select team, week,
             sum(pr) filter (where grp = 'EDGE') as edge_p, sum(sk) filter (where grp = 'EDGE') as edge_s,
             sum(pr) filter (where grp = 'DL') as dl_p,
             sum(yd) filter (where grp = 'CB') as cb_yds, sum(cm) filter (where grp = 'CB') as cb_cmp,
             sum(tg) filter (where grp = 'CB') as cb_targets,
             sum(yd) filter (where grp = 'S') as s_yds, sum(tg) filter (where grp = 'S') as s_targets,
             sum(mt) filter (where grp = 'S') as s_missed, sum(mt + tk) filter (where grp = 'S') as s_chances,
             sum(mt) filter (where grp = 'LB') as lb_missed, sum(mt + tk) filter (where grp = 'LB') as lb_chances
           from dd group by 1, 2)
    select * from gm
    left join off using (team, week) left join def using (team, week) left join pp using (team, week)
    left join ry using (team, week) left join ory using (team, week) left join dw using (team, week)
    order by team, week
    """
    return con.sql(q).pl()


def stats(
    sums: pl.DataFrame,
    counted: dict[tuple[str, str], set[int]] | None = None,
    players: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """team -> {games, room -> {stat: value}} from the weekly sums. `counted` limits a (team, room)
    to the weeks it was near full strength (`healthy_weeks`); a room with fewer than `MIN_GAMES`
    such weeks uses every week."""
    out: dict[str, dict] = {}
    for (team,), df in sums.partition_by("team", as_dict=True).items():
        weeks = set(df["week"].to_list())
        t = {"games": len(weeks)}
        for room, specs in STATS.items():
            if room in PLAYER_ROOMS:
                pr = (players or {}).get(team, {}).get(room)
                t[room] = {"basis": "players", "plays": pr["plays"] if pr else 0,
                           **{k: (pr or {}).get(k) for k, _, _ in specs}}  # fmt: skip
                continue
            keep = (counted or {}).get((team, room))
            use = keep & weeks if keep is not None and len(keep & weeks) >= MIN_GAMES else weeks
            d = df.filter(pl.col("week").is_in(sorted(use)))
            vals = {}
            for key, _, _ in specs:
                n, dn = RATIO[key]
                den = d[dn].fill_null(0).sum()
                vals[key] = d[n].fill_null(0).sum() / den if den else None
            t[room] = {"basis": "team", "games": len(use), **vals}
        out[team] = t
    return out


def healthy_weeks(
    by_week: dict[str, list[dict]], share: float = 0.8
) -> dict[tuple[str, str], set[int]]:
    """(team, room) -> the weeks the room went in with at least `share` of its spot weight: from
    team health's `by_week` rows, which carry `rooms` (room -> health)."""
    out: dict[tuple[str, str], set[int]] = {}
    for team, weeks in by_week.items():
        for w in weeks:
            for room, h in (w.get("rooms") or {}).items():
                if h is not None and h >= share:
                    out.setdefault((team, room), set()).add(w["week"])
    return out


def label(rank: int) -> str:
    return next(lab for top, lab in LABELS if rank <= top)


def _rank(value: float, others: list[float]) -> int:
    """1 + how many of `others` are strictly better (higher)."""
    return 1 + sum(1 for o in others if o > value)


def grades(st: dict[str, dict]) -> dict[str, dict[str, dict]]:
    """team -> room -> {z, rank, label, basis, games or plays, stats: [{key, label, value, rank}]}."""
    teams = sorted(t for t, v in st.items() if v["games"] >= MIN_GAMES)
    out: dict[str, dict[str, dict]] = {t: {} for t in teams}
    for room, specs in STATS.items():
        zs: dict[str, list[float]] = {t: [] for t in teams}
        rows: dict[str, list[dict]] = {t: [] for t in teams}
        for key, lab, higher in specs:
            vals = {t: st[t][room][key] for t in teams if st[t][room][key] is not None}
            if len(vals) < 2:
                continue
            xs = list(vals.values())
            mean = sum(xs) / len(xs)
            sd = (sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5
            if not sd:
                continue
            signed = {t: v if higher else -v for t, v in vals.items()}
            for t, v in vals.items():
                zs[t].append((v - mean) / sd * (1 if higher else -1))
                rows[t].append(
                    {
                        "key": key,
                        "label": lab,
                        "value": round(v, 4),
                        "rank": _rank(signed[t], list(signed.values())),
                    }
                )
        z = {t: sum(v) / len(v) for t, v in zs.items() if v}
        for t, zt in z.items():
            r = _rank(zt, list(z.values()))
            out[t][room] = {"z": round(zt, 3), "rank": r, "label": label(r), "basis": st[t][room]["basis"],
                          "games": st[t][room].get("games"), "plays": st[t][room].get("plays"), "stats": rows[t]}  # fmt: skip
    return out


def with_now(
    rooms: dict[str, dict[str, dict]], groups: dict[str, list[dict]]
) -> dict[str, list[dict]]:
    """team -> [room rows] with the estimate now: `groups` is team -> its health groups (`grp`,
    `health`). The now rank is against every team's full grade in that room."""
    out: dict[str, list[dict]] = {}
    for team, rs in rooms.items():
        hs = {g["grp"]: g.get("health") for g in groups.get(team, [])}
        rows = []
        for room in STATS:
            if room not in rs:
                continue
            r = rs[room]
            league = [o[room]["z"] for t, o in rooms.items() if t != team and room in o]
            h = hs.get(room)
            z_now = r["z"] if h is None else h * r["z"] + (1 - h) * Z_REPLACEMENT
            now = _rank(z_now, league)
            rows.append(
                {
                    "grp": room,
                    **r,
                    "health": h,
                    "z_now": round(z_now, 3),
                    "now_rank": now,
                    "now_label": label(now),
                }
            )
        out[team] = rows
    return out
