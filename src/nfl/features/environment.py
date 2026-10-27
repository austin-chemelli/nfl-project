"""Environment family: rest, travel, time-zone shift (team) and venue / schedule context (game).

Built from the curated games frame plus `stadiums.csv` (one row per stadium_id: coordinates, IANA
time zone, altitude, roof type). See architecture §3.3.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

from nfl.config import Paths
from nfl.features import store

SOURCE = "schedules"
VERSION = "1"

STADIUMS_CSV = Path(__file__).with_name("stadiums.csv")
REST_CAP = 14.0
EARTH_RADIUS_KM = 6371.0088
NY = ZoneInfo("America/New_York")

# The curated data tags the 2026 London game at Tottenham with Jacksonville's id (JAX00).
NAME_OVERRIDES = {"Tottenham Hotspur Stadium": "LON02"}


@cache
def load_stadiums() -> dict[str, dict]:
    df = pl.read_csv(STADIUMS_CSV)
    return {r["stadium_id"]: r for r in df.iter_rows(named=True)}


def resolve_stadium(stadium_id: str | None, name: str | None) -> str | None:
    """Stadium key for a game row: id, corrected by name where the source id is wrong."""
    return NAME_OVERRIDES.get(name or "", stadium_id)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _utc_offset_h(tz: str, kickoff: datetime | None) -> float | None:
    if kickoff is None:
        return None
    off = kickoff.replace(tzinfo=UTC).astimezone(ZoneInfo(tz)).utcoffset()
    return off.total_seconds() / 3600 if off is not None else None


def home_stadiums(games: pl.DataFrame) -> dict[tuple[str, int], str]:
    """(team, season) -> modal stadium among the team's own 'Home' games that season.
    Seasons with no home games borrow the nearest season's stadium."""
    counts: dict[tuple[str, int], Counter] = {}
    for r in games.filter(pl.col("location") == "Home").iter_rows(named=True):
        key = resolve_stadium(r["stadium_id"], r["stadium"])
        counts.setdefault((r["home_team"], r["season"]), Counter())[key] += 1
    out = {k: min(c.items(), key=lambda kv: (-kv[1], kv[0]))[0] for k, c in counts.items()}
    by_team: dict[str, list[int]] = {}
    for team, season in out:
        by_team.setdefault(team, []).append(season)
    for r in games.select("home_team", "away_team", "season").iter_rows():
        for team in r[:2]:
            if (team, r[2]) not in out and team in by_team:
                near = min(by_team[team], key=lambda s: abs(s - r[2]))
                out[(team, r[2])] = out[(team, near)]
    return out


def _grass(surface: str | None) -> float | None:
    s = (surface or "").strip().lower()
    if not s:
        return None
    return 0.0 if s == "grass" else 1.0


def _is_dome(roof: str | None, stadium_roof_type: str | None) -> float | None:
    """1 for a closed roof, 0 for open air. An open-air venue (CSV roof_type 'outdoors') is always 0:
    nflverse labels some international open-air venues (Munich, Paris, Melbourne) as 'dome'."""
    if stadium_roof_type == "outdoors":
        return 0.0
    r = (roof or "").strip().lower()
    if r in ("dome", "closed"):
        return 1.0
    if r in ("outdoors", "open"):
        return 0.0
    return {"dome": 1.0}.get(stadium_roof_type or "")


def build(paths: Paths, games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    stadiums = load_stadiums()
    g = games.sort("kickoff_utc", "game_id", nulls_last=True)
    homes = home_stadiums(g)

    team_rows: list[tuple] = []
    game_rows: list[tuple] = []
    last_surface: dict[str, float] = {}

    for r in g.iter_rows(named=True):
        gid, kick = r["game_id"], r["kickoff_utc"]
        key = resolve_stadium(r["stadium_id"], r["stadium"])
        venue = stadiums.get(key)
        venue_off = _utc_offset_h(venue["tz"], kick) if venue else None

        for side, team, rest in (
            ("home", r["home_team"], r["home_rest"]),
            ("away", r["away_team"], r["away_rest"]),
        ):
            team_rows.append(
                (gid, team, "environment.rest_days", None if rest is None else min(rest, REST_CAP))
            )
            home = stadiums.get(homes.get((team, r["season"])))
            km = shift = None
            if venue and home:
                km = haversine_km(home["lat"], home["lon"], venue["lat"], venue["lon"])
                home_off = _utc_offset_h(home["tz"], kick)
                if venue_off is not None and home_off is not None:
                    shift = venue_off - home_off
            team_rows.append((gid, team, "environment.travel_km", km))
            team_rows.append((gid, team, "environment.tz_shift", shift))

        dome = _is_dome(r["roof"], venue["roof_type"] if venue else None)
        turf = _grass(r["surface"])
        if turf is None:
            turf = last_surface.get(key)
        elif key is not None:
            last_surface[key] = turf
        if kick is not None:
            et = kick.replace(tzinfo=UTC).astimezone(NY)
            prime = et.hour >= 19 or r["weekday"] in ("Thursday", "Monday")
        else:
            prime = r["weekday"] in ("Thursday", "Monday")
        div = r["div_game"]
        game_rows += [
            (gid, "environment.is_dome", dome),
            (gid, "environment.is_turf", turf),
            (gid, "environment.div_game", None if div is None else float(div)),
            (gid, "environment.primetime", float(prime)),
            (gid, "environment.neutral_site", float(r["location"] == "Neutral")),
        ]

    tv = pl.DataFrame(
        team_rows,
        schema={"game_id": pl.Utf8, "team": pl.Utf8, "feature": pl.Utf8, "value": pl.Float64},
        orient="row",
    )
    gv = pl.DataFrame(
        game_rows,
        schema={"game_id": pl.Utf8, "feature": pl.Utf8, "value": pl.Float64},
        orient="row",
    )
    kw = {"source": SOURCE, "version": VERSION, "build_ts": build_ts}
    return pl.concat([store.from_team_values(tv, g, **kw), store.from_game_values(gv, g, **kw)])
