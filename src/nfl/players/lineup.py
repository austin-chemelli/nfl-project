"""Each side's eleven starters on offense and defense for an upcoming game, with what each is worth
and his status this week: the data behind the Injuries tab's formation map (ADR 0027, M24.5).

Starters come from the team's latest depth chart taken before the cutoff (the 2026 charts are
timestamped): the top-ranked player at each formation spot of the base offense (3WR 1TE) and base
defense (4-3 or 3-4). The fullback and the nickel back are extra spots, not part of the eleven.
Values come from the M24.2 model; linebackers and interior linemen have none yet (not a v1 group), so
they carry no number. A status shows only for a player listed Out, Doubtful or Questionable on the
game week's report; everyone else is unlisted, never "healthy" by inference.

Context only: nothing here reaches a lock or a feature.
"""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl

from nfl.players import claims as C

EXTRA = ("FB", "NB")
OFFENSE_ORDER = ("LT", "LG", "C", "RG", "RT", "TE", "WR1", "WR2", "WR3", "QB", "RB")
DEFENSE_ORDER = (
    "LDE", "LDT", "NT", "RDT", "RDE", "SLB", "LILB", "MLB", "RILB", "WLB", "LCB", "RCB", "SS", "FS",
)  # fmt: skip


def _ts(dt: str) -> datetime:
    """A chart's time as naive UTC: an offset is converted, a naive time is taken as UTC."""
    t = datetime.fromisoformat(dt)
    return t.astimezone(UTC).replace(tzinfo=None) if t.tzinfo else t


def with_chart_dt(depth: pl.DataFrame) -> pl.DataFrame:
    """`chart_dt` (naive UTC) from `dt`, unless the frame already has it (parse once per build)."""
    if "chart_dt" in depth.columns:
        return depth
    return depth.with_columns(
        pl.col("dt").map_elements(_ts, return_dtype=pl.Datetime("us")).alias("chart_dt")
    )


def starters(depth: pl.DataFrame, team: str, cutoff: datetime) -> pl.DataFrame:
    """The team's latest chart before `cutoff`: one row per formation spot (slot, unit, formation,
    gsis_id, player, chart_dt), the top-ranked player at each. Empty without a chart."""
    d = depth.filter(
        (pl.col("team") == team)
        & pl.col("dt").is_not_null()
        & (pl.col("pos_grp") != "Special Teams")
        & ~pl.col("pos_abb").is_in(EXTRA)
    )
    d = with_chart_dt(d).filter(pl.col("chart_dt") < cutoff)
    if d.is_empty():
        return pl.DataFrame()
    d = d.filter(pl.col("chart_dt") == d["chart_dt"].max())
    # the starter is the top rank at each spot; a starter the chart can't name leaves the spot empty
    # rather than promoting his backup
    top = (
        d.sort("pos_rank")
        .group_by("pos_abb", "pos_slot", maintain_order=True)
        .first()
        .filter(pl.col("gsis_id").is_not_null() & pl.col("player_name").is_not_null())
    )
    wr = top.filter(pl.col("pos_abb") == "WR").sort("pos_rank")
    wr = wr.with_columns(pl.format("WR{}", pl.int_range(1, wr.height + 1)).alias("slot"))
    rest = top.filter(pl.col("pos_abb") != "WR").with_columns(pl.col("pos_abb").alias("slot"))
    return pl.concat([wr, rest], how="diagonal").select(
        "slot",
        pl.when(pl.col("pos_grp").str.starts_with("Base"))
        .then(pl.lit("defense"))
        .otherwise(pl.lit("offense"))
        .alias("unit"),
        pl.col("pos_grp").alias("formation"),
        "pos_abb",
        "gsis_id",
        pl.col("player_name").alias("player"),
        "chart_dt",
    )


def _spot(r: dict, values: dict, listed: dict, rates: dict) -> dict:
    v = values.get(r["gsis_id"])
    value = round(float(v["value_pts"]), 2) if v else None
    inj = listed.get(r["gsis_id"])
    status = inj["status"] if inj else None
    # Out never plays, as in the claims (the rate table's Out rows are a few late activations)
    p_play = (
        (0.0 if status == "Out" else C._rate(rates, status, inj.get("pos"))[0]) if inj else None
    )
    p_play = round(p_play, 4) if p_play is not None else None
    at_risk = round(value * (1 - p_play), 2) if value is not None and p_play is not None else None
    return {
        "slot": r["slot"], "player": r["player"], "grp": v["grp"] if v else None,
        "value_pts": value, "status": status, "p_play": p_play, "at_risk": at_risk,
    }  # fmt: skip


def side(
    depth: pl.DataFrame, team: str, week: int, cutoff: datetime, values: pl.DataFrame,
    injuries: list[dict], rates: dict,
) -> dict | None:  # fmt: skip
    """One side's lineup: formations, the chart's time (UTC), whether the week's report has any game
    status for the team yet (`reported`: before it, a full ring means no report, not "healthy"), and
    each unit's spots in display order."""
    s = starters(depth, team, cutoff)
    if s.is_empty():
        return None
    if "week" in values.columns:
        values = values.filter(pl.col("week") == week)
    # by player, not team: a player traded since his last game is valued for his new team
    vals = {r["gsis_id"]: r for r in values.iter_rows(named=True)}
    week_rows = [i for i in injuries if i["team"] == team and i["week"] == week]
    listed = {i["gsis_id"]: i for i in week_rows if i["status"] in C.GAME_STATUSES}
    out: dict = {
        "chart_ts": s["chart_dt"].max().isoformat() + "Z",
        "reported": any(i["status"] in C.GAME_STATUSES for i in week_rows),
    }
    # a regular starter on the report whom the chart has already moved down: the map would show his
    # replacement full, hiding the very absence it is for
    on_map = set(s["gsis_id"].to_list())
    out["off_chart"] = sorted(
        (
            {**_spot({"slot": v["grp"], "player": v["player"], "gsis_id": g}, vals, listed, rates)}
            for g, v in vals.items()
            if g in listed
            and g not in on_map
            and v.get("role", 0) >= C.STARTER_ROLE
            and v["value_pts"] >= C.MIN_VALUE  # as in the claims: below it, nothing to say
        ),
        key=lambda x: -(x["value_pts"] or 0),
    )
    for unit, order in (("offense", OFFENSE_ORDER), ("defense", DEFENSE_ORDER)):
        u = s.filter(pl.col("unit") == unit)
        rank = {k: i for i, k in enumerate(order)}
        rows = sorted(u.iter_rows(named=True), key=lambda r: rank.get(r["slot"], len(order)))
        out[unit] = [_spot(r, vals, listed, rates) for r in rows]
        out[f"{unit}_formation"] = u["formation"][0] if u.height else None
    return out


def lineups(
    games: pl.DataFrame, depth: pl.DataFrame, values: pl.DataFrame, injuries: list[dict],
    rates: dict, now: datetime,
) -> dict[str, dict]:  # fmt: skip
    """game_id -> {home, away} lineups for the games not yet kicked off; the chart cutoff is now."""
    out = {}
    for g in games.filter(pl.col("kickoff_utc") > now).iter_rows(named=True):
        sides = {
            k: side(depth, g[f"{k}_team"], g["week"], now, values, injuries, rates)
            for k in ("home", "away")
        }
        if any(sides.values()):
            out[g["game_id"]] = sides
    return out
