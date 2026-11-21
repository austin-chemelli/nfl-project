"""News family: countable facts from the narrative records (ADR 0032), live only.

Two team features, derived in code from a record's cited, roster-checked fields (schema v3), so the
news adjustment (`nfl.approaches.news`) reads facts, not moods:

- `news.qb_change_confirmed`: 1 when reporting names a starting QB (`qb_named_starter`) who is
  neither the franchise's primary passer in its previous game nor the depth chart's QB1 as of the
  record's `known_as_of` (the depth-chart disagreement, idea A6); 0 otherwise (nothing named, or the
  same man; also 0 when no reference QB is known, as nothing can be said to differ).
- `news.starters_ruled_out`: how many names the record's `starters_ruled_out` holds (the record's own
  frozen count). Whether the official report already lists them is decided at the lock
  (`nfl.approaches.news.adjustment`, from the report rows the lock reads): recomputing it here would
  move on every rebuild, as 2025-26 injury rows carry no `date_modified`.

The QB check reads depth charts as of the record's `known_as_of` (timestamped charts from 2025, so a
rebuild never rewrites it) and the franchise's previous game's passer (a fixed fact).

Rows are stamped with the record's `known_as_of` (a lock only sees records before it), one set per
record, never backfilled. Records older than schema v3 emit nothing: they didn't ask. This is its
own family (not part of `narrative`) because `build.py` requires a family's features to carry its
name and the other agent reads `news.*`.
"""

from __future__ import annotations

import warnings
from datetime import datetime

import polars as pl

from nfl.config import Paths
from nfl.features import availability, store
from nfl.llm.checks import same_person
from nfl.llm.narrative import GameNarrative, load_records

SOURCE = "llm_news"
VERSION = "1"


def player_names(paths: Paths) -> dict[str, set[str]]:
    """gsis_id -> the names a player goes by (display name, first and last, football name)."""
    f = paths.curated_table("players")
    files = sorted(f.glob("*.parquet")) + sorted(f.glob("*/*.parquet"))
    if not files:
        return {}
    d = pl.read_parquet(files[0], columns=["gsis_id", "display_name", "first_name", "last_name", "football_name"])  # fmt: skip
    out: dict[str, set[str]] = {}
    for g, disp, first, last, fb in d.iter_rows():
        if g:
            out[g] = {n for n in (disp, f"{first} {last}" if first and last else None,
                                  f"{fb} {last}" if fb and last else None) if n}  # fmt: skip
    return out


def _qb_refs(
    records: list[GameNarrative],
    gt: pl.DataFrame,
    prev: pl.DataFrame | None,
    depth: pl.DataFrame | None,
    names: dict[str, set[str]],
) -> dict[tuple[int, str], set[str]]:
    """(id(record), team) -> names of the charted QB1 as of the record's `known_as_of` and the
    previous game's passer. One chart lookup per round of records (a game normally has one record,
    so one call), never per record."""
    out: dict[tuple[int, str], set[str]] = {}
    if depth is None or prev is None or not records:
        return out
    passer = {(r[0], r[1]): r[2] for r in prev.drop_nulls("prev_passer").iter_rows()}
    seen: dict[tuple[str, str], int] = {}
    rounds: dict[int, list[tuple[GameNarrative, str]]] = {}
    for rec in records:
        for side in (rec.home, rec.away):
            k = (rec.game_id, side.team)
            rounds.setdefault(seen.get(k, 0), []).append((rec, side.team))
            seen[k] = seen.get(k, 0) + 1
    for batch in rounds.values():
        cut = pl.DataFrame(
            {"game_id": [r.game_id for r, _ in batch], "team": [t for _, t in batch],
             "cutoff": [r.known_as_of for r, _ in batch]},
            schema={"game_id": pl.Utf8, "team": pl.Utf8, "cutoff": pl.Datetime("us")},
        )  # fmt: skip
        one = gt.drop("cutoff").join(cut, on=["game_id", "team"], how="inner")
        chart = availability._charts(one, depth).filter(pl.col("pos") == "QB").sort("ord")
        qb1 = {(r[0], r[1]): r[2] for r in chart.group_by("game_id", "team", maintain_order=True).first().select("game_id", "team", "gsis_id").iter_rows()}  # fmt: skip
        for rec, team in batch:
            ids = [qb1.get((rec.game_id, team)), passer.get((rec.game_id, team))]
            out[(id(rec), team)] = {n for i in ids if i for n in names.get(i, ())}
    return out


def _rows(
    records: list[GameNarrative],
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    depth: pl.DataFrame | None,
    names: dict[str, set[str]],
    build_ts: datetime,
) -> pl.DataFrame:
    gt = availability._game_teams(games, build_ts)
    prev = availability._prev_passer(gt, plays) if plays is not None else None
    team_of = {(r["game_id"], r["team"]): r for r in gt.iter_rows(named=True)}
    rows = []
    refs = _qb_refs(records, gt, prev, depth, names)
    for rec in records:
        for side in (rec.home, rec.away):
            if (rec.game_id, side.team) not in team_of:
                continue
            r = refs.get((id(rec), side.team), set())
            named = side.qb_named_starter
            qb = 1.0 if named and r and not any(same_person(named, n) for n in r) else 0.0
            rows.append((rec.game_id, side.team, "news.qb_change_confirmed", qb, rec.known_as_of))
            rows.append(
                (
                    rec.game_id,
                    side.team,
                    "news.starters_ruled_out",
                    float(len(side.starters_ruled_out)),
                    rec.known_as_of,
                )
            )
    if not rows:
        return pl.DataFrame(schema=store.FEATURE_SCHEMA)
    v = pl.DataFrame(rows, schema=["game_id", "team", "feature", "value", "known_as_of"], orient="row")  # fmt: skip
    return store.from_team_values(v, games, source=SOURCE, version=VERSION, build_ts=build_ts)


def build(paths: Paths, games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    kick = dict(zip(games["game_id"], games["kickoff_utc"].dt.replace_time_zone(None), strict=True))
    records = []
    for r in load_records(paths):
        if r.schema_version != "3":
            continue
        k = kick.get(r.game_id)
        if k is None or r.known_as_of >= k:
            warnings.warn(f"skipping news record {r.game_id} @ {r.known_as_of}: not before kickoff {k}", stacklevel=2)  # fmt: skip
            continue
        records.append(r)
    if not records:
        return pl.DataFrame(schema=store.FEATURE_SCHEMA)
    plays = depth = None
    try:
        _, depth, plays = availability.load_inputs(paths)
        seasons = {r.season for r in records}
        depth = (
            depth.filter(pl.col("season").is_in(seasons)) if "season" in depth.columns else depth
        )
    except Exception as e:  # noqa: BLE001  (no charts or plays on this machine: only the injury half)
        print(f"(news: no depth charts or plays: {type(e).__name__})")
    return _rows(records, games, plays, depth, player_names(paths), build_ts)
