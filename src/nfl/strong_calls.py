"""Strong calls: where an approach differs from the market, why, and how it turned out (ADR 0024, M20.7).

At each live lock, every approach-game whose win chance is at least `STRONG_GAP` from the market's
becomes a row of `marts/strong_calls.parquet`, append-only like the predictions. A row holds the side
the approach likes more than the market does, both chances and spreads, the three groups that pull
hardest toward that side (from the locked contributions), the quarterback each team's line assumed,
the quarterback what-if where the starter was in doubt, and one sentence built only from those stored
numbers (no LLM, D21).

Grading is derived each run (`grade`, written to `strong_calls_graded.parquet`): the result, the log
loss of the approach and of the market on that game, and whether the line moved toward the call
between the lock and kickoff. Backfill runs never write strong calls: this is a live record, weeks
tracked from the first lock that wrote one.
"""

from __future__ import annotations

import json
import math
from datetime import datetime

import polars as pl

from nfl import io
from nfl.config import Paths
from nfl.features.groups import FEATURE_GROUP, GROUPS

STRONG_GAP = 0.10
APPROACHES = ("traditionalist", "analyst", "sharp", "student", "student_v2")
FILE = "strong_calls.parquet"
GRADED = "strong_calls_graded.parquet"
TOP_GROUPS = 3
GRADE_COLS = {"result": pl.Utf8, "log_loss": pl.Float64, "market_log_loss": pl.Float64,
              "closing_toward": pl.Boolean}  # fmt: skip
SCHEMA = {
    "game_id": pl.Utf8, "season": pl.Int64, "week": pl.Int64, "model_id": pl.Utf8,
    "lock_ts": pl.Datetime("us"), "side": pl.Utf8, "team": pl.Utf8, "p_home": pl.Float64,
    "market_p": pl.Float64, "spread_home": pl.Float64, "market_spread": pl.Float64,
    "top_groups": pl.Utf8, "assumption": pl.Utf8, "what_if_p_home": pl.Float64, "sentence": pl.Utf8,
}  # fmt: skip


def pct(p: float) -> str:
    return f"{round(100 * p)}%"


def top_groups(contributions: str | dict | None, side: str, n: int = TOP_GROUPS) -> list[dict]:
    """Groups ordered by how hard they pull toward `side` (logit units, summed over members); only
    groups pulling that way. Home field is left out: the market prices it too, so it explains
    nothing about a disagreement."""
    c = json.loads(contributions) if isinstance(contributions, str) else (contributions or {})
    sign = 1.0 if side == "home" else -1.0
    sums: dict[str, float] = {}
    for feat, v in c.items():
        if v is None:
            continue
        g = FEATURE_GROUP.get(feat)
        if g is not None:
            sums[g] = sums.get(g, 0.0) + sign * float(v)
    pull = sorted(((g, v) for g, v in sums.items() if v > 0), key=lambda x: -x[1])[:n]
    return [{"group": g, "name": GROUPS[g].name, "logit": round(v, 4)} for g, v in pull]


def _join(names: list[str]) -> str:
    names = [n.lower() for n in names]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"


def sentence(label: str, team: str, p_side: float, m_side: float, groups: list[dict],
             assumption: dict | None, what_if_side: float | None) -> str:  # fmt: skip
    """'The Student has BAL at 62% against the market's 52%. It leans on quarterback and offense.
    It assumes Lamar Jackson starts for BAL; with Tyler Huntley it reads 54%.'"""
    out = f"{label} has {team} at {pct(p_side)} against the market's {pct(m_side)}."
    if groups:
        out += f" It leans on {_join([g['name'] for g in groups])}."
    if (
        assumption
        and assumption.get("assumed")
        and assumption.get("alternative")
        and what_if_side is not None
    ):
        out += (f" It assumes {assumption['assumed']} starts for {assumption['team']}; with "
                f"{assumption['alternative']} it reads {pct(what_if_side)}.")  # fmt: skip
    return out


def calls(
    scored: list, market: pl.DataFrame, slate: pl.DataFrame, lock_ts: datetime,
    labels: dict[str, str], swings: dict[str, list[dict]] | None = None,
) -> pl.DataFrame:  # fmt: skip
    """The lock's strong calls. `scored`: the lock's `Scored` list; `market`: game_id, p_home,
    spread_home; `swings`: `site._swings` output as of the lock (the quarterback assumption)."""
    mk = {r["game_id"]: r for r in market.iter_rows(named=True)} if not market.is_empty() else {}
    games = {r["game_id"]: r for r in slate.iter_rows(named=True)}
    rows = []
    for s in scored:
        if s.model_id not in APPROACHES:
            continue
        for r in s.frame.iter_rows(named=True):
            m, g = mk.get(r["game_id"]), games.get(r["game_id"])
            if m is None or g is None or m["p_home"] is None or r["p_home"] is None:
                continue
            gap = r["p_home"] - m["p_home"]
            if round(abs(gap), 9) < STRONG_GAP:  # 0.62 - 0.52 is 0.0999... in floats
                continue
            side = "home" if gap > 0 else "away"
            team = g["home_team"] if side == "home" else g["away_team"]
            groups = top_groups(r.get("contributions"), side)
            qbs = [x for x in (swings or {}).get(r["game_id"], []) if x.get("kind") == "qb"]
            # the call's own team's quarterback first: its sentence is about that side
            qb = next((x for x in qbs if x.get("team") == team), qbs[0] if qbs else None)
            assumption = what = None
            if qb:
                assumption = {"team": qb["team"], "assumed": qb["assumed"]["name"], "alternative": qb["alternative"]["name"],
                              "why": qb.get("why")}  # fmt: skip
                what = qb["alternative"]["p_home"].get(s.model_id)
            to_side = (lambda p: p) if side == "home" else (lambda p: 1 - p)
            rows.append({
                "game_id": r["game_id"], "season": int(g["season"]), "week": int(g["week"]), "model_id": s.model_id,
                "lock_ts": lock_ts, "side": side, "team": team, "p_home": r["p_home"], "market_p": m["p_home"],
                "spread_home": r.get("spread_home"), "market_spread": m.get("spread_home"),
                "top_groups": json.dumps(groups), "assumption": json.dumps(assumption) if assumption else None,
                "what_if_p_home": what,
                "sentence": sentence(labels.get(s.model_id, s.model_id), team, to_side(r["p_home"]),
                                     to_side(m["p_home"]), groups, assumption, None if what is None else to_side(what)),
            })  # fmt: skip
    return pl.DataFrame(rows, schema=SCHEMA) if rows else pl.DataFrame(schema=SCHEMA)


def append(paths: Paths, new: pl.DataFrame) -> int:
    """Append-only: rows already written are never modified or dropped."""
    if new.is_empty():
        return 0
    return io.append(paths.marts / FILE, new, SCHEMA)


def load(paths: Paths) -> pl.DataFrame:
    f = paths.marts / FILE
    return pl.read_parquet(f) if f.exists() else pl.DataFrame(schema=SCHEMA)


def _ll(p: float, won: bool) -> float:
    q = min(max(p if won else 1 - p, 1e-6), 1 - 1e-6)
    return -math.log(q)


def grade(
    calls_df: pl.DataFrame, games: pl.DataFrame, closing: dict[str, float | None]
) -> pl.DataFrame:
    """Each call with `result` ('right'|'wrong'|'tie'|None before the game), `log_loss`,
    `market_log_loss` (both on the home result), and `closing_toward` (did the spread move toward the
    call's side between the lock and the last pre-kickoff snapshot; None without a closing line).
    `closing`: game_id -> the last pre-kickoff consensus spread (home +)."""
    if calls_df.is_empty():
        return calls_df.with_columns(pl.lit(None, dtype=pl.Utf8).alias("result"), pl.lit(None, dtype=pl.Float64).alias("log_loss"),
                                     pl.lit(None, dtype=pl.Float64).alias("market_log_loss"), pl.lit(None, dtype=pl.Boolean).alias("closing_toward"))  # fmt: skip
    res = {r["game_id"]: r.get("result") for r in games.iter_rows(named=True)}
    out = []
    for r in calls_df.iter_rows(named=True):
        margin = res.get(r["game_id"])
        if margin is None:
            result, ll, mll = None, None, None
        elif margin == 0:
            result, ll, mll = "tie", None, None
        else:
            home_won = margin > 0
            result = "right" if (r["side"] == "home") == home_won else "wrong"
            ll, mll = _ll(r["p_home"], home_won), _ll(r["market_p"], home_won)
        c = closing.get(r["game_id"])
        toward = None
        if c is not None and r["market_spread"] is not None:
            d = c - r["market_spread"]
            toward = None if abs(d) < 1e-9 else (d > 0) == (r["side"] == "home")
        out.append(
            {
                **r,
                "result": result,
                "log_loss": ll,
                "market_log_loss": mll,
                "closing_toward": toward,
            }
        )
    return pl.DataFrame(out, schema={**dict(calls_df.schema), **GRADE_COLS})


def grade_all(paths) -> pl.DataFrame:
    """Every recorded call graded as of now: results for finished games, the line's move since the
    lock from the last pre-kickoff snapshot so far. Cheap; the site and `nfl grade` both call it."""
    from nfl import market_history
    from nfl.features import store
    from nfl.odds import read_lines

    calls = load(paths)
    if calls.is_empty():
        return grade(calls, pl.DataFrame(), {})
    seasons = (int(calls["season"].min()), int(calls["season"].max()))
    games = store.games_frame(paths).filter(
        pl.col("game_id").is_in(calls["game_id"].unique().to_list())
    )
    pts = market_history.paths(read_lines(paths, seasons))
    closing = {
        r["game_id"]: r["spread_home"]
        for r in pts.filter(pl.col("spread_home").is_not_null()).sort("snapshot_ts").group_by("game_id").last().iter_rows(named=True)
    }  # fmt: skip
    return grade(calls, games.select("game_id", "result"), closing)


def last_lock(calls: pl.DataFrame) -> pl.DataFrame:
    """One row per approach-game: the call from its latest lock (a relocked game counts once)."""
    if calls.is_empty():
        return calls
    return calls.sort("lock_ts").group_by("game_id", "model_id", maintain_order=True).last()


def record(graded: pl.DataFrame) -> list[dict]:
    """Per approach: calls, decided, right, log loss vs the market's on those games, line moved toward."""
    out = []
    graded = last_lock(graded)
    for m in APPROACHES:
        g = graded.filter(pl.col("model_id") == m) if not graded.is_empty() else graded
        decided = g.filter(pl.col("result").is_in(["right", "wrong"])) if not g.is_empty() else g
        toward = g.filter(pl.col("closing_toward").is_not_null()) if not g.is_empty() else g
        out.append({
            "model_id": m, "n": g.height, "decided": decided.height,
            "right": decided.filter(pl.col("result") == "right").height if decided.height else 0,
            "log_loss": round(decided["log_loss"].mean(), 4) if decided.height else None,
            "market_log_loss": round(decided["market_log_loss"].mean(), 4) if decided.height else None,
            "moved_toward": toward.filter(pl.col("closing_toward")).height if toward.height else 0,
            "with_close": toward.height,
        })  # fmt: skip
    return out
