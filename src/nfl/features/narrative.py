"""Narrative family: LLM-researched, cited features from narrative records (live only).

Rows are stamped with each record's `known_as_of` (when the research finished), never the backtest
rule, so a Thursday lock can only see research finished before it. One row per record, so repeated
research runs for the same game coexist in the store and `as_of` picks the latest before a lock.
`version` is the record's prompt_version. There is nothing to backfill: the family is empty before
the first live week, and the UI must say "weeks tracked".
"""

from __future__ import annotations

import warnings
from datetime import datetime

import polars as pl

from nfl.config import Paths
from nfl.features import store
from nfl.llm.narrative import GameNarrative, load_records

SOURCE = "llm_narrative"
VERSION = "1"  # builder version; rows carry the prompt_version instead

TEAM_FIELDS = [
    "qb_status",
    "injury_impact",
    "sentiment",
    "hype",
    "coaching_turmoil",
    "motivation",
    "revenge",
    "lookahead",
]
GAME_FIELDS = ["upset_buzz", "public_bet_pct_home", "weather_concern"]


def rows_from_records(records: list[GameNarrative], games: pl.DataFrame) -> pl.DataFrame:
    team_rows, game_rows = [], []
    for r in records:
        for side in (r.home, r.away):
            for f in TEAM_FIELDS:
                v = getattr(side, f)
                team_rows.append(
                    (
                        r.game_id,
                        side.team,
                        f"narrative.{f}",
                        float(v),
                        r.known_as_of,
                        r.prompt_version,
                    )
                )
        for f in GAME_FIELDS:
            v = getattr(r, f)
            game_rows.append((r.game_id, f"narrative.{f}", None if v is None else float(v), r.known_as_of, r.prompt_version))  # fmt: skip
    out = []
    tcols = ["game_id", "team", "feature", "value", "known_as_of", "prompt_version"]
    gcols = ["game_id", "feature", "value", "known_as_of", "prompt_version"]
    t = pl.DataFrame(team_rows, schema=tcols, orient="row")
    g = pl.DataFrame(game_rows, schema=gcols, orient="row")
    for pv in sorted(set(t["prompt_version"]) | set(g["prompt_version"])):
        tp = t.filter(pl.col("prompt_version") == pv).drop("prompt_version")
        gp = g.filter(pl.col("prompt_version") == pv).drop("prompt_version")
        if not tp.is_empty():
            out.append(
                store.from_team_values(
                    tp, games, source=SOURCE, version=pv, build_ts=datetime.now()
                )
            )
        if not gp.is_empty():
            out.append(
                store.from_game_values(
                    gp, games, source=SOURCE, version=pv, build_ts=datetime.now()
                )
            )
    return pl.concat(out) if out else pl.DataFrame(schema=store.FEATURE_SCHEMA)


def build(paths: Paths, games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    records = load_records(paths)
    if not records:
        return pl.DataFrame(schema=store.FEATURE_SCHEMA)
    # A record whose stamp isn't strictly before the scheduled kickoff (e.g. the game was flexed
    # earlier after ingest) is skipped with a warning, never allowed to break the feature build.
    kick = dict(zip(games["game_id"], games["kickoff_utc"].dt.replace_time_zone(None), strict=True))
    keep = []
    for r in records:
        k = kick.get(r.game_id)
        if k is None or r.known_as_of >= k:
            warnings.warn(
                f"skipping narrative record {r.game_id} @ {r.known_as_of}: not before kickoff {k}",
                stacklevel=2,
            )
            continue
        keep.append(r)
    return rows_from_records(keep, games) if keep else pl.DataFrame(schema=store.FEATURE_SCHEMA)
