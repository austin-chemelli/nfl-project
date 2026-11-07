"""Kickoff weather forecasts for upcoming open-air games (ADR 0024, M20.10).

Open-Meteo (free, no key) at the stadium's coordinates for the kickoff hour: temperature (°F), wind
and gusts (mph) and the chance of precipitation (%). One raw snapshot per fetch:
    raw/open_meteo/snapshot_ts=<ts>/forecasts.json   (list of {game_id, kickoff_utc, temp_f, ...})
stamped at the fetch time, so a forecast is never known before it was fetched. Games under a roof
(dome, closed, retractable) are skipped: their weather is the building's. `nfl.features.weather`
turns the snapshots into features.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import polars as pl

from nfl.config import Paths, now_utc, snapshot_ts

URL = "https://api.open-meteo.com/v1/forecast"
FIELDS = "temperature_2m,precipitation_probability,wind_speed_10m,wind_gusts_10m"
HORIZON = timedelta(days=8)  # this week's games; the forecast's range is 16 days
OPEN_AIR = {"outdoors", "open"}


def raw_root(paths: Paths) -> Path:
    return paths.root / "raw" / "open_meteo"


def open_air(roof: str | None, stadium_roof: str | None) -> bool:
    """The schedule's roof when it has one, else the stadium's type; retractable counts as covered."""
    if roof:
        return roof in OPEN_AIR
    return stadium_roof == "outdoors"


def _hour(hourly: dict[str, Any], kickoff: datetime) -> dict | None:
    try:
        i = hourly["time"].index(f"{kickoff:%Y-%m-%dT%H}:00")
    except KeyError, ValueError:
        return None
    temp, rain, wind, gusts = (hourly[k][i] for k in FIELDS.split(","))
    if temp is None or wind is None:
        return None
    return {"temp_f": float(temp), "precip_pct": None if rain is None else float(rain),
            "wind_mph": float(wind), "gusts_mph": None if gusts is None else float(gusts)}  # fmt: skip


def fetch_one(client: httpx.Client, lat: float, lon: float, kickoff: datetime) -> dict | None:
    day = kickoff.date().isoformat()
    q = urlencode({"latitude": lat, "longitude": lon, "hourly": FIELDS, "timezone": "UTC",
                   "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
                   "start_date": day, "end_date": day})  # fmt: skip
    try:
        r = client.get(f"{URL}?{q}")
        return _hour(r.json().get("hourly", {}), kickoff) if r.status_code == 200 else None
    except httpx.HTTPError, ValueError:
        return None


def snapshot(
    paths: Paths,
    games: pl.DataFrame,
    now: datetime | None = None,
    client: httpx.Client | None = None,
) -> int:
    """Fetch forecasts for upcoming open-air games within `HORIZON`; write one snapshot. Returns games
    with a forecast."""
    from nfl.features.environment import load_stadiums, resolve_stadium

    now = (now or now_utc()).replace(tzinfo=None, microsecond=0)
    k = pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us"))
    up = games.with_columns(k.alias("_k")).filter(
        (pl.col("_k") > now) & (pl.col("_k") <= now + HORIZON)
    )
    stadiums = load_stadiums()
    out = []
    http = client or httpx.Client(timeout=15.0)
    try:
        for g in up.iter_rows(named=True):
            st = stadiums.get(resolve_stadium(g.get("stadium_id"), g.get("stadium")) or "")
            if st is None or not open_air(g.get("roof"), st.get("roof_type")):
                continue
            f = fetch_one(http, st["lat"], st["lon"], g["_k"])
            if f:
                out.append({"game_id": g["game_id"], "kickoff_utc": g["_k"].isoformat(), **f})
    finally:
        if client is None:
            http.close()
    if out:
        d = raw_root(paths) / f"snapshot_ts={snapshot_ts()}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "forecasts.json").write_text(json.dumps(out, indent=1))
    return len(out)


def load_snapshots(paths: Paths) -> pl.DataFrame:
    """Every forecast we fetched: game_id, fetched_at, temp_f, wind_mph, gusts_mph, precip_pct."""
    rows = []
    for d in sorted(raw_root(paths).glob("snapshot_ts=*")) if raw_root(paths).exists() else []:
        ts = datetime.strptime(d.name.split("=", 1)[1], "%Y%m%dT%H%M%SZ")
        for r in json.loads((d / "forecasts.json").read_text()):
            rows.append({"game_id": r["game_id"], "fetched_at": ts, "temp_f": r["temp_f"], "wind_mph": r["wind_mph"],
                         "gusts_mph": r.get("gusts_mph"), "precip_pct": r.get("precip_pct")})  # fmt: skip
    schema = {"game_id": pl.Utf8, "fetched_at": pl.Datetime("us"), "temp_f": pl.Float64, "wind_mph": pl.Float64,
              "gusts_mph": pl.Float64, "precip_pct": pl.Float64}  # fmt: skip
    return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)
