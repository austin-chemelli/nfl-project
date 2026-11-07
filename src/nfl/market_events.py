"""What changed in the window: dated events that line up with a line move (ADR 0023, M20.3).

The words are "in the same window", never "because": a move and an event at the same time are
shown together, and the reader judges. Every event carries the time we first saw it.

Sources, all already in the pipeline:
- **Depth chart QB1** (`curated/depth_charts`, timestamped from 2025 by `dt`): the team's rank-1
  quarterback changing between two chart snapshots.
- **Injury report** (raw nflverse snapshots): a starter's game status changing between two of our
  ingests (None -> Questionable -> Out, or off the report). The time is our ingest, so it is as late
  as our last ingest, never earlier than the report was published.
- **Narrative notes** (the desktop passes): injury and coaching notes the pass rated at the strongest
  impact (|impact| = 2), with their cited source, at the record's `known_as_of`; at most
  `MAX_NOTES` a game, since one record lands as one burst.
- **Recent results**: each team's games in the window, at their end (kickoff + `GAME_LENGTH`), with the
  score. A line often moves most while a team is playing the week before.
- **The lock** of the headline line.

A coaching change has a week but no time, so it is listed among the swing factors (M20.6), not here.
"""

from __future__ import annotations

import bisect
from datetime import datetime, timedelta

import polars as pl

from nfl.models.elo import TEAM_ALIASES

GAME_STATUSES = ("Out", "Doubtful", "Questionable")
WINDOW_BEFORE = timedelta(days=2)  # events this long before the first line still explain it
MAX_NOTES = 3
GAME_LENGTH = timedelta(hours=3, minutes=30)


def _canon(team: str) -> str:
    return TEAM_ALIASES.get(team, team)


def qb_changes(depth: pl.DataFrame) -> list[dict]:
    """(team, ts, qb, was) for each change of the rank-1 QB between timestamped chart snapshots."""
    if depth.is_empty() or "dt" not in depth.columns:
        return []
    q = (
        depth.filter(
            (pl.col("pos_abb") == "QB") & (pl.col("pos_rank") == 1) & pl.col("dt").is_not_null()
        )
        .select("team", "dt", "player_name")
        .unique(subset=["team", "dt"], keep="first")
        .sort("team", "dt")
    )
    out, prev = [], {}
    for r in q.iter_rows(named=True):
        team = _canon(r["team"])
        was = prev.get(team)
        if was is not None and was != r["player_name"]:
            ts = datetime.fromisoformat(r["dt"]).replace(tzinfo=None)
            out.append({"team": team, "ts": ts, "qb": r["player_name"], "was": was})
        prev[team] = r["player_name"]
    return out


def injury_transitions(snapshots: list[tuple[datetime, pl.DataFrame]]) -> list[dict]:
    """Status changes per (team, player, week) between consecutive snapshots of the injury report.

    Each frame has `team, week, gsis_id, full_name, position, report_status`. A player first seen
    with a game status is a change from None; a player who drops off the report (or to no game
    status) is a change to None."""
    out, prev = [], {}
    for ts, df in sorted(snapshots, key=lambda x: x[0]):
        now: dict[tuple, tuple] = {}
        for r in df.iter_rows(named=True):
            st = r["report_status"] if r["report_status"] in GAME_STATUSES else None
            now[(_canon(r["team"]), r["week"], r["gsis_id"])] = (st, r["full_name"], r["position"])
        if prev:
            weeks = {k[1] for k in now}
            for key in set(prev) | set(now):
                if key[1] not in weeks:
                    continue  # that week isn't in this snapshot (yet), not a change
                was = prev.get(key, (None, None, None))
                cur = now.get(key, (None, was[1], was[2]))
                if was[0] != cur[0]:
                    team, week, gsis = key
                    out.append({"team": team, "week": week, "gsis_id": gsis, "ts": ts,
                                "player": cur[1] or was[1], "pos": cur[2] or was[2],
                                "status": cur[0], "was": was[0]})  # fmt: skip
        prev = now
    return out


def _status_text(e: dict) -> str:
    who = f"{e['player']} ({e['pos']}, {e['team']})"
    if e["status"] is None:
        return f"Injury report: {who} off the report (was {e['was']})"
    if e["was"] is None:
        return f"Injury report: {who} listed {e['status']}"
    return f"Injury report: {who} now {e['status']} (was {e['was']})"


def results(games: pl.DataFrame) -> list[dict]:
    """(team, ts, text) for every finished game, once per team, timed at its end."""
    out = []
    if not {"home_score", "away_score"} <= set(games.columns):
        return out
    done = games.filter(pl.col("home_score").is_not_null() & pl.col("away_score").is_not_null())
    for g in done.iter_rows(named=True):
        ts = g["kickoff_utc"] + GAME_LENGTH
        hs, as_ = int(g["home_score"]), int(g["away_score"])
        for team, opp, pf, pa, at in ((g["home_team"], g["away_team"], hs, as_, "vs"),
                                      (g["away_team"], g["home_team"], as_, hs, "@")):  # fmt: skip
            word = "beat" if pf > pa else "lost to" if pf < pa else "tied"
            out.append({"team": _canon(team), "ts": ts,
                        "text": f"Result: {team} {word} {opp} {pf}–{pa} ({at} {opp})"})  # fmt: skip
    return out


def game_events(
    game: dict,
    points: list[dict],
    qbs: list[dict],
    injuries: list[dict],
    starters: set[str],
    notes: list[dict],
    lock_ts: datetime | None,
    finished: list[dict] | None = None,
) -> list[dict]:
    """Events for one game between its first line (less `WINDOW_BEFORE`) and kickoff, oldest first.

    `after` is the index of the last line point before the event (-1: before the first), so an
    event belongs to the move from point `after` to `after + 1` and to no other."""
    if not points:
        return []
    teams = {_canon(game["home_team"]), _canon(game["away_team"])}
    start, end = points[0]["snapshot_ts"] - WINDOW_BEFORE, game["kickoff_utc"]
    ev: list[dict] = []
    for q in qbs:
        if q["team"] in teams:
            ev.append({"ts": q["ts"], "kind": "qb", "team": q["team"], "source_url": None,
                       "text": f"Depth chart: {q['qb']} listed as {q['team']}'s starting QB (was {q['was']})"})  # fmt: skip
    for i in injuries:
        if (
            i["team"] in teams
            and i["week"] == game["week"]
            and (i["gsis_id"] in starters or i["pos"] == "QB")
        ):
            ev.append({"ts": i["ts"], "kind": "injury", "team": i["team"], "source_url": None,
                       "text": _status_text(i)})  # fmt: skip
    for n in notes:
        ev.append({"ts": n["ts"], "kind": n["kind"], "team": n["team"], "source_url": n.get("source_url"),
                   "text": f"{n['team']} news: {n['text']}"})  # fmt: skip
    for r in finished or []:
        if r["team"] in teams:
            ev.append(
                {
                    "ts": r["ts"],
                    "kind": "game",
                    "team": r["team"],
                    "source_url": None,
                    "text": r["text"],
                }
            )
    if lock_ts is not None:
        ev.append({"ts": lock_ts, "kind": "lock", "team": None, "source_url": None,
                   "text": "The Student's pick was locked"})  # fmt: skip
    ev = [e for e in ev if start <= e["ts"] < end]
    stamps = [p["snapshot_ts"] for p in points]
    for e in ev:
        e["after"] = bisect.bisect_left(stamps, e["ts"]) - 1
    return sorted(ev, key=lambda e: (e["ts"], e["kind"]))


def narrative_notes(record) -> list[dict]:
    """A narrative record's strongest injury and coaching notes (|impact| = 2), at its `known_as_of`."""
    out = []
    for side in (record.home, record.away):
        for n in side.notes:
            if n.kind in ("injury", "coaching") and abs(n.impact) >= 2 and len(out) < MAX_NOTES:
                out.append({"ts": record.known_as_of.replace(tzinfo=None), "kind": n.kind,
                            "team": _canon(side.team), "text": n.text,
                            "source_url": str(n.source_url) if n.source_url else None})  # fmt: skip
    return out


def load_injury_snapshots(paths, season: int) -> list[tuple[datetime, pl.DataFrame]]:
    """Every raw snapshot of this season's injury report we ingested, oldest first."""
    from nfl.ingest import list_snapshots

    out = []
    for ts, f in list_snapshots(paths, "injuries", f"injuries_{season}.parquet"):
        df = pl.read_parquet(
            f, columns=["team", "week", "gsis_id", "full_name", "position", "report_status"]
        )
        out.append((datetime.strptime(ts, "%Y%m%dT%H%M%SZ"), df))
    return out
