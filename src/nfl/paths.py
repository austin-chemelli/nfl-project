"""Paths to an upset (ADR 0028, M25.4): conditions, never a probability.

Pure functions over the `upset_conditions` SQL model (one row per game and team, see
src/nfl/sql/models/upset_conditions.sql). Pass a DuckDB connection from `nfl.catalog.connect` or the
model's polars frame; nothing here reads or writes files. Every number in a sentence comes from the
returned record (ADR 0024's rule); the record is plain data (`dataclasses.asdict` gives site JSON).

Point in time: the bucket table for a game in season S reads seasons < S; a team's rate of producing or
allowing a condition reads that season's games with week < `as_of_week`. The game itself and later
games are never read.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import polars as pl

from nfl.models.elo import TEAM_ALIASES

COIN_FLIP = "coin flip for every team"
WEAK = "weakly predictable"

BUCKETS = ("0-2.5", "3-6.5", "7-9.5", "10+")
TOP_N = 3


@dataclass(frozen=True)
class Condition:
    id: str
    column: str  # boolean column in upset_conditions, from the team's view
    label: str
    definition: str
    plan: str  # "to win" phrasing after "How X wins:"
    done: str  # past tense after the team name, for the outcome sentence
    plausibility: str
    measured_r: float | None  # pre-game r of both teams' season rates with the realized margin
    help: str


CONDITIONS: tuple[Condition, ...] = (
    Condition(
        "turnovers",
        "turnovers",
        "Win the turnover battle",
        "Takeaways minus giveaways (interceptions and lost fumbles) of at least +1.",
        "win the turnover battle",
        "won the turnover battle",
        COIN_FLIP,
        0.005,
        "Before a game, both teams' turnover rates to date predict its turnover margin with r +0.005 "
        "(2006-2025): a coin flip for every team.",
    ),
    Condition(
        "early_down",
        "early_down",
        "Win early downs",
        "The team's EPA per play on first and second down (win probability 20-80%) beats the opponent's.",
        "win early downs",
        "won early downs",
        WEAK,
        0.17,
        "Season-to-date early-down EPA predicts the game's with r +0.17 (2006-2025): weakly predictable.",
    ),
    Condition(
        "explosives",
        "explosives_more",
        "More explosive plays",
        "More passes of 20+ yards and runs of 10+ yards than the opponent.",
        "hit more explosive plays",
        "had more explosive plays",
        WEAK,
        0.16,
        "Season-to-date explosive plays predict the game's with r +0.16 (2006-2025): weakly predictable.",
    ),
    Condition(
        "sacks",
        "sacks",
        "Sack the quarterback more",
        "The opponent's offense was sacked at least two more times than this team's.",
        "out-sack the other side by two",
        "out-sacked the other side by two",
        WEAK,
        0.15,
        "Season-to-date sack rates predict the game's sack margin with r +0.15 (2006-2025): weakly "
        "predictable.",
    ),
    Condition(
        "special_teams",
        "special_teams",
        "Win special teams",
        "Special-teams EPA at least +3 points better than the opponent's.",
        "win special teams by a field goal",
        "won special teams by a field goal",
        WEAK,
        None,
        "Not measured before the game; the history says what winning dogs did, nothing about whether "
        "either team tends to produce it.",
    ),
)
BY_ID = {c.id: c for c in CONDITIONS}

TAIL = " None of this is in the odds we show; it is what winning underdogs did."


# ---- records (plain data; asdict -> JSON) ----------------------------------------------------


@dataclass
class BucketCell:
    """One size bucket x condition over earlier seasons' dogs."""

    bucket: str
    condition: str
    n_dogs: int  # dogs in the bucket
    n: int  # of them, how many met the condition
    win_rate_if: float | None  # dog win rate given the condition (None when n = 0)
    happens: float | None  # share of dogs in the bucket that met it
    base_rate: float | None  # the bucket's dog win rate


@dataclass
class ConditionPath:
    id: str
    label: str
    definition: str
    win_rate_if: float | None
    win_rate_pct: int | None
    n: int
    happens: float | None
    happens_pct: int | None
    base_rate: float | None
    base_rate_pct: int | None
    dog_games: int  # the dog's games this season before the as-of week
    dog_count: int  # of them, how many it produced the condition
    fav_games: int  # the favorite's games, same window
    fav_count: int  # of them, how many it allowed the condition (the other side produced it)
    plausibility: str
    measured_r: float | None
    help: str


@dataclass
class UpsetPaths:
    game_id: str | None
    season: int
    week: int
    as_of_week: int
    dog: str
    favorite: str
    size: float  # points, |spread|
    bucket: str
    base_rate: float | None
    base_rate_pct: int | None
    conditions: list[ConditionPath] = field(default_factory=list)  # all five, best win rate first
    top: list[str] = field(default_factory=list)  # ids of the conditions the sentence names
    sentence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OutcomeCondition:
    id: str
    label: str
    met: bool


@dataclass
class PathsOutcome:
    game_id: str
    dog: str
    favorite: str
    size: float
    bucket: str
    dog_won: bool
    tied: bool
    margin: float  # the dog's margin
    conditions: list[OutcomeCondition] = field(default_factory=list)
    met: list[str] = field(default_factory=list)  # ids
    sentence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---- helpers ---------------------------------------------------------------------------------


def load_conditions(con) -> pl.DataFrame:
    """The `upset_conditions` model from a catalog connection (empty when it isn't built)."""
    return con.sql("select * from upset_conditions").pl()


def _frame(con_or_df) -> pl.DataFrame:
    return con_or_df if isinstance(con_or_df, pl.DataFrame) else load_conditions(con_or_df)


def bucket_of(spread: float) -> str:
    a = abs(spread)
    return "0-2.5" if a < 3 else "3-6.5" if a < 7 else "7-9.5" if a < 10 else "10+"


def _code(team: str) -> str:
    return TEAM_ALIASES.get(team, team)


def _pct(x: float | None) -> int | None:
    return None if x is None else round(100 * x)


# ---- the bucket table ------------------------------------------------------------------------


def bucket_table(con_or_df, before_season: int) -> list[BucketCell]:
    """Dogs' win rate by size bucket x condition over seasons < `before_season` (point in time)."""
    df = _frame(con_or_df)
    dogs = df.filter((pl.col("role") == "dog") & (pl.col("season") < before_season))
    out = []
    for b in BUCKETS:
        d = dogs.filter(pl.col("size_bucket") == b)
        n_dogs = d.height
        base = d["won"].mean() if n_dogs else None
        for c in CONDITIONS:
            w = d.filter(pl.col(c.column))
            n = w.height
            out.append(
                BucketCell(
                    b, c.id, n_dogs, n,
                    w["won"].mean() if n else None,
                    n / n_dogs if n_dogs else None,
                    base,
                )
            )  # fmt: skip
    return out


# ---- before the game -------------------------------------------------------------------------


def _rate_counts(df: pl.DataFrame, season: int, as_of_week: int, team: str, col: str, *, own: bool):
    """(games, count): the team's games this season before the as-of week where `col` held for the
    team (own=True: what it produces) or for its opponent (own=False: what it allows)."""
    key = "team" if own else "opponent"
    g = df.filter(
        (pl.col("season") == season) & (pl.col("week") < as_of_week) & (pl.col(key) == team)
    )
    return g.height, int(g[col].fill_null(False).sum()) if g.height else 0


def _gv(game: Any, key: str):
    return game[key] if isinstance(game, dict) else getattr(game, key)


def _gv0(game: Any, key: str, default=None):
    try:
        return _gv(game, key)
    except KeyError, AttributeError:
        return default


def upset_paths(game: Any, as_of_week: int, con_or_df) -> UpsetPaths | None:
    """How the underdog can win `game`, as conditions with history. `game` has season, week, home_team,
    away_team and spread_line (> 0 means home favored); game_id optional. None for a pick'em or a
    missing line. Never a probability."""
    spread = _gv0(game, "spread_line")
    if spread is None or np.isnan(spread) or spread == 0:
        return None
    season, week = int(_gv(game, "season")), int(_gv(game, "week"))
    home, away = _gv(game, "home_team"), _gv(game, "away_team")
    dog, fav = (away, home) if spread > 0 else (home, away)
    df = _frame(con_or_df)
    bucket = bucket_of(spread)
    cells = {c.condition: c for c in bucket_table(df, season) if c.bucket == bucket}
    base = next(iter(cells.values())).base_rate
    conds = []
    for c in CONDITIONS:
        cell = cells[c.id]
        dg, dc = _rate_counts(df, season, as_of_week, _code(dog), c.column, own=True)
        fg, fc = _rate_counts(df, season, as_of_week, _code(fav), c.column, own=False)
        conds.append(
            ConditionPath(
                c.id, c.label, c.definition, cell.win_rate_if, _pct(cell.win_rate_if), cell.n,
                cell.happens, _pct(cell.happens), base, _pct(base), dg, dc, fg, fc,
                c.plausibility, c.measured_r, c.help,
            )
        )  # fmt: skip
    conds.sort(key=lambda x: -(x.win_rate_if if x.win_rate_if is not None else -1.0))
    top = [x.id for x in conds if x.win_rate_if is not None][:TOP_N]
    out = UpsetPaths(
        _gv0(game, "game_id"), season, week, int(as_of_week), dog, fav, abs(float(spread)), bucket,
        base, _pct(base), conds, top,
    )  # fmt: skip
    out.sentence = _paths_sentence(out)
    return out


def _clause(p: UpsetPaths, c: ConditionPath) -> str:
    bits = [f"dogs of this size who did won {c.win_rate_pct}%"]
    if c.dog_games:
        bits.append(f"{p.dog} has done it in {c.dog_count} of {c.dog_games} games")
    else:
        bits.append(f"{p.dog} has no games yet to go on")
    if c.fav_games:
        bits.append(f"{p.favorite} has allowed it in {c.fav_count} of {c.fav_games}")
    return f"{BY_ID[c.id].plan.format(dog=p.dog, fav=p.favorite)} ({'; '.join(bits)})"


def _paths_sentence(p: UpsetPaths) -> str:
    by_id = {c.id: c for c in p.conditions}
    parts = [_clause(p, by_id[i]) for i in p.top]
    if not parts:
        return f"No history yet for how {p.dog} wins.{TAIL}"
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return f"How {p.dog} wins: {joined}.{TAIL}"


# ---- after the game --------------------------------------------------------------------------


def paths_outcome(game_id: str, con_or_df) -> PathsOutcome | None:
    """For a finished game: which of the five conditions the underdog met, and whether it won. None
    for a pick'em or a game the model doesn't hold (unplayed, postseason, no line)."""
    df = _frame(con_or_df).filter(pl.col("game_id") == game_id)
    dog = df.filter(pl.col("role") == "dog")
    if dog.height != 1:
        return None
    r = dog.row(0, named=True)
    conds = [OutcomeCondition(c.id, c.label, bool(r[c.column])) for c in CONDITIONS]
    met = [c.id for c in conds if c.met]
    tied = r["margin"] == 0
    won = bool(r["won"])
    fate = "it won" if won else "it tied" if tied else "it lost"
    team = r["team"]
    if met:
        phr = [BY_ID[i].done.format(dog=team, fav=r["opponent"]) for i in met]
        said = phr[0] if len(phr) == 1 else ", ".join(phr[:-1]) + " and " + phr[-1]
        sentence = f"{team} {said}; {fate}."
    else:
        sentence = f"{team} met none of the conditions; {fate}."
    return PathsOutcome(
        game_id, team, r["opponent"], abs(float(r["spread"])), r["size_bucket"], won, tied,
        float(r["margin"]), conds, met, sentence,
    )  # fmt: skip
