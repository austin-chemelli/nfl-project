"""Position priors for the player value model (ADR 0027, M24.2).

`TOP_STARTER_POINTS`: what a top starter (about the 90th percentile of regular starters at his
position) is worth in points of spread over a replacement. From the published sizes the research
collected (`.notes/plans/research-player-impact-methods.md`): an elite quarterback 4 to 7 points over
his backup; a star elsewhere 0.5 to 1.5, at most about 2 (PFF's examples: a top receiver about 1.5,
a top corner about 0.6, a top edge about 0.5; market studies agree on the range). These are priors:
M24.3 fits them against our residuals and the closing line, and they change only with that evidence.
"""

from __future__ import annotations

TOP_STARTER_POINTS: dict[str, float] = {
    "QB": 6.0,
    "WR": 1.2,
    "TE": 0.8,
    "RB": 0.6,
    "OL": 0.5,  # per starter: five of them, about 2.5 for the line
    "EDGE": 1.0,
    "DL": 0.7,  # interior: a top one (a Chris Jones) a bit under a top edge (M24.7)
    "LB": 0.4,  # off-ball linebackers: the smallest effect in the published ranges
    "CB": 0.8,
    "S": 0.5,
}
GROUPS = tuple(TOP_STARTER_POINTS)

# The quality percentile among regular starters that maps to 0 (replacement) and to 1 (a top starter).
REPLACEMENT_PCT = 0.30
TOP_PCT = 0.90
MAX_MULTIPLIER = 1.25  # the best of the best, a little above "top starter"

# How each group's quality blends production with the contract-or-draft prior (weight on production).
PRODUCTION_WEIGHT: dict[str, float] = {
    "QB": 0.8, "WR": 0.8, "TE": 0.8, "RB": 0.8,
    "EDGE": 0.5, "DL": 0.5, "LB": 0.5, "CB": 0.5, "S": 0.5,
    "OL": 0.0,  # no free per-lineman production: the prior alone
}  # fmt: skip

# Shrinkage: production toward the group mean with this many pseudo-observations (games, or
# dropbacks for quarterbacks, as in `features/qb.py`).
N0: dict[str, float] = {
    "QB": 250.0,
    "WR": 4.0,
    "TE": 4.0,
    "RB": 4.0,
    "EDGE": 4.0,
    "DL": 4.0,
    "LB": 4.0,
    "CB": 4.0,
    "S": 4.0,
}
SEASON_DECAY = 0.75  # last season counts 0.75, the one before 0.5625 (as `features/qb.py`)
SEASONS_BACK = 3
REGULAR_ROLE = 0.5  # a regular starter: at least half his unit's snaps in his recent games
FULL_ROLE = 0.7  # a role this large counts fully; a smaller one scales the value down

# PFF position first (it separates edges from linebackers), then NGS, then the snap-count position.
POSITION_GROUP: dict[str, str] = {
    # PFF
    "QB": "QB", "HB": "RB", "WR": "WR", "TE": "TE", "T": "OL", "G": "OL", "C": "OL",
    "ED": "EDGE", "DI": "DL", "LB": "LB", "CB": "CB", "S": "S",
    # NGS
    "RB": "RB", "SLOT_WR": "WR", "EDGE": "EDGE", "OLB": "EDGE", "SLOT_CB": "CB",
    "SAFETY": "S", "HIGH_SAFETY": "S", "INTERIOR_LINE": "DL", "MLB": "LB", "ILB": "LB",
    # snap counts (PFR)
    "OT": "OL", "OL": "OL", "C/G": "OL", "G/T": "OL", "G/C": "OL", "DE": "EDGE",
    "DT": "DL", "NT": "DL", "FS": "S", "SS": "S", "DB": "CB",
}  # fmt: skip
