"""The situation-split registry (ADR 0028, M25.0): one place that names every split in the SQL model
`team_split_week` (`src/nfl/sql/models/team_split_week.sql`).

A split is a situation a play can be in or out of. The model stores, per unit (team and side) and week,
the plays, EPA, success and explosive plays "with" the situation (`flag` true) and "without" it
(`flag` false), over the split's own universe of plays (see the SQL header). `chooser` says who picks
the situation: the offense (play call, formation), the defense (coverage, pressure, box) or neither
(down, field position, game script, opponent). `source` is where the column comes from: play-by-play
(`pbp`, every season) or FTN charting (`ftn`, 2022 onward; null before). A test holds this registry and
the SQL's split ids equal.

Pure: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Chooser = Literal["offense", "defense", "neither"]
Source = Literal["pbp", "ftn"]


@dataclass(frozen=True)
class Split:
    id: str
    label: str
    chooser: Chooser
    source: Source
    first_season: int
    definition: str


SPLITS: tuple[Split, ...] = (
    Split("blitz", "Blitz", "defense", "ftn", 2022,
          "A dropback where the defense sent at least one blitzer (FTN n_blitzers >= 1)."),
    Split("box_light", "Light box", "defense", "ftn", 2022,
          "A run against a box of six or fewer defenders (FTN n_defense_box <= 6)."),
    Split("box_heavy", "Heavy box", "defense", "ftn", 2022,
          "A run against a box of seven or more defenders (FTN n_defense_box >= 7)."),
    Split("play_action", "Play action", "offense", "ftn", 2022,
          "A dropback that used play action (FTN is_play_action)."),
    Split("motion", "Pre-snap motion", "offense", "ftn", 2022,
          "A play with a player in motion at the snap (FTN is_motion)."),
    Split("screen", "Screen pass", "offense", "ftn", 2022,
          "A dropback that was a screen pass (FTN is_screen_pass)."),
    Split("rpo", "Run-pass option", "offense", "ftn", 2022,
          "A play that was a run-pass option (FTN is_rpo)."),
    Split("shotgun", "Shotgun", "offense", "pbp", 1999,
          "A play with the quarterback in shotgun rather than under center."),
    Split("no_huddle", "No huddle", "offense", "pbp", 1999,
          "A play run without a huddle."),
    Split("early_down", "Early downs", "neither", "pbp", 1999,
          "A play on first or second down, against third and fourth."),
    Split("third_down", "Third down", "neither", "pbp", 1999,
          "A play on third down, against first, second and fourth."),
    Split("red_zone", "Red zone", "neither", "pbp", 1999,
          "A play from the opponent's 20-yard line or closer."),
    Split("own_territory", "Own territory", "neither", "pbp", 1999,
          "A play from the offense's own side of the 50."),
    Split("neutral_script", "Neutral game script", "neither", "pbp", 1999,
          "A play with the offense's win probability between 20% and 80%."),
    Split("deep_pass", "Deep pass", "offense", "pbp", 1999,
          "A pass with at least 15 air yards, against shorter passes (sacks and throwaways without air yards are out)."),
    Split("vs_top10_def", "Against a top-ten defense", "neither", "pbp", 1999,
          "An offense's play against a defense in the top ten by our opponent-adjusted EPA allowed as of the week (null before Week 4)."),
    Split("vs_top10_off", "Against a top-ten offense", "neither", "pbp", 1999,
          "A defense's play against an offense in the top ten by our opponent-adjusted EPA as of the week (null before Week 4)."),
)  # fmt: skip

BY_ID: dict[str, Split] = {s.id: s for s in SPLITS}


def get(split_id: str) -> Split:
    """The registry entry for `split_id` (KeyError when there is none)."""
    return BY_ID[split_id]


def ids() -> list[str]:
    return [s.id for s in SPLITS]
