"""Market leans from the candidates ledger (ADR 0028, M25.6): context, never a line.

For a game, every ledger candidate whose latest verdict is `use` (and `pregame`) says how far, per
standard deviation of its home-minus-away gap, the final margin has landed from the market's spread
(`resid_mk`, points per SD, with its 90% CI). The lean is the sum over those candidates of that slope
times this game's standardized gap, in points toward the home team: positive means history says the home
team does better against the spread than the market expects. The CI sums each slope's CI times the gap,
which is conservative (the candidates overlap). Pure functions over catalog tables; nothing here writes,
and nothing here reaches `predictions.parquet`, the scorecard or the README (a test greps the writers).

Point in time: a team's value reads its games of that season with week < the game's week (the screen's
`asof_frame` rule); the gap's mean and SD come from seasons before the game's season; the ledger row is
the latest one (its slopes were fit on finished games, which the docs say). No lean before `MIN_WEEK`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import polars as pl

from nfl import candidate_screen as screen
from nfl import candidates as cand

MIN_WEEK = screen.MIN_WEEK
SEASON_FROM = 2006
TRACK_FROM = (2026, 10)  # the live record starts here (M25.6)


@dataclass
class LeanPart:
    candidate: str
    label: str
    pts: float  # toward the home team
    lo: float
    hi: float


@dataclass
class Lean:
    game_id: str | None
    season: int
    week: int
    home: str
    away: str
    pts: float  # sum of the parts, toward the home team (negative: toward the away team)
    lo: float
    hi: float
    side: str  # the team the lean favors against the market
    parts: list[LeanPart] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def use_rows(ledger: pl.DataFrame) -> list[tuple[cand.Candidate, dict]]:
    """(candidate, latest ledger row) for every `use`, pregame, spread candidate this module can
    compute (team-level over `team_week`). Empty for an empty ledger."""
    if ledger.is_empty() or "verdict" not in ledger.columns:
        return []
    out = []
    for r in ledger.filter(pl.col("verdict") == "use").iter_rows(named=True):
        c = cand.BY_ID.get(r["candidate"])
        if c is None or not r.get("pregame") or r.get("resid_mk") is None:
            continue
        if c.kind != "spread" or c.level != "team" or c.frame != "team_week":
            continue  # not computable here; the screen still holds it
        out.append((c, r))
    return out


def _canon(team: str) -> str:
    from nfl.models.elo import TEAM_ALIASES

    return TEAM_ALIASES.get(team, team)


class Leaner:
    """Leans for any game, from the `team_week` and `games` tables and the ledger. Build once per run."""

    def __init__(self, con, ledger: pl.DataFrame, season_from: int = SEASON_FROM):
        self.use = use_rows(ledger)
        self.games = con.sql(
            f"select * from games where game_type = 'REG' and season >= {season_from}"
        ).pl()
        tw = con.sql(
            f"select * from team_week where season_type = 'REG' and season >= {season_from}"
        ).pl()
        self.tg = screen.team_games(tw, self.games)
        asof = screen.asof_frame(self.tg)
        self._hist: dict[str, pl.DataFrame] = {}
        finished = self.games.filter(pl.col("result").is_not_null() & (pl.col("week") >= MIN_WEEK))
        for c, _ in self.use:
            a = asof.select("game_id", "team", (c.value() * float(c.good)).alias("_v"))
            self._hist[c.id] = (
                finished.with_columns(
                    screen._canon("home_team").alias("_h"), screen._canon("away_team").alias("_a")
                )
                .join(
                    a.rename({"_v": "_vh"}), left_on=["game_id", "_h"], right_on=["game_id", "team"]
                )
                .join(
                    a.rename({"_v": "_va"}), left_on=["game_id", "_a"], right_on=["game_id", "team"]
                )
                .select("season", (pl.col("_vh") - pl.col("_va")).alias("x"))
                .filter(pl.col("x").is_finite())
            )

    def team_value(self, c: cand.Candidate, season: int, week: int, team: str) -> float | None:
        """The candidate's value for `team` from its games this season with week < `week`."""
        rows = self.tg.filter(
            (pl.col("season") == season)
            & (pl.col("week") < week)
            & (pl.col("team") == _canon(team))
        )
        if rows.is_empty():
            return None
        sums = rows.select(pl.col(k).sum() for k in screen.SUM_COLS)
        v = sums.select((c.value() * float(c.good)).alias("v"))["v"][0]
        return None if v is None or not np.isfinite(v) else float(v)

    def _scale(self, c: cand.Candidate, season: int) -> tuple[float, float] | None:
        x = self._hist[c.id].filter(pl.col("season") < season)["x"].to_numpy()
        if len(x) < 30 or x.std() == 0:
            return None
        return float(x.mean()), float(x.std())

    def lean(self, game: dict, as_of_week: int | None = None) -> Lean | None:
        """The lean for `game` (season, week, home_team, away_team; game_id optional) from the teams'
        games before `as_of_week` (default the game's week). None before MIN_WEEK, without a `use`
        candidate, or when a team has no value yet."""
        season, week = int(game["season"]), int(game["week"])
        as_of = int(as_of_week or week)
        if as_of < MIN_WEEK or not self.use:
            return None
        home, away = game["home_team"], game["away_team"]
        parts = []
        for c, r in self.use:
            vh = self.team_value(c, season, as_of, home)
            va = self.team_value(c, season, as_of, away)
            sc = self._scale(c, season)
            if vh is None or va is None or sc is None:
                continue
            z = (vh - va - sc[0]) / sc[1]
            ends = sorted([r["resid_mk_lo"] * z, r["resid_mk_hi"] * z])
            parts.append(
                LeanPart(
                    c.id, c.label, round(r["resid_mk"] * z, 2), round(ends[0], 2), round(ends[1], 2)
                )
            )
        if not parts:
            return None
        pts = round(sum(p.pts for p in parts), 2)
        lo = round(sum(p.lo for p in parts), 2)
        hi = round(sum(p.hi for p in parts), 2)
        side = home if pts > 0 else away if pts < 0 else ""
        return Lean(game.get("game_id"), season, week, home, away, pts, lo, hi, side, parts)


def grade(lean: Lean, result: float | None, spread_line: float | None) -> str | None:
    """For a finished game: 'right' when the margin landed on the lean's side of the market spread,
    'wrong' on the other side, 'push' on the number or with no lean. None before a result or a line.
    `result` is home minus away; `spread_line` > 0 means home favored (the home team covers when
    result > spread_line)."""
    if result is None or spread_line is None:
        return None
    beat = result - spread_line  # > 0: home did better than the market said
    if beat == 0 or lean.pts == 0:
        return "push"
    return "right" if (beat > 0) == (lean.pts > 0) else "wrong"


def tracked(season: int, week: int) -> bool:
    """Whether a game counts in the live record (from TRACK_FROM on)."""
    return (season, week) >= TRACK_FROM
