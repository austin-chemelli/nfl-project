"""Matchup family (ADR 0028, M25.8/M25.9): the matchup engine's edges as team-level features.

`matchup.net_edge_pg`: for team T in a game, the summed `edge_pts_pg` of T's offense against the
opponent's defense minus the summed edge of the opponent's offense against T's defense, in points per
game (positive = the matchups favour T). The sum runs over the splits that carry an edge
(`splits.SPLITS` with a chooser and no `no_edge`); `neither` and context-only splits have none. There
is no separate "headline" net in the engine or `site.py` (the Preview shows per-split edges and the
largest one), so this is the plain sum of what the Matchups tab lists. The split edges overlap
(`box_light` and `box_heavy` mirror each other, `play_action` and `screen` are both dropbacks), so
the sum is an index of lean, not points to add to a spread.

`matchup.edge_<split>`: T's offensive edge in that split minus the opponent's offensive edge in it.
Only the splits with an edge get a feature; the others would be null in every row.

Values come straight from `matchups.Engine.side_rows` (the same numbers as `matchup_edges`), so the
point-in-time rules are the engine's: a game in week w reads season weeks < w for the rates, gaps and
league figures and seasons < S for the shrinkage constant. Week < `MIN_WEEK` is null (one week of
plays is not a team's habit). A split without a value on either side is null for that split; the net
is null when no split has a value on either side. Every edge-bearing split is FTN-charted (2022+), so
all of this is null before 2022 and the family's `SOURCE` is "ftn". `known_as_of` is stamped by
`store.from_team_values` like the strength family (synthetic pre-kickoff time for played games).

Needs the SQL model `team_split_week` (`nfl models build team_split_week`); without it the builder
returns no rows and `nfl features` reports the family empty.
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from nfl import catalog, splits
from nfl.config import Paths
from nfl.features import store
from nfl.matchups import Engine, load_split_model
from nfl.models.elo import TEAM_ALIASES

SOURCE = "ftn"
VERSION = "1"
MIN_WEEK = 3
EDGE_SPLITS = tuple(s.id for s in splits.SPLITS if s.chooser != "neither" and not s.no_edge)
FEATURES = ["matchup.net_edge_pg", *[f"matchup.edge_{s}" for s in EDGE_SPLITS]]


def _code(team: str) -> str:
    return TEAM_ALIASES.get(team, team)


def _side_edges(engine: Engine, season: int, week: int, off: str, deff: str) -> dict[str, float]:
    """split -> edge_pts_pg for `off`'s offense against `deff`'s defense (non-null edges only)."""
    rows = engine.side_rows(season, week, off, deff, {})
    return {r.split: r.edge_pts_pg for r in rows if r.has_edge and r.edge_pts_pg is not None}


def compute(games: pl.DataFrame, split_model: pl.DataFrame) -> pl.DataFrame:
    """(game_id, team, feature, value) for every game and both teams. Pure given the two frames."""
    engine = Engine(split_model)
    out: list[tuple[str, str, str, float | None]] = []
    for g in games.select("game_id", "season", "week", "home_team", "away_team").iter_rows(
        named=True
    ):
        season, week = int(g["season"]), int(g["week"])
        h, a = g["home_team"], g["away_team"]
        if week >= MIN_WEEK and split_model.height:
            eh = _side_edges(engine, season, week, _code(h), _code(a))
            ea = _side_edges(engine, season, week, _code(a), _code(h))
        else:
            eh, ea = {}, {}
        for team, mine, theirs in ((h, eh, ea), (a, ea, eh)):
            per = {s: mine[s] - theirs[s] for s in EDGE_SPLITS if s in mine and s in theirs}
            net = (
                sum(mine[s] for s in per) - sum(theirs[s] for s in per) if per else None
            )  # the same splits on both sides, so the net is the sum of the per-split values
            out.append((g["game_id"], team, "matchup.net_edge_pg", net))
            for s in EDGE_SPLITS:
                out.append((g["game_id"], team, f"matchup.edge_{s}", per.get(s)))
    return pl.DataFrame(
        out,
        schema={
            "game_id": pl.String, "team": pl.String, "feature": pl.String, "value": pl.Float64,
        },
        orient="row",
    )  # fmt: skip


def build(paths: Paths, games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    con = catalog.connect(paths, only=["team_split_week"])
    if "team_split_week" not in {d["name"] for d in catalog.describe(con)}:
        split_model = pl.DataFrame()
        games = games.head(0)  # no model: no rows, rather than a column of nulls
    else:
        split_model = load_split_model(con)
    values = compute(games, split_model)
    return store.from_team_values(values, games, source=SOURCE, version=VERSION, build_ts=build_ts)
