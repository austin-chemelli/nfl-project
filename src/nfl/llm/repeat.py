"""Do the research ratings repeat? (ADR 0032, idea A1.)

Every week a few games are researched a second time, not stored (`nfl narrative repeat`), and each
rating of the rerun is compared with the stored record's. `marts/narrative_repeat.parquet`
(append-only) holds one row per game, team and rating; `agreement` is the share of pairs that
agree within one step, per rating. The news adjustment (`nfl.approaches.news`) gives a rating
weight 0 when it repeats on less than `MIN_AGREEMENT` of at least `MIN_PAIRS` pairs.

Agreement: integer scales (`qb_status` 0..2, `injury_impact` 0..3) within 1; continuous scales
(−1..1 and 0..1) within 0.25; flags (`revenge`, `lookahead`) equal.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime

import polars as pl

from nfl import io
from nfl.config import Paths, now_utc

MIN_AGREEMENT = 0.70  # below this, once MIN_PAIRS exist, the rating has no weight (ADR 0032)
MIN_PAIRS = 12
TEAM_RATINGS = {
    "qb_status": 1.0,
    "injury_impact": 1.0,
    "motivation": 0.25,
    "sentiment": 0.25,
    "hype": 0.25,
    "coaching_turmoil": 0.25,
    "revenge": 0.0,
    "lookahead": 0.0,
}  # fmt: skip  (rating -> tolerance; 0 = the flags must be equal)
GAME_RATINGS = {"weather_concern": 0.25, "upset_buzz": 0.25}
SCHEMA = {
    "season": pl.Int64(), "week": pl.Int64(), "game_id": pl.Utf8(), "team": pl.Utf8(),
    "rating": pl.Utf8(), "value_a": pl.Float64(), "value_b": pl.Float64(),
    "agree": pl.Boolean(), "run_at": pl.Datetime("us"),
}  # fmt: skip


def path(paths: Paths):
    return paths.marts / "narrative_repeat.parquet"


def agrees(rating: str, a: float, b: float) -> bool:
    tol = {**TEAM_RATINGS, **GAME_RATINGS}[rating]
    return abs(a - b) <= tol + 1e-9


def compare(a: dict, b: dict, run_at: datetime) -> pl.DataFrame:
    """Rows for one game: record `a` (stored) against `b` (the rerun), both as dicts."""
    rows = []
    for side in ("home", "away"):
        for r in TEAM_RATINGS:
            x, y = float(a[side][r]), float(b[side][r])
            rows.append((a["season"], a["week"], a["game_id"], a[side]["team"], r, x, y, agrees(r, x, y), run_at))  # fmt: skip
    for r in GAME_RATINGS:
        x, y = float(a[r]), float(b[r])
        rows.append((a["season"], a["week"], a["game_id"], None, r, x, y, agrees(r, x, y), run_at))
    return pl.DataFrame(rows, schema=SCHEMA, orient="row")


def agreement(paths: Paths) -> dict[str, tuple[float, int]]:
    """rating -> (share of pairs that agree, number of pairs) over every stored row. {} without
    the file."""
    f = path(paths)
    if not f.exists():
        return {}
    df = io.read(f, SCHEMA)
    if df.is_empty():
        return {}
    g = df.group_by("rating").agg(pl.col("agree").mean().alias("share"), pl.len().alias("n"))
    return {r: (float(s), int(n)) for r, s, n in g.sort("rating").iter_rows()}


def silenced(paths: Paths) -> set[str]:
    """Ratings with enough pairs that repeat below MIN_AGREEMENT (weight 0 under ADR 0032)."""
    return {r for r, (s, n) in agreement(paths).items() if n >= MIN_PAIRS and s < MIN_AGREEMENT}


def pick_games(paths: Paths, season: int, week: int, n: int, now: datetime) -> list[str]:
    """Up to `n` upcoming games with a full `claude_max` record from the latest scheduled pass,
    games not yet repeated this week first."""
    from nfl.llm.narrative import last_pass, load_records, slate

    since = last_pass(now)
    kick = {r["game_id"]: r["kickoff_utc"] for r in slate(paths, season, week).to_dicts()}
    ids = sorted({
        r.game_id for r in load_records(paths, (season, season))
        if r.week == week and r.producer == "claude_max" and r.pass_kind == "full"
        and r.known_as_of >= since and kick.get(r.game_id, now) > now
    })  # fmt: skip
    f = path(paths)
    done = set(io.read(f, SCHEMA)["game_id"].to_list()) if f.exists() else set()
    return sorted(ids, key=lambda g: (g in done, g))[:n]


def run(paths: Paths, season: int, week: int, n: int = 3, *, model: str | None = None, runner=subprocess.run, login=None) -> list[tuple[str, str | None]]:  # fmt: skip
    """Research `n` games again, not stored, and append the comparison with the stored record.
    Returns (game_id, error or None) per game."""
    from nfl.llm import claude_research as cr
    from nfl.llm.narrative import slate

    print(f"claude login ok (plan {(login or cr.require_subscription_login)()})", flush=True)
    now = now_utc()
    ids = pick_games(paths, season, week, n, now.replace(tzinfo=None))
    if not ids:
        raise ValueError(f"no game of {season} week {week} has a stored full record from the latest pass to repeat")  # fmt: skip
    rows = {r["game_id"]: r for r in slate(paths, season, week).to_dicts()}
    out = []
    for gid in ids:
        res = cr.research_game(paths, rows[gid], model=model or cr.MODEL, store=False, run=runner)
        if not res.ok or res.folder is None:
            out.append((gid, res.error or "no record"))
            continue
        a = _latest_full(paths, season, week, gid)
        b = json.loads((res.folder / "record.checked.json").read_text())
        io.append(path(paths), compare(json.loads(a.model_dump_json()), b, now.replace(tzinfo=None, microsecond=0)), SCHEMA)  # fmt: skip
        out.append((gid, None))
    return out


def _latest_full(paths: Paths, season: int, week: int, game_id: str):
    from nfl.llm.narrative import load_records

    recs = [r for r in load_records(paths, (season, season)) if r.game_id == game_id and r.producer == "claude_max" and r.pass_kind == "full"]  # fmt: skip
    return max(recs, key=lambda r: r.known_as_of)


def report(paths: Paths) -> str:
    """The agreement table as markdown."""
    ag = agreement(paths)
    if not ag:
        return "No repeat pairs yet (`nfl narrative repeat <season> <week>`)."
    lines = ["| rating | pairs | agree within one step | counts |", "|---|---|---|---|"]
    for r, (s, n) in ag.items():
        verdict = "no (weight 0)" if n >= MIN_PAIRS and s < MIN_AGREEMENT else "yes" if n >= MIN_PAIRS else f"unmeasured (<{MIN_PAIRS} pairs)"  # fmt: skip
        lines.append(f"| {r} | {n} | {s:.0%} | {verdict} |")
    return "\n".join(lines)
