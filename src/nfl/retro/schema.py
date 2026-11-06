"""The retrospective contract (ADR 0016, architecture §3.6c). One `RetroGame` per finished game,
one `WeekRecap` per week, and the league `Expectations` they are priced with. Marts and site files
hold these exact shapes; `web/src/data/contract.ts` mirrors them in zod.

Conventions: swing points are from the named team's view (positive = helped it); `pp` is
win-probability points toward the home team, as on the game page; `value` is the drop-one
log-loss change (positive = the group made the forecast better). Every sentence is a template
whose numbers come from the same record.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "6"  # v6 2026-11-05: wp_series and drives (ADR 0020)
# v5 2026-11-05: preview Elo on full history, new swing sentence; v4: the recap's bold calls
# v3 2026-11-04: played-like inputs, the phase scorecard; game-only headlines

Side = Literal["home", "away"]
Unit = Literal["epa", "pct", "pp", "count", "yards", "points"]
LuckKind = Literal[
    "fumbles", "interceptions", "third_down", "fourth_down", "kicking", "penalties", "special_teams"
]  # fmt: skip


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------------------------ expectations


class Bucket(_Model):
    """One situation cell: a distance range and the league's rate there. `value` is the EPA gap
    between success and failure in the cell (conversion vs stop, make vs miss)."""

    key: str  # "1", "2-3", "4-6", "7-10", "11+"; field goals "<30", "30-34", ..., "60+"
    lo: float
    hi: float | None  # inclusive; None = open-ended
    rate: float
    n: int
    value: float


class PlayedLikeFit(_Model):
    """Logistic of home win on the difference (home - away) of non-turnover EPA per play and of
    success rate, with an intercept for home field."""

    intercept: float
    b_epa: float
    b_success: float
    n: int


class Expectations(_Model):
    version: str
    built_at: str
    seasons: tuple[int, int]
    third_down: list[Bucket]
    fourth_down: list[Bucket]  # went for it: a pass or run on 4th down
    field_goal: list[Bucket]
    extra_point_rate: float
    extra_point_n: int
    fumble_lost_share: float
    fumble_n: int
    value_fumble_lost: float  # EPA a lost fumble costs vs a recovered one (positive number)
    value_interception: float  # mean EPA lost on an interception (positive number)
    value_penalty_yard: float  # EPA per penalty yard against (positive number)
    special_teams_big_plays_pg: float  # return TDs + blocked kicks per team-game
    value_special_teams_big_play: float
    played_like: PlayedLikeFit


# ------------------------------------------------------------------------------------- game retro


class Result(_Model):
    home_score: int
    away_score: int
    margin: int  # home - away


class Efficiency(_Model):
    """One metric for one unit of a team: this game, its season to date (games that kicked off
    before this one) and the league over the same span."""

    metric: str  # off_epa_play, off_success, off_epa_dropback, off_epa_rush, off_explosive, off_sack_rate, off_proe; def_* alike
    unit_side: Literal["off", "def"]
    label: str
    unit: Unit
    higher_is_better: bool  # from this team's view (defensive EPA allowed: False)
    game: float | None
    season: float | None
    league: float | None
    # 10th/90th percentile of the teams' season-to-date values before this game; None when fewer
    # than 8 teams have a value
    league_lo: float | None = None
    league_hi: float | None = None
    season_games: int


class LuckFactor(_Model):
    factor: LuckKind
    label: str
    actual: float
    expected: float
    unit: Unit
    attempts: int | None  # fumbles, 3rd-down tries, kicks, dropbacks; None where it doesn't apply
    swing_pts: float  # positive = helped this team
    partly_skill: bool = False
    sentence: str


class TeamRetro(_Model):
    team: str
    score: int
    efficiency: list[Efficiency]
    luck: list[LuckFactor]
    luck_net: float  # sum of swing_pts; an estimate


class PlayedLike(_Model):
    p_home: float  # how often teams that played this efficiently (turnovers aside) won, home view
    favored: str  # team code the efficiency favored
    matches_result: bool | None  # None for a tie
    sentence: str
    # What went in (None on records from before v3). Interceptions and lost fumbles are out of both
    # rates. EPA is the fit's one input; success rate is context (see expectations.py).
    home_epa: float | None = None
    away_epa: float | None = None
    home_success: float | None = None
    away_success: float | None = None
    p_base: float | None = None  # the home side's win chance before any plays: the fit's intercept


class Phase(_Model):
    """One part of the game, both teams side by side. Descriptive: a phase carries no weight in
    the played-like verdict, and phases aren't worth the same as each other."""

    phase: str  # passing, rushing, explosive, third_down, red_zone, special_teams, field_position, turnovers
    label: str
    note: str
    home: float | None  # None when the phase didn't come up (no red-zone trip)
    away: float | None
    home_text: str
    away_text: str
    leader: Side | None  # None when even, or when one side has nothing to compare


class GradedPick(_Model):
    model_id: str
    label: str
    kind: Literal["approach", "ensemble", "reference", "global"]
    status: str  # locked | pregame | backfill
    p_home: float
    pick: str  # team code
    p_pick: float
    right: bool | None  # None for a tie
    log_loss: float
    spread_home: float | None  # > 0 = home favored by that many points
    spread_error: float | None  # |spread_home - margin|
    best: bool  # lowest log loss among approaches and the ensemble


class GroupValue(_Model):
    group: str
    label: str
    pp: float  # win-probability points toward home
    value: float  # LL(p - pp) - LL(p); positive = helped


class Attribution(_Model):
    model_id: str
    label: str
    groups: list[GroupValue]  # sorted by value, most helpful first
    most_valuable: str | None  # group id; None when no group helped


class WpPlay(_Model):
    """A turning point: one of the game's biggest real plays by win-probability swing. Probabilities
    are the home team's; `factor` names the luck factor the play is counted in, if any."""

    play_id: int
    t: int  # elapsed game seconds at the snap; overtime continues past 3600
    qtr: int  # 5 and up = overtime
    clock: str  # time left in the quarter, "0:10"
    team: str | None  # the offense, games-table code
    p_before: float
    p_after: float
    wpa: float  # p_after - p_before
    factor: LuckKind | None
    text: str  # nflverse's play description, trimmed to 160 characters at a word boundary


class WpSeries(_Model):
    """How the game unfolded (ADR 0020): home win probability after each play that changed it.

    `points` are [t, p] pairs in play order. The first is the kickoff's opening value at t = 0, each
    later one is the value AFTER the play snapped at t (so a turning point's (t, p_after) lies on
    the curve), and the last is the result at `end_t`: 1, 0, or 0.5 for a tie."""

    model: Literal["nflfastr_vegas", "nflfastr"]  # which nflfastR win probability fed `points`
    points: list[tuple[int, float]]
    end_t: int  # 3600, or 3600 plus the overtime played
    ot: bool
    plays: list[WpPlay]  # at most 5 real plays with |wpa| >= 0.05, largest first
    winner_low: (
        tuple[int, float] | None
    )  # (t, the winner's lowest win prob, its own view); None for a tie


class Drive(_Model):
    """One possession. Yard lines are yards from the offense's own goal line."""

    n: int  # 1-based, in time order
    team: str  # the offense, games-table code
    qtr: int
    t0: int  # elapsed game seconds, as in WpSeries
    t1: int
    start_yl: int | None
    end_yl: int | None
    plays: int | None
    result: str | None  # nflverse's fixed_drive_result: Punt, Touchdown, Field goal, Turnover, ...


class RetroGame(_Model):
    schema_version: str = SCHEMA_VERSION
    game_id: str
    season: int
    week: int
    kickoff_utc: str
    away: str
    home: str
    result: Result
    built_at: str
    pbp_snapshot_ts: str  # information: the snapshot the plays came from
    pbp_hash: str | None = None  # hash of this game's plays; a rebuild happens only when it changes
    expectations_version: str
    headlines: list[str] = Field(min_length=1, max_length=6)
    played_like: PlayedLike
    phases: list[Phase] = []
    teams: dict[Side, TeamRetro]
    predictions: list[GradedPick]
    best_model: str | None
    attribution: list[Attribution]  # approaches and the ensemble
    # None on records from before v6, and when the plays lack the columns
    wp_series: WpSeries | None = None
    drives: list[Drive] | None = None


# ------------------------------------------------------------------------------------ week recap


class RecapModel(_Model):
    model_id: str
    label: str
    kind: Literal["approach", "ensemble", "reference", "global"]
    n: int
    right: int
    log_loss: float  # mean over the week's games
    vs_market: float | None  # log_loss - market's; negative = beat the market
    rank: int  # 1 = lowest log loss among approaches and the ensemble; references get 0


class RecapGame(_Model):
    game_id: str
    away: str
    home: str
    value: float  # upsets: the winner's market win %; misread: the ensemble's log loss
    sentence: str


class RecapTeam(_Model):
    team: str
    game_id: str
    luck_net: float
    sentence: str


class BoldCall(_Model):
    game_id: str
    away: str
    home: str
    model_id: str
    label: str
    pick: str  # team code
    p_pick: float
    log_loss: float
    earned: float  # ln 2 - log_loss: what the call scored against a coin flip
    sentence: str


class WeekRecap(_Model):
    schema_version: str = SCHEMA_VERSION
    season: int
    week: int
    built_at: str
    games: list[str]  # game ids with a retro
    best_model: str | None
    models: list[RecapModel]
    upsets: list[RecapGame]
    misread: list[RecapGame]
    luckiest: list[RecapTeam]
    unluckiest: list[RecapTeam]
    note: str  # one week says little about a model
    best_call: BoldCall | None = None  # one per week across approaches
    costliest_call: BoldCall | None = None
