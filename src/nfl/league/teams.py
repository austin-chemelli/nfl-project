"""Team-level latest values and `site/teams.json` (ADR 0019, M14.2).

`team_latest` is the one table both teams.json and the game page's feature bands read: each team's
value for its next game as of the last feature build, else its last. Rows must be known before `now`
and finite. The old bands took the last-kickoff row, a Week 18 pregame row, so recency-weighted and
per-game features were stale. "Next" is measured from the build, not from `now`: site builds run
between feature builds (the Sunday odds snapshots), and a kicked-off game must not move a team onto
a later row, which was built before that game and can differ (`form.epa_trend` averages only the
played games in its window). The numbers change when the features do, and not otherwise.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import polars as pl

from nfl.features import store
from nfl.features.groups import GROUPS
from nfl.league.divisions import conference_of, division_of

SCHEMA_VERSION = "1"
MIN_TEAMS = 20  # below this a percentile of team values says little
# Groups that are per-game, matchup or availability state rather than a team's own state.
SCATTER_EXCLUDE_GROUPS = {
    "rest_travel", "health", "stakes", "venue_weather", "market", "buzz", "matchups"
}  # fmt: skip
EXCLUDE_PREFIXES = ("availability.", "narrative.")
# Their sign is a forecasting prior, not a judgment of good or bad.
NEUTRAL = {"strength.luck", "strength.sos"}
VALUE_DECIMALS = 4

LATEST_SCHEMA = ["feature", "team", "value", "game_id", "kickoff_utc", "known_as_of"]


def _feature_build(rows: pl.DataFrame) -> datetime:
    """When the features were last built: the newest `strength.*` stamp. Only the refresh and the
    locks write that family; market and narrative rows land between builds."""
    strength = rows.filter(pl.col("feature").str.starts_with("strength."))
    return (rows if strength.is_empty() else strength)["known_as_of"].max()


def team_latest(feats: pl.DataFrame, games: pl.DataFrame, now: datetime) -> pl.DataFrame:
    """One row per (feature, team): the earliest game kicking off after the last feature build,
    else the team's last game. Only rows with known_as_of < now and finite values; team-side rows
    only. `games` needs game_id, kickoff_utc, home_team, away_team (naive UTC kickoffs, like `now`).
    """
    empty = pl.DataFrame(
        schema={"feature": pl.Utf8, "team": pl.Utf8, "value": pl.Float64, "game_id": pl.Utf8,
                "kickoff_utc": pl.Datetime("us"), "known_as_of": pl.Datetime("us")}
    )  # fmt: skip
    if feats.is_empty() or games.is_empty():
        return empty
    keys = games.select("game_id", "kickoff_utc", "home_team", "away_team")
    x = (
        store.as_of(feats, now)
        .filter(pl.col("side").is_in(["home", "away"]) & pl.col("value").is_finite())
        .join(keys, on="game_id")
        .with_columns(
            pl.when(pl.col("side") == "home")
            .then(pl.col("home_team"))
            .otherwise(pl.col("away_team"))
            .alias("team"),
        )
        .select(LATEST_SCHEMA)
        .sort("kickoff_utc", "game_id")
    )
    if x.is_empty():
        return empty
    build = pl.lit(_feature_build(x), dtype=pl.Datetime("us"))
    x = x.with_columns((pl.col("kickoff_utc") > build).fill_null(False).alias("_future"))
    by = ["feature", "team"]
    nxt = x.filter(pl.col("_future")).group_by(by, maintain_order=True).first()
    last = (
        x.filter(~pl.col("_future"))
        .group_by(by, maintain_order=True)
        .last()
        .join(nxt.select(by), on=by, how="anti")
    )
    return pl.concat([nxt, last]).select(LATEST_SCHEMA).sort(by)


def _ts(x: datetime) -> str:
    return x.strftime("%Y-%m-%dT%H:%M:%SZ")


def _included(feature: str, group_id: str, unit: str) -> bool:
    return (
        group_id not in SCATTER_EXCLUDE_GROUPS
        and unit != "flag"
        and not feature.startswith(EXCLUDE_PREFIXES)
    )


def _better(feature: str, sign: int, context_only: bool) -> str | None:
    if context_only or feature in NEUTRAL or sign == 0:
        return None
    return "higher" if sign > 0 else "lower"


def _ranks(values: dict[str, float], better: str | None) -> tuple[dict[str, float], dict[str, int]]:
    """pct: 100 x (average ascending rank - 1)/(n - 1), 100 = highest value. rank: min-rank, 1 is
    best by `better` (the highest value when better is null)."""
    codes = list(values)
    v = np.array([values[c] for c in codes])
    n = len(v)
    pct, rank = {}, {}
    for c, x in zip(codes, v, strict=True):
        below = int((v < x).sum())
        ties = int((v == x).sum())
        avg_rank = below + (ties + 1) / 2  # 1-based average ascending rank
        pct[c] = round(100 * (avg_rank - 1) / (n - 1), 1)
        above = int((v > x).sum())
        rank[c] = (below if better == "lower" else above) + 1
    return pct, rank


def _team_games(games: pl.DataFrame, cut: datetime, now: datetime) -> dict[str, dict]:
    """Per team: the games list, record, points, last and next game id, and the week of its latest
    counted result. A result counts only when the game kicked off before `cut`, so the record never
    runs ahead of the values."""
    out: dict[str, dict] = {}
    g = games.sort("kickoff_utc", "game_id", nulls_last=True)
    cut = cut.replace(tzinfo=None)
    now = now.replace(tzinfo=None)
    for r in g.iter_rows(named=True):
        kick = r["kickoff_utc"].replace(tzinfo=None) if r["kickoff_utc"] else None
        scored = (
            kick is not None
            and kick < cut
            and r["home_score"] is not None
            and r["away_score"] is not None
        )
        regular = r.get("game_type", "REG") == "REG"  # a record is the regular season's
        for team, opp, home in ((r["home_team"], r["away_team"], True), (r["away_team"], r["home_team"], False)):  # fmt: skip
            t = out.setdefault(
                team,
                {"wins": 0, "losses": 0, "ties": 0, "games_played": 0, "points_for": 0,
                 "points_against": 0, "through_week": None, "last_game_id": None,
                 "next_game_id": None, "games": []},
            )  # fmt: skip
            pf = pa = None
            if scored:
                pf, pa = (
                    (int(r["home_score"]), int(r["away_score"]))
                    if home
                    else (int(r["away_score"]), int(r["home_score"]))
                )
                t["last_game_id"] = r["game_id"]
                if regular:
                    t["games_played"] += 1
                    t["points_for"] += pf
                    t["points_against"] += pa
                    t["wins" if pf > pa else "losses" if pf < pa else "ties"] += 1
                    t["through_week"] = int(r["week"])
            elif kick is not None and kick > now and t["next_game_id"] is None:
                t["next_game_id"] = r["game_id"]
            t["games"].append(
                {"id": r["game_id"], "week": int(r["week"]), "opp": opp, "home": home, "pf": pf, "pa": pa}
            )  # fmt: skip
    return out


def teams_file(feats: pl.DataFrame, games: pl.DataFrame, now: datetime, week: int) -> dict | None:
    """The teams.json object, or None when there are no team-level feature rows yet."""
    latest = team_latest(feats, games, now)
    if latest.is_empty():
        return None
    by_feature: dict[str, dict[str, float]] = {}
    for feature, team, value in latest.select("feature", "team", "value").iter_rows():
        if conference_of(team):
            by_feature.setdefault(feature, {})[team] = round(float(value), VALUE_DECIMALS)

    features, pct, rank = [], {}, {}
    for group in GROUPS.values():
        for m in group.members:
            vals = by_feature.get(m.feature)
            if not vals or len(vals) < MIN_TEAMS or not _included(m.feature, group.id, m.unit):
                continue
            better = _better(m.feature, m.sign, group.context_only)
            pct[m.feature], rank[m.feature] = _ranks(vals, better)
            arr = list(vals.values())
            lo, q1, med, q3, hi = np.percentile(arr, (10, 25, 50, 75, 90))  # as `feature_bands`
            features.append(
                {"id": m.feature, "label": m.label, "short": m.short or m.label,
                 "description": m.description, "unit": m.unit, "group": group.id,
                 "group_name": group.name, "better": better, "n": len(vals),
                 "mean": round(float(np.mean(arr)), VALUE_DECIMALS),
                 "lo": round(float(lo), VALUE_DECIMALS), "q1": round(float(q1), VALUE_DECIMALS),
                 "med": round(float(med), VALUE_DECIMALS), "q3": round(float(q3), VALUE_DECIMALS),
                 "hi": round(float(hi), VALUE_DECIMALS)}
            )  # fmt: skip

    if not features:
        return None
    # Only the published rows: a narrative or market row stamped later would let the record run
    # ahead of the values shown beside it.
    published = [f["id"] for f in features]
    as_of = latest.filter(pl.col("feature").is_in(published))["known_as_of"].max()
    # With nothing left to play no build will pass the last kickoff, so the cut would strand it.
    done = games.filter(pl.col("kickoff_utc") > now.replace(tzinfo=None)).is_empty()
    record = _team_games(games, now if done else as_of, now)
    teams = {}
    for code in sorted(record):
        if not conference_of(code):
            continue
        teams[code] = {
            "conference": conference_of(code),
            "division": division_of(code),
            **record[code],
            "values": {f["id"]: by_feature[f["id"]][code] for f in features if code in by_feature[f["id"]]},
            "pct": {f: p[code] for f, p in pct.items() if code in p},
            "rank": {f: r[code] for f, r in rank.items() if code in r},
        }  # fmt: skip
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _ts(now),
        "season": int(games["season"][0]) if "season" in games.columns and not games.is_empty() else None,
        "week": int(week),
        "as_of": _ts(as_of),
        "features": features,
        "teams": teams,
    }  # fmt: skip
