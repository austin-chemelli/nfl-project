"""Scored impact claims (ADR 0027, M24.4).

While player value is context only, the public claim is the player's value and his status, e.g.
"Ja'Marr Chase is worth about 1.2 points to CIN. Questionable: wide receivers listed Questionable
have played 73% of the time." Each daily pass records, per upcoming game and side, the three most
valuable listed starters (game status Out, Doubtful or Questionable) in `marts/player_claims.parquet`,
append-only: one row per (game, player, injury snapshot). `player_claims_passes.parquet` logs every
(game, snapshot) a pass looked at, claims or not, so a rerun on the same snapshot adds nothing and the
pages show the latest look ("nobody listed now" replaces an older snapshot's claims).

**Grading.** The market had priced his absence at P(out) x value. When a later injury snapshot shows
him Out before kickoff, the rest, `expected = value x P(play)`, should move the line toward the
opponent. The claim made from the last snapshot before the change is graded once against the
consensus spread's move from the first line at or after the claim's snapshot to the first line after
the change, and only when his status just before Out was the claim's
(`market_history.paths`), and written to `marts/player_claims_graded.parquet`, append-only: a graded
claim is never graded again. Claims about players who play, or who were already Out, get no market
grade; the game's result against the pre-change line (`margin_vs_line`) is derived for the season-end
look. Most values are under a point and one line move is noisy, so only the aggregate means much.

The lock never reads these files: claims are context, not model input.
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from nfl import io
from nfl.config import Paths
from nfl.players import priors as P
from nfl.players import status as S

FILE = "player_claims.parquet"
GRADED = "player_claims_graded.parquet"
PASSES = "player_claims_passes.parquet"  # every (game, injury snapshot) a pass looked at
TOP_N = 3
GAME_STATUSES = ("Out", "Doubtful", "Questionable")
STARTER_ROLE = P.REGULAR_ROLE  # a listed player counts as a starter from this snap share
MIN_VALUE = 0.1  # points: below this a claim says nothing ("worth about 0.0 points")
ERA = f"{S.CURRENT_ERA_FROM}+"

SCHEMA = {
    "claim_id": pl.Utf8, "pass_ts": pl.Datetime("us"), "injury_ts": pl.Datetime("us"),
    "season": pl.Int64, "week": pl.Int64, "game_id": pl.Utf8, "kickoff_utc": pl.Datetime("us"),
    "team": pl.Utf8, "opponent": pl.Utf8, "side": pl.Utf8, "gsis_id": pl.Utf8, "player": pl.Utf8,
    "pos": pl.Utf8, "grp": pl.Utf8, "status": pl.Utf8, "p_play": pl.Float64, "p_play_n": pl.Int64,
    "value_pts": pl.Float64, "at_risk": pl.Float64, "rank": pl.Int64, "sentence": pl.Utf8,
}  # fmt: skip
PASS_SCHEMA = {
    "pass_ts": pl.Datetime("us"), "injury_ts": pl.Datetime("us"), "season": pl.Int64,
    "week": pl.Int64, "game_id": pl.Utf8, "home_team": pl.Utf8, "away_team": pl.Utf8,
}  # fmt: skip
GRADE_SCHEMA = {
    "claim_id": pl.Utf8, "graded_ts": pl.Datetime("us"), "out_ts": pl.Datetime("us"),
    "line_before_ts": pl.Datetime("us"), "line_before": pl.Float64,
    "line_after_ts": pl.Datetime("us"), "line_after": pl.Float64,
    "expected": pl.Float64, "moved": pl.Float64, "hours": pl.Float64,
}  # fmt: skip

GROUP_PLURAL = {
    "QB": "quarterbacks", "RB": "running backs", "WR": "wide receivers", "TE": "tight ends",
    "OL": "offensive linemen", "DL": "defensive linemen", "LB": "linebackers",
    "DB": "defensive backs", "ST": "specialists",
}  # fmt: skip


# ------------------------------------------------------------------------------------ the claims


def play_rates(rates: pl.DataFrame) -> dict[tuple[str, str], tuple[float, int]]:
    """(status, report position group) -> (P(played), n) for the current era; 'all' per status too."""
    r = rates.filter(pl.col("era") == ERA)
    return {(x["status"], x["pos_group"]): (float(x["rate"]), int(x["n"])) for x in r.iter_rows(named=True)}  # fmt: skip


def _rate(rates: dict, status: str, pos: str | None) -> tuple[float, int, str]:
    grp = S.POS_GROUP.get((pos or "").strip())
    if (status, grp) in rates:
        return (*rates[(status, grp)], grp)
    p, n = rates.get((status, "all"), (0.0 if status == "Out" else None, 0))
    return p, n, "all"


def pct(p: float) -> str:
    return f"{round(100 * p)}%"


def sentence(player: str, team: str, value: float, status: str, p_play: float | None, rate_grp: str) -> str:  # fmt: skip
    """'J. Chase is worth about 1.2 points to CIN. Questionable: wide receivers listed Questionable
    have played 73% of the time.'"""
    out = f"{player} is worth about {value:.1f} points to {team}."
    if status == "Out" or p_play is None:
        return out + f" {status}."
    who = GROUP_PLURAL.get(rate_grp, "players")
    return out + f" {status}: {who} listed {status} have played {pct(p_play)} of the time."


def make(
    games: pl.DataFrame, injuries: pl.DataFrame, injury_ts: datetime, values: pl.DataFrame,
    rates: dict, pass_ts: datetime,
) -> pl.DataFrame:  # fmt: skip
    """The claims for `games` (upcoming: game_id, season, week, kickoff_utc, home_team, away_team)
    from one injury snapshot (team, week, gsis_id, full_name, position, report_status) and the week's
    values (season, week, gsis_id, grp, role, value_pts). Pure."""
    if games.is_empty() or injuries.is_empty() or values.is_empty():
        return pl.DataFrame(schema=SCHEMA)
    listed = injuries.filter(
        pl.col("report_status").is_in(GAME_STATUSES) & pl.col("gsis_id").is_not_null()
    ).unique(["team", "week", "gsis_id"], keep="last")
    val = values.filter(
        (pl.col("role") >= STARTER_ROLE) & (pl.col("value_pts") >= MIN_VALUE)
    ).select("season", "week", "gsis_id", "grp", "value_pts")
    rows = []
    for g in games.iter_rows(named=True):
        for side, team, opp in (("home", g["home_team"], g["away_team"]), ("away", g["away_team"], g["home_team"])):  # fmt: skip
            inj = listed.filter((pl.col("team") == team) & (pl.col("week") == g["week"]))
            if inj.is_empty():
                continue
            v = inj.join(
                val.filter((pl.col("season") == g["season"]) & (pl.col("week") == g["week"])),
                on=["week", "gsis_id"],
            ).sort("value_pts", "gsis_id", descending=[True, False])
            for rank, r in enumerate(v.head(TOP_N).iter_rows(named=True), start=1):
                st = r["report_status"]
                p_play, n, rgrp = (0.0, *_rate(rates, st, r["position"])[1:]) if st == "Out" else _rate(rates, st, r["position"])  # fmt: skip
                value = round(float(r["value_pts"]), 2)
                rows.append({
                    "claim_id": f"{g['game_id']}:{r['gsis_id']}:{injury_ts:%Y%m%dT%H%M%S}",
                    "pass_ts": pass_ts, "injury_ts": injury_ts, "season": int(g["season"]),
                    "week": int(g["week"]), "game_id": g["game_id"], "kickoff_utc": g["kickoff_utc"],
                    "team": team, "opponent": opp, "side": side, "gsis_id": r["gsis_id"],
                    "player": r["full_name"], "pos": r["position"], "grp": r["grp"], "status": st,
                    "p_play": None if p_play is None else round(p_play, 4), "p_play_n": n,
                    "value_pts": value,
                    "at_risk": None if p_play is None else round(value * (1 - p_play), 2),
                    "rank": rank,
                    "sentence": sentence(r["full_name"], team, value, st, p_play, rgrp),
                })  # fmt: skip
    return pl.DataFrame(rows, schema=SCHEMA) if rows else pl.DataFrame(schema=SCHEMA)


def load(paths: Paths) -> pl.DataFrame:
    return io.read(paths.marts / FILE, SCHEMA)


def load_passes(paths: Paths) -> pl.DataFrame:
    return io.read(paths.marts / PASSES, PASS_SCHEMA)


def append(
    paths: Paths, new: pl.DataFrame, games: pl.DataFrame, injury_ts: datetime, pass_ts: datetime
) -> int:
    """Append-only. A (game, injury snapshot) already looked at is skipped whole, so a rerun on the
    same snapshot adds nothing even if values moved in between. Every game looked at is logged, with
    or without claims: "nobody listed now" must replace an older snapshot's claims on the pages."""
    seen = load_passes(paths).filter(pl.col("injury_ts") == injury_ts)["game_id"]
    fresh = games.filter(~pl.col("game_id").is_in(seen.implode()))
    if fresh.is_empty():
        return 0
    log = fresh.select(
        pl.lit(pass_ts, dtype=pl.Datetime("us")).alias("pass_ts"),
        pl.lit(injury_ts, dtype=pl.Datetime("us")).alias("injury_ts"),
        "season", "week", "game_id", "home_team", "away_team",
    )  # fmt: skip
    io.append(paths.marts / PASSES, log, PASS_SCHEMA)
    new = new.filter(pl.col("game_id").is_in(fresh["game_id"].implode()))
    return io.append(paths.marts / FILE, new, SCHEMA) if not new.is_empty() else 0


# ------------------------------------------------------------------------------------- grading


def _lines(points: list[dict], claim_ts: datetime, change: datetime) -> tuple[dict, dict] | None:
    """(before, after) the change. Before: the first line taken at or after the claim's snapshot
    (the claim's own pass takes odds right after its ingest), so a line taken after the news broke
    but before our next ingest saw it can't stand in for "before"; the last line before the claim
    when none falls inside the window. After: the first line at or after the change."""
    seq = [p for p in points if p.get("spread_home") is not None]
    inside = [p for p in seq if claim_ts <= p["snapshot_ts"] < change]
    earlier = [p for p in seq if p["snapshot_ts"] < claim_ts]
    after = [p for p in seq if p["snapshot_ts"] >= change]
    a = inside[0] if inside else (earlier[-1] if earlier else None)
    return (a, after[0]) if a is not None and after else None


def grade(
    claims: pl.DataFrame, transitions: list[dict], points: dict[str, list[dict]],
    done: set[str], now: datetime,
) -> pl.DataFrame:  # fmt: skip
    """Grade rows for claims not in `done`. `transitions`: `market_events.injury_transitions`;
    `points`: game_id -> `market_history.paths` rows, oldest first. A claim is graded when the first
    change to Out after it is seen before kickoff and a line exists on both sides of that change;
    a change seen after kickoff never grades. Pure."""
    if claims.is_empty():
        return pl.DataFrame(schema=GRADE_SCHEMA)
    outs: dict[tuple[int, str], list[tuple[datetime, str | None]]] = {}
    for t in transitions:
        if t["status"] == "Out":
            outs.setdefault((int(t["week"]), t["gsis_id"]), []).append((t["ts"], t["was"]))
    rows = []
    open_ = claims.filter(pl.col("status") != "Out").sort("injury_ts")
    for (gid, gsis), c in open_.group_by("game_id", "gsis_id", maintain_order=True):
        first = c.row(0, named=True)
        kick = first["kickoff_utc"]
        found = min(
            (x for x in outs.get((first["week"], gsis), []) if first["injury_ts"] < x[0] < kick),
            default=None,
        )
        if found is None:
            continue
        change, was = found
        claim = c.filter(pl.col("injury_ts") < change).row(-1, named=True)
        # his status just before Out must be the claim's: Questionable, then cleared, then Out was
        # priced as playing, and the claim's P(play) would set the wrong expectation
        if claim["claim_id"] in done or was != claim["status"] or claim["p_play"] is None:
            continue
        ab = _lines(points.get(gid, []), claim["injury_ts"], change)
        if ab is None:
            continue  # no line on one side yet: wait (a game that kicks off first never grades)
        a, b = ab
        d = b["spread_home"] - a["spread_home"]
        moved = -d if claim["side"] == "home" else d  # toward the opponent, in points
        rows.append({
            "claim_id": claim["claim_id"], "graded_ts": now, "out_ts": change,
            "line_before_ts": a["snapshot_ts"], "line_before": a["spread_home"],
            "line_after_ts": b["snapshot_ts"], "line_after": b["spread_home"],
            "expected": round(claim["value_pts"] * claim["p_play"], 2),
            "moved": round(moved, 2),
            "hours": round((b["snapshot_ts"] - a["snapshot_ts"]).total_seconds() / 3600, 1),
        })  # fmt: skip
    return pl.DataFrame(rows, schema=GRADE_SCHEMA) if rows else pl.DataFrame(schema=GRADE_SCHEMA)


def load_grades(paths: Paths) -> pl.DataFrame:
    return io.read(paths.marts / GRADED, GRADE_SCHEMA)


def grade_new(paths: Paths, season: int, now: datetime) -> int:
    """Grade every claim that can be graded and hasn't been; append the grades."""
    from nfl import market_events, market_history
    from nfl.odds import read_lines

    claims = load(paths).filter(pl.col("season") == season)
    if claims.is_empty():
        return 0
    done = set(load_grades(paths)["claim_id"].to_list())
    trans = market_events.injury_transitions(market_events.load_injury_snapshots(paths, season))
    pts: dict[str, list[dict]] = {}
    for r in market_history.paths(read_lines(paths, (season, season))).iter_rows(named=True):
        pts.setdefault(r["game_id"], []).append(r)
    new = grade(claims, trans, pts, done, now)
    return io.append(paths.marts / GRADED, new, GRADE_SCHEMA) if not new.is_empty() else 0


# ------------------------------------------------------------------------------------ the pass


def rate_table(paths: Paths) -> pl.DataFrame:
    f = S.out_path(paths)
    return pl.read_parquet(f) if f.exists() else S.build(paths)


def run(paths: Paths, season: int, now: datetime) -> tuple[int, int]:
    """The daily pass's step: claims for every upcoming game of `season` from the latest injury
    snapshot, then grades for any claim the newest snapshots settle. Returns (claims, grades) added."""
    from nfl import market_events
    from nfl.features import store
    from nfl.players.value import week_values

    now = now.replace(tzinfo=None)
    snaps = market_events.load_injury_snapshots(paths, season)
    added = 0
    if snaps:
        injury_ts, inj = snaps[-1]
        games = (
            store.games_frame(paths)
            .filter(pl.col("season") == season)
            .with_columns(pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us")))
            .filter((pl.col("kickoff_utc") > now) & (pl.col("game_type") == "REG"))
        )
        if not games.is_empty():
            values = week_values(paths, season, games["week"].unique().to_list())
            new = make(games, inj, injury_ts, values, play_rates(rate_table(paths)), now)
            added = append(paths, new, games, injury_ts, now)
    return added, grade_new(paths, season, now)


# --------------------------------------------------------------------------------- site sections

_PUBLIC = [
    "player",
    "pos",
    "grp",
    "status",
    "p_play",
    "p_play_n",
    "value_pts",
    "at_risk",
    "sentence",
]


def _latest(claims: pl.DataFrame, passes: pl.DataFrame) -> tuple[dict[str, datetime], pl.DataFrame]:  # fmt: skip
    """game_id -> the last snapshot a pass looked at for it, and the claims from exactly that one."""
    if passes.is_empty():
        return {}, claims.clear()
    last = passes.group_by("game_id").agg(pl.col("injury_ts").max().alias("_last"))
    latest = claims.join(last, on="game_id").filter(pl.col("injury_ts") == pl.col("_last"))
    return dict(last.iter_rows()), latest.drop("_last")


def key_players(claims: pl.DataFrame, passes: pl.DataFrame) -> dict[str, dict[str, list[dict]]]:
    """game_id -> {home, away}: the claims from the last snapshot a pass looked at for that game, by
    rank; empty lists when nobody was listed then. Games no pass looked at are absent."""
    looked, latest = _latest(claims, passes)
    out: dict[str, dict[str, list[dict]]] = {g: {"home": [], "away": []} for g in looked}
    for r in latest.sort("game_id", "side", "rank").iter_rows(named=True):
        out[r["game_id"]][r["side"]].append({k: r[k] for k in _PUBLIC})
    return out


def record(claims: pl.DataFrame, grades: pl.DataFrame, results: dict[str, float | None]) -> dict | None:  # fmt: skip
    """The tracker section: counts, the graded claims newest first, and their means. `results`:
    game_id -> home margin for finished games (`margin_vs_line`: the team's margin against the
    pre-change line, from its own side; expected around -`expected`)."""
    if claims.is_empty():
        return None
    g = grades.join(claims, on="claim_id", how="inner").sort("out_ts", descending=True)
    rows = []
    for r in g.iter_rows(named=True):
        m = results.get(r["game_id"])
        team_margin = None if m is None else (m if r["side"] == "home" else -m)
        line_team = r["line_before"] if r["side"] == "home" else -r["line_before"]
        rows.append({
            "game_id": r["game_id"], "season": r["season"], "week": r["week"], "team": r["team"],
            "opponent": r["opponent"], "player": r["player"], "pos": r["pos"], "grp": r["grp"],
            "status_before": r["status"], "p_play": r["p_play"], "value_pts": r["value_pts"],
            "expected": r["expected"], "moved": r["moved"], "hours": r["hours"],
            "out_seen": r["out_ts"].isoformat() + "Z",
            "margin_vs_line": None if team_margin is None else round(team_margin - line_team, 1),
        })  # fmt: skip
    mean = lambda k: round(sum(x[k] for x in rows) / len(rows), 2) if rows else None
    return {
        "first_pass": claims["pass_ts"].min().isoformat() + "Z",
        "claims": claims.select("game_id", "gsis_id").unique().height,
        "graded": len(rows),
        "mean_expected": mean("expected"),
        "mean_moved": mean("moved"),
        "rows": rows,
    }


def availability(
    values: pl.DataFrame, claims: pl.DataFrame, passes: pl.DataFrame, team: str, n: int = 6,
    injuries: list[dict] | None = None, rates: dict | None = None,
) -> dict | None:  # fmt: skip
    """A team's most valuable regular starters for the week, each with his status, and the value at
    risk summed over its listed starters. With `injuries` (the site's report rows) and `rates`, the
    statuses come from the week's report itself, so the panel agrees with the game page and the map;
    without, from the last snapshot a claims pass looked at. `reported` is false, and the value at
    risk null, before the week's report has any game status: no report yet is not "nobody hurt".
    `listed` is the scored claims (their sentences), from the last pass."""
    v = values.filter((pl.col("team") == team) & (pl.col("role") >= STARTER_ROLE))
    if v.is_empty():
        return None
    week = int(v["week"].max())
    games = passes.filter(
        (pl.col("week") == week) & ((pl.col("home_team") == team) | (pl.col("away_team") == team))
    )
    looked, latest = _latest(claims, games)
    c = latest.filter(pl.col("team") == team)
    by_id = {r["gsis_id"]: r for r in c.iter_rows(named=True)}
    if injuries is not None:
        report = {
            i["gsis_id"]: i
            for i in injuries
            if i["team"] == team and i["week"] == week and i["status"] in GAME_STATUSES
        }

        def status(r: dict) -> dict | None:
            i = report.get(r["gsis_id"])
            if not i:
                return None
            p = 0.0 if i["status"] == "Out" else _rate(rates or {}, i["status"], i.get("pos"))[0]
            risk = round(float(r["value_pts"]) * (1 - p), 2) if p is not None else None
            return {
                "status": i["status"],
                "p_play": round(p, 4) if p is not None else None,
                "at_risk": risk,
            }

        reported = bool(report) or bool(looked)
        risks = [
            x["at_risk"]
            for x in map(status, v.iter_rows(named=True))
            if x and x["at_risk"] is not None
        ]
    else:

        def status(r: dict) -> dict | None:
            return by_id.get(r["gsis_id"])

        reported = bool(looked)
        risks = [x["at_risk"] for x in by_id.values() if x["at_risk"] is not None]
    players = []
    for r in v.sort("value_pts", descending=True).head(n).iter_rows(named=True):
        st = status(r)
        players.append({
            "player": r["player"], "grp": r["grp"], "value_pts": round(float(r["value_pts"]), 2),
            "status": st["status"] if st else None, "p_play": st["p_play"] if st else None,
            "at_risk": st["at_risk"] if st else None,
        })  # fmt: skip
    return {
        "week": week,
        "reported": reported,
        "players": players,
        "listed": [
            {k: x[k] for k in _PUBLIC} for x in sorted(by_id.values(), key=lambda x: x["rank"])
        ],
        "value_at_risk": (round(sum(risks), 2) if risks else 0.0) if reported else None,
    }
