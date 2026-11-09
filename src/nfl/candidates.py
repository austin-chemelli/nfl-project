"""The candidates registry (ADR 0026, M23.2): every second-level feature idea, defined once.

A candidate is a number about a team (or a game) that might explain something the Student and the
market miss. `nfl candidates run` screens each through the gates in `nfl.candidate_screen` and appends
the numbers to `marts/candidates.parquet`; a failed candidate stays in the ledger (never delete one).

`value()` returns a Polars expression over a frame of **as-of sums** (see `candidate_screen.SUM_COLS`):
one row per team-game, each column the sum over the team's earlier games that season (or, for the
split-half and future gates, over a chosen set of weeks). Everything is a ratio of sums, so the same
expression works for any set of weeks. Prefixes: `o_` the team's offense, `d_` what its defense
allowed or forced; `games` the number of games summed. A `game`-level candidate (wind) is an
expression over the games frame instead and has no team-week history.

Fields that steer the gates:
- `kind`: 'spread' (home-minus-away candidate against result - spread) or 'total' (home + away against
  total - total line).
- `good`: +1 when a higher value is better for the team (the value is multiplied by it, so positive
  always reads "helps the team"); -1 for e.g. a sack rate on offense. Totals ignore it.
- `outcome`: which second-half result the future gate predicts, as goodness for the team: 'off'
  (offense EPA/play), 'def' (minus EPA/play allowed), 'net' (both), or None (no future gate).
- `replaces`: the existing stat (`BASE` key) the partial correlation controls for; '' for none.
- `luck`: a luck-type measure: failing the split-half gate on purpose makes it a 'luck' verdict.
- `halves`: whether the split-half and future gates apply (not for candidates that need plays
  directly or have no team-season rate).
- `pregame`: False when the value uses something known only after kickoff (observed wind, the
  game's actual passer). Such a candidate can't be `use`: at best it's `context` until a pregame
  version exists (a forecast, the depth chart's starter).
- `in_model`: the stat is already a member of a weighted group (a baseline, not a new idea); the site
  says so instead of presenting it as a find.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import polars as pl

OUTDOOR = ("outdoors", "open")


def ratio(num: str, den: str) -> pl.Expr:
    """A ratio of two summed columns, null when the denominator is zero."""
    return pl.when(pl.col(den) > 0).then(pl.col(num) / pl.col(den)).otherwise(None)


# Existing stats the partial correlation controls for, oriented as goodness for the team.
BASE: dict[str, Callable[[], pl.Expr]] = {
    "epa_off": lambda: ratio("o_epa", "o_n"),
    "epa_def": lambda: -ratio("d_epa", "d_n"),
    "epa_net": lambda: ratio("o_epa", "o_n") - ratio("d_epa", "d_n"),
}


@dataclass(frozen=True, eq=False)
class Candidate:
    id: str
    label: str
    sentence: str  # what it is, in one sentence
    kind: str  # 'spread' | 'total'
    source: str  # where the inputs come from
    first_season: int
    replaces: str  # key of BASE, or ''
    interesting: bool
    note: str
    value: Callable[[], pl.Expr]
    good: int = 1
    outcome: str | None = None  # 'off' | 'def' | 'net' | None
    luck: bool = False
    halves: bool = True
    level: str = "team"  # 'team' | 'game'
    pregame: bool = True
    in_model: bool = False


def _wind(k: int) -> Callable[[], pl.Expr]:
    """1 when an outdoor game's wind is at least k mph, 0 when lower, null for domes/unknown."""
    return lambda: (
        pl.when(pl.col("roof").is_in(OUTDOOR) & pl.col("wind").is_not_null())
        .then((pl.col("wind") >= k).cast(pl.Float64))
        .otherwise(None)
    )


def _wind_candidate(k: int, interesting: bool = False) -> Candidate:
    return Candidate(
        id=f"wind_{k}",
        label=f"Wind of {k} mph or more",
        sentence=f"The game is outdoors and the recorded wind is at least {k} mph.",
        kind="total",
        source="games.wind, games.roof (observed after the game)",
        first_season=2006,
        replaces="",
        interesting=interesting,
        note="Observed wind is post-game data; a forecast version waits for forecast archives.",
        value=_wind(k),
        halves=False,
        level="game",
        pregame=False,
    )


def _net(num_o: str, den_o: str, num_d: str, den_d: str) -> Callable[[], pl.Expr]:
    return lambda: ratio(num_o, den_o) - ratio(num_d, den_d)


CANDIDATES: tuple[Candidate, ...] = (
    Candidate(
        "net_epa", "Net EPA per play",
        "Offense EPA per play minus the EPA per play its defense allowed, season to date.",
        "spread", "plays", 2006, "epa_net", False,
        "The baseline every other EPA variant is compared with; negative against the Student (it over-weights it).",
        _net("o_epa", "o_n", "d_epa", "d_n"), outcome="net", in_model=True,
    ),
    Candidate(
        "net_wepa", "Net win-probability-weighted EPA",
        "Net EPA per play with each play weighted by 4 x wp x (1 - wp), so close-game plays count more.",
        "spread", "plays", 2006, "epa_net", True,
        "Public +14% claim, worse here.",
        _net("o_wepa", "o_w", "d_wepa", "d_w"), outcome="net",
    ),
    Candidate(
        "net_epa_noto", "Net EPA without turnovers",
        "Net EPA per play counting only plays with no interception and no lost fumble (in the total of all plays).",
        "spread", "plays", 2006, "epa_net", True,
        "Defense EPA without turnovers predicted the second half beyond plain EPA (partial r +0.09).",
        _net("o_noto", "o_n", "d_noto", "d_n"), outcome="net",
    ),
    Candidate(
        "net_def_half", "Net EPA with the defense at half weight",
        "Offense EPA per play minus half of the EPA per play the defense allowed.",
        "spread", "plays", 2006, "epa_net", False,
        "Defenses repeat half as much as offenses (0.31 vs 0.61), so this tests whether to discount them.",
        lambda: ratio("o_epa", "o_n") - 0.5 * ratio("d_epa", "d_n"), outcome="net",
    ),
    Candidate(
        "fum_luck", "Fumble luck",
        "Per game: own fumbles kept above a coin flip plus opponents' fumbles recovered above a coin flip.",
        "spread", "plays", 2006, "epa_net", True,
        "Fumble recovery is a coin flip (split-half 0.00); a luck readout, not a rating.",
        lambda: ((0.5 * pl.col("o_fum") - pl.col("o_fum_lost"))
                 + (pl.col("d_fum_lost") - 0.5 * pl.col("d_fum"))) / pl.col("games"),
        outcome="net", luck=True,
    ),
    Candidate(
        "qb_sack_rate", "Quarterback's own sack rate",
        "The game's main passer's sacks per dropback over his earlier games (this and two prior seasons), shrunk to the league.",
        "spread", "plays (passer id)", 2006, "epa_off", False,
        "Uses the game's actual passer, so it is post-game information; a screen, not a feature.",
        lambda: pl.col("qb_sack_rate"), good=-1, outcome="off", halves=False, pregame=False,
    ),
    Candidate(
        "success_off", "Offensive success rate",
        "Share of the offense's plays with positive success (nflverse success flag).",
        "spread", "plays", 2006, "epa_off", True,
        "The one clear market residual in the 15 screened (+0.63 points per SD).",
        lambda: ratio("o_succ", "o_n"), outcome="off", in_model=True,
    ),
    Candidate(
        "sack_off", "Sacks taken per dropback",
        "Sacks the offense took per dropback.",
        "spread", "plays", 2006, "epa_off", False,
        "Oriented so a lower sack rate counts as better.",
        lambda: ratio("o_sacks", "o_db"), good=-1, outcome="off", in_model=True,
    ),
    Candidate(
        "sack_def", "Sacks made per dropback faced",
        "Sacks the defense made per opposing dropback.",
        "spread", "plays", 2006, "epa_def", False, "",
        lambda: ratio("d_sacks", "d_db"), outcome="def", in_model=True,
    ),
    Candidate(
        "proe", "Pass rate over expected",
        "Average pass_oe (pass rate minus the model's expectation) on downs 1-2 in games within 20-80% win probability, first three quarters.",
        "total", "plays", 2006, "", False,
        "Context only: nothing against the market total.",
        lambda: ratio("o_proe_sum", "o_proe_n"),
    ),
    Candidate(
        "plays_pg", "Plays per game",
        "The offense's pass and rush plays per game.",
        "total", "plays", 2006, "", False, "Pace is context only (0 against the market total).",
        lambda: pl.col("o_n") / pl.col("games"),
    ),
    Candidate(
        "neutral_pg", "Neutral-script plays per game",
        "Plays per game while win probability is between 20% and 80%.",
        "total", "plays", 2006, "", False, "Pace without garbage time; context only.",
        lambda: pl.col("o_neutral") / pl.col("games"),
    ),
    Candidate(
        "plays_allowed_pg", "Plays allowed per game",
        "Pass and rush plays the defense faced per game.",
        "total", "plays", 2006, "", False, "",
        lambda: pl.col("d_n") / pl.col("games"),
    ),
    _wind_candidate(10),
    _wind_candidate(15, True),
    _wind_candidate(20),
    Candidate(
        "one_score_luck", "One-score-game luck",
        "Per game this season: wins in games decided by 8 points or fewer minus half of those games.",
        "spread", "games", 2006, "epa_net", True,
        "Close-game records regress; a luck term for Quality if it passes.",
        lambda: (pl.col("os_wins") - 0.5 * pl.col("os_games")) / pl.col("games"),
        outcome="net", luck=True,
    ),
    Candidate(
        "turnover_margin_minus_expected", "Turnover margin with fumbles at expectation",
        "Per game: takeaways minus giveaways with interceptions counted as they happened and every fumble counted as a coin flip (0.5 recovery).",
        "spread", "plays", 2006, "epa_net", False,
        "The luck-stripped margin: actual margin minus fum_luck. The luck part itself is fum_luck.",
        lambda: ((pl.col("d_ints") - pl.col("o_ints")) + 0.5 * (pl.col("d_fum") - pl.col("o_fum")))
        / pl.col("games"),
        outcome="net",
    ),
)  # fmt: skip

BY_ID = {c.id: c for c in CANDIDATES}
