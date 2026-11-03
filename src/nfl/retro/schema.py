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

SCHEMA_VERSION = "2"

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
    teams: dict[Side, TeamRetro]
    predictions: list[GradedPick]
    best_model: str | None
    attribution: list[Attribution]  # approaches and the ensemble


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
